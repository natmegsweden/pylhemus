from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QHeaderView,
    QSlider,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QFormLayout,
    QToolButton,
    QSizePolicy,
)
from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtGui import QFont, QPalette, QColor
from pyvistaqt import QtInteractor

from .controller import DigitisationController
from ..settings import resolve_settings_path
from ..template import __all__ as available_templates


def setup_dark_theme(app: QApplication):
    """Apply consistent dark theme across platforms (macOS, Windows, Linux)."""
    # Set application style for consistency
    app.setStyle("Fusion")
    
    # Create dark palette
    dark_palette = QPalette()
    
    # Color definitions
    dark_color = QColor(45, 45, 48)       # Main background
    darker_color = QColor(30, 30, 33)     # Lighter elements
    light_color = QColor(220, 220, 220)   # Text color
    accent_color = QColor(0, 120, 212)    # Selection/highlight
    
    # Set palette colors
    dark_palette.setColor(QPalette.Window, dark_color)
    dark_palette.setColor(QPalette.WindowText, light_color)
    dark_palette.setColor(QPalette.Base, darker_color)
    dark_palette.setColor(QPalette.AlternateBase, dark_color)
    dark_palette.setColor(QPalette.ToolTipBase, accent_color)
    dark_palette.setColor(QPalette.ToolTipText, light_color)
    dark_palette.setColor(QPalette.Text, light_color)
    dark_palette.setColor(QPalette.Button, dark_color)
    dark_palette.setColor(QPalette.ButtonText, light_color)
    dark_palette.setColor(QPalette.BrightText, Qt.white)
    dark_palette.setColor(QPalette.Link, accent_color)
    dark_palette.setColor(QPalette.Highlight, accent_color)
    dark_palette.setColor(QPalette.HighlightedText, Qt.white)
    
    # Disabled state colors
    dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(128, 128, 128))
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, QColor(128, 128, 128))
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(128, 128, 128))
    
    app.setPalette(dark_palette)
    
    # Additional stylesheet for fine-tuning
    app.setStyleSheet("""
        QToolTip {
            color: #ffffff;
            background-color: #0078d4;
            border: 1px solid #ffffff;
            padding: 4px;
        }
        QComboBox {
            background-color: #2d2d30;
            color: #dcdcdc;
            border: 1px solid #3e3e42;
            padding: 4px;
        }
        QComboBox::drop-down {
            border: none;
        }
        QComboBox QAbstractItemView {
            background-color: #2d2d30;
            color: #dcdcdc;
            selection-background-color: #0078d4;
        }
        QLineEdit {
            background-color: #252526;
            color: #dcdcdc;
            border: 1px solid #3e3e42;
            padding: 4px;
        }
        QLineEdit:focus {
            border: 1px solid #0078d4;
        }
        QListWidget {
            background-color: #252526;
            color: #dcdcdc;
            border: 1px solid #3e3e42;
        }
        QListWidget::item:selected {
            background-color: #0078d4;
        }
    """)


_DEFAULT_SETTINGS_PATH = resolve_settings_path()

_DEFAULT_DIGITISATION_SETTINGS = {
    "capture_interval_ms": 100,
    "output_dir": "output",
    "category_colors": {
        "OPM": "royalblue",
        "head": "lightgray",
        "fiducials": "seagreen",
        "EEG": "orchid",
        "HPI_coils": "darkorange",
    },
    "default_schema_preset": "standard",
    "schema_presets": {
        "standard": [
            {"category": "fiducials", "labels": ["lpa", "nasion", "rpa"], "dig_type": "single"},
            {"category": "HPI_coils", "labels": ["hpi1", "hpi2", "hpi3", "hpi4"], "dig_type": "single"},
            {"category": "head", "dig_type": "continuous", "n_points": 60},
        ]
    },
}


def _merge_digitisation_settings(overrides: dict) -> dict:
    merged = json.loads(json.dumps(_DEFAULT_DIGITISATION_SETTINGS))
    merged.update({k: v for k, v in overrides.items() if k != "category_colors" and k != "schema_presets"})
    merged["category_colors"].update(overrides.get("category_colors", {}))
    merged["schema_presets"].update(overrides.get("schema_presets", {}))
    return merged


def _load_dig_settings(settings_path: Path | None = None) -> dict:
    path = settings_path or _DEFAULT_SETTINGS_PATH
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return _merge_digitisation_settings(data.get("digitisation", {}))
    return _merge_digitisation_settings({})


# ---------------------------------------------------------------------------
# Participant dialog
# ---------------------------------------------------------------------------

class ParticipantDialog(QDialog):
    """Modal dialog shown at startup to capture participant ID."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("New Digitisation Session")
        self.setFixedSize(340, 160)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Participant ID:"))
        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("e.g. sub-001")
        layout.addWidget(self.id_edit)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.id_edit.returnPressed.connect(self._on_accept)

    def _on_accept(self):
        if not self.id_edit.text().strip():
            QMessageBox.warning(self, "Required", "Participant ID cannot be empty.")
            return
        self.accept()


# ---------------------------------------------------------------------------
# Add-item sub-dialog
# ---------------------------------------------------------------------------

class _AddSchemaItemDialog(QDialog):
    def __init__(self, parent=None, existing_item=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Schema Item")
        self.setFixedSize(400, 220)
        self.item_data: dict = existing_item or {}

        form = QFormLayout(self)
        self.category_edit = QLineEdit(self.item_data.get("category", ""))
        self.category_edit.setPlaceholderText("e.g. fiducials")
        form.addRow("Category:", self.category_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["single", "continuous"])
        self.type_combo.setCurrentText(self.item_data.get("dig_type", "single"))
        form.addRow("Type:", self.type_combo)

        self.labels_edit = QLineEdit(", ".join(self.item_data.get("labels", [])) if self.item_data.get("dig_type") == "single" else str(self.item_data.get("n_points", "")))
        self.labels_edit.setPlaceholderText("label1, label2  —or—  number of points (continuous)")
        form.addRow("Labels / n_points:", self.labels_edit)

        self.template_combo = QComboBox()
        self.template_combo.addItem("None")
        self.template_combo.addItems(available_templates)  # Dynamically populate from __init__.pyi
        self.template_combo.setCurrentText(self.item_data.get("template", "None"))
        form.addRow("Template:", self.template_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_accept(self):
        category = self.category_edit.text().strip()
        if not category:
            QMessageBox.warning(self, "Required", "Category is required.")
            return
        dig_type = self.type_combo.currentText()
        raw = self.labels_edit.text().strip()
        template = self.template_combo.currentText()
        if dig_type == "continuous":
            try:
                n = int(raw)
            except ValueError:
                n = 60
            self.item_data = {"category": category, "dig_type": "continuous", "n_points": n}
        else:
            labels = [lbl.strip() for lbl in raw.split(",") if lbl.strip()]
            self.item_data = {"category": category, "dig_type": "single", "labels": labels}
        if template != "None":
            self.item_data["template"] = template
        self.accept()


# ---------------------------------------------------------------------------
# Schema editor dialog
# ---------------------------------------------------------------------------

class SchemaEditorDialog(QDialog):
    """Settings window (⚙) to define, order, and save schema presets."""

    def __init__(self, settings_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.settings_path = settings_path or _DEFAULT_SETTINGS_PATH
        self.setWindowTitle("Schema Settings ⚙")
        self.setMinimumSize(520, 480)

        if self.settings_path.exists():
            self._raw_settings = json.loads(self.settings_path.read_text(encoding="utf-8"))
        else:
            self._raw_settings = {"digitisation": _merge_digitisation_settings({})}
        dig = self._raw_settings.setdefault("digitisation", {})
        dig = _merge_digitisation_settings(dig)
        self._raw_settings["digitisation"] = dig
        self._presets: dict = dig.setdefault("schema_presets", {})

        layout = QVBoxLayout(self)

        # --- Preset dropdown ---
        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        self._populate_combo()
        preset_row.addWidget(self.preset_combo, stretch=1)
        self.del_preset_btn = QPushButton("Delete Preset")
        preset_row.addWidget(self.del_preset_btn)
        layout.addLayout(preset_row)

        # --- Item list (drag to reorder) ---
        layout.addWidget(QLabel("Items — drag to reorder:"))
        self.item_list = QListWidget()
        self.item_list.setDragDropMode(QListWidget.InternalMove)
        self.item_list.setMinimumHeight(180)
        layout.addWidget(self.item_list, stretch=1)

        item_btns = QHBoxLayout()
        self.add_item_btn = QPushButton("＋ Add Item")
        self.edit_item_btn = QPushButton("✎ Edit Item")
        self.remove_item_btn = QPushButton("－ Remove Selected")
        item_btns.addWidget(self.add_item_btn)
        item_btns.addWidget(self.edit_item_btn)
        item_btns.addWidget(self.remove_item_btn)
        item_btns.addStretch(1)
        layout.addLayout(item_btns)

        # --- Save as preset ---
        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("Save current list as:"))
        self.save_name_edit = QLineEdit()
        save_row.addWidget(self.save_name_edit, stretch=1)
        self.save_preset_btn = QPushButton("Save Preset")
        save_row.addWidget(self.save_preset_btn)
        layout.addLayout(save_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.preset_combo.currentTextChanged.connect(self._load_preset_into_list)
        self.add_item_btn.clicked.connect(self._add_item)
        self.edit_item_btn.clicked.connect(self._edit_item)
        self.remove_item_btn.clicked.connect(self._remove_selected)
        self.save_preset_btn.clicked.connect(self._save_preset)
        self.del_preset_btn.clicked.connect(self._delete_preset)

        self._load_preset_into_list()

    def _populate_combo(self):
        current = self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for name in self._presets:
            self.preset_combo.addItem(name)
        default = self._raw_settings.get("digitisation", {}).get("default_schema_preset", "")
        target = current or default
        idx = self.preset_combo.findText(target)
        self.preset_combo.setCurrentIndex(max(idx, 0))
        self.preset_combo.blockSignals(False)

    def _item_text(self, item: dict) -> str:
        category = item.get("category", "?")
        dig_type = item.get("dig_type", "single")
        if dig_type == "continuous":
            n = item.get("n_points", "∞")
            return f"{category}  [continuous, n≥{n}]"
        labels = item.get("labels", [])
        return f"{category}  [single: {', '.join(labels)}]"

    def _load_preset_into_list(self):
        name = self.preset_combo.currentText()
        items = list(self._presets.get(name, []))
        self.item_list.clear()
        for item in items:
            list_item = QListWidgetItem(self._item_text(item))
            list_item.setData(Qt.UserRole, dict(item))
            self.item_list.addItem(list_item)
        self.save_name_edit.setText(name)

    def _add_item(self):
        dlg = _AddSchemaItemDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            list_item = QListWidgetItem(self._item_text(dlg.item_data))
            list_item.setData(Qt.UserRole, dlg.item_data)
            self.item_list.addItem(list_item)

    def _edit_item(self):
        current_row = self.item_list.currentRow()
        if current_row < 0:
            QMessageBox.warning(self, "Select Item", "Please select an item to edit.")
            return

        list_item = self.item_list.currentItem()
        existing_data = list_item.data(Qt.UserRole)
        dlg = _AddSchemaItemDialog(self, existing_item=existing_data)
        if dlg.exec_() == QDialog.Accepted:
            updated_item = dlg.item_data
            list_item.setText(self._item_text(updated_item))
            list_item.setData(Qt.UserRole, updated_item)

    def _remove_selected(self):
        row = self.item_list.currentRow()
        if row >= 0:
            self.item_list.takeItem(row)

    def _current_list_items(self) -> list[dict]:
        return [self.item_list.item(i).data(Qt.UserRole) for i in range(self.item_list.count())]

    def _save_preset(self):
        name = self.save_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Enter a preset name.")
            return
        self._presets[name] = self._current_list_items()
        self._persist()
        self._populate_combo()
        self.preset_combo.setCurrentText(name)
        QMessageBox.information(self, "Saved", f"Preset '{name}' saved.")

    def _delete_preset(self):
        name = self.preset_combo.currentText()
        if not name:
            return
        reply = QMessageBox.question(self, "Delete Preset", f"Delete preset '{name}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._presets.pop(name, None)
            self._persist()
            self._populate_combo()
            self._load_preset_into_list()

    def _persist(self):
        self._raw_settings.setdefault("digitisation", {})["schema_presets"] = self._presets
        self.settings_path.write_text(
            json.dumps(self._raw_settings, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _on_accept(self):
        self.accept()

    def selected_schema(self) -> list[dict]:
        return self._current_list_items()


# ---------------------------------------------------------------------------
# Launch dialog: participant ID + schema selection
# ---------------------------------------------------------------------------

class LaunchDialog(QDialog):
    """Startup dialog: enter participant ID and select schema preset."""

    def __init__(self, settings_path: Path | None = None, parent=None):
        super().__init__(parent)
        self.settings_path = settings_path or _DEFAULT_SETTINGS_PATH
        self.setWindowTitle("OPM Digitisation — New Session")
        self.setFixedSize(420, 200)

        dig = _load_dig_settings(self.settings_path)
        self._presets: dict = dig.get("schema_presets", {})
        self._default_preset: str = dig.get("default_schema_preset", "")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.id_edit = QLineEdit()
        self.id_edit.setPlaceholderText("e.g. sub-001")
        form.addRow("Participant ID:", self.id_edit)

        schema_row = QHBoxLayout()
        self.schema_combo = QComboBox()
        for name in self._presets:
            self.schema_combo.addItem(name)
        idx = self.schema_combo.findText(self._default_preset)
        if idx >= 0:
            self.schema_combo.setCurrentIndex(idx)
        schema_row.addWidget(self.schema_combo, stretch=1)

        manage_btn = QToolButton()
        manage_btn.setText("⚙")
        manage_btn.setToolTip("Manage schema presets")
        manage_btn.clicked.connect(self._open_schema_editor)
        schema_row.addWidget(manage_btn)
        form.addRow("Schema:", schema_row)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.id_edit.returnPressed.connect(self._on_accept)

    def _on_accept(self):
        if not self.id_edit.text().strip():
            QMessageBox.warning(self, "Required", "Participant ID cannot be empty.")
            return
        self.accept()

    @property
    def participant_id(self) -> str:
        return self.id_edit.text().strip()

    def selected_schema(self) -> list[dict]:
        name = self.schema_combo.currentText()
        schema = list(self._presets.get(name, []))
        if not self._validate_schema(schema):
            return []
        return schema

    def _validate_schema(self, schema: list[dict]) -> bool:
        """Ensure all single-point schemas have labels or templates populated."""
        for item in schema:
            if item["dig_type"] == "single":
                labels = item.get("labels", [])
                template = item.get("template", None)
                if not labels and not template:
                    QMessageBox.warning(self, "Validation Error", f"Category '{item['category']}' requires labels or a template.")
                    return False
        return True

    def _open_schema_editor(self):
        dlg = SchemaEditorDialog(settings_path=self.settings_path, parent=self)
        dlg.exec_()


# ---------------------------------------------------------------------------
# Main digitisation window
# ---------------------------------------------------------------------------

class DigitisationMainWindow(QMainWindow):
    def __init__(self, controller: DigitisationController, settings_path: Path | None = None, dev_mode: bool = False):
        super().__init__()
        self.controller = controller
        self._settings_path = settings_path or _DEFAULT_SETTINGS_PATH
        self._updating_table = False
        self._camera_initialized = False
        self._zoom_factor = 1.0
        self._dev_mode = dev_mode
        self._show_transformed = False
        self._selected_row = -1
        self._session_saved = False

        dig = _load_dig_settings(self._settings_path)
        interval = int(dig.get("capture_interval_ms", 100))
        self._category_colors: dict = dig.get("category_colors", {})

        self._auto_capture_timer = QTimer(self)
        self._auto_capture_timer.setInterval(interval)
        self._auto_capture_timer.timeout.connect(self.on_auto_capture_tick)

        pid = getattr(controller, "participant_id", "") or ""
        title = f"OPM Digitisation — subject: {pid}" if pid else "OPM Digitisation GUI"
        self.setWindowTitle(title)
        self.resize(1400, 850)

        # Auto-save timer (every 5 seconds)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(5000)  # 5 seconds
        self._autosave_timer.timeout.connect(self._auto_save_session)
        self._autosave_timer.start()

        self._build_ui()
        # Only start fresh if no points exist (not restored session)
        if len(self.controller.digitised_points) == 0:
            self.controller.start()
        self.refresh_ui()
        if not self.controller.is_finished and not self._dev_mode:
            self._auto_capture_timer.start()


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout()
        central.setLayout(root)

        if self._dev_mode:
            banner = QLabel("DEV MODE - Simulated FASTRAK Hardware (No Physical Device)")
            banner.setStyleSheet("background-color: #ff4444; color: white; padding: 10px; font-weight: bold; font-size: 14px;")
            banner.setAlignment(Qt.AlignCenter)
            root.addWidget(banner)

        # Main horizontal layout: left panel, plotter, right panel
        main_row = QHBoxLayout()
        root.addLayout(main_row, stretch=4)

        # LEFT PANEL: Visual controls (zoom + transform)
        left_panel = QVBoxLayout()
        left_panel.setSpacing(10)
        left_panel.setContentsMargins(10, 10, 10, 10)
        
        self.zoom_slider = QSlider(Qt.Vertical)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setValue(100)
        self.zoom_slider.setFixedWidth(40)
        self.zoom_slider.setMinimumHeight(200)
        
        self.zoom_value_label = QLabel("100%")
        self.zoom_value_label.setAlignment(Qt.AlignCenter)
        
        self.transform_toggle_btn = QPushButton("Trans\nOff")
        self.transform_toggle_btn.setEnabled(False)
        self.transform_toggle_btn.setFixedSize(60, 60)
        self._transform_off_style = """
            QPushButton {
                background-color: #cc3333;
                color: white;
                border: 3px solid white;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #dd4444;
            }
            QPushButton:pressed {
                background-color: #aa2222;
            }
            QPushButton:disabled {
                background-color: #222;
                color: #888;
                border: 3px solid #888;
            }
        """
        self._transform_on_style = """
            QPushButton {
                background-color: #33cc33;
                color: white;
                border: 3px solid white;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #44dd44;
            }
            QPushButton:pressed {
                background-color: #22aa22;
            }
            QPushButton:disabled {
                background-color: #222;
                color: #888;
                border: 3px solid #888;
            }
        """
        self.transform_toggle_btn.setStyleSheet(self._transform_off_style)
        
        left_panel.addStretch(1)
        left_panel.addWidget(QLabel("Zoom"))
        left_panel.addWidget(self.zoom_slider)
        left_panel.addWidget(self.zoom_value_label)
        left_panel.addSpacing(20)
        left_panel.addWidget(self.transform_toggle_btn)
        left_panel.addStretch(1)
        
        main_row.addLayout(left_panel)

        # CENTER: 3D Plotter
        self.plotter = QtInteractor(self)
        self.plotter.set_background("#101418")

        import pyvista as pv
        pv.global_theme.axes.x_color = "white"
        pv.global_theme.axes.y_color = "white"
        pv.global_theme.axes.z_color = "white"
        pv.global_theme.font.color = "white"

        main_row.addWidget(self.plotter.interactor, stretch=4)

        # RIGHT PANEL: Labels + Buttons
        right_panel = QVBoxLayout()
        right_panel.setSpacing(10)
        right_panel.setContentsMargins(10, 10, 10, 10)
        
        # Labels with thin border
        label_style = "border: 1px solid #666; padding: 4px; border-radius: 2px; color: white;"
        
        self.category_label = QLabel("Category: -")
        self.category_label.setStyleSheet(label_style)
        self.target_label = QLabel("Target: -")
        self.target_label.setStyleSheet(label_style)
        self.progress_label = QLabel("Progress: -")
        self.progress_label.setStyleSheet(label_style)
        
        right_panel.addWidget(self.category_label)
        right_panel.addWidget(self.target_label)
        right_panel.addWidget(self.progress_label)
        right_panel.addSpacing(20)
        
        # Square buttons (80x80)
        button_style = """
            QPushButton {
                background-color: #333;
                color: white;
                border: 3px solid white;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #222;
            }
            QPushButton:disabled {
                background-color: #222;
                color: #888;
                border: 3px solid #888;
            }
        """
        
        # Button row 1: Undo | Restart
        btn_row1 = QHBoxLayout()
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setFixedSize(80, 80)
        self.undo_btn.setStyleSheet(button_style)
        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setFixedSize(80, 80)
        self.restart_btn.setStyleSheet(button_style)
        btn_row1.addWidget(self.undo_btn)
        btn_row1.addWidget(self.restart_btn)
        right_panel.addLayout(btn_row1)
        
        # Button row 2: Save CSV | Finish
        btn_row2 = QHBoxLayout()
        self.save_csv_btn = QPushButton("Save\nCSV")
        self.save_csv_btn.setFixedSize(80, 80)
        self.save_csv_btn.setStyleSheet(button_style)
        self.finish_btn = QPushButton("Finish")
        self.finish_btn.setFixedSize(80, 80)
        self.finish_btn.setStyleSheet(button_style)
        btn_row2.addWidget(self.save_csv_btn)
        btn_row2.addWidget(self.finish_btn)
        right_panel.addLayout(btn_row2)
        
        # Delete button (for continuous points) - RED - centered
        delete_row = QHBoxLayout()
        delete_row.addStretch(1)
        self.delete_btn = QPushButton("Delete\nPoint")
        self.delete_btn.setFixedSize(80, 80)
        self.delete_btn.setStyleSheet("""
            QPushButton {
                background-color: #cc3333;
                color: white;
                border: 3px solid white;
                border-radius: 4px;
                font-weight: bold;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #dd4444;
            }
            QPushButton:pressed {
                background-color: #aa2222;
            }
            QPushButton:disabled {
                background-color: #222;
                color: #888;
                border: 3px solid #888;
            }
        """)
        self.delete_btn.setEnabled(False)
        delete_row.addWidget(self.delete_btn)
        delete_row.addStretch(1)
        right_panel.addLayout(delete_row)
        
        # Dev mode buttons
        if self._dev_mode:
            right_panel.addSpacing(10)
            dev_row = QHBoxLayout()
            self.dev_add_btn = QPushButton("Add\nPoint")
            self.dev_add_btn.setFixedSize(80, 80)
            self.dev_add_btn.setStyleSheet(button_style)
            self.dev_faulty_btn = QPushButton("Add\nFaulty")
            self.dev_faulty_btn.setFixedSize(80, 80)
            self.dev_faulty_btn.setStyleSheet(button_style)
            dev_row.addWidget(self.dev_add_btn)
            dev_row.addWidget(self.dev_faulty_btn)
            right_panel.addLayout(dev_row)
        
        right_panel.addStretch(1)
        main_row.addLayout(right_panel)

        # Table (non-editable)
        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels(["participant_id", "category", "label", "x", "y", "z", "x'", "y'", "z'"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        root.addWidget(self.table, stretch=2)

        # Connect signals
        self.undo_btn.clicked.connect(self.on_undo)
        self.restart_btn.clicked.connect(self.on_restart)
        self.save_csv_btn.clicked.connect(self.on_save_csv)
        self.finish_btn.clicked.connect(self.close)
        self.delete_btn.clicked.connect(self.on_delete_point)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        self.transform_toggle_btn.clicked.connect(self.on_toggle_transform_view)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)

        if self._dev_mode:
            self.dev_add_btn.clicked.connect(self.on_dev_add_point)
            self.dev_faulty_btn.clicked.connect(self.on_dev_add_faulty_point)

        # Enable point picking in plotter
        self.plotter.enable_point_picking(callback=self.on_plot_point_picked, show_message=False)

    def _open_settings(self):
        dlg = SchemaEditorDialog(settings_path=self._settings_path, parent=self)
        dlg.exec_()


    def refresh_ui(self):
        category, target, progress = self.controller.status_text()
        self.category_label.setText(f"Category: {category}")
        self.target_label.setText(f"Target: {target}")
        self.progress_label.setText(f"Progress: {progress}")

        self._render_scene(highlight_row=self._selected_row)
        self._refresh_table()
        self._update_transform_ui()

    def _update_transform_ui(self):
        has_transform = self.controller.has_valid_neuromag_transform()
        self.transform_toggle_btn.setEnabled(has_transform)

        if has_transform:
            if self._show_transformed:
                self.transform_toggle_btn.setText("Trans\nOn")
                self.transform_toggle_btn.setStyleSheet(self._transform_on_style)
            else:
                self.transform_toggle_btn.setText("Trans\nOff")
                self.transform_toggle_btn.setStyleSheet(self._transform_off_style)
        else:
            self.transform_toggle_btn.setText("Trans\nN/A")
            self.transform_toggle_btn.setStyleSheet(self._transform_off_style)

        if has_transform and not self._show_transformed and not self.controller._auto_switched_to_transformed:
            df = self.controller.digitised_points
            fiducials = df[df["category"] == "fiducials"]
            if len(fiducials) >= 3:
                lpa = fiducials[fiducials["label"] == "lpa"]
                nas = fiducials[fiducials["label"] == "nasion"]
                rpa = fiducials[fiducials["label"] == "rpa"]
                if len(lpa) >= 1 and len(nas) >= 1 and len(rpa) >= 1:
                    self._show_transformed = True
                    self.controller._auto_switched_to_transformed = True

    def on_toggle_transform_view(self):
        if self.controller.has_valid_neuromag_transform():
            self._show_transformed = not self._show_transformed
            self.refresh_ui()

    def _render_scene(self, highlight_row=-1):
        self.plotter.clear()
        self.plotter.set_background("#101418")

        scene_points = []

        df = self.controller.digitised_points
        if not df.empty:
            for category in sorted(df["category"].unique()):
                subset = df[df["category"] == category]
                if self._show_transformed and self.controller.has_valid_neuromag_transform():
                    points_list = []
                    for _, row in subset.iterrows():
                        transformed = self.controller.apply_neuromag_transform((row["x"], row["y"], row["z"]))
                        if transformed is not None:
                            points_list.append(transformed)
                    points = np.array(points_list) if points_list else np.array([]).reshape(0, 3)
                else:
                    points = subset[["x", "y", "z"]].astype(float).to_numpy()
                
                color = self._category_colors.get(category, "white")
                
                # Check if we need to highlight a specific point in this category
                highlight_indices = []
                if highlight_row >= 0 and highlight_row < len(df):
                    row_data = df.iloc[highlight_row]
                    if row_data["category"] == category:
                        # Find the index within this category's points
                        category_rows = subset.index.tolist()
                        if highlight_row in category_rows:
                            highlight_indices.append(category_rows.index(highlight_row))
                
                if len(points) > 0:
                    scene_points.append(points)
                    
                    if highlight_indices:
                        # Split points into normal and highlighted
                        normal_mask = np.ones(len(points), dtype=bool)
                        normal_mask[highlight_indices] = False
                        
                        # Render normal points
                        if np.any(normal_mask):
                            normal_points = points[normal_mask]
                            self.plotter.add_points(normal_points, color=color, point_size=10, render_points_as_spheres=True)
                        
                        # Render highlighted points (larger, yellow)
                        highlighted_points = points[highlight_indices]
                        self.plotter.add_points(highlighted_points, color="yellow", point_size=20, render_points_as_spheres=True)
                    else:
                        # No highlight, render all normally
                        self.plotter.add_points(points, color=color, point_size=10, render_points_as_spheres=True)

        item = self.controller.current_item
        if item is not None:
            if isinstance(item.template, str):
                try:
                    item.template = globals()[item.template]()
                except KeyError:
                    QMessageBox.critical(self, "Template Error", f"Template '{item.template}' not found.")
                    return

            if item.template is not None:
                template_points = np.asarray(item.template.get_chs_pos())
                if template_points.size > 0:
                    scene_points.append(template_points)
                    self.plotter.add_points(
                        template_points,
                        color="gray",
                        point_size=6,
                        opacity=0.35,
                        render_points_as_spheres=True,
                    )

                if self.controller.current_label is not None:
                    focus = item.template.get_chs_pos([self.controller.current_label])
                    if len(focus) > 0:
                        scene_points.append(np.asarray(focus))
                        self.plotter.add_points(
                            np.asarray(focus),
                            color="red",
                            point_size=20,
                            render_points_as_spheres=True,
                        )

        self.plotter.show_axes()
        self._fit_camera(scene_points)

    def _fit_camera(self, scene_points: list[np.ndarray]):
        if not scene_points:
            if not self._camera_initialized:
                self.plotter.reset_camera()
                self._camera_initialized = True
            return

        points = np.vstack([arr for arr in scene_points if arr.size > 0])
        center = points.mean(axis=0)
        radius = np.max(np.linalg.norm(points - center, axis=1))
        if radius <= 1e-9:
            radius = 1.0

        camera = self.plotter.camera
        view_angle = float(getattr(camera, "view_angle", 30.0))
        view_angle = min(max(view_angle, 10.0), 120.0)

        if self._camera_initialized:
            cam_pos = np.asarray(camera.position, dtype=float)
            focal = np.asarray(camera.focal_point, dtype=float)
            direction = cam_pos - focal
            norm = np.linalg.norm(direction)
            if norm <= 1e-9:
                direction = np.array([1.0, 1.0, 1.0], dtype=float)
                direction /= np.linalg.norm(direction)
            else:
                direction /= norm
        else:
            direction = np.array([1.0, 1.0, 1.0], dtype=float)
            direction /= np.linalg.norm(direction)

        fit_distance = (radius * 1.35) / np.tan(np.deg2rad(view_angle / 2.0))
        zoomed_distance = fit_distance / max(self._zoom_factor, 0.1)
        new_position = center + direction * zoomed_distance

        camera.focal_point = tuple(center.tolist())
        camera.position = tuple(new_position.tolist())
        self._camera_initialized = True

    def on_zoom_changed(self, slider_value: int):
        self._zoom_factor = float(slider_value) / 100.0
        self.zoom_value_label.setText(f"Zoom: {slider_value}%")
        self._render_scene()

    def _refresh_table(self):
        self._updating_table = True
        try:
            df = self.controller.digitised_points
            pid = getattr(self.controller, "participant_id", "")
            self.table.setRowCount(len(df))

            for row_idx, row in df.reset_index(drop=True).iterrows():
                x, y, z = float(row["x"]), float(row["y"]), float(row["z"])

                if self._show_transformed and self.controller.has_valid_neuromag_transform():
                    transformed = self.controller.apply_neuromag_transform((x, y, z))
                    if transformed:
                        tx, ty, tz = transformed
                        orig_x, orig_y, orig_z = x, y, z
                    else:
                        tx, ty, tz = x, y, z
                        orig_x, orig_y, orig_z = "--", "--", "--"
                else:
                    orig_x, orig_y, orig_z = x, y, z
                    if self.controller.has_valid_neuromag_transform():
                        transformed = self.controller.apply_neuromag_transform((x, y, z))
                        if transformed:
                            tx, ty, tz = transformed
                        else:
                            tx, ty, tz = "--", "--", "--"
                    else:
                        tx, ty, tz = "--", "--", "--"

                self.table.setItem(row_idx, 0, QTableWidgetItem(str(pid)))
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(row["category"])))
                self.table.setItem(row_idx, 2, QTableWidgetItem(str(row["label"])))
                self.table.setItem(row_idx, 3, QTableWidgetItem(f"{orig_x:.6f}" if isinstance(orig_x, float) else str(orig_x)))
                self.table.setItem(row_idx, 4, QTableWidgetItem(f"{orig_y:.6f}" if isinstance(orig_y, float) else str(orig_y)))
                self.table.setItem(row_idx, 5, QTableWidgetItem(f"{orig_z:.6f}" if isinstance(orig_z, float) else str(orig_z)))
                self.table.setItem(row_idx, 6, QTableWidgetItem(f"{tx:.6f}" if isinstance(tx, float) else str(tx)))
                self.table.setItem(row_idx, 7, QTableWidgetItem(f"{ty:.6f}" if isinstance(ty, float) else str(ty)))
                self.table.setItem(row_idx, 8, QTableWidgetItem(f"{tz:.6f}" if isinstance(tz, float) else str(tz)))
        finally:
            self._updating_table = False

    def on_auto_capture_tick(self):
        if self.controller.is_finished:
            self._auto_capture_timer.stop()
            return

        try:
            position = self.controller.capture_from_connector()
        except Exception:
            # Ignore transient connector read errors and try again on next tick.
            return

        if position is None:
            # Check if this was a rejected point (too far)
            if self.controller.was_last_capture_rejected():
                self._show_faulty_warning()
            else:
                self.progress_label.setText("Progress: waiting for FASTRAK data...")
            return

        self.refresh_ui()
        if self.controller.is_finished:
            self._auto_capture_timer.stop()

    def _show_faulty_warning(self):
        """Show temporary warning banner for rejected/faulty points."""
        if hasattr(self, "_faulty_warning_label"):
            self._faulty_warning_label.hide()
        else:
            self._faulty_warning_label = QLabel("Faulty point rejected (>30cm)")
            self._faulty_warning_label.setStyleSheet(
                "background-color: #ff8800; color: white; padding: 5px; font-weight: bold; font-size: 12px;"
            )
            self.centralWidget().layout().insertWidget(0, self._faulty_warning_label)
        self._faulty_warning_label.show()
        QTimer.singleShot(1000, self._faulty_warning_label.hide)

    def on_undo(self):
        self.controller.undo()
        self.refresh_ui()
        if not self.controller.is_finished and not self._dev_mode and not self._auto_capture_timer.isActive():
            self._auto_capture_timer.start()

    def on_next(self):
        self.controller.next_target()
        self.refresh_ui()

    def on_save_csv(self):
        pid = getattr(self.controller, "participant_id", "") or "digitisation"
        default_name = f"digitisation_sub-{pid}.csv"
        dig = _load_dig_settings(self._settings_path)
        output_dir = str(Path(dig.get("output_dir", "output")).resolve())
        path, _ = QFileDialog.getSaveFileName(self, "Save digitisation CSV",
                                              str(Path(output_dir) / default_name), "CSV (*.csv)")
        if not path:
            return
        self.controller.save_csv(Path(path))
        self._session_saved = True

    def on_save_session(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save session", "", "JSON (*.json)")
        if not path:
            return
        self.controller.save_session(Path(path))
        self._session_saved = True

    def on_load_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load session", "", "JSON (*.json)")
        if not path:
            return

        try:
            self.controller.load_session(Path(path))
            self.refresh_ui()
            if not self.controller.is_finished and not self._dev_mode and not self._auto_capture_timer.isActive():
                self._auto_capture_timer.start()
        except Exception as exc:
            QMessageBox.critical(self, "Load session failed", str(exc))

    def _auto_save_session(self):
        """Auto-save session every 5 seconds to temp file."""
        if len(self.controller.digitised_points) == 0:
            return
        
        import tempfile
        import os
        
        # Use temp directory for auto-save
        temp_dir = tempfile.gettempdir()
        pid = getattr(self.controller, "participant_id", "") or "pylhemus"
        autosave_path = Path(temp_dir) / f"digitisation_sub-{pid}_autosave.json"
        try:
            self.controller.save_session_with_transform(autosave_path)
        except Exception:
            pass  # Silent fail for auto-save

    def on_table_item_changed(self, _item):
        if self._updating_table:
            return

        row = self.table.currentRow()
        if row < 0:
            return

        try:
            category = self.table.item(row, 1).text()
            label = self.table.item(row, 2).text()
            x = float(self.table.item(row, 3).text())
            y = float(self.table.item(row, 4).text())
            z = float(self.table.item(row, 5).text())
            self.controller.update_point(row, category, label, x, y, z)
            self.refresh_ui()
        except Exception as exc:
            QMessageBox.warning(self, "Invalid table edit", str(exc))

    def closeEvent(self, event):
        if self._auto_capture_timer.isActive():
            self._auto_capture_timer.stop()
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()

        if not self._session_saved and len(self.controller.digitised_points) > 0:
            reply = QMessageBox.question(
                self, "Save Digitisation?",
                "You have unsaved data. Save before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Yes:
                self.on_save_csv()
                self._session_saved = True
            elif reply == QMessageBox.No:
                self._session_saved = True  # Mark as "handled" so no auto-save
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return

        super().closeEvent(event)

    def on_restart(self):
        reply = QMessageBox.question(
            self, "Restart Session?",
            "All unsaved data will be lost. Are you sure?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.controller.digitised_points = pd.DataFrame(columns=["category", "label", "x", "y", "z"])
            self.controller.current_scheme_idx = 0
            self.controller.current_label_idx = 0
            self.controller._neuromag_transform = None
            self.controller._transform_valid = False
            self.controller._auto_switched_to_transformed = False
            self._show_transformed = False
            self._selected_row = -1
            self._session_saved = False
            self.controller.start()
            self.refresh_ui()

    def on_delete_point(self):
        if self._selected_row < 0:
            return
        
        row_idx = self._selected_row
        df = self.controller.digitised_points
        if row_idx >= len(df):
            return
        
        category = df.iloc[row_idx]["category"]
        dig_type = None
        for item in self.controller.scheme:
            if item.category == category:
                dig_type = item.dig_type
                break
        
        if dig_type != "continuous":
            QMessageBox.information(self, "Cannot Delete", "Only continuous points can be deleted.")
            return
        
        # Delete immediately without confirmation
        self.controller.digitised_points = df.drop(df.index[row_idx]).reset_index(drop=True)
        self.controller._auto_switched_to_transformed = False
        self.controller.update_neuromag_transform(force=True)
        self._selected_row = -1
        self.delete_btn.setEnabled(False)
        self.refresh_ui()

    def on_dev_add_point(self):
        if self.controller.is_finished:
            QMessageBox.information(self, "Digitisation Complete", "All schema items have been digitised.")
            return

        connector = self.controller.connector
        if hasattr(connector, "inject_point"):
            connector.inject_point(faulty=False)
            try:
                position = self.controller.capture_from_connector()
                if position is not None:
                    self.refresh_ui()
            except Exception as exc:
                QMessageBox.warning(self, "Capture Error", str(exc))
        else:
            QMessageBox.warning(self, "Dev Mode Error", "Connector does not support dev mode point injection.")

    def on_dev_add_faulty_point(self):
        if self.controller.is_finished:
            QMessageBox.information(self, "Digitisation Complete", "All schema items have been digitised.")
            return

        connector = self.controller.connector
        if hasattr(connector, "inject_point"):
            connector.inject_point(faulty=True)
            try:
                position = self.controller.capture_from_connector()
                if position is None:
                    self._show_faulty_warning()
                self.refresh_ui()
            except Exception as exc:
                QMessageBox.warning(self, "Capture Error", str(exc))
        else:
            QMessageBox.warning(self, "Dev Mode Error", "Connector does not support dev mode point injection.")

    def on_table_selection_changed(self):
        selected = self.table.selectedItems()
        if selected:
            self._selected_row = selected[0].row()
            self._highlight_point_in_plot(self._selected_row)
            
            # Enable delete button only for continuous points
            df = self.controller.digitised_points
            if self._selected_row < len(df):
                category = df.iloc[self._selected_row]["category"]
                for item in self.controller.scheme:
                    if item.category == category:
                        self.delete_btn.setEnabled(item.dig_type == "continuous")
                        break
            else:
                self.delete_btn.setEnabled(False)
        else:
            self._selected_row = -1
            self.delete_btn.setEnabled(False)

    def on_plot_point_picked(self, point):
        if point is None or len(self.controller.digitised_points) == 0:
            return
        
        # Find closest point
        df = self.controller.digitised_points
        coords = df[["x", "y", "z"]].values
        distances = np.linalg.norm(coords - point, axis=1)
        closest_idx = np.argmin(distances)
        
        if distances[closest_idx] < 10:  # Within 10cm threshold
            self.table.selectRow(closest_idx)
            self._selected_row = closest_idx

    def _highlight_point_in_plot(self, row_idx):
        self._render_scene(highlight_row=row_idx)
