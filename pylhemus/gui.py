from __future__ import annotations

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
) -> int:
    resolved_settings_path = resolve_settings_path(settings_path)
    settings = load_settings(resolved_settings_path)
    dig_settings = settings.get("digitisation", {})

    app = QApplication.instance() or QApplication(sys.argv)

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

    try:
        connector = FastrakConnector(usb_port=com_port)
        connector.prepare_for_digitisation()
    except Exception as exc:
        try:
            QMessageBox.critical(
                None,
                "FASTRAK Connection Error",
                f"Could not initialise FASTRAK on port {com_port}.\n\n{exc}",
            )
        except Exception:
            print(f"Could not initialise FASTRAK on port {com_port}: {exc}", file=sys.stderr)
        return 2

    controller = DigitisationController(connector=connector)
    controller.participant_id = participant_id
    for item in schema_items:
        if item.get("dig_type") == "continuous" and "n_points" not in item:
            item["n_points"] = 60  # Provide a default value for n_points
        controller.add(**item)

    window = DigitisationMainWindow(controller=controller, settings_path=resolved_settings_path)
    window.show()
    exit_code = app.exec_()

    csv_path = output_path / f"{participant_id}_digitisation.csv"
    controller.save_csv(csv_path)
    print(f"Saved: {csv_path}")

    return exit_code