# FASTRAK command quick reference

This document is a cleaned implementation-facing command summary derived from
FASTRAK_User_Manual_OPM00PI002-G.pdf and current `pylhemus` behavior.

Use this as an operator and development reference for `pylhemus talk`
commands. For normative command definitions, rely on the vendor PDF.

## Serial baseline

- Interface: ASCII commands over serial.
- Typical line ending for commands: carriage return.
- Default `pylhemus` settings: 9600 baud, 8 data bits, no parity, 1 stop bit,
  no flow control.

## `pylhemus talk` quick index

- `pylhemus talk --port <PORT> status`: reads `S`, `X`, `y`, `v`, and `x`.
- `pylhemus talk --port <PORT> receivers`: reads `l1`.
- `pylhemus talk --port <PORT> station --id <1-4>`: reads `Hn`, `An`, `Gn`, `In`, `On`, `Vn`, `Qn`, `rn`, `Nn`.
- `pylhemus talk --port <PORT> dump-settings`: full settings snapshot using the above command families.
- `pylhemus talk --port <PORT> set-units cm|in`: sends `u` or `U`.
- `pylhemus talk --port <PORT> prepare`: sends `W`, then `u`, then checks `l1`.
- `pylhemus talk --port <PORT> send-raw <cmd>`: sends one raw command as-is (supports `^S` style control notation).

## `pylhemus talk` command mapping

- `pylhemus talk --port <PORT> status`
  - Sends: `S`, `X`, `y`, filter queries `v` and `x`.
  - Purpose: read system status, configuration, synchronization mode, filter parameters.

- `pylhemus talk --port <PORT> receivers`
  - Sends: `l1`.
  - Purpose: read active station state for stations 1-4.

- `pylhemus talk --port <PORT> station --id <1-4>`
  - Sends: `Hn`, `An`, `Gn`, `In`, `On`, `Vn`, `Qn`, `rn`, `Nn`.
  - Purpose: read per-station configuration and envelopes.

- `pylhemus talk --port <PORT> dump-settings [--out file.json]`
  - Sends: all status + active stations + station commands for active stations.
  - Purpose: one-shot settings snapshot.

- `pylhemus talk --port <PORT> set-units cm|in`
  - Sends: `u` (metric) or `U` (english/inches).
  - Purpose: set conversion units.

- `pylhemus talk --port <PORT> prepare`
  - Sends: `W`, `u`, then `l1`.
  - Purpose: reset to defaults, switch to metric, verify active stations.

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
- Use `send-raw` for features not wrapped by friendly subcommands.
- If the device appears stuck in streaming mode, suspend transmission (`^S`) before querying settings.
