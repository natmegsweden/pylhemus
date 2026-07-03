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
pylhemus read-settings --port COM3
pylhemus read-settings --port COM3 >> settings.json
```

Supported options:

- `--port <port>` required serial port
- `--baud <int>` baud rate, default `9600`
- `--out <path>` optional output JSON path; if omitted, JSON is printed to stdout
- `--timeout <seconds>` serial read timeout, default `1.0`

## `pylhemus talk`

Run readable FASTRAK inspection and control commands.

Example commands:

```bash
pylhemus talk --port COM3 status
pylhemus talk --port COM3 receivers
pylhemus talk --port COM3 station --id 1
pylhemus talk --port COM3 dump-settings --out settings.json
pylhemus talk --port COM3 set-units cm
pylhemus talk --port COM3 prepare
pylhemus talk --port COM3 send-raw S
```

Supported subcommands:

- `status` reads system status and configuration
- `receivers` shows active stations
- `station --id <1-4>` reads one station configuration
- `dump-settings` writes a combined JSON summary
- `set-units cm|in` changes the active measurement units
- `prepare` runs the basic prepare sequence
- `send-raw <command>` sends a raw FASTRAK command

Global options:

- `--port <port>` required serial port
- `--baud <int>` baud rate, default `9600`
- `--timeout <seconds>` serial timeout, default `1.0`
- `--json` prints structured JSON output when available
