# FASTRAK command quick reference

This document is a cleaned implementation-facing command summary derived from
FASTRAK_User_Manual_OPM00PI002-G.pdf and current `pylhemus` behavior.

Use this as an operator and development reference for `pylhemus talk` and the
serial-device modes of `pylhemus settings`. For normative command definitions,
rely on the vendor PDF.

## Serial baseline

- Interface: ASCII commands over serial.
- Typical line ending for commands: carriage return.
- Default `pylhemus` settings: 9600 baud, 8 data bits, no parity, 1 stop bit,
  no flow control.

## `pylhemus talk` quick index

- `pylhemus talk --port <PORT> status`: reads `S`, `X`, `y`, `v`, and `x`.
- `pylhemus talk --port <PORT> receivers`: reads `l1`.
- `pylhemus talk --port <PORT> station --id <1-4>`: reads `Hn`, `An`, `Gn`, `In`, `On`, `Vn`, `Qn`, `rn`, `Nn`.
- `pylhemus talk --port <PORT> set-units cm|in`: sends `u` or `U`.
- `pylhemus talk --port <PORT> prepare`: sends `W`, then `u`, then checks `l1`.
- `pylhemus talk --port <PORT> stream`: reads streaming sample lines.
- `pylhemus talk --port <PORT> send-raw <cmd>`: sends one raw command as-is (supports `^S` style control notation).

## `pylhemus settings` serial quick index

- `pylhemus settings --dump [--out <file.json>] [--port <PORT>]`: full settings snapshot using the same status and station query families.
- `pylhemus settings --apply --from <file.json> [--port <PORT>]`: replays restorable settings from a previous dump.

## Command mapping

- `pylhemus talk --port <PORT> status`
  - Sends: `S`, `X`, `y`, filter queries `v` and `x`.
  - Purpose: read system status, configuration, synchronization mode, filter parameters.

- `pylhemus talk --port <PORT> receivers`
  - Sends: `l1`.
  - Purpose: read active station state for stations 1-4.

- `pylhemus talk --port <PORT> station --id <1-4>`
  - Sends: `Hn`, `An`, `Gn`, `In`, `On`, `Vn`, `Qn`, `rn`, `Nn`.
  - Purpose: read per-station configuration and envelopes.

- `pylhemus settings --dump [--out file.json] [--port <PORT>]`
  - Sends: all status + active stations + station commands for active stations.
  - Purpose: one-shot settings snapshot.
  - Output: JSON with the parsed system block, active-station state, and per-station settings for active stations.

- `pylhemus settings --apply --from file.json [--port <PORT>]`
  - Sends: restorable commands extracted from a previous dump.
  - Output: restore report from `read_settings.apply_settings()`.

- `pylhemus talk --port <PORT> set-units cm|in`
  - Sends: `u` (metric) or `U` (english/inches).
  - Purpose: set conversion units.

- `pylhemus talk --port <PORT> prepare`
  - Sends: `W`, `u`, then `l1`.
  - Purpose: reset to defaults, switch to metric, verify active stations.

- `pylhemus talk --port <PORT> stream`
  - Sends: `^S`, `c`, `F` unless `--no-prepare` is used; optionally `u` for `--metric`; optionally `C` for `--continuous`.
  - Purpose: stream live sample lines while keeping the interface in a readable ASCII mode.

- `pylhemus talk --port <PORT> send-raw <cmd>`
  - Sends: the raw command text exactly (supports caret notation like `^S`).
  - Purpose: advanced/manual command access.

## Core FASTRAK command summary

### System and transport

- `F`: enable ASCII output format.
- `f`: enable binary output format.
- `W`: reset system to defaults.
- `X`: configuration control data.
- `S`: system status record.
- `T`: built-in-test information.
- `o`: set output port.
- `^Q`: resume data transmission.
- `^S`: suspend data transmission.
- `^Y`: reinitialize system.
- `^K`: save operational configuration.

### Units and synchronization

- `U`: english units (inches).
- `u`: metric units (centimeters).
- `y`: synchronization mode.

### Output control

- `P`: single data record output.
- `C`: continuous output mode.
- `c`: disable continuous printing.
- `O`: output data list.

### Station and geometry

- `l`: active station state.
- `A`: alignment reference frame.
- `R`: reset alignment reference frame.
- `B`: boresight.
- `b`: unboresight.
- `G`: boresight reference angles.
- `H`: hemisphere of operation.
- `I`: increment definition.
- `N`: tip offsets.
- `Q`: angular operational envelope.
- `V`: position operational envelope.
- `r`: transmitter mounting frame.

### Compensation and filters

- `D`: enable fixed metal compensation.
- `d`: disable fixed metal compensation.
- `v`: attitude filter parameters.
- `x`: position filter parameters.

## Notes for operators

- Commands marked with `*` in the vendor manual are not persisted to EEPROM.
- `pylhemus settings --dump` writes a snapshot that can be replayed with `pylhemus settings --apply`.
- `pylhemus settings --apply` does not send `W` (reset defaults) or `^K` (save to EEPROM) automatically.
- If you need persistence after `pylhemus settings --apply`, send `pylhemus talk --port <PORT> send-raw ^K` manually after verifying the restore report.
- Use `send-raw` for features not wrapped by friendly subcommands.
- FASTRAK uses `*` as an in-line field terminator in some replies. `send-raw` now splits those fields into separate response entries automatically.
- `send-raw` always reports `diagnostics.outcome` as one of `accepted`, `rejected`, or `no_response`.
- If the device appears stuck in streaming mode, suspend transmission (`^S`) before querying settings.
- Use `send-raw --prepare` if the device may still be in streaming or noisy mode before a query.
- Some FASTRAK units/firmware configurations reject certain write/config commands and return
  `E*ERROR* ... EC -99 ...` even when query commands (for example `S`, `X`, `y`) still work.
  In that case, treat the command as unsupported in the current device mode/firmware profile.

## Example backup and restore workflow

```bash
# Create a restore-ready JSON snapshot
pylhemus settings --dump --port COM1 --out settings.json

# Replay the saved settings to a device
pylhemus settings --apply --port COM1 --from settings.json

# Optionally persist the live configuration to EEPROM
pylhemus talk --port COM1 send-raw ^K
```
