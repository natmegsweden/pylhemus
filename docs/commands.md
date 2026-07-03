# Commands

`pylhemus` provides three command-line entry points.

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
- `--output-dir <path>` to override the CSV output directory
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

## `pylhemus read-settings`

Read the current FASTRAK configuration and print it as JSON.

```bash
pylhemus read-settings
pylhemus read-settings >> settings.json
```

Supported options:

- `--port <port>` required serial port
- `--baud <int>` baud rate, default `9600`
- `--timeout <seconds>` serial read timeout, default `1.0`

## `pylhemus talk`

Run readable FASTRAK inspection and control commands.

Example commands:

```bash
pylhemus talk status
pylhemus talk receivers
pylhemus talk station --id 1
pylhemus talk dump-settings --out settings.json
pylhemus talk set-units cm
pylhemus talk prepare
pylhemus talk send-raw S
```

Supported subcommands:

- `status` reads system status and configuration
- `receivers` shows active stations
- `station --id <1-4>` reads one station configuration
- `dump-settings` writes a combined JSON summary
- `set-units cm|in` changes the active measurement units
- `prepare` runs the basic prepare sequence
- `send-raw <command>` sends a raw FASTRAK command

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

- `--port <port>` serial port, default `COM1`
- `--baud <int>` baud rate, default `9600`
- `--timeout <seconds>` serial read timeout, default `1.0`
- `--duration <seconds>` stream for a fixed duration; `0` means until interrupted
- `--max-lines <int>` stop after this many received lines; `0` means unlimited
- `--parsed` emit one JSON object per received line
- `--continuous`, `--continous` enable continuous output mode by sending `C`
- `--metric` set centimeters before starting the stream
- `--no-prepare` skip `^S / c / F` before starting the stream

Global options:

- `--port <port>` required serial port
- `--baud <int>` baud rate, default `9600`
- `--timeout <seconds>` serial timeout, default `1.0`
- `--json` prints structured JSON output when available
