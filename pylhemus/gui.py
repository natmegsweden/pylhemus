from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from .digitise import FastrakConnector, DigitisationController, DigitisationMainWindow
from .digitise.pyvista_gui import LaunchDialog, setup_dark_theme
from .settings_loader import load_settings


def _parse_fastrak_hemisphere(dig_settings: dict) -> tuple[float, float, float] | None:
    hemisphere = dig_settings.get("hemisphere", [0.0, 0.0, 1.0])
    if hemisphere is None:
        return None
    if not isinstance(hemisphere, (list, tuple)) or len(hemisphere) != 3:
        raise ValueError("digitisation.hemisphere must be a 3-value list or tuple.")

    values = tuple(float(value) for value in hemisphere)
    if values == (0.0, 0.0, 0.0):
        raise ValueError("digitisation.hemisphere must not be the zero vector.")
    return values


def _open_viewer(app: QApplication, df, participant_id: str) -> int:
    from .digitise import DevModeConnector

    controller = DigitisationController(connector=DevModeConnector())
    controller.digitised_points = df.copy()
    controller.participant_id = participant_id
    controller.update_neuromag_transform(force=True)

    window = DigitisationMainWindow(controller=controller, dev_mode=False, read_only=True)
    window.show()
    return app.exec_()


def launch_gui(
    settings_path: Path | None = None,
    serial_port: str | None = None,
    output_dir: Path | None = None,
    dev_mode: bool = False,
    restore_last: bool = False,
) -> int:
    settings = load_settings()
    dig_settings = settings.get("digitisation", {})

    app = QApplication.instance() or QApplication(sys.argv)
    
    # Apply consistent dark theme across platforms
    setup_dark_theme(app)

    # Check for restore first
    autosave_data = None
    found_autosave_path = None
    if restore_last:
        import tempfile
        # Try to find any autosave file
        temp_dir = Path(tempfile.gettempdir())
        autosave_files = list(temp_dir.glob(f"digitisation_*_autosave.json"))
        if autosave_files:
            # Use the most recent one
            found_autosave_path = max(autosave_files, key=lambda p: p.stat().st_mtime)
            try:
                autosave_data = json.loads(found_autosave_path.read_text(encoding="utf-8"))
                print(f"Restoring from: {found_autosave_path}")
            except Exception as exc:
                QMessageBox.warning(None, "Restore Failed", f"Could not read autosave: {exc}")
                autosave_data = None

    # Skip LaunchDialog if restoring
    if autosave_data:
        participant_id = autosave_data.get("participant_id", "restored")
        project = autosave_data.get("project", "")
        # Use schema from autosave
        schema_items = [
            {
                "category": item["category"],
                "labels": item.get("labels", []),
                "dig_type": item.get("dig_type", "single"),
                "n_points": item.get("n_points", 0) if item.get("dig_type") == "continuous" else None,
            }
            for item in autosave_data.get("scheme", [])
        ]
    else:
        # Show LaunchDialog for new session
        launch = LaunchDialog()
        if launch.exec_() != QDialog.Accepted:
            return 0
        if launch.loaded_data is not None and launch.loaded_data_path is not None:
            return _open_viewer(app, launch.loaded_data, launch.loaded_data_path.stem)
        participant_id = launch.participant_id
        project = launch.project
        schema_items = launch.selected_schema()

    com_port = serial_port or settings.get("serial_port", "COM1")
    hemisphere = _parse_fastrak_hemisphere(dig_settings)
    configured_output_dir = output_dir or dig_settings.get("output_dir", "output")
    output_path = Path(configured_output_dir)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    if project:
        output_path = output_path / project
    output_path.mkdir(parents=True, exist_ok=True)

    connector = None
    if not dev_mode:
        try:
            connector = FastrakConnector(usb_port=com_port, hemisphere=hemisphere)
            startup_warnings = connector.prepare_for_digitisation()
            if startup_warnings:
                QMessageBox.warning(
                    None,
                    "FASTRAK Settings Failed",
                    "Connected to FASTRAK, but some startup settings were rejected or could not be verified.\n\n"
                    + "\n".join(f"- {warning}" for warning in startup_warnings),
                )
        except Exception as exc:
            QMessageBox.information(
                None,
                "FASTRAK Not Detected",
                f"Could not connect to FASTRAK on port {com_port}.\n\n"
                f"Error: {exc}\n\n"
                "Switching to DEVELOPMENT MODE with simulated hardware.",
            )
            connector = None

    if connector is None:
        from .digitise import DevModeConnector
        connector = DevModeConnector()
        dev_mode = True

    controller = DigitisationController(connector=connector)
    controller.participant_id = participant_id
    controller.project = project
    for item in schema_items:
        if item.get("dig_type") == "continuous" and "n_points" not in item:
            item["n_points"] = 60
        controller.add(**item)

    # Restore from autosave data if available
    if autosave_data and found_autosave_path:
        try:
            controller.load_session(found_autosave_path)
            # Restore transform state
            controller._auto_switched_to_transformed = autosave_data.get("auto_switched_to_transformed", False)
            # Recompute transform from loaded fiducials
            controller.update_neuromag_transform(force=True)
            # Sync indices to continue from last captured position
            controller.sync_indices_to_captured_points()
        except Exception as exc:
            QMessageBox.warning(None, "Restore Failed", f"Could not restore session: {exc}")

    window = DigitisationMainWindow(controller=controller, dev_mode=dev_mode)
    window.show()
    exit_code = app.exec_()

    # Only auto-save if user hasn't explicitly declined to save
    if not window._session_saved and len(controller.digitised_points) > 0:
        json_path = output_path / f"digitisation_sub-{participant_id}.json"
        controller.save_dig_json(json_path)
        print(f"Saved: {json_path}")

    return exit_code
