# pylhemus

FASTRAK digitisation GUI for OPM/MEG head tracking. Records 3D coordinates of fiducials, HPI coils, and head shape.

Original code by [Laura B Paulsen](https://github.com/laurabpaulsen/OPM_lab).

## Installation

```bash
python -m pip install -e .
```

## Quick Start

Launch the digitisation GUI:

```bash
pylhemus gui
```

## Features

### Coordinate Systems
- Records raw FASTRAK coordinates
- **Neuromag transform**: Automatically computes RAS coordinates from fiducials (LPA, Nasion, RPA)
- Toggle between original and transformed views

### Auto-Save & Recovery
- Session auto-saved every 5 seconds to temp directory
- Restore crashed sessions:
  ```bash
  pylhemus gui --restore-last
  ```

### Development Mode
Test without FASTRAK hardware:
```bash
pylhemus gui --dev-mode
```
Features:
- Simulated FASTRAK connector
- Manual point injection buttons
- Faulty point simulation (>30cm rejection)

### GUI Controls

**Left Panel:**
- Vertical zoom slider
- Transform toggle button (green=ON, red=OFF)

**Right Panel:**
- Category, target, and progress labels
- Square control buttons:
  - **Undo** - Remove last point
  - **Restart** - Clear all data
  - **Save CSV** - Export to file
  - **Finish** - Close and save
  - **Delete Point** - Remove selected continuous point (red button)

**Table:**
- 9 columns: participant_id, category, label, x, y, z, x', y', z'
- Select row to highlight point in 3D view
- Click point in 3D to select table row

### Protection Features
- **Duplicate protection**: Single-type categories (fiducials, HPI_coils) can only be captured once
- **Distance check**: Points >30cm from head are rejected
- **Continuous point deletion**: Only head shape points can be deleted

## Commands

```bash
# Launch GUI
pylhemus gui

# With custom settings
pylhemus gui --settings my_settings.json

# Development mode (no hardware)
pylhemus gui --dev-mode

# Restore last session
pylhemus gui --restore-last

# Read FASTRAK settings
pylhemus read-settings --port COM1 --out settings.json

# Run without installing
python -m pylhemus gui
```

## Workflow

1. Launch GUI with `pylhemus gui`
2. Enter participant ID and select schema
3. Capture fiducials (LPA, Nasion, RPA) - transform activates automatically
4. Capture HPI coils (hpi1-4)
5. Capture head shape points (continuous)
6. Click **Save CSV** or **Finish** to export

## CSV Output

Columns: participant_id, category, label, x, y, z, x_t, y_t, z_t

- x, y, z: Original FASTRAK coordinates
- x_t, y_t, z_t: Transformed Neuromag coordinates (if fiducials captured)

## Documentation

See `docs/` directory for detailed documentation.
