---
title: Polhemus digitistation
nav_order: 1
parent: Digtising
layout: default
---

# Polhemus digitisation

## Physical setup
* Polhemus Fastrak device, transmitter, stylus, reciever

Transmitter: Connect the transmitter to the port labelled transmitter on the device
Receiver ports: Stylus connected to receiver port 1, receiver to be placed on forehead connected to receiver port 2
Computer: Connect the computer to the RS-232 using a USB to RS-232 converter

## Code
The supported digitisation workflow is the packaged CLI command:

```python
pylhemus gui
```

`pylhemus gui` opens a startup dialog where you enter the participant ID and choose a schema preset. The default presets are stored in `default_settings.json` under `digitisation.schema_presets`.

The GUI then:

- connects to the FASTRAK on the configured serial port
- prepares the device for digitisation
- loads the selected schema into the session controller
- writes the captured points to `output/<participant_id>_digitisation.csv` when the window closes

The default serial port is also configured in `default_settings.json`:

```json
{
	"serial_port": "COM1"
}
```

If needed, edit the schema presets in `default_settings.json` before launching the GUI, or use the schema editor from the startup dialog.

If the current working directory does not already contain `default_settings.json`, pylhemus creates a writable settings file automatically in the user config directory.

To query the FASTRAK configuration without opening the GUI, use:

```python
pylhemus read-settings --port COM1 --out plh_settings.json
```

