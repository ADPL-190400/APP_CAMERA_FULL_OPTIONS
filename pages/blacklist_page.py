"""
Controller cho trang quản lý Blacklist - danh sách người trong "danh sách
đen" (core/blacklist_store.py), tạo entry mới bằng cách chọn nhiều ảnh
Stranger đã phát hiện (ui/dialogs/blacklist_photo_picker_dialog.py), bổ sung
thêm ảnh vào entry đã có từ lịch sử BLACKLIST_ALERT của ĐÚNG người đó.

Trang này KHÔNG tự giữ dữ liệu - mọi đọc/ghi đều qua BlacklistStore.instance(),
tự làm mới khi store phát signal `updated` (thêm/sửa/xoá/bổ sung ảnh từ BẤT
KỲ đâu, kể cả từ chính dialog picker mở ra từ đây)."""
from __future__ import annotations

import os

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

from core.blacklist_store import BlacklistEntry, BlacklistStore
from ui.dialogs.blacklist_photo_picker_dialog import BlacklistPhotoPickerDialog
from ui.ui_menu.i18n import LanguageManager, tr

COL_PHOTO = 0
COL_NAME = 1
COL_NOTE = 2
COL_PHOTOS = 3
COL_STATUS = 4

_THUMB_SIZE = QSize(72, 72)


class BlacklistPage(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        layout = QtWidgets.QVBoxLayout(self)

        header = QtWidgets.QHBoxLayout()
        self.lbl_title = QtWidgets.QLabel()
        self.lbl_title.setStyleSheet("font-size: 18px; font-weight: 600;")
        header.addWidget(self.lbl_title)
        header.addStretch()
        self.btn_new_entry = QtWidgets.QPushButton()
        self.btn_add_photos = QtWidgets.QPushButton()
        self.btn_edit = QtWidgets.QPushButton()
        self.btn_delete = QtWidgets.QPushButton()
        self.btn_refresh = QtWidgets.QPushButton()
        for btn in (self.btn_new_entry, self.btn_add_photos, self.btn_edit, self.btn_delete, self.btn_refresh):
            header.addWidget(btn)
        layout.addLayout(header)

        self.lbl_hint = QtWidgets.QLabel()
        self.lbl_hint.setStyleSheet("color: #7a8aaa; font-size: 11px;")
        self.lbl_hint.setWordWrap(True)
        layout.addWidget(self.lbl_hint)

        self.table = QtWidgets.QTableWidget()
        self.table.setColumnCount(5)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(COL_PHOTO, QtWidgets.QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(COL_PHOTO, _THUMB_SIZE.width() + 14)
        header_view.setSectionResizeMode(COL_NAME, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_NAME, 180)
        header_view.setSectionResizeMode(COL_PHOTOS, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_PHOTOS, 90)
        header_view.setSectionResizeMode(COL_STATUS, QtWidgets.QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(COL_STATUS, 100)
        header_view.setStretchLastSection(False)
        header_view.setSectionResizeMode(COL_NOTE, QtWidgets.QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        self.btn_new_entry.clicked.connect(self._on_new_entry)
        self.btn_add_photos.clicked.connect(self._on_add_photos)
        self.btn_edit.clicked.connect(self._on_edit)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_refresh.clicked.connect(self.reload_entries)
        self.table.itemSelectionChanged.connect(self._update_button_states)
        self.table.itemDoubleClicked.connect(lambda _item: self._on_edit())

        BlacklistStore.instance().updated.connect(self.reload_entries)

        self.reload_entries()
        self._update_button_states()

        self.retranslate_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    # ------------------------------------------------------------------ #
    # i18n
    # ------------------------------------------------------------------ #
    def retranslate_ui(self, _lang: str = "") -> None:
        self.lbl_title.setText(tr("Blacklist"))
        self.lbl_hint.setText(
            tr(
                "People flagged here are matched against every camera with Face Recognition enabled - a match "
                "raises a Blacklist alert (highest priority, shown in red) regardless of known/stranger status."
            )
        )
        self.btn_new_entry.setText(tr("➕  New Entry"))
        self.btn_add_photos.setText(tr("🖼  Add Photos…"))
        self.btn_edit.setText(tr("✎  Edit"))
        self.btn_delete.setText(tr("🗑  Delete"))
        self.btn_refresh.setText(tr("↻  Refresh"))
        self.table.setHorizontalHeaderLabels(
            [tr("Photo"), tr("Name"), tr("Note"), tr("Photos"), tr("Status")]
        )

    # ------------------------------------------------------------------ #
    # Danh sách
    # ------------------------------------------------------------------ #
    def reload_entries(self) -> None:
        selected_id = self._selected_entry_id()
        self.table.setRowCount(0)
        for entry in BlacklistStore.instance().entries:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setRowHeight(row, _THUMB_SIZE.height() + 8)

            photo_item = QtWidgets.QTableWidgetItem()
            pixmap = self._load_thumbnail(entry.photo_paths[0]) if entry.photo_paths else None
            if pixmap is not None:
                photo_item.setIcon(QIcon(pixmap))
            photo_item.setData(Qt.ItemDataRole.UserRole, entry.id)
            self.table.setItem(row, COL_PHOTO, photo_item)

            self.table.setItem(row, COL_NAME, QtWidgets.QTableWidgetItem(entry.name))
            self.table.setItem(row, COL_NOTE, QtWidgets.QTableWidgetItem(entry.note))
            self.table.setItem(row, COL_PHOTOS, QtWidgets.QTableWidgetItem(str(len(entry.embeddings))))
            self.table.setItem(
                row, COL_STATUS, QtWidgets.QTableWidgetItem(tr("Active") if entry.active else tr("Inactive"))
            )

            if entry.id == selected_id:
                self.table.selectRow(row)

        self._update_button_states()

    def _selected_entry_id(self) -> str | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        item = self.table.item(rows[0].row(), COL_PHOTO)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selected_entry(self) -> BlacklistEntry | None:
        entry_id = self._selected_entry_id()
        return BlacklistStore.instance().get_entry(entry_id) if entry_id else None

    def _update_button_states(self) -> None:
        has_selection = self._selected_entry_id() is not None
        self.btn_add_photos.setEnabled(has_selection)
        self.btn_edit.setEnabled(has_selection)
        self.btn_delete.setEnabled(has_selection)

    # ------------------------------------------------------------------ #
    # Hành động
    # ------------------------------------------------------------------ #
    def _on_new_entry(self) -> None:
        self.open_create_dialog()

    def open_create_dialog(self, preselect_event_id: str | None = None) -> None:
        """mode="create" - cầu nối từ Event Log (nút "Đưa vào Blacklist...")
        gọi hàm này với preselect_event_id để mở sẵn dialog kèm đúng ảnh đó
        đã tick chọn - xem pages/event_log_page.py."""
        dialog = BlacklistPhotoPickerDialog(mode="create", preselect_event_id=preselect_event_id, parent=self)
        dialog.exec()  # reload tự động qua BlacklistStore.updated nếu tạo thành công

    def _on_add_photos(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        dialog = BlacklistPhotoPickerDialog(mode="add", entry=entry, parent=self)
        dialog.exec()

    def _on_edit(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        dialog = _EditEntryDialog(entry, parent=self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            BlacklistStore.instance().update_entry(
                entry.id, name=dialog.result_name, note=dialog.result_note, active=dialog.result_active
            )

    def _on_delete(self) -> None:
        entry = self._selected_entry()
        if entry is None:
            return
        reply = QtWidgets.QMessageBox.question(
            self, tr("Delete entry"),
            tr("Delete \"{name}\" from the blacklist? This cannot be undone.").format(name=entry.name),
        )
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            BlacklistStore.instance().delete_entry(entry.id)

    @staticmethod
    def _load_thumbnail(image_path: str) -> QPixmap | None:
        if not image_path or not os.path.exists(image_path):
            return None
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            return None
        return pixmap.scaled(
            _THUMB_SIZE, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
        )


class _EditEntryDialog(QtWidgets.QDialog):
    """Sửa Tên/Ghi chú/Active của 1 entry đã có - dialog nhỏ, không cần .ui
    riêng (cùng phong cách ui/dialogs/ai_settings_dialog.py)."""

    def __init__(self, entry: BlacklistEntry, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Edit Entry"))
        self.result_name = entry.name
        self.result_note = entry.note
        self.result_active = entry.active

        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.edit_name = QtWidgets.QLineEdit(entry.name)
        form.addRow(tr("Name / Label") + " *", self.edit_name)
        self.edit_note = QtWidgets.QLineEdit(entry.note)
        form.addRow(tr("Note"), self.edit_note)
        self.check_active = QtWidgets.QCheckBox(tr("Active (raise alerts when matched)"))
        self.check_active.setChecked(entry.active)
        form.addRow("", self.check_active)
        layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        name = self.edit_name.text().strip()
        if not name:
            QtWidgets.QMessageBox.warning(self, tr("Name required"), tr("Enter a name/label first."))
            return
        self.result_name = name
        self.result_note = self.edit_note.text().strip()
        self.result_active = self.check_active.isChecked()
        self.accept()
