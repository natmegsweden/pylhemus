# pylhemus

Python 3.10+, single package `pylhemus/`.

## Install

```bash
pip install -e .
```

## Commands

```bash
# Basic usage
pylhemus gui                                          # Launch digitisation GUI
pylhemus gui --settings x.json                       # With custom settings
pylhemus gui --dev-mode                              # Development mode (simulated hardware)
pylhemus gui --restore-last                          # Restore from auto-saved session

# FASTRAK settings
pylhemus read-settings --port COM3 --out settings.json

# Without installing
python -m pylhemus gui
```

## Package layout

- `pylhemus/cli.py` — entry point (`pylhemus` console script)
- `pylhemus/gui.py` — `launch_gui()`, wires together the digitisation window
- `pylhemus/read_settings.py` — CLI for reading FASTRAK settings via serial
- `pylhemus/settings.py` — settings resolution: bundled defaults → `~/.pylhemus/default_settings.json` → cwd → explicit path
- `pylhemus/digitise/` — core digitisation: connector, controller, PyVista GUI
- `pylhemus/digitise/dev_connector.py` — `DevModeConnector` for testing without hardware

Settings file (`default_settings.json`) is bundled as package data.

## Key Features

### Dev Mode
- Auto-detects missing FASTRAK and switches to simulated hardware
- Manual point injection via "Add Point" / "Add Faulty Point" buttons
- No auto-capture timer (manual control only)

### Neuromag Coordinate Transform
- Computes RAS coordinates from fiducials (LPA, Nasion, RPA)
- Transform applied when all 3 fiducials captured
- Original and transformed coords shown in table (x, y, z, x', y', z')
- Toggle button switches view (green=ON, red=OFF)

### Auto-Save & Restore
- Saves to temp dir every 5 seconds: `{temp_dir}/{participant_id}_autosave.json`
- Includes transformed points for full restore
- `--restore-last` skips LaunchDialog, continues from last position
- `sync_indices_to_captured_points()` calculates correct resume position

### Duplicate Protection
- Single-type categories (fiducials, HPI_coils) can only be captured once
- Auto-skips already-captured labels

### GUI Layout
- Left: Vertical zoom slider + transform toggle button
- Right: Category labels (bordered) + square buttons (80x80)
- Table: 9 columns (participant_id, category, label, x, y, z, x', y', z')
- Bidirectional selection: table row ↔ plot point (yellow highlight)

### Cross-Platform Dark Theme
- Explicit dark palette applied via `setup_dark_theme()`
- Consistent appearance on macOS, Windows, and Linux
- Fusion style used for uniform widget rendering
- Explicit colors prevent white-on-white text issues

## No test/lint tooling

There is no `pytest`, `ruff`, `mypy`, or pre-commit config. The docs site (`.github/workflows/ci.yml`) uses Jekyll CI only.
