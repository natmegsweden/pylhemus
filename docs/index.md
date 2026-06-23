# pylhemus Documentation

This directory contains the project documentation for `pylhemus`.

## Overview

`pylhemus` provides a GUI workflow for Polhemus FASTRAK digitisation. It is intended for capturing participant fiducials, HPI coils, and head-shape points, then exporting those measurements for later analysis.

## Getting Started

Install the package in editable mode:

```bash
python -m pip install -e .
```

Launch the GUI:

```bash
pylhemus gui
```

## Documentation Map

- [Commands](commands.md)
- [Settings](settings.md)
- [Digitisation overview](digitising/index.md)
- [Polhemus digitisation guide](digitising/polhemus_digitisation.md)
- [FASTRAK command quick reference](reference/fastrak_commands.md)

## Main Capabilities

- Interactive GUI for digitisation sessions
- Automatic Neuromag transform once fiducials are captured
- Autosave and restore-last workflow
- Development mode without FASTRAK hardware
- CLI utilities for reading and querying FASTRAK settings
