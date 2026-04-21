from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import os
from typing import Any

import pandas as pd
from ..template.EEG_layout import EEGcapTemplate


@dataclass
class SchemeItem:
    category: str
    labels: list[str]
    dig_type: str
    n_points: int
    unbounded: bool = False
    template: EEGcapTemplate | None = None  # Allow EEGcapTemplate objects


class DigitisationController:
    """GUI-agnostic state and actions for digitisation workflows."""

    def __init__(self, connector: Any, digitisation_scheme: list[dict] | None = None):
        self.connector = connector
        self.debug_serial = os.getenv("PYLHEMUS_DEBUG_SERIAL", "").lower() in {"1", "true", "yes", "on"}
        self.scheme: list[SchemeItem] = []
        self.digitised_points = pd.DataFrame(columns=["category", "label", "x", "y", "z"])
        self.current_scheme_idx = 0
        self.current_label_idx = 0
        self.participant_id: str = ""

        for item in digitisation_scheme or []:
            self.add(**item)

    def add(
        self,
        category: str,
        labels: list[str] | None = None,
        dig_type: str = "single",
        n_points: int | None = None,
        template: str | None = None,  # Expecting a montage name as string
    ):
        if dig_type not in {"single", "continuous"}:
            raise ValueError("dig_type must be either 'single' or 'continuous'.")

        labels = labels or []
        unbounded = dig_type == "continuous"

        # Convert template string to EEGcapTemplate object
        template_obj = None
        if template:
            try:
                template_obj = EEGcapTemplate(template)
            except ValueError as e:
                raise ValueError(f"Invalid template: {e}")

        self.scheme.append(
            SchemeItem(
                category=category,
                labels=list(labels),
                dig_type=dig_type,
                n_points=n_points or 0,
                unbounded=unbounded,
                template=template_obj,
            )
        )

    @property
    def current_item(self) -> SchemeItem | None:
        if not self.scheme:
            return None
        if self.current_scheme_idx >= len(self.scheme):
            return None
        return self.scheme[self.current_scheme_idx]

    @property
    def is_finished(self) -> bool:
        return self.current_item is None

    @property
    def current_label(self) -> str | None:
        item = self.current_item
        if item is None:
            return None
        if item.dig_type == "continuous" and item.unbounded:
            if self.current_label_idx < len(item.labels):
                return item.labels[self.current_label_idx]
            return f"{item.category}_{self.current_label_idx + 1}"
        if self.current_label_idx >= len(item.labels):
            return None
        return item.labels[self.current_label_idx]

    def start(self):
        self.current_scheme_idx = 0
        self.current_label_idx = 0
        if self.connector is not None:
            self.connector.clear_old_data()

    def capture_from_connector(self) -> tuple[float, float, float] | None:
        item = self.current_item
        if item is None:
            raise RuntimeError("Digitisation scheme is finished.")

        if self.connector is None:
            raise RuntimeError("No connector is configured.")

        # Avoid blocking the GUI thread: only read when a full sample is available.
        serialobj = getattr(self.connector, "serialobj", None)
        n_receivers = getattr(self.connector, "n_receivers", None)
        data_length = getattr(self.connector, "data_length", None)
        if serialobj is not None:
            if not isinstance(n_receivers, int) or not isinstance(data_length, int):
                return None
            if n_receivers <= 0 or data_length <= 0:
                return None
            # Do not require a full fixed-size byte buffer here; FASTRAK line lengths
            # can vary slightly and click-triggered output may arrive in bursts.
            if serialobj.in_waiting <= 0:
                return None

        sensor_data, position = self.connector.get_position_relative_to_head_receiver()
        if position is None:
            return None

        if item.dig_type == "single":
            stylus_point = tuple(float(sensor_data[axis, 0]) for axis in range(1, 4))
            head_point = tuple(float(sensor_data[axis, 1]) for axis in range(1, 4))
            distance = self.calculate_distance(stylus_point, head_point)
            next_idx, accepted = self.idx_of_next_point(distance, self.current_label_idx)

            if self.debug_serial:
                print(
                    "[CAPTURE CHECK] "
                    f"distance={distance:.3f} idx={self.current_label_idx} "
                    f"next_idx={next_idx} accepted={accepted}"
                )

            if not accepted:
                if not self.digitised_points.empty:
                    self.undo()
                self.current_label_idx = max(0, next_idx)
                return None

        self.capture_position(position)
        return position

    def capture_position(self, position: tuple[float, float, float]):
        item = self.current_item
        label = self.current_label
        if item is None or label is None:
            return

        if len(position) < 3:
            return

        x = float(position[0])
        y = float(position[1])
        z = float(position[2])
        if not pd.notna(x) or not pd.notna(y) or not pd.notna(z):
            return

        new_data = pd.DataFrame(
            {
                "category": [item.category],
                "label": [label],
                "x": [x],
                "y": [y],
                "z": [z],
            }
        )
        self.digitised_points = pd.concat([self.digitised_points, new_data], ignore_index=True)

        self.current_label_idx += 1
        self._advance_if_needed()

    def next_target(self):
        if self.current_item is None:
            return
        self.current_label_idx += 1
        self._advance_if_needed()

    def calculate_distance(self, point1: tuple[float, float, float], point2: tuple[float, float, float]) -> float:
        """Calculate the Euclidean distance between two points."""
        if len(point1) != 3 or len(point2) != 3:
            raise ValueError("Both points must be 3D coordinates.")
        return math.sqrt(sum((p1 - p2) ** 2 for p1, p2 in zip(point1, point2)))

    def idx_of_next_point(self, distance: float, idx: int, limit: float = 30.0) -> tuple[int, bool]:
        if distance > limit:
            if idx <= 0:
                return 0, False
            return idx - 1, False
        return idx + 1, True

    def undo(self):
        if self.digitised_points.empty:
            return

        # Remove the last captured point globally.
        self.digitised_points = self.digitised_points.iloc[:-1].copy()

        # Move target pointer one step back, potentially into previous scheme item.
        if self.current_item is None:
            self.current_scheme_idx = max(0, len(self.scheme) - 1)
            self.current_label_idx = self.current_item.n_points if self.current_item else 0

        if self.current_label_idx > 0:
            self.current_label_idx -= 1
            return

        if self.current_scheme_idx > 0:
            self.current_scheme_idx -= 1
            self.current_label_idx = max(0, self.current_item.n_points - 1) if self.current_item else 0

    def update_point(self, index: int, category: str, label: str, x: float, y: float, z: float):
        if index < 0 or index >= len(self.digitised_points):
            raise IndexError("Point index out of range")

        self.digitised_points.loc[index, "category"] = str(category)
        self.digitised_points.loc[index, "label"] = str(label)
        self.digitised_points.loc[index, "x"] = float(x)
        self.digitised_points.loc[index, "y"] = float(y)
        self.digitised_points.loc[index, "z"] = float(z)

    def save_csv(self, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df = self.digitised_points.copy()
        if self.participant_id:
            df.insert(0, "participant_id", self.participant_id)
        df.to_csv(output_path, index=False)

    def save_session(self, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "participant_id": self.participant_id,
            "current_scheme_idx": self.current_scheme_idx,
            "current_label_idx": self.current_label_idx,
            "scheme": [
                {
                    "category": item.category,
                    "labels": item.labels,
                    "dig_type": item.dig_type,
                    "n_points": item.n_points,
                    "unbounded": item.unbounded,
                }
                for item in self.scheme
            ],
            "digitised_points": self.digitised_points.to_dict(orient="records"),
        }
        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_session(self, input_path: Path):
        payload = json.loads(input_path.read_text(encoding="utf-8"))

        loaded_scheme: list[SchemeItem] = []
        for item in payload.get("scheme", []):
            loaded_scheme.append(
                SchemeItem(
                    category=item["category"],
                    labels=list(item.get("labels", [])),
                    dig_type=item.get("dig_type", "single"),
                    n_points=int(item.get("n_points", 0)),
                    unbounded=bool(item.get("unbounded", item.get("dig_type", "single") == "continuous")),
                    template=None,
                )
            )

        if loaded_scheme:
            for idx, old in enumerate(self.scheme):
                if idx < len(loaded_scheme):
                    loaded_scheme[idx].template = old.template
            self.scheme = loaded_scheme

        self.participant_id = str(payload.get("participant_id", ""))
        self.current_scheme_idx = int(payload.get("current_scheme_idx", 0))
        self.current_label_idx = int(payload.get("current_label_idx", 0))

        df = pd.DataFrame(payload.get("digitised_points", []))
        if df.empty:
            self.digitised_points = pd.DataFrame(columns=["category", "label", "x", "y", "z"])
        else:
            self.digitised_points = df[["category", "label", "x", "y", "z"]].copy()

    def validate_schema(self) -> bool:
        """Ensure all single-point schemas have labels or templates populated."""
        for item in self.scheme:
            if item.dig_type == "single" and not item.labels and not item.template:
                raise ValueError(f"Category '{item.category}' requires labels or a template.")
        return True

    def status_text(self) -> tuple[str, str, str]:
        if self.is_finished:
            return "Done", "No active target", "Finished all scheme items"

        item = self.current_item
        if item is None:
            return "No category", "No target", "No progress"

        current_target = self.current_label or "(none)"
        if item.dig_type == "continuous" and item.unbounded:
            progress = f"{self.current_label_idx} points"
        else:
            progress = f"{self.current_label_idx}/{item.n_points}"
        return item.category, current_target, progress

    def _advance_if_needed(self):
        item = self.current_item
        if item is None:
            return

        if item.dig_type == "continuous" and item.unbounded:
            return

        if item.dig_type == "single" and self.current_label_idx < len(item.labels):
            return

        if item.dig_type == "continuous" and self.current_label_idx < item.n_points:
            return

        self.current_scheme_idx += 1
        self.current_label_idx = 0

        if self.current_item is not None and self.connector is not None:
            self.connector.clear_old_data()
