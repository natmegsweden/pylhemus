from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import os
from typing import Any

import numpy as np
import pandas as pd
from ..template.EEG_layout import EEGcapTemplate


def neuromag_transform_general(LPA, NAS, RPA):
    """

    Compute neuromag-like head coordinate transform without assuming

    that the origin is at the midpoint between LPA and RPA.

    Origin is the perpendicular projection of NAS onto the Y-axis.

    """

    LPA = np.asarray(LPA, float)
    NAS = np.asarray(NAS, float)
    RPA = np.asarray(RPA, float)

    # 1. Y-axis from LPA → RPA
    y = RPA - LPA
    y = y / np.linalg.norm(y)

    # 2. Project NAS onto Y-axis to find the true origin O
    #    O = LPA + ( (NAS-LPA)·y ) * y
    vec = NAS - LPA
    proj_length = np.dot(vec, y)
    origin = LPA + proj_length * y

    # 3. X-axis is the direction from origin to NAS
    x = NAS - origin
    x = x / np.linalg.norm(x)

    # 4. Z-axis by right-hand rule
    z = np.cross(x, y)
    z = z / np.linalg.norm(z)

    # 5. Rotation matrix (rows = new coordinate axes)
    R = np.vstack([x, y, z])

    # 6. Homogeneous transform: transforms points into this system
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = -R @ origin

    return T


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
        self._neuromag_transform: np.ndarray | None = None
        self._transform_valid: bool = False
        self._auto_switched_to_transformed: bool = False

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

        # Check for duplicates in single-type categories
        if item.dig_type == "single":
            existing = self.digitised_points[
                (self.digitised_points["category"] == item.category) &
                (self.digitised_points["label"] == label)
            ]
            if len(existing) > 0:
                print(f"Duplicate: {label} in {item.category} already captured, skipping")
                # Auto-advance to next
                self.current_label_idx += 1
                self._advance_if_needed()
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
        self.update_neuromag_transform()

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

        # Remove the last captured point
        self.digitised_points = self.digitised_points.iloc[:-1].copy()

        # Move target pointer one step back
        if self.current_label_idx > 0:
            # Just move back within current scheme item
            self.current_label_idx -= 1
        elif self.current_scheme_idx > 0:
            # Move to previous scheme item
            self.current_scheme_idx -= 1
            item = self.current_item
            if item:
                if item.dig_type == "single":
                    self.current_label_idx = len(item.labels) - 1
                else:
                    self.current_label_idx = item.n_points - 1
            else:
                self.current_label_idx = 0
        else:
            # At the very beginning
            self.current_label_idx = 0

        self._auto_switched_to_transformed = False
        self.update_neuromag_transform(force=True)

    def update_point(self, index: int, category: str, label: str, x: float, y: float, z: float):
        if index < 0 or index >= len(self.digitised_points):
            raise IndexError("Point index out of range")

        self.digitised_points.loc[index, "category"] = str(category)
        self.digitised_points.loc[index, "label"] = str(label)
        self.digitised_points.loc[index, "x"] = float(x)
        self.digitised_points.loc[index, "y"] = float(y)
        self.digitised_points.loc[index, "z"] = float(z)

        self._auto_switched_to_transformed = False
        self.update_neuromag_transform(force=True)

    def save_csv(self, output_path: Path):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df = self.digitised_points.copy()
        if self.participant_id:
            df.insert(0, "participant_id", self.participant_id)

        if self.has_valid_neuromag_transform():
            x_t_list, y_t_list, z_t_list = [], [], []
            for _, row in df.iterrows():
                t = self.apply_neuromag_transform((row["x"], row["y"], row["z"]))
                if t:
                    x_t_list.append(t[0])
                    y_t_list.append(t[1])
                    z_t_list.append(t[2])
                else:
                    x_t_list.append(None)
                    y_t_list.append(None)
                    z_t_list.append(None)
            df["x_t"] = x_t_list
            df["y_t"] = y_t_list
            df["z_t"] = z_t_list

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

    def save_session_with_transform(self, output_path: Path):
        """Save session including transformed points for full restore."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Get points with transforms if available
        points_data = self.digitised_points.to_dict(orient="records")
        
        # Add transformed coordinates if transform is valid
        if self.has_valid_neuromag_transform():
            for i, point in enumerate(points_data):
                transformed = self.apply_neuromag_transform(
                    (point["x"], point["y"], point["z"])
                )
                if transformed:
                    point["x_t"] = transformed[0]
                    point["y_t"] = transformed[1]
                    point["z_t"] = transformed[2]
        
        payload = {
            "participant_id": self.participant_id,
            "current_scheme_idx": self.current_scheme_idx,
            "current_label_idx": self.current_label_idx,
            "transform_valid": self._transform_valid,
            "auto_switched_to_transformed": self._auto_switched_to_transformed,
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
            "digitised_points": points_data,
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

    def sync_indices_to_captured_points(self):
        """After loading session, adjust indices to continue from last captured position."""
        if self.digitised_points.empty:
            self.current_scheme_idx = 0
            self.current_label_idx = 0
            return
        
        # Count points per category
        category_counts = self.digitised_points.groupby("category").size().to_dict()
        
        # Find which scheme item we're on
        for scheme_idx, item in enumerate(self.scheme):
            count = category_counts.get(item.category, 0)
            
            if item.dig_type == "single":
                # For single-type, check if all labels are captured
                captured_labels = set(
                    self.digitised_points[self.digitised_points["category"] == item.category]["label"].tolist()
                )
                
                if len(captured_labels) >= len(item.labels):
                    # All captured, move to next scheme
                    continue
                else:
                    # Partially captured, find next missing label
                    self.current_scheme_idx = scheme_idx
                    for label_idx, label in enumerate(item.labels):
                        if label not in captured_labels:
                            self.current_label_idx = label_idx
                            return
                    # Should not reach here
                    self.current_label_idx = len(item.labels)
                    return
            else:
                # Continuous type - position at the end
                self.current_scheme_idx = scheme_idx
                self.current_label_idx = count
                return
        
        # All scheme items completed
        self.current_scheme_idx = len(self.scheme)
        self.current_label_idx = 0

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
        elif item.dig_type == "single":
            progress = f"{self.current_label_idx}/{len(item.labels)}"
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

    def has_valid_neuromag_transform(self) -> bool:
        return self._transform_valid and self._neuromag_transform is not None

    def get_fiducials_for_transform(self) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
        df = self.digitised_points
        fiducials = df[df["category"] == "fiducials"]
        if len(fiducials) < 3:
            return None
        lpa_row = fiducials[fiducials["label"] == "lpa"]
        nas_row = fiducials[fiducials["label"] == "nasion"]
        rpa_row = fiducials[fiducials["label"] == "rpa"]
        if len(lpa_row) < 1 or len(nas_row) < 1 or len(rpa_row) < 1:
            return None
        lpa = lpa_row[["x", "y", "z"]].values[0]
        nas = nas_row[["x", "y", "z"]].values[0]
        rpa = rpa_row[["x", "y", "z"]].values[0]
        return lpa, nas, rpa

    def is_fiducial_degenerate(self) -> bool:
        fiducials = self.get_fiducials_for_transform()
        if fiducials is None:
            return False
        lpa, nas, rpa = fiducials
        v1 = nas - lpa
        v2 = rpa - lpa
        cross = np.cross(v1, v2)
        return np.linalg.norm(cross) < 1e-6

    def update_neuromag_transform(self, force: bool = False):
        if self._transform_valid and not force:
            return
        fiducials = self.get_fiducials_for_transform()
        if fiducials is None:
            self._neuromag_transform = None
            self._transform_valid = False
            return
        lpa, nas, rpa = fiducials
        if self.is_fiducial_degenerate():
            self._neuromag_transform = None
            self._transform_valid = False
            return
        self._neuromag_transform = neuromag_transform_general(LPA=lpa, NAS=nas, RPA=rpa)
        self._transform_valid = True

    def apply_neuromag_transform(self, point: tuple[float, float, float]) -> tuple[float, float, float] | None:
        if self._neuromag_transform is None:
            return None
        pt = np.array([point[0], point[1], point[2], 1.0])
        transformed = self._neuromag_transform @ pt
        return (float(transformed[0]), float(transformed[1]), float(transformed[2]))

    def get_transformed_points(self) -> pd.DataFrame:
        if not self.has_valid_neuromag_transform():
            return self.digitised_points.copy()
        result = self.digitised_points.copy()
        def transform_row(row):
            pt = (row["x"], row["y"], row["z"])
            transformed = self.apply_neuromag_transform(pt)
            if transformed is None:
                return np.nan, np.nan, np.nan
            return transformed[0], transformed[1], transformed[2]
        transformed = result.apply(transform_row, axis=1, result_type="expand")
        result["x_transformed"] = transformed[0]
        result["y_transformed"] = transformed[1]
        result["z_transformed"] = transformed[2]
        return result
