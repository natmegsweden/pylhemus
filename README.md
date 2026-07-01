# pylhemus

FASTRAK digitisation GUI for OPM/MEG head tracking. Records 3D coordinates of fiducials, HPI coils, and head shape.

Original code by [Laura B Paulsen](https://github.com/laurabpaulsen/OPM_lab).

![Head example](docs/pylhemus_example.png)


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

# Friendly FASTRAK command interface
pylhemus talk --port COM1 status
pylhemus talk --port COM1 receivers
pylhemus talk --port COM1 station --id 1
pylhemus talk --port COM1 dump-settings --out settings.json
pylhemus talk --port COM1 apply-settings --from settings.json
pylhemus talk --port COM1 set-units cm
pylhemus talk --port COM1 send-raw S

# Run without installing
python -m pylhemus gui
```

## FASTRAK settings backup and restore

- `pylhemus read-settings --port COM1 --out settings.json` reads the current FASTRAK configuration into JSON.
- `pylhemus talk --port COM1 dump-settings --out settings.json` produces an enriched snapshot with parsed values and restore-ready command fields.
- `pylhemus talk --port COM1 apply-settings --from settings.json` replays the saved restorable settings to a live device and returns a per-command restore report.
- Per-station restore commands are only sent for stations that are active on the target device.
- Settings are not persisted to FASTRAK EEPROM automatically. If persistence is needed after restore, run `pylhemus talk --port COM1 send-raw ^K` manually.

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
