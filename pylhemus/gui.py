from __future__ import annotations

import json
import sys
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QDialog, QMessageBox

from .digitise import FastrakConnector, DigitisationController, DigitisationMainWindow
from .digitise.pyvista_gui import LaunchDialog
from .settings import load_settings, resolve_settings_path


def launch_gui(
    settings_path: Path | None = None,
    serial_port: str | None = None,
    output_dir: Path | None = None,
    dev_mode: bool = False,
    restore_last: bool = False,
) -> int:
    resolved_settings_path = resolve_settings_path(settings_path)
    settings = load_settings(resolved_settings_path)
    dig_settings = settings.get("digitisation", {})

    app = QApplication.instance() or QApplication(sys.argv)

    # Check for restore first
    autosave_data = None
    if restore_last:
        import tempfile
        # Try to find any autosave file
        temp_dir = Path(tempfile.gettempdir())
        autosave_files = list(temp_dir.glob(f"digitisation_*_autosave.json"))
        if autosave_files:
            # Use the most recent one
            autosave_path = max(autosave_files, key=lambda p: p.stat().st_mtime)
            try:
                autosave_data = json.loads(autosave_path.read_text(encoding="utf-8"))
                print(f"Restoring from: {autosave_path}")
            except Exception as exc:
                QMessageBox.warning(None, "Restore Failed", f"Could not read autosave: {exc}")
                autosave_data = None

    # Skip LaunchDialog if restoring
    if autosave_data:
        participant_id = autosave_data.get("participant_id", "restored")
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
        launch = LaunchDialog(settings_path=resolved_settings_path)
        if launch.exec_() != QDialog.Accepted:
            return 0
        participant_id = launch.participant_id
        schema_items = launch.selected_schema()

    com_port = serial_port or settings.get("serial_port", "COM1")
    configured_output_dir = output_dir or dig_settings.get("output_dir", "output")
    output_path = Path(configured_output_dir)
    if not output_path.is_absolute():
        output_path = Path.cwd() / output_path
    output_path.mkdir(parents=True, exist_ok=True)

    connector = None
    if not dev_mode:
        try:
            connector = FastrakConnector(usb_port=com_port)
            connector.prepare_for_digitisation()
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
    for item in schema_items:
        if item.get("dig_type") == "continuous" and "n_points" not in item:
            item["n_points"] = 60
        controller.add(**item)

    # Restore from autosave data if available
    if autosave_data:
        import tempfile
        autosave_path = Path(tempfile.gettempdir()) / f"digitisation_sub-{participant_id}_autosave.json"
        if autosave_path.exists():
            try:
                controller.load_session(autosave_path)
                # Restore transform state
                controller._auto_switched_to_transformed = autosave_data.get("auto_switched_to_transformed", False)
                # Recompute transform from loaded fiducials
                controller.update_neuromag_transform(force=True)
                # Sync indices to continue from last captured position
                controller.sync_indices_to_captured_points()
            except Exception as exc:
                QMessageBox.warning(None, "Restore Failed", f"Could not restore session: {exc}")

    window = DigitisationMainWindow(controller=controller, settings_path=resolved_settings_path, dev_mode=dev_mode)
    window.show()
    exit_code = app.exec_()

    # Only auto-save if user hasn't explicitly declined to save
    if not window._session_saved and len(controller.digitised_points) > 0:
        csv_path = output_path / f"digitisation_sub-{participant_id}.csv"
        controller.save_csv(csv_path)
        print(f"Saved: {csv_path}")

    return exit_code