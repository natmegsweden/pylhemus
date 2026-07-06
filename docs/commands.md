# Commands

`pylhemus` provides four top-level commands.

## Command references

- Use this page for the user-facing CLI overview.
- See [FASTRAK command quick reference](reference/fastrak_commands.md) for the
  low-level `pylhemus talk` to FASTRAK command mapping.

## `pylhemus gui`

Launch the digitisation GUI.

```bash
pylhemus gui
```

Supported options:

- `--settings <path>` to load an explicit settings JSON file
- `--port <port>` to override the configured serial port
- `--output-dir <path>` to override the save/export output directory
- `--dev-mode` to use simulated FASTRAK hardware
- `--restore-last` to resume the latest autosaved session

Examples:

```bash
pylhemus gui --settings my_settings.json
pylhemus gui --port /dev/ttyUSB0
pylhemus gui --output-dir output
pylhemus gui --dev-mode
pylhemus gui --restore-last
```

## `pylhemus settings`

Open the standalone settings dialog, dump live FASTRAK settings, apply a saved
device snapshot, or update the user settings file without opening the GUI.

```bash
pylhemus settings
pylhemus settings --dump
pylhemus settings --dump --out settings.json
pylhemus settings --apply --from settings.json
pylhemus settings --set-units inch
pylhemus settings --set-metal-compensation off
pylhemus settings --set-factory-defaults off
```

Modes:

- no flags: open the settings dialog
- `--dump`: query the live FASTRAK device and print JSON
- `--apply --from <file>`: replay settings from a previous dump
- `--set-units cm|inch`: write `digitisation.units` in the user settings file
- `--set-metal-compensation on|off`: write `digitisation.metal_compensation`
- `--set-factory-defaults on|off`: write `digitisation.set_factory_software_defaults`

Device options for `--dump` and `--apply`:

- `--port <port>` serial port; defaults to the configured settings value
- `--baud <int>` baud rate; defaults to the configured settings value
- `--timeout <seconds>` serial read timeout, default `1.0`
- `--out <file>` write `--dump` JSON to a file instead of stdout
- `--from <file>` input JSON for `--apply`

Notes:

- `--dump` and `--apply` require a serial connection.
- `--set-*` options only modify the user settings file and do not contact the device.
- `--dump`, `--apply`, and `--set-*` modes cannot be combined.

## `pylhemus talk`

Run readable FASTRAK inspection and control commands.

Example commands:

```bash
pylhemus talk status
pylhemus talk receivers
pylhemus talk station --id 1
pylhemus talk set-units cm
pylhemus talk prepare
pylhemus talk stream --parsed --max-lines 20
pylhemus talk send-raw S
```

Supported subcommands:

- `status` reads system status and configuration
- `receivers` shows active stations
- `station --id <1-4>` reads one station configuration
- `set-units cm|in` changes the active measurement units
- `prepare` runs the basic prepare sequence
- `stream` streams sample lines through the `talk` interface
- `send-raw <command>` sends a raw FASTRAK command

Talk-wide options:

- `--port <port>` serial port, default `COM1`
- `--baud <int>` baud rate, default `9600`
- `--timeout <seconds>` serial timeout, default `1.0`
- `--json` prints structured JSON output when available

## `pylhemus stream`

Open the FASTRAK serial port and print streamed records without launching the GUI.
This command uses the same startup/settings path as the GUI, including
`digitisation.hemisphere`.

```bash
pylhemus stream --port COM3 --metric
pylhemus stream --port COM3 --parsed --max-lines 20
pylhemus stream --port COM3 --max-lines 20
pylhemus stream --port COM3 --continuous --max-lines 20
```

Supported options:

- `--port <port>` serial port; defaults to the configured settings value, then `COM1`
- `--baud <int>` baud rate, default `9600`
- `--timeout <seconds>` serial read timeout, default `1.0`
- `--duration <seconds>` stream for a fixed duration; `0` means until interrupted
- `--max-lines <int>` stop after this many received lines; `0` means unlimited
- `--parsed` emit one JSON object per received line
- `--continuous`, `--continous` enable continuous output mode by sending `C`
- `--metric` set centimeters before starting the stream
- `--no-prepare` skip `^S / c / F` before starting the stream
