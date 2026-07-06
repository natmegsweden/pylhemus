# Digitisation

This section covers the participant digitisation workflow.

## Summary

Use `pylhemus gui` to start a session, select a schema, and capture points in the GUI.

The usual capture order is:

1. Fiducials: `lpa`, `nasion`, `rpa`
2. HPI coils
3. Head-shape points

Once the three fiducials are present, `pylhemus` computes the Neuromag transform and adds transformed coordinates to the table, exported dig JSON files, and CSV exports.

## Related Pages

- [Polhemus digitisation guide](polhemus_digitisation.md)
- [Settings](../settings.md)
- [Commands](../commands.md)
- [FASTRAK command quick reference](../reference/fastrak_commands.md)
