from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from PyQt5.QtWidgets import (
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
from PyQt5.QtGui import QFont
from pyvistaqt import QtInteractor

from .controller import DigitisationController
from ..settings import resolve_settings_path

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
        self.setFixedSize(340, 120)

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

    @property
    def participant_id(self) -> str:
        return self.id_edit.text().strip()


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
        self.template_combo.addItems(["EEG_layout", "template_base"])
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

    def _open_schema_editor(self):
        dlg = SchemaEditorDialog(settings_path=self.settings_path, parent=self)
        dlg.exec_()
        # Refresh combo after potential preset changes
        current = self.schema_combo.currentText()
        dig = _load_dig_settings(self.settings_path)
        self._presets = dig.get("schema_presets", {})
        self.schema_combo.clear()
        for name in self._presets:
            self.schema_combo.addItem(name)
        idx = self.schema_combo.findText(current)
        if idx >= 0:
            self.schema_combo.setCurrentIndex(idx)

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
        return list(self._presets.get(name, []))


# ---------------------------------------------------------------------------
# Main digitisation window
# ---------------------------------------------------------------------------

class DigitisationMainWindow(QMainWindow):
    def __init__(self, controller: DigitisationController, settings_path: Path | None = None):
        super().__init__()
        self.controller = controller
        self._settings_path = settings_path or _DEFAULT_SETTINGS_PATH
        self._updating_table = False
        self._camera_initialized = False
        self._zoom_factor = 1.0

        dig = _load_dig_settings(self._settings_path)
        interval = int(dig.get("capture_interval_ms", 100))
        self._category_colors: dict = dig.get("category_colors", {})

        self._auto_capture_timer = QTimer(self)
        self._auto_capture_timer.setInterval(interval)
        self._auto_capture_timer.timeout.connect(self.on_auto_capture_tick)

        pid = getattr(controller, "participant_id", "") or ""
        title = f"OPM Digitisation — {pid}" if pid else "OPM Digitisation GUI"
        self.setWindowTitle(title)
        self.resize(1400, 850)

        self._build_ui()
        self.controller.start()
        self.refresh_ui()
        if not self.controller.is_finished:
            self._auto_capture_timer.start()


    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout()
        central.setLayout(root)

        top_row = QHBoxLayout()
        root.addLayout(top_row, stretch=4)

        self.plotter = QtInteractor(self)
        top_row.addWidget(self.plotter.interactor, stretch=4)

        side_panel = QVBoxLayout()
        top_row.addLayout(side_panel, stretch=1)

        # Cog button row
        cog_row = QHBoxLayout()
        cog_btn = QToolButton()
        cog_btn.setText("⚙")
        cog_btn.setToolTip("Manage schema presets")
        cog_btn.setFont(QFont("", 14))
        cog_btn.clicked.connect(self._open_settings)
        cog_row.addStretch(1)
        cog_row.addWidget(cog_btn)
        side_panel.addLayout(cog_row)

        self.category_label = QLabel("Category: -")
        self.target_label = QLabel("Target: -")
        self.progress_label = QLabel("Progress: -")
        self.zoom_value_label = QLabel("Zoom: 100%")
        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setRange(50, 300)
        self.zoom_slider.setSingleStep(5)
        self.zoom_slider.setValue(100)

        side_panel.addWidget(self.category_label)
        side_panel.addWidget(self.target_label)
        side_panel.addWidget(self.progress_label)
        side_panel.addWidget(self.zoom_value_label)
        side_panel.addWidget(self.zoom_slider)

        self.undo_btn = QPushButton("Undo")
        self.next_btn = QPushButton("Next")
        self.save_csv_btn = QPushButton("Save CSV")
        self.save_session_btn = QPushButton("Save Session")
        self.load_session_btn = QPushButton("Load Session")
        self.finish_btn = QPushButton("Finish")

        side_panel.addWidget(self.undo_btn)
        side_panel.addWidget(self.next_btn)
        side_panel.addWidget(self.save_csv_btn)
        side_panel.addWidget(self.save_session_btn)
        side_panel.addWidget(self.load_session_btn)
        side_panel.addWidget(self.finish_btn)
        side_panel.addStretch(1)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["participant_id", "category", "label", "x", "y", "z"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        root.addWidget(self.table, stretch=2)

        self.undo_btn.clicked.connect(self.on_undo)
        self.next_btn.clicked.connect(self.on_next)
        self.save_csv_btn.clicked.connect(self.on_save_csv)
        self.save_session_btn.clicked.connect(self.on_save_session)
        self.load_session_btn.clicked.connect(self.on_load_session)
        self.finish_btn.clicked.connect(self.close)
        self.table.itemChanged.connect(self.on_table_item_changed)
        self.zoom_slider.valueChanged.connect(self.on_zoom_changed)

    def _open_settings(self):
        dlg = SchemaEditorDialog(settings_path=self._settings_path, parent=self)
        dlg.exec_()


    def refresh_ui(self):
        category, target, progress = self.controller.status_text()
        self.category_label.setText(f"Category: {category}")
        self.target_label.setText(f"Target: {target}")
        self.progress_label.setText(f"Progress: {progress}")

        self._render_scene()
        self._refresh_table()

        finished = self.controller.is_finished
        self.next_btn.setEnabled(not finished)

    def _render_scene(self):
        self.plotter.clear()
        self.plotter.set_background("#101418")

        scene_points = []

        df = self.controller.digitised_points
        if not df.empty:
            for category in sorted(df["category"].unique()):
                subset = df[df["category"] == category]
                points = subset[["x", "y", "z"]].astype(float).to_numpy()
                color = self._category_colors.get(category, "white")
                if len(points) > 0:
                    scene_points.append(points)
                    self.plotter.add_points(points, color=color, point_size=10, render_points_as_spheres=True)

        item = self.controller.current_item
        if item is not None and item.template is not None:
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
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(pid)))
                self.table.setItem(row_idx, 1, QTableWidgetItem(str(row["category"])))
                self.table.setItem(row_idx, 2, QTableWidgetItem(str(row["label"])))
                self.table.setItem(row_idx, 3, QTableWidgetItem(f"{float(row['x']):.6f}"))
                self.table.setItem(row_idx, 4, QTableWidgetItem(f"{float(row['y']):.6f}"))
                self.table.setItem(row_idx, 5, QTableWidgetItem(f"{float(row['z']):.6f}"))
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
            self.progress_label.setText("Progress: waiting for FASTRAK data...")
            return

        self.refresh_ui()
        if self.controller.is_finished:
            self._auto_capture_timer.stop()

    def on_undo(self):
        self.controller.undo()
        self.refresh_ui()
        if not self.controller.is_finished and not self._auto_capture_timer.isActive():
            self._auto_capture_timer.start()

    def on_next(self):
        self.controller.next_target()
        self.refresh_ui()

    def on_save_csv(self):
        pid = getattr(self.controller, "participant_id", "") or "digitisation"
        default_name = f"{pid}_digitisation.csv"
        dig = _load_dig_settings(self._settings_path)
        output_dir = str(Path(dig.get("output_dir", "output")).resolve())
        path, _ = QFileDialog.getSaveFileName(self, "Save digitisation CSV",
                                              str(Path(output_dir) / default_name), "CSV (*.csv)")
        if not path:
            return
        self.controller.save_csv(Path(path))

    def on_save_session(self):
        path, _ = QFileDialog.getSaveFileName(self, "Save session", "", "JSON (*.json)")
        if not path:
            return
        self.controller.save_session(Path(path))

    def on_load_session(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load session", "", "JSON (*.json)")
        if not path:
            return

        try:
            self.controller.load_session(Path(path))
            self.refresh_ui()
            if not self.controller.is_finished and not self._auto_capture_timer.isActive():
                self._auto_capture_timer.start()
        except Exception as exc:
            QMessageBox.critical(self, "Load session failed", str(exc))

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
        super().closeEvent(event)
