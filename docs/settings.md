# Settings

`pylhemus` loads settings from multiple layers.

## Resolution order

Settings are merged in this order, from lowest to highest priority:

1. Bundled defaults in `pylhemus/default_settings.json`
2. User settings in the per-user config directory
3. Project settings in the current working directory
4. An explicit file passed with `pylhemus gui --settings`

Later layers override earlier ones.

## Settings file locations

User settings path:

- Windows: `%APPDATA%\pylhemus\settings.json`
- macOS and Linux: `~/.pylhemus/settings.json`

Project settings path:

- `pylhemus.settings.json` in the current working directory

Legacy user settings at `default_settings.json` inside the user config directory are migrated automatically to `settings.json`.

## Common fields

Typical top-level settings include:

- `serial_port`
- `serial_baud`
- `digitisation.output_dir`
- `digitisation.capture_interval_ms`
- `digitisation.default_schema_preset`
- `digitisation.schema_presets`

## Example

```json
{
  "serial_port": "COM3",
  "serial_baud": 9600,
  "digitisation": {
    "output_dir": "output",
    "default_schema_preset": "standard"
  }
}
```

## Recommended usage

- Put machine-specific defaults in the user settings file.
- Put study- or project-specific overrides in `pylhemus.settings.json`.
- Use `--settings` for one-off sessions that should not affect normal defaults.
