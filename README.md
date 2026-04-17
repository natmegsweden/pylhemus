# pylhemus
Under development. The primary supported workflow in this repository is the FASTRAK digitisation GUI started with `pylhemus gui`. The original code is created by [Laura B Paulsen](https://github.com/laurabpaulsen/OPM_lab)


## Documentation 
TBA


## Installation
```bash
python -m pip install -e .
```

Then launch the GUI with:

```bash
pylhemus gui
```

To dump FASTRAK settings to JSON from the CLI:

```bash
pylhemus read-settings --port COM1 --out plh_settings.json
```

If you want to run it without installing the console script, use:

```bash
python -m pylhemus gui
```