from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QMainWindow,
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QColorDialog,
    QFileDialog,
    QTableWidget,
    QTableWidgetItem,
    QMessageBox,
    QGroupBox,
    QHeaderView,
    QSlider,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QListWidget,
    QListWidgetItem,
    QLineEdit,
    QFormLayout,
    QPlainTextEdit,
    QScrollArea,
    QSizePolicy,
    QDoubleSpinBox,
    QSpinBox,
    QTabWidget,
    QToolButton,
)
from PyQt5.QtCore import QTimer, Qt, QUrl
from PyQt5.QtGui import QFont, QPalette, QColor
from PyQt5.QtMultimedia import QSoundEffect
from pyvistaqt import QtInteractor

from .controller import DigitisationController
from ..read_data import read_file
from ..settings_loader import load_settings, load_user_effective_settings
from ..template.registry import list_templates, create_template


# Minimum button height for comfortable touch-screen use.
DIALOG_BTN_HEIGHT = 44


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


def _load_dig_settings() -> dict:
    settings = load_settings()
    return settings.get("digitisation", {})


def _resolve_sound_path(sound_path: str) -> Path | None:
    candidate = Path(sound_path)
    if candidate.is_absolute():
        return candidate if candidate.exists() else None

    search_roots = [
        Path(__file__).resolve().parents[1],
        Path.cwd(),
    ]

    for root in search_roots:
        resolved = root / candidate
        if resolved.exists():
            return resolved
    return None


class _PointSoundManager:
    def __init__(self, parent, mapping: dict[str, str] | None = None):
        self._parent = parent
        self._mapping = mapping or {}
        self._effects: dict[str, QSoundEffect] = {}

    def _ensure_loaded(self, event_name: str):
        if event_name in self._effects:
            return

        sound_path = self._mapping.get(event_name)
        if not sound_path:
            return

        try:
            resolved = _resolve_sound_path(str(sound_path))
            if resolved is None:
                return
            effect = QSoundEffect(self._parent)
            effect.setSource(QUrl.fromLocalFile(str(resolved)))
            effect.setLoopCount(1)
            effect.setVolume(0.8)
            self._effects[event_name] = effect
        except Exception:
            # Silently ignore sound loading errors
            pass

    def play(self, event_name: str):
        self._ensure_loaded(event_name)
        effect = self._effects.get(event_name)
        if effect is None:
            return
        try:
            effect.play()
        except Exception:
            # Silently ignore sound playback errors so they don't break UI
            pass

    def play_point_sound(self, dig_type: str):
        try:
            self.play(dig_type)
        except Exception:
            # Silently ignore sound errors so they don't break button handlers
            pass

    def play_faulty_sound(self):
        try:
            self.play("faulty")
        except Exception:
            # Silently ignore sound errors so they don't break button handlers
            pass


# ---------------------------------------------------------------------------
# Add-item sub-dialog
# ---------------------------------------------------------------------------

class _AddSchemaItemDialog(QDialog):
    def __init__(self, parent=None, existing_item=None):
        super().__init__(parent)
        self.setWindowTitle("Add/Edit Schema Item")
        self.setFixedSize(430, 300)
        self.item_data: dict = existing_item or {}
        self._custom_labels_dirty = (
            self.item_data.get("template") == "Custom"
            and bool(self.item_data.get("labels", []))
        )

        form = QFormLayout(self)
        self.category_edit = QLineEdit(self.item_data.get("category", ""))
        self.category_edit.setPlaceholderText("e.g. fiducials")
        form.addRow("Category:", self.category_edit)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["single", "continuous"])
        self.type_combo.setCurrentText(self.item_data.get("dig_type", "single"))
        form.addRow("Type:", self.type_combo)

        self.labels_edit = QLineEdit(", ".join(self.item_data.get("labels", [])) if self.item_data.get("dig_type") == "single" else str(self.item_data.get("n_points", "")))
        self.labels_edit.setPlaceholderText("label1, label2  - or - number of points (continuous)")
        labels_row = QHBoxLayout()
        labels_row.addWidget(self.labels_edit)
        self.edit_labels_btn = QToolButton()
        self.edit_labels_btn.setText("✎")
        self.edit_labels_btn.setToolTip("Edit labels in a larger textbox")
        self.edit_labels_btn.clicked.connect(self._open_labels_editor)
        labels_row.addWidget(self.edit_labels_btn)
        labels_widget = QWidget()
        labels_widget.setLayout(labels_row)
        form.addRow("Labels / n_points:", labels_widget)

        self.template_combo = QComboBox()
        self.template_combo.addItem("None")
        self.template_combo.addItems(list_templates())
        self.template_combo.addItem("Custom")
        self.template_combo.setCurrentText(self.item_data.get("template", "None"))
        form.addRow("Template:", self.template_combo)

        # Custom channel count (only visible when template == Custom)
        self.custom_channels = QSpinBox()
        self.custom_channels.setRange(1, 1024)
        self.custom_channels.setValue(max(len(self.item_data.get("labels", [])), 1) if self.item_data.get("template") == "Custom" else 64)
        self.custom_channels.hide()
        form.addRow("Channels:", self.custom_channels)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

        # Centralized UI state management
        self.type_combo.currentTextChanged.connect(self._update_ui_state)
        self.template_combo.currentTextChanged.connect(self._update_ui_state)
        self.custom_channels.valueChanged.connect(self._generate_custom_labels)

        self._update_ui_state()

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

    def _current_labels(self) -> list[str]:
        return [lbl.strip() for lbl in self.labels_edit.text().split(",") if lbl.strip()]

    def _set_custom_labels(self, labels: list[str]):
        clean = [label.strip() for label in labels if label.strip()]
        if not clean:
            return
        self.labels_edit.setText(", ".join(clean))
        self.custom_channels.blockSignals(True)
        self.custom_channels.setValue(len(clean))
        self.custom_channels.blockSignals(False)

    def _open_labels_editor(self):
        if self.template_combo.currentText() != "Custom" or self.type_combo.currentText() != "single":
            return

        labels = self._current_labels()
        dlg = QDialog(self)
        dlg.setWindowTitle("Edit Custom Labels")
        dlg.resize(520, 420)

        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Enter one label per line:"))

        editor = QPlainTextEdit()
        editor.setPlainText("\n".join(labels))
        layout.addWidget(editor, stretch=1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec_() != QDialog.Accepted:
            return

        edited_labels = [
            line.strip() for line in editor.toPlainText().splitlines() if line.strip()
        ]
        if not edited_labels:
            QMessageBox.warning(self, "Required", "At least one label is required.")
            return

        self._custom_labels_dirty = True
        self._set_custom_labels(edited_labels)

    def _update_ui_state(self):
        dig_type = self.type_combo.currentText()
        template = self.template_combo.currentText()
        previous_template = getattr(self, "_previous_template", template)

        if dig_type == "continuous":
            self.template_combo.setEnabled(False)
            self.custom_channels.hide()
            self.labels_edit.setEnabled(True)
            self.edit_labels_btn.hide()
            self._previous_template = template
            return

        self.template_combo.setEnabled(True)

        if template == "None":
            self.custom_channels.hide()
            self.labels_edit.setEnabled(True)
            self.edit_labels_btn.hide()

        elif template == "Custom":
            self.custom_channels.show()
            self.edit_labels_btn.show()
            self.labels_edit.setEnabled(False)
            preserve_custom_labels = (
                previous_template == "Custom"
                and self._custom_labels_dirty
                and bool(self._current_labels())
            )
            if not preserve_custom_labels:
                self._generate_custom_labels()

        else:
            self.custom_channels.hide()
            self.edit_labels_btn.hide()
            try:
                template_obj = create_template(template)
                labels = template_obj.labels
                self.labels_edit.setText(", ".join(labels))
                self.labels_edit.setEnabled(False)
            except Exception:
                self.labels_edit.setEnabled(True)

        self._previous_template = template

    def _generate_custom_labels(self):
        if self.template_combo.currentText() != "Custom":
            return
        n = self.custom_channels.value()
        labels = [f"eeg{i}" for i in range(1, n + 1)]
        self.labels_edit.setText(", ".join(labels))
        self.labels_edit.setEnabled(False)
        self._custom_labels_dirty = False

    # valueChanged handled by centralized logic


# ---------------------------------------------------------------------------
# Schema editor dialog
# ---------------------------------------------------------------------------

class SchemaEditorDialog(QDialog):
    """Settings window (⚙) to define, order, and save schema presets."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Schema Settings ⚙")
        self.setMinimumSize(520, 480)

        # Load layered presets: defaults + user overlay
        settings = load_settings()
        defaults = settings.get("digitisation", {})

        from ..settings_loader import load_user_settings

        user = load_user_settings().get("digitisation", {})

        self._default_presets: dict = defaults.get("schema_presets", {})
        self._user_presets: dict = user.get("schema_presets", {})

        # merged view used by the editor
        self._presets: dict = {**self._default_presets, **self._user_presets}

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
            label = name
            if name in self._default_presets and name not in self._user_presets:
                label = f"{name} (default)"
            self.preset_combo.addItem(label, name)
        default = load_settings().get("digitisation", {}).get("default_schema_preset", "")
        target = current or default
        idx = self.preset_combo.findData(target)
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
        name = self.preset_combo.currentData() or ""
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
        items = self._current_list_items()

        # Validate continuous items are last
        for i, item in enumerate(items[:-1]):
            if item.get("dig_type") == "continuous":
                QMessageBox.warning(
                    self,
                    "Invalid Schema",
                    "Continuous schema items must be last in the list."
                )
                return

        self._user_presets[name] = items
        self._presets = {**self._default_presets, **self._user_presets}
        self._persist()
        self._populate_combo()
        self.preset_combo.setCurrentText(name)
        QMessageBox.information(self, "Saved", f"Preset '{name}' saved.")

    def _delete_preset(self):
        name = self.preset_combo.currentData()
        if not name:
            return
        reply = QMessageBox.question(self, "Delete Preset", f"Delete preset '{name}'?",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self._user_presets.pop(name, None)
            self._presets = {**self._default_presets, **self._user_presets}
            self._persist()
            self._populate_combo()
            self._load_preset_into_list()

    def _persist(self):
        # Persist only user presets to user layer
        from ..settings_loader import load_user_settings, user_settings_path

        user_settings = load_user_settings()
        user_settings.setdefault("digitisation", {})["schema_presets"] = self._user_presets

        path = user_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(user_settings, indent=2, ensure_ascii=False), encoding="utf-8")

    def _on_accept(self):
        self.accept()

    def selected_schema(self) -> list[dict]:
        return self._current_list_items()


class SettingsDialog(QDialog):
    """Full user-settings editor."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pylhemus Settings")
        self.setMinimumSize(600, 520)

        from ..settings_loader import (
            ensure_user_settings_file,
            load_user_settings,
            user_settings_path,
        )

        ensure_user_settings_file()

        merged = load_user_effective_settings()
        user = load_user_settings()

        self._user_settings_path = user_settings_path()
        self._merged = merged
        self._user = user

        defaults = merged.get("digitisation", {})
        user_dig = user.get("digitisation", {})

        self._default_presets: dict = defaults.get("schema_presets", {})
        self._user_presets: dict = user_dig.get("schema_presets", {})
        self._presets: dict = {**self._default_presets, **self._user_presets}

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(merged, user), "General")
        tabs.addTab(self._build_schema_tab(), "Schema Presets")
        tabs.addTab(self._build_gui_tab(merged), "GUI")
        tabs.addTab(self._build_advanced_tab(merged), "Advanced")

        outer = QVBoxLayout(self)
        outer.addWidget(tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        for btn in self.findChildren(QPushButton):
            btn.setMinimumHeight(DIALOG_BTN_HEIGHT)

        self.preset_combo.currentTextChanged.connect(self._load_preset_into_list)
        self.add_item_btn.clicked.connect(self._add_item)
        self.edit_item_btn.clicked.connect(self._edit_item)
        self.remove_item_btn.clicked.connect(self._remove_selected)
        self.save_preset_btn.clicked.connect(self._save_preset)
        self.del_preset_btn.clicked.connect(self._delete_preset)

        self._populate_combo()
        self._load_preset_into_list()
        self._sync_default_preset_combo()

    def _build_general_tab(self, merged: dict, user: dict) -> QWidget:
        del user
        page = QWidget()
        outer = QVBoxLayout(page)
        form = QFormLayout()
        outer.addLayout(form)
        outer.addStretch(1)

        output_row = QHBoxLayout()
        self.output_dir_edit = QLineEdit(
            merged.get("digitisation", {}).get("output_dir", "output")
        )
        output_browse_btn = QPushButton("Browse...")
        output_browse_btn.setFixedWidth(80)
        output_browse_btn.clicked.connect(self._browse_output_dir)
        output_row.addWidget(self.output_dir_edit)
        output_row.addWidget(output_browse_btn)
        output_widget = QWidget()
        output_widget.setLayout(output_row)
        form.addRow("Output directory:", output_widget)

        return page

    def _build_schema_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        dig = self._merged.get("digitisation", {})

        default_row = QHBoxLayout()
        default_row.addWidget(QLabel("Default preset:"))
        self.default_preset_combo = QComboBox()
        for name in self._presets:
            self.default_preset_combo.addItem(name)
        current_default = dig.get("default_schema_preset", "")
        idx = self.default_preset_combo.findText(current_default)
        if idx >= 0:
            self.default_preset_combo.setCurrentIndex(idx)
        default_row.addWidget(self.default_preset_combo, stretch=1)
        layout.addLayout(default_row)

        layout.addSpacing(8)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Preset:"))
        self.preset_combo = QComboBox()
        preset_row.addWidget(self.preset_combo, stretch=1)
        self.del_preset_btn = QPushButton("Delete Preset")
        preset_row.addWidget(self.del_preset_btn)
        layout.addLayout(preset_row)

        layout.addWidget(QLabel("Items - drag to reorder:"))
        self.item_list = QListWidget()
        self.item_list.setDragDropMode(QListWidget.InternalMove)
        self.item_list.setMinimumHeight(180)
        layout.addWidget(self.item_list, stretch=1)

        item_btns = QHBoxLayout()
        self.add_item_btn = QPushButton("+ Add Item")
        self.edit_item_btn = QPushButton("Edit Item")
        self.remove_item_btn = QPushButton("- Remove Selected")
        item_btns.addWidget(self.add_item_btn)
        item_btns.addWidget(self.edit_item_btn)
        item_btns.addWidget(self.remove_item_btn)
        item_btns.addStretch(1)
        layout.addLayout(item_btns)

        save_row = QHBoxLayout()
        save_row.addWidget(QLabel("Save current list as:"))
        self.save_name_edit = QLineEdit()
        save_row.addWidget(self.save_name_edit, stretch=1)
        self.save_preset_btn = QPushButton("Save Preset")
        save_row.addWidget(self.save_preset_btn)
        layout.addLayout(save_row)

        return page

    def _build_gui_tab(self, merged: dict) -> QWidget:
        dig = merged.get("digitisation", {})
        page = QWidget()
        outer = QVBoxLayout(page)
        form = QFormLayout()
        outer.addLayout(form)
        outer.addStretch(1)

        sounds = dig.get("point_sounds", {})
        self._sound_edits: dict[str, QLineEdit] = {}
        for key in ("single", "continuous", "faulty"):
            row = QHBoxLayout()
            edit = QLineEdit(sounds.get(key, ""))
            browse = QPushButton("Browse...")
            browse.setFixedWidth(80)
            browse.clicked.connect(lambda _checked, e=edit: self._browse_sound(e))
            row.addWidget(edit)
            row.addWidget(browse)
            self._sound_edits[key] = edit
            widget = QWidget()
            widget.setLayout(row)
            form.addRow(f"Sound ({key}):", widget)

        colors = dig.get("category_colors", {})
        self._color_edits: dict[str, str] = dict(colors)
        self._color_btns: dict[str, QPushButton] = {}
        for cat, color in colors.items():
            btn = QPushButton()
            btn.setFixedWidth(100)
            self._apply_color_to_btn(btn, color)
            btn.clicked.connect(lambda _checked, c=cat: self._pick_color(c))
            self._color_btns[cat] = btn
            form.addRow(f"Colour ({cat}):", btn)

        return page

    def _build_advanced_tab(self, merged: dict) -> QWidget:
        dig = merged.get("digitisation", {})
        page = QWidget()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        scroll.setWidget(inner)
        form = QFormLayout(inner)

        self.serial_port_edit = QLineEdit(merged.get("serial_port", "COM1"))
        form.addRow("Serial port:", self.serial_port_edit)

        self.serial_baud_spin = QSpinBox()
        self.serial_baud_spin.setRange(300, 115200)
        self.serial_baud_spin.setValue(int(merged.get("serial_baud", 9600)))
        form.addRow("Baud rate:", self.serial_baud_spin)

        self.units_combo = QComboBox()
        self.units_combo.addItems(["cm", "inch"])
        self.units_combo.setCurrentText(str(dig.get("units", "cm")))
        form.addRow("Units:", self.units_combo)

        self.metal_comp_check = QCheckBox()
        self.metal_comp_check.setChecked(bool(dig.get("metal_compensation", True)))
        form.addRow("Metal compensation:", self.metal_comp_check)

        self.factory_defaults_check = QCheckBox()
        self.factory_defaults_check.setChecked(
            bool(dig.get("set_factory_software_defaults", True))
        )
        form.addRow("Factory defaults on start:", self.factory_defaults_check)

        hemisphere = dig.get("hemisphere", [0.0, 0.0, 1.0])
        if not isinstance(hemisphere, (list, tuple)) or len(hemisphere) != 3:
            hemisphere = [0.0, 0.0, 1.0]
        hemisphere_row = QHBoxLayout()
        self.hemisphere_x_spin = QDoubleSpinBox()
        self.hemisphere_y_spin = QDoubleSpinBox()
        self.hemisphere_z_spin = QDoubleSpinBox()
        for spin, value in zip(
            (self.hemisphere_x_spin, self.hemisphere_y_spin, self.hemisphere_z_spin),
            hemisphere,
        ):
            spin.setRange(-1.0, 1.0)
            spin.setSingleStep(0.1)
            spin.setDecimals(2)
            spin.setValue(float(value))
            hemisphere_row.addWidget(spin)
        hemisphere_widget = QWidget()
        hemisphere_widget.setLayout(hemisphere_row)
        form.addRow("Hemisphere X/Y/Z:", hemisphere_widget)

        self.capture_interval_spin = QSpinBox()
        self.capture_interval_spin.setRange(10, 5000)
        self.capture_interval_spin.setSuffix(" ms")
        self.capture_interval_spin.setValue(int(dig.get("capture_interval_ms", 100)))
        form.addRow("Capture interval:", self.capture_interval_spin)

        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        return page

    def _browse_sound(self, edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select sound file", "", "Audio (*.wav *.ogg *.mp3)"
        )
        if path:
            edit.setText(path)

    def _browse_output_dir(self):
        path = QFileDialog.getExistingDirectory(
            self,
            "Select output directory",
            self.output_dir_edit.text().strip() or str(Path.cwd()),
        )
        if path:
            self.output_dir_edit.setText(path)

    def _apply_color_to_btn(self, btn: QPushButton, color: str):
        btn.setText(color)
        text_color = "#000000" if QColor(color).lightness() > 128 else "#ffffff"
        btn.setStyleSheet(f"background-color: {color}; color: {text_color};")

    def _pick_color(self, category: str):
        initial = QColor(self._color_edits.get(category, "#888888"))
        chosen = QColorDialog.getColor(initial, self, f"Pick colour for {category}")
        if chosen.isValid():
            hex_color = chosen.name()
            self._color_edits[category] = hex_color
            self._apply_color_to_btn(self._color_btns[category], hex_color)

    def _sync_default_preset_combo(self):
        current = self.default_preset_combo.currentText()
        fallback = self._merged.get("digitisation", {}).get("default_schema_preset", "")
        self.default_preset_combo.blockSignals(True)
        self.default_preset_combo.clear()
        for name in self._presets:
            self.default_preset_combo.addItem(name)
        target = current if current in self._presets else fallback
        idx = self.default_preset_combo.findText(target)
        if idx >= 0:
            self.default_preset_combo.setCurrentIndex(idx)
        self.default_preset_combo.blockSignals(False)

    def _populate_combo(self):
        current = self.preset_combo.currentText()
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for name in self._presets:
            label = name
            if name in self._default_presets and name not in self._user_presets:
                label = f"{name} (default)"
            self.preset_combo.addItem(label, name)
        default = self._merged.get("digitisation", {}).get("default_schema_preset", "")
        target = current or default
        idx = self.preset_combo.findData(target)
        self.preset_combo.setCurrentIndex(max(idx, 0))
        self.preset_combo.blockSignals(False)
        self._sync_default_preset_combo()

    def _item_text(self, item: dict) -> str:
        category = item.get("category", "?")
        dig_type = item.get("dig_type", "single")
        if dig_type == "continuous":
            n = item.get("n_points", "\u221e")
            return f"{category}  [continuous, n\u2265{n}]"
        labels = item.get("labels", [])
        return f"{category}  [single: {', '.join(labels)}]"

    def _load_preset_into_list(self):
        name = self.preset_combo.currentData()
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
        return [
            self.item_list.item(i).data(Qt.UserRole)
            for i in range(self.item_list.count())
        ]

    def _save_preset(self):
        name = self.save_name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Required", "Enter a preset name.")
            return
        items = self._current_list_items()

        for i, item in enumerate(items[:-1]):
            if item.get("dig_type") == "continuous":
                QMessageBox.warning(
                    self,
                    "Invalid Schema",
                    "Continuous schema items must be last in the list.",
                )
                return

        self._user_presets[name] = items
        self._presets = {**self._default_presets, **self._user_presets}
        self._populate_combo()
        idx = self.preset_combo.findData(name)
        if idx >= 0:
            self.preset_combo.setCurrentIndex(idx)
        QMessageBox.information(self, "Saved", f"Preset '{name}' saved.")

    def _delete_preset(self):
        name = self.preset_combo.currentData()
        if not name:
            return
        reply = QMessageBox.question(
            self,
            "Delete Preset",
            f"Delete preset '{name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._user_presets.pop(name, None)
            self._presets = {**self._default_presets, **self._user_presets}
            self._populate_combo()
            self._load_preset_into_list()

    def _persist(self):
        from ..settings_loader import load_user_settings, user_settings_path

        user_settings = load_user_settings()
        user_settings.setdefault("digitisation", {})["schema_presets"] = self._user_presets

        path = user_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(user_settings, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def _build_user_settings_payload(self, current_user: dict) -> dict:
        user = json.loads(json.dumps(current_user))
        hemisphere = [
            self.hemisphere_x_spin.value(),
            self.hemisphere_y_spin.value(),
            self.hemisphere_z_spin.value(),
        ]
        user.setdefault("digitisation", {})
        user["serial_port"] = self.serial_port_edit.text().strip()
        user["serial_baud"] = self.serial_baud_spin.value()
        user["digitisation"]["default_schema_preset"] = (
            self.default_preset_combo.currentText()
        )
        user["digitisation"]["units"] = self.units_combo.currentText()
        user["digitisation"]["metal_compensation"] = (
            self.metal_comp_check.isChecked()
        )
        user["digitisation"]["set_factory_software_defaults"] = (
            self.factory_defaults_check.isChecked()
        )
        user["digitisation"]["hemisphere"] = hemisphere
        user["digitisation"]["output_dir"] = self.output_dir_edit.text().strip()
        user["digitisation"]["schema_presets"] = self._user_presets
        user["digitisation"]["capture_interval_ms"] = self.capture_interval_spin.value()
        user["digitisation"]["point_sounds"] = {
            key: edit.text() for key, edit in self._sound_edits.items()
        }
        user["digitisation"]["category_colors"] = dict(self._color_edits)
        return user

    def _collect_changed_paths(
        self, before, after, prefix: str = ""
    ) -> list[str]:
        if before == after:
            return []

        if isinstance(before, dict) and isinstance(after, dict):
            changed: list[str] = []
            keys = sorted(set(before) | set(after))
            for key in keys:
                path = f"{prefix}.{key}" if prefix else str(key)
                if key not in before or key not in after:
                    changed.append(path)
                    continue
                changed.extend(self._collect_changed_paths(before[key], after[key], path))
            return changed

        return [prefix or "settings"]

    def _on_accept(self):
        from ..settings_loader import load_user_settings

        hemisphere = [
            self.hemisphere_x_spin.value(),
            self.hemisphere_y_spin.value(),
            self.hemisphere_z_spin.value(),
        ]
        if hemisphere == [0.0, 0.0, 0.0]:
            QMessageBox.warning(
                self,
                "Invalid Hemisphere",
                "Hemisphere must not be the zero vector.",
            )
            return

        current_user = load_user_settings()
        user = self._build_user_settings_payload(current_user)
        changed_paths = self._collect_changed_paths(current_user, user)

        if changed_paths:
            preview = changed_paths[:12]
            summary = "\n".join(f"• {path}" for path in preview)
            remaining = len(changed_paths) - len(preview)
            if remaining > 0:
                summary += f"\n• … and {remaining} more"
            reply = QMessageBox.question(
                self,
                "Confirm Changes",
                "Save these settings changes?\n\n" + summary,
                QMessageBox.Ok | QMessageBox.Cancel,
                QMessageBox.Ok,
            )
            if reply != QMessageBox.Ok:
                return

        self._user_settings_path.parent.mkdir(parents=True, exist_ok=True)
        self._user_settings_path.write_text(
            json.dumps(user, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        self.accept()


# ---------------------------------------------------------------------------
# Launch dialog: participant ID + schema selection
# ---------------------------------------------------------------------------

class LaunchDialog(QDialog):
    """Startup dialog: enter participant ID and project, select schema preset."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("OPM Digitisation — New Session")
        self.setMinimumSize(420, 300)
        self.loaded_data: pd.DataFrame | None = None
        self.loaded_data_path: Path | None = None

        dig = _load_dig_settings()
        self._presets: dict = dig.get("schema_presets", {})
        self._default_preset: str = dig.get("default_schema_preset", "")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.project_edit = QLineEdit()
        self.project_edit.setPlaceholderText("e.g. MEG001")
        form.addRow("Project:", self.project_edit)

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
        form.addRow("Schema:", schema_row)

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        self.load_data_btn = QPushButton("Load Data...")
        self.load_data_btn.clicked.connect(self._on_load_data)
        btn_row.addWidget(self.load_data_btn)
        btn_row.addStretch(1)
        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self._on_accept)
        cancel_btn.clicked.connect(self.reject)
        for _btn in (self.load_data_btn, cancel_btn, ok_btn):
            _btn.setMinimumHeight(DIALOG_BTN_HEIGHT)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addLayout(btn_row)
        self.id_edit.returnPressed.connect(self._on_accept)
        self.project_edit.returnPressed.connect(self._on_accept)

    def _on_accept(self):
        if self.loaded_data is not None:
            self.accept()
            return
        if not self.project_edit.text().strip():
            QMessageBox.warning(self, "Required", "Project cannot be empty.")
            return
        if not self.id_edit.text().strip():
            QMessageBox.warning(self, "Required", "Participant ID cannot be empty.")
            return
        self.accept()

    def _on_load_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load digitisation data",
            str(Path.cwd()),
            "Data files (*.csv *.fif *.json)",
        )
        if not path:
            return

        data_path = Path(path)
        try:
            self.loaded_data = read_file(data_path)
            self.loaded_data_path = data_path
        except Exception as exc:
            self.loaded_data = None
            self.loaded_data_path = None
            self.load_data_btn.setText("Load Data...")
            QMessageBox.critical(self, "Load Failed", str(exc))
            return

        self.load_data_btn.setText(f"Loaded: {data_path.name}")

    @property
    def project(self) -> str:
        return self.project_edit.text().strip()

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

# ---------------------------------------------------------------------------
# Main digitisation window
# ---------------------------------------------------------------------------

class DigitisationMainWindow(QMainWindow):
    def __init__(self, controller: DigitisationController, dev_mode: bool = False, read_only: bool = False):
        super().__init__()
        self.controller = controller
        self._updating_table = False
        self._camera_initialized = False
        self._zoom_factor = 1.0
        self._dev_mode = dev_mode
        self._read_only = read_only
        self._show_transformed = False
        self._selected_row = -1
        self._session_saved = False

        dig = _load_dig_settings()
        interval = int(dig.get("capture_interval_ms", 100))
        self._category_colors: dict = dig.get("category_colors", {})
        self._sound_manager = _PointSoundManager(self, dig.get("point_sounds", {}))

        self._auto_capture_timer = QTimer(self)
        self._auto_capture_timer.setInterval(interval)
        self._auto_capture_timer.timeout.connect(self.on_auto_capture_tick)

        self._faulty_warning_timer = QTimer(self)
        self._faulty_warning_timer.setSingleShot(True)
        self._faulty_warning_timer.timeout.connect(self._hide_faulty_warning)

        self._cardinal_warning_timer = QTimer(self)
        self._cardinal_warning_timer.setSingleShot(True)
        self._cardinal_warning_timer.timeout.connect(self._hide_cardinal_warning)

        pid = getattr(controller, "participant_id", "") or ""
        if self._read_only:
            title = "OPM Digitisation — Viewer"
        else:
            title = f"OPM Digitisation — subject: {pid}" if pid else "OPM Digitisation GUI"
        self.setWindowTitle(title)
        self.resize(1400, 850)

        # Auto-save timer (every 5 seconds)
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setInterval(5000)  # 5 seconds
        self._autosave_timer.timeout.connect(self._auto_save_session)
        if not self._read_only:
            self._autosave_timer.start()

        self._build_ui()
        # Only start fresh if no points exist (not restored session)
        if not self._read_only and len(self.controller.digitised_points) == 0:
            self.controller.start()
        self.refresh_ui()
        if not self._read_only and not self.controller.is_finished and not self._dev_mode:
            self._auto_capture_timer.start()


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout()
        central.setLayout(root)

        if self._read_only:
            banner = QLabel("VIEW MODE - loaded data (read-only)")
            banner.setStyleSheet(
                "background-color: #3f5870; color: white; padding: 10px; font-weight: bold; font-size: 14px;"
            )
            banner.setAlignment(Qt.AlignCenter)
            root.addWidget(banner)
        elif self._dev_mode:
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

        self.reset_view_btn = QPushButton("Reset\nView")
        self.reset_view_btn.setFixedSize(60, 60)
        self.reset_view_btn.setStyleSheet("""
            QPushButton {
                background-color: #445566;
                color: white;
                border: 2px solid #667788;
                border-radius: 4px;
                font-weight: bold;
                font-size: 10px;
            }
            QPushButton:hover {
                background-color: #556677;
            }
            QPushButton:pressed {
                background-color: #334455;
            }
        """)
        
        left_panel.addStretch(1)
        left_panel.addWidget(QLabel("Zoom"))
        left_panel.addWidget(self.zoom_slider)
        left_panel.addWidget(self.zoom_value_label)
        left_panel.addSpacing(20)
        left_panel.addWidget(self.transform_toggle_btn)
        left_panel.addSpacing(4)
        left_panel.addWidget(self.reset_view_btn)
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
        
        self.status_frame = QFrame()
        self.status_frame.setStyleSheet(
            "QFrame {"
            "background-color: #2a2a2e;"
            "border: 1px solid #666;"
            "border-radius: 6px;"
            "padding: 8px;"
            "}"
        )
        status_layout = QVBoxLayout(self.status_frame)
        status_layout.setSpacing(8)
        status_layout.setContentsMargins(10, 8, 10, 8)

        status_top_row = QHBoxLayout()
        status_top_row.setSpacing(8)
        self.status_category_label = QLabel("-")
        self.status_category_label.setStyleSheet(
            "border: none; color: #aaa; font-size: 10pt; font-weight: 500;"
        )
        self.status_progress_label = QLabel("-")
        self.status_progress_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.status_progress_label.setStyleSheet(
            "border: none; color: #aaa; font-size: 10pt; font-weight: 500;"
        )
        status_top_row.addWidget(self.status_category_label, stretch=1)
        status_top_row.addWidget(self.status_progress_label)

        self.status_target_label = QLabel("-")
        self.status_target_label.setAlignment(Qt.AlignCenter)
        self.status_target_label.setStyleSheet(
            "border: none; color: white; font-size: 18pt; font-weight: 700;"
        )

        status_layout.addLayout(status_top_row)
        status_layout.addWidget(self.status_target_label)

        right_panel.addWidget(self.status_frame)
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
        
        # Button row 1: Undo | Delete
        btn_row1 = QHBoxLayout()
        self.undo_btn = QPushButton("Undo")
        self.undo_btn.setFixedSize(80, 80)
        self.undo_btn.setStyleSheet(button_style)
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
        btn_row1.addWidget(self.undo_btn)
        btn_row1.addWidget(self.delete_btn)
        right_panel.addLayout(btn_row1)
        
        # Button row 2: Restart | Finish
        btn_row2 = QHBoxLayout()
        self.restart_btn = QPushButton("Restart")
        self.restart_btn.setFixedSize(80, 80)
        self.restart_btn.setStyleSheet(button_style)
        self.finish_btn = QPushButton("Finish")
        self.finish_btn.setFixedSize(80, 80)
        self.finish_btn.setStyleSheet(button_style)
        btn_row2.addWidget(self.restart_btn)
        btn_row2.addWidget(self.finish_btn)
        right_panel.addLayout(btn_row2)

        # Button row 3: Save
        btn_row3 = QHBoxLayout()
        self.save_btn = QPushButton("Save")
        self.save_btn.setFixedSize(160, 80)
        self.save_btn.setStyleSheet(button_style)
        btn_row3.addWidget(self.save_btn)
        right_panel.addLayout(btn_row3)
        
        # Dev mode buttons
        if self._dev_mode and not self._read_only:
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
        if self._read_only:
            self.save_btn.clicked.connect(self._on_save_csv_only)
        else:
            self.save_btn.clicked.connect(self.on_save)
        self.finish_btn.clicked.connect(self.close)
        self.delete_btn.clicked.connect(self.on_delete_point)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)
        self.transform_toggle_btn.clicked.connect(self.on_toggle_transform_view)
        self.reset_view_btn.clicked.connect(self.on_reset_view)
        self.table.itemSelectionChanged.connect(self.on_table_selection_changed)

        if self._dev_mode and not self._read_only:
            self.dev_add_btn.clicked.connect(self.on_dev_add_point)
            self.dev_faulty_btn.clicked.connect(self.on_dev_add_faulty_point)

        if self._read_only:
            self.undo_btn.setEnabled(False)
            self.restart_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)
            self.save_btn.setText("Export CSV")
            self.finish_btn.hide()

        # Enable point picking in plotter
        self.plotter.enable_point_picking(callback=self.on_plot_point_picked, show_message=False)

        # Press 'p' to print camera state for tuning reset view
        self.plotter.iren.add_observer("KeyPressEvent", self._on_keypress)

    def _on_keypress(self, obj, event):
        if obj.GetKeySym() == "p":
            cam = self.plotter.camera
            pos = cam.GetPosition()
            fp = cam.GetFocalPoint()
            up = cam.GetViewUp()
            print(f"Camera position:  ({pos[0]:.2f}, {pos[1]:.2f}, {pos[2]:.2f})")
            print(f"Focal point:      ({fp[0]:.2f}, {fp[1]:.2f}, {fp[2]:.2f})")
            print(f"View up:          ({up[0]:.3f}, {up[1]:.3f}, {up[2]:.3f})")

    def refresh_ui(self):
        category, target, progress = self.controller.status_text()
        self.status_category_label.setText(category)
        self.status_target_label.setText(target)
        self.status_progress_label.setText(progress)

        self._render_scene(highlight_row=self._selected_row)
        self._refresh_table()
        self._update_transform_ui()

        warning = self.controller.pop_pending_cardinal_warning()
        if warning:
            self._show_cardinal_warning(warning)

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

    def on_reset_view(self):
        self._zoom_factor = 1.0
        self.zoom_slider.setValue(100)

        df = self.controller.digitised_points
        if df.empty:
            self.plotter.reset_camera()
            self._render_scene(highlight_row=self._selected_row)
            return

        if self._show_transformed and self.controller.has_valid_neuromag_transform():
            coords = np.array([
                self.controller.apply_neuromag_transform((r["x"], r["y"], r["z"]))
                for _, r in df.iterrows()
            ])
        else:
            coords = df[["x", "y", "z"]].astype(float).to_numpy()

        center = coords.mean(axis=0)
        radius = max(np.max(np.linalg.norm(coords - center, axis=1)), 10.0)
        dist = radius * 3.0

        camera = self.plotter.camera
        frame = self._estimate_reset_view_frame(coords)
        if frame is not None:
            center = frame["focal_point"]
            direction = frame["direction"]
            view_up = frame["view_up"]
            source = frame["source"]
        else:
            direction = np.array([-0.35, 1.25, 0.7], dtype=float)
            direction /= np.linalg.norm(direction)
            view_up = np.array([0.0, 0.0, 1.0], dtype=float)
            source = "fallback"

        if getattr(self.controller, "debug_serial", False):
            mode = "transformed" if self._show_transformed and self.controller.has_valid_neuromag_transform() else "raw"
            print(
                "[RESET VIEW] "
                f"mode={mode} source={source} center={tuple(np.round(center, 3))} "
                f"direction={tuple(np.round(direction, 3))} view_up={tuple(np.round(view_up, 3))}"
            )

        camera.SetFocalPoint(*center)
        camera.SetPosition(*(center + direction * dist))
        camera.SetViewUp(*view_up)
        self._camera_initialized = True

        self._render_scene(highlight_row=self._selected_row)

    def _estimate_reset_view_frame(self, coords: np.ndarray) -> dict[str, np.ndarray | str] | None:
        fiducials = self.controller.digitised_points
        fiducials = fiducials[fiducials["category"] == "fiducials"]
        if len(fiducials) < 3:
            return None

        display_points: list[np.ndarray] = []
        for _, row in fiducials.iterrows():
            point = (float(row["x"]), float(row["y"]), float(row["z"]))
            if self._show_transformed and self.controller.has_valid_neuromag_transform():
                transformed = self.controller.apply_neuromag_transform(point)
                if transformed is None:
                    continue
                display_points.append(np.asarray(transformed, dtype=float))
            else:
                display_points.append(np.asarray(point, dtype=float))

        if len(display_points) != 3:
            return None

        basis = self._estimate_cardinal_basis(np.vstack(display_points))
        if basis is None:
            return None

        up_reference = self._reset_view_up_reference()
        if float(np.dot(basis["superior"], up_reference)) < 0.0:
            basis["superior"] = -basis["superior"]

        point_radius = max(np.max(np.linalg.norm(coords - basis["origin"], axis=1)), 1.0)
        focal_point = basis["origin"] + (0.18 * point_radius) * basis["anterior"] + (0.05 * point_radius) * basis["superior"]
        direction = (-0.42 * basis["right"]) + (1.35 * basis["anterior"]) + (0.72 * basis["superior"])
        direction /= np.linalg.norm(direction)

        view_up = basis["superior"] - np.dot(basis["superior"], direction) * direction
        view_up_norm = np.linalg.norm(view_up)
        if view_up_norm <= 1e-9:
            view_up = basis["anterior"]
        else:
            view_up /= view_up_norm

        return {
            "focal_point": focal_point,
            "direction": direction,
            "view_up": view_up,
            "source": str(basis["source"]),
        }

    def _reset_view_up_reference(self) -> np.ndarray:
        if self._show_transformed and self.controller.has_valid_neuromag_transform():
            return np.array([0.0, 0.0, 1.0], dtype=float)

        if self._camera_initialized:
            try:
                view_up = np.asarray(self.plotter.camera.GetViewUp(), dtype=float)
                norm = np.linalg.norm(view_up)
                if norm > 1e-9:
                    return view_up / norm
            except Exception:
                pass

        return np.array([0.0, 0.0, 1.0], dtype=float)

    def _estimate_cardinal_basis(self, points: np.ndarray) -> dict[str, np.ndarray | str] | None:
        if points.shape != (3, 3):
            return None

        pair_distances: list[tuple[float, tuple[int, int]]] = []
        for i in range(3):
            for j in range(i + 1, 3):
                pair_distances.append((float(np.linalg.norm(points[i] - points[j])), (i, j)))

        _, lateral_pair = max(pair_distances, key=lambda item: item[0])
        nasion_idx = next(index for index in range(3) if index not in lateral_pair)
        lateral_indices = list(lateral_pair)

        if self._show_transformed and self.controller.has_valid_neuromag_transform():
            lateral_indices.sort(key=lambda index: points[index][0], reverse=True)
        elif self._camera_initialized:
            camera = self.plotter.camera
            camera_dir = np.asarray(camera.position, dtype=float) - np.asarray(camera.focal_point, dtype=float)
            if np.linalg.norm(camera_dir) > 1e-9:
                trial = points[lateral_indices[0]] - points[lateral_indices[1]]
                if np.dot(camera_dir, trial) < 0:
                    lateral_indices.reverse()

        left_idx, right_idx = lateral_indices
        left = points[left_idx]
        right = points[right_idx]
        nasion = points[nasion_idx]

        right_axis = right - left
        right_norm = np.linalg.norm(right_axis)
        if right_norm <= 1e-9:
            return None
        right_axis /= right_norm

        origin = left + np.dot(nasion - left, right_axis) * right_axis
        anterior = nasion - origin
        anterior_norm = np.linalg.norm(anterior)
        if anterior_norm <= 1e-9:
            return None
        anterior /= anterior_norm

        superior = np.cross(right_axis, anterior)
        superior_norm = np.linalg.norm(superior)
        if superior_norm <= 1e-9:
            return None
        superior /= superior_norm

        return {
            "origin": origin,
            "right": right_axis,
            "anterior": anterior,
            "superior": superior,
            "source": "cardinal_estimate",
        }

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
                    item.template = create_template(item.template)
                except Exception:
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

        active_item = self.controller.current_item
        active_dig_type = active_item.dig_type if active_item is not None else "single"

        try:
            position = self.controller.capture_from_connector()
        except Exception:
            # Ignore transient connector read errors and try again on next tick.
            return

        if position is None:
            # Check if this was a rejected point (too far)
            if self.controller.was_last_capture_rejected():
                self._sound_manager.play_faulty_sound()
                self._show_faulty_warning()
            else:
                waiting_msg = "waiting for FASTRAK data..."
                if self.status_progress_label.text() != waiting_msg:
                    self.status_progress_label.setText(waiting_msg)
            return

        self._sound_manager.play_point_sound(active_dig_type)
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
        self._faulty_warning_timer.start(1000)

    def _hide_faulty_warning(self):
        if hasattr(self, "_faulty_warning_label"):
            self._faulty_warning_label.hide()

    def _show_cardinal_warning(self, message: str):
        if hasattr(self, "_cardinal_warning_label"):
            self._cardinal_warning_label.hide()
        else:
            self._cardinal_warning_label = QLabel()
            self._cardinal_warning_label.setWordWrap(True)
            self._cardinal_warning_label.setStyleSheet(
                "background-color: #d69e2e; color: black; padding: 6px; font-weight: bold; font-size: 12px;"
            )
            self.centralWidget().layout().insertWidget(0, self._cardinal_warning_label)
        self._cardinal_warning_label.setText(message)
        self._cardinal_warning_label.show()
        self._cardinal_warning_timer.start(5000)

    def _hide_cardinal_warning(self):
        if hasattr(self, "_cardinal_warning_label"):
            self._cardinal_warning_label.hide()

    def on_undo(self):
        self.controller.undo()
        self.refresh_ui()
        if not self._read_only and not self.controller.is_finished and not self._dev_mode and not self._auto_capture_timer.isActive():
            self._auto_capture_timer.start()

    def on_save(self):
        pid = getattr(self.controller, "participant_id", "") or "digitisation"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        default_name = f"digitisation_sub-{pid}_{timestamp}.json"
        dig = _load_dig_settings()
        output_dir = Path(dig.get("output_dir", "output")).resolve()
        project = getattr(self.controller, "project", "") or ""
        if project:
            output_dir = output_dir / project
        path, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save digitisation",
            str(output_dir / default_name),
            "Pylhemus JSON (*.json);;CSV (*.csv)",
        )
        if not path:
            return

        output_path = Path(path)
        try:
            if selected_filter.startswith("CSV") or output_path.suffix.lower() == ".csv":
                self.controller.save_csv(output_path)
            else:
                self.controller.save_dig_json(output_path)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self._session_saved = True

    def _on_save_csv_only(self):
        pid = getattr(self.controller, "participant_id", "") or "digitisation"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        default_name = f"digitisation_sub-{pid}_{timestamp}.csv"
        dig = _load_dig_settings()
        output_dir = Path(dig.get("output_dir", "output")).resolve()
        project = getattr(self.controller, "project", "") or ""
        if project:
            output_dir = output_dir / project
        path, _ = QFileDialog.getSaveFileName(self, "Save digitisation CSV",
                                              str(output_dir / default_name), "CSV (*.csv)")
        if not path:
            return

        try:
            self.controller.save_csv(Path(path))
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return

        self._session_saved = True

    def _restore_running_timers(self):
        if not self._read_only:
            self._autosave_timer.start()
        if not self._read_only and not self.controller.is_finished and not self._dev_mode:
            self._auto_capture_timer.start()

    def _auto_save_session(self):
        """Auto-save session every 5 seconds to temp file."""
        if len(self.controller.digitised_points) == 0:
            return
        
        import tempfile
        import os
        
        # Use temp directory for auto-save
        temp_dir = tempfile.gettempdir()
        pid = getattr(self.controller, "participant_id", "") or "pylhemus"
        proj = getattr(self.controller, "project", "") or ""
        prefix = f"digitisation_{proj}_sub-" if proj else "digitisation_sub-"
        autosave_path = Path(temp_dir) / f"{prefix}{pid}_autosave.json"
        try:
            self.controller.save_session_with_transform(autosave_path)
        except Exception:
            pass  # Silent fail for auto-save

    def closeEvent(self, event):
        if self._auto_capture_timer.isActive():
            self._auto_capture_timer.stop()
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()

        if not self._read_only and not self._session_saved and len(self.controller.digitised_points) > 0:
            reply = QMessageBox.question(
                self, "Save Digitisation?",
                "You have unsaved data. Save before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel
            )
            if reply == QMessageBox.Yes:
                self.on_save()
                if not self._session_saved:
                    self._restore_running_timers()
                    event.ignore()
                    return
            elif reply == QMessageBox.No:
                self._session_saved = True  # Mark as "handled" so no auto-save
            elif reply == QMessageBox.Cancel:
                self._restore_running_timers()
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
            active_item = self.controller.current_item
            active_dig_type = active_item.dig_type if active_item is not None else "single"
            connector.inject_point(faulty=False)
            try:
                position = self.controller.capture_from_connector()
                if position is not None:
                    self._sound_manager.play_point_sound(active_dig_type)
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
            active_item = self.controller.current_item
            active_dig_type = active_item.dig_type if active_item is not None else "single"
            connector.inject_point(faulty=True)
            try:
                position = self.controller.capture_from_connector()
                if position is None:
                    self._sound_manager.play_faulty_sound()
                    self._show_faulty_warning()
                else:
                    self._sound_manager.play_point_sound(active_dig_type)
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
            if self._read_only:
                self.delete_btn.setEnabled(False)
                return
            
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
        
        point = np.asarray(point, dtype=float).ravel()
        if point.size != 3:
            return
        
        # Find closest point
        df = self.controller.digitised_points
        coords = df[["x", "y", "z"]].values.astype(float)
        distances = np.linalg.norm(coords - point, axis=1)
        closest_idx = int(np.argmin(distances))
        
        if distances[closest_idx] < 10:  # Within 10cm threshold
            self.table.selectRow(closest_idx)
            self._selected_row = closest_idx

    def _highlight_point_in_plot(self, row_idx):
        self._render_scene(highlight_row=row_idx)
