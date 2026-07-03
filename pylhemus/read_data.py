from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


POINT_COLUMNS = ["category", "label", "x", "y", "z"]
CSV_REQUIRED_COLUMNS = set(POINT_COLUMNS)
CATEGORY_TO_KIND = {"fiducials": 1, "HPI_coils": 2}
KIND_TO_CATEGORY = {1: "fiducials", 2: "HPI_coils", 4: "extra"}
CARDINAL_LABEL_TO_IDENT = {"lpa": 1, "nasion": 2, "rpa": 3}
IDENT_TO_CARDINAL_LABEL = {1: "lpa", 2: "nasion", 3: "rpa"}
COORD_FRAME_NAMES = {2: "isotrak", 4: "head"}
KIND_NAMES = {1: "cardinal", 2: "hpi", 3: "eeg", 4: "extra"}


def read_csv(path: Path | str) -> pd.DataFrame:
    csv_path = Path(path)
    df = pd.read_csv(csv_path)

    missing = sorted(CSV_REQUIRED_COLUMNS - set(df.columns))
    if missing:
        raise ValueError(f"Missing required CSV columns: {', '.join(missing)}")

    return df.loc[:, POINT_COLUMNS].copy()


def read_fif(path: Path | str) -> pd.DataFrame:
    try:
        from mne.io import read_info
    except ImportError as exc:
        raise ImportError("Reading FIF files requires the optional 'mne' dependency.") from exc

    fif_path = Path(path)
    info = read_info(fif_path, verbose=False)
    dig_points = info.get("dig") or []
    if not dig_points:
        raise ValueError(f"No digitisation points found in FIF file: {fif_path}")

    rows: list[dict[str, str | float]] = []
    for dig_point in dig_points:
        kind = int(dig_point.get("kind", -1))
        ident = int(dig_point.get("ident", 0))
        x, y, z = (float(value) * 100.0 for value in dig_point["r"])

        category, label = _fallback_category_and_label(kind=kind, ident=ident)

        rows.append(
            {
                "category": category,
                "label": label,
                "x": x,
                "y": y,
                "z": z,
            }
        )

    return pd.DataFrame(rows, columns=POINT_COLUMNS)


def write_dig_json(path: Path | str, df: pd.DataFrame, controller) -> None:
    output_path = Path(path)
    dig: list[dict[str, object]] = []
    hpi_ident = 0
    extra_ident = 0

    for _, row in df.iterrows():
        category = str(row["category"])
        label = str(row["label"])
        kind = CATEGORY_TO_KIND.get(category, 4)

        if kind == 1:
            ident = CARDINAL_LABEL_TO_IDENT.get(label.lower(), 0)
            ident_name = IDENT_TO_CARDINAL_LABEL.get(ident)
        elif kind == 2:
            hpi_ident += 1
            ident = hpi_ident
            ident_name = None
        else:
            extra_ident += 1
            ident = extra_ident
            ident_name = None

        dig.append(
            {
                "kind": kind,
                "kind_name": KIND_NAMES.get(kind, "unknown"),
                "ident": ident,
                "ident_name": ident_name,
                "coord_frame": 2,
                "coord_frame_name": COORD_FRAME_NAMES[2],
                "r": [float(row["x"]) / 100.0, float(row["y"]) / 100.0, float(row["z"]) / 100.0],
                "pylhemus_category": category,
                "pylhemus_label": label,
            }
        )

    dev_head_t = None
    if controller.has_valid_neuromag_transform():
        transform = controller._neuromag_transform.copy()
        transform[:3, 3] = transform[:3, 3] / 100.0
        dev_head_t = {
            "from": 2,
            "from_name": COORD_FRAME_NAMES[2],
            "to": 4,
            "to_name": COORD_FRAME_NAMES[4],
            "trans": transform.tolist(),
        }

    payload = {
        "format": "pylhemus-dig/1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "subject": {
            "participant_id": getattr(controller, "participant_id", "") or "",
            "project": getattr(controller, "project", "") or "",
        },
        "coord_frame": {
            "raw": 2,
            "raw_name": COORD_FRAME_NAMES[2],
            "units": "m",
        },
        "dig": dig,
        "dev_head_t": dev_head_t,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def read_dig_json(path: Path | str) -> pd.DataFrame:
    input_path = Path(path)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    fmt = str(payload.get("format", ""))
    if not fmt.startswith("pylhemus-dig/"):
        raise ValueError(f"Unsupported digitisation JSON format: {fmt or '<missing>'}")

    dig_points = payload.get("dig")
    if not dig_points:
        raise ValueError(f"No digitisation points found in JSON file: {input_path}")

    rows: list[dict[str, str | float]] = []
    for dig_point in dig_points:
        kind = int(dig_point.get("kind", -1))
        ident = int(dig_point.get("ident", 0))
        coords = dig_point.get("r")
        if not isinstance(coords, list) or len(coords) != 3:
            raise ValueError(f"Invalid digitisation point coordinates in JSON file: {input_path}")

        category = str(dig_point.get("pylhemus_category") or "")
        label = str(dig_point.get("pylhemus_label") or "")
        if not category or not label:
            category, label = _fallback_category_and_label(kind=kind, ident=ident)

        rows.append(
            {
                "category": category,
                "label": label,
                "x": float(coords[0]) * 100.0,
                "y": float(coords[1]) * 100.0,
                "z": float(coords[2]) * 100.0,
            }
        )

    return pd.DataFrame(rows, columns=POINT_COLUMNS)


def _fallback_category_and_label(kind: int, ident: int) -> tuple[str, str]:
    if kind == 1:
        label = IDENT_TO_CARDINAL_LABEL.get(ident)
        if label is not None:
            return "fiducials", label
    elif kind == 2:
        return "HPI_coils", f"hpi{ident}"
    elif kind == 4:
        return "extra", f"extra{ident}"

    return KIND_TO_CATEGORY.get(kind, "unknown"), f"point{ident}"


def read_file(path: Path | str) -> pd.DataFrame:
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".csv":
        return read_csv(file_path)
    if suffix == ".fif":
        return read_fif(file_path)
    if suffix == ".json":
        return read_dig_json(file_path)

    raise ValueError(f"Unsupported file type: {file_path.suffix or '<none>'}")
