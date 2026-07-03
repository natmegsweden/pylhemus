# Polhemus digitisation

## Purpose

Use this workflow to capture fiducials, HPI coils, and head-shape points from a Polhemus FASTRAK session.

## Hardware setup

Required hardware:

- Polhemus FASTRAK unit
- Transmitter
- Stylus
- Receiver for the participant
- RS-232 connection or USB-to-RS-232 adapter

Recommended connection layout:

- Connect the transmitter to the transmitter port on the FASTRAK unit.
- Connect the stylus to receiver port 1.
- Connect the participant receiver to receiver port 2.
- Connect the FASTRAK unit to the computer over RS-232.

## Start the GUI

```bash
pylhemus gui
```

Useful launch options:

```bash
pylhemus gui --settings my_settings.json
pylhemus gui --port COM3
pylhemus gui --output-dir output
pylhemus gui --dev-mode
pylhemus gui --restore-last
```

The startup dialog lets you:

- enter the participant ID
- choose a schema preset
- review or edit the schema before starting

## Capture workflow

Recommended order:

1. Capture `lpa`.
2. Capture `nasion`.
3. Capture `rpa`.
4. Capture HPI coils.
5. Capture continuous head-shape points.

After the three fiducials are present, the GUI computes the Neuromag transform automatically.

## During the session

The GUI provides:

- point capture progress and current target labels
- a 3D point view
- a table of raw and transformed coordinates
- `Undo`, `Delete`, `Restart`, `Save`, and `Finish` actions
- point deletion for selected continuous points

Duplicate protection applies to single-capture categories such as fiducials and HPI coils.
By default, the first three fiducials are auto-swapped to `lpa`, `nasion`, and
`rpa` using the old Neuromag-style assumption that nasion is the front-most
point and LPA/RPA are separated primarily along the sensor-frame `y` axis.

## Saving and restoring

- CSV output is written to the configured output directory.
- Autosave runs periodically in the system temporary directory.
- `pylhemus gui --restore-last` resumes the most recent autosaved session.

The exported CSV contains:

- `participant_id`
- `category`
- `label`
- `x`, `y`, `z`
- `x_t`, `y_t`, `z_t` when the transform is valid

## Settings and overrides

The default serial port can be set in the user settings file:

- Windows: `%APPDATA%\pylhemus\settings.json`
- macOS and Linux: `~/.pylhemus/settings.json`

Example:

```json
{
  "serial_port": "COM3",
  "digitisation": {
    "hemisphere": [0, 0, 1]
  }
}
```

The GUI no longer reorders the first three fiducials automatically. If the
captured geometry suggests the current labels are inconsistent, it shows a
warning and keeps the labels unchanged.

`digitisation.hemisphere` maps to FASTRAK `H` for each active station during
startup. The default `[0, 0, 1]` matches the old Neuromag Isotrak configs that
were recovered from the legacy `dacq` tree.

For project-specific overrides in the current working directory, use `pylhemus.settings.json`.

## Inspect FASTRAK settings without the GUI

Dump a JSON summary:

```bash
pylhemus read-settings --port COM3
pylhemus read-settings --port COM3 >> plh_settings.json
```

Query the device interactively:

```bash
pylhemus talk --port COM3 status
pylhemus talk --port COM3 receivers
pylhemus talk --port COM3 station --id 1
```

See [Commands](../commands.md) for the full CLI overview and
[FASTRAK command quick reference](../reference/fastrak_commands.md) for the
low-level command mapping.
