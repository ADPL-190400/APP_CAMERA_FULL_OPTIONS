"""
BlacklistPhotoPickerDialog: lưới ảnh cho phép chọn NHIỀU ảnh cùng lúc bằng
mắt (giống chọn ảnh trong thư viện điện thoại) - dùng cho 2 tình huống, cùng
1 dialog (khác NGUỒN ảnh + có/không có form Tên/Ghi chú):

  mode="create" - Tạo entry Blacklist MỚI. Nguồn ảnh = mọi sự kiện
                   STRANGER_ALERT đã ghi nhận (lọc được theo camera/thời
                   gian) - admin tick chọn nhiều ảnh của CÙNG 1 người, đặt
                   tên/ghi chú, xác nhận -> BlacklistStore.create_entry().

  mode="add"     - Bổ sung ảnh vào 1 entry ĐÃ CÓ (luồng "Thêm ảnh từ lịch sử
                   nhận diện" - xem pages/blacklist_page.py). Nguồn ảnh = các
                   sự kiện BLACKLIST_ALERT ĐÃ khớp với ĐÚNG entry đó (lọc
                   theo detail == entry.name - xem ghi chú ở _reload_photos)
                   - không có form Tên/Ghi chú, chỉ chọn + xác nhận ->
                   BlacklistStore.add_embeddings().

Chỉ những sự kiện CÓ embedding đã lưu sẵn (EventStore.get_embedding, xem
core/event_store.py) mới hiện trong lưới - sự kiện cũ từ trước khi tính năng
này tồn tại (chưa có cột embedding) bị loại khỏi danh sách, không detect lại
trên ảnh crop đã lưu (đo thật: ~55% thất bại vì crop quá nhỏ/đã nén JPEG)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

import numpy as np
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QIcon, QPixmap

from core.blacklist_store import BlacklistEntry, BlacklistStore
from core.device_manager import DeviceManager
from core.event_store import EventStore
from core.models.event_record import EventKind
from ui.ui_menu.i18n import tr

_THUMB_SIZE = QSize(140, 79)

_TIME_FILTER_KEYS = ["All time", "Today", "Last 7 days", "Last 30 days"]
_TIME_FILTER_VALUES: list[timedelta | None] = [
    None, timedelta(days=1), timedelta(days=7), timedelta(days=30),
]


class BlacklistPhotoPickerDialog(QtWidgets.QDialog):
    def __init__(self, mode: str, entry: BlacklistEntry | None = None, preselect_event_id: str | None = None, parent=None):
        super().__init__(parent)
        self._mode = mode  # "create" | "add"
        self._entry = entry
        self._preselect_event_id = preselect_event_id
        self.setMinimumSize(720, 560)
        self.setWindowTitle(
            tr("New Blacklist Entry") if mode == "create" else tr("Add Photos to \"{name}\"").format(name=entry.name)
        )

        layout = QtWidgets.QVBoxLayout(self)

        # --- Bộ lọc nguồn ảnh ---
        filter_row = QtWidgets.QHBoxLayout()
        filter_row.addWidget(QtWidgets.QLabel(tr("Camera")))
        self.combo_camera = QtWidgets.QComboBox()
        self.combo_camera.addItem(tr("All cameras"), None)
        for device in DeviceManager.instance().all_devices():
            self.combo_camera.addItem(device.name, device.name)
        self.combo_camera.currentIndexChanged.connect(self._reload_photos)
        filter_row.addWidget(self.combo_camera)

        filter_row.addWidget(QtWidgets.QLabel(tr("Time")))
        self.combo_time = QtWidgets.QComboBox()
        for key in _TIME_FILTER_KEYS:
            self.combo_time.addItem(tr(key))
        self.combo_time.currentIndexChanged.connect(self._reload_photos)
        filter_row.addWidget(self.combo_time)
        filter_row.addStretch()
        layout.addLayout(filter_row)

        # --- Lưới ảnh (chọn nhiều) ---
        self.list_photos = QtWidgets.QListWidget()
        self.list_photos.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.list_photos.setIconSize(_THUMB_SIZE)
        self.list_photos.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.list_photos.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.MultiSelection)
        self.list_photos.setSpacing(8)
        self.list_photos.setMovement(QtWidgets.QListView.Movement.Static)
        layout.addWidget(self.list_photos, stretch=1)

        self.lbl_hint = QtWidgets.QLabel(
            tr("Click to select multiple photos of the SAME person, then confirm below.")
        )
        self.lbl_hint.setStyleSheet("color: #7a8aaa; font-size: 11px;")
        layout.addWidget(self.lbl_hint)

        # --- Form Tên/Ghi chú - CHỈ mode="create" ---
        self.edit_name: QtWidgets.QLineEdit | None = None
        self.edit_note: QtWidgets.QLineEdit | None = None
        if mode == "create":
            form = QtWidgets.QFormLayout()
            self.edit_name = QtWidgets.QLineEdit()
            self.edit_name.setPlaceholderText(tr("e.g. \"Unknown - red jacket 15/8\" or a real name if known"))
            form.addRow(tr("Name / Label") + " *", self.edit_name)
            self.edit_note = QtWidgets.QLineEdit()
            self.edit_note.setPlaceholderText(tr("Reason for adding to the blacklist (optional)"))
            form.addRow(tr("Note"), self.edit_note)
            layout.addLayout(form)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_confirm)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._reload_photos()

    # ------------------------------------------------------------------ #
    # Nạp ảnh theo bộ lọc
    # ------------------------------------------------------------------ #
    def _reload_photos(self) -> None:
        self.list_photos.clear()
        camera_name = self.combo_camera.currentData()
        since_delta = _TIME_FILTER_VALUES[self.combo_time.currentIndex()]
        since = datetime.now() - since_delta if since_delta is not None else None

        if self._mode == "create":
            kind = EventKind.STRANGER_ALERT
        else:
            kind = EventKind.BLACKLIST_ALERT

        events = EventStore.instance().query_events(
            camera_name=camera_name, kind=kind, since=since, limit=200
        )
        if self._mode == "add":
            # BLACKLIST_ALERT không lưu trực tiếp entry_id - lọc theo
            # detail == tên entry (xem docstring module) - đủ dùng vì detail
            # được ghi ĐÚNG lúc alert khớp entry này (CameraPipeline._capture_face_events).
            events = [e for e in events if e.detail == self._entry.name]

        store = EventStore.instance()
        preselect_item = None
        for event in events:
            embedding = store.get_embedding(event.id)
            if not embedding:
                continue  # sự kiện cũ chưa có embedding (trước khi tính năng này tồn tại) - bỏ qua
            pixmap = self._load_thumbnail(event.image_path)
            item = QtWidgets.QListWidgetItem()
            if pixmap is not None:
                item.setIcon(QIcon(pixmap))
            item.setText(self._format_ts(event.timestamp))
            item.setData(Qt.ItemDataRole.UserRole, event.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, event.image_path)
            self.list_photos.addItem(item)
            if event.id == self._preselect_event_id:
                preselect_item = item

        if preselect_item is not None:
            preselect_item.setSelected(True)
            self.list_photos.scrollToItem(preselect_item)

    # ------------------------------------------------------------------ #
    # Xác nhận
    # ------------------------------------------------------------------ #
    def _on_confirm(self) -> None:
        selected_items = self.list_photos.selectedItems()
        if not selected_items:
            QtWidgets.QMessageBox.warning(self, tr("No photos selected"), tr("Select at least 1 photo first."))
            return

        embeddings, photo_paths = self._load_embeddings(selected_items)
        if not embeddings:
            QtWidgets.QMessageBox.warning(
                self, tr("No usable photos"), tr("The selected photos have no usable face data.")
            )
            return

        if self._mode == "create":
            name = self.edit_name.text().strip()
            if not name:
                QtWidgets.QMessageBox.warning(self, tr("Name required"), tr("Enter a name/label first."))
                return
            note = self.edit_note.text().strip()
            BlacklistStore.instance().create_entry(name, note, embeddings, photo_paths)
        else:
            BlacklistStore.instance().add_embeddings(self._entry.id, embeddings, photo_paths)

        self.accept()

    @staticmethod
    def _load_embeddings(items: list[QtWidgets.QListWidgetItem]) -> tuple[list[np.ndarray], list[str]]:
        """Trả về 2 danh sách CÙNG độ dài, CÙNG thứ tự (embeddings[i] trích
        từ ảnh photo_paths[i]) - xem BlacklistStore.create_entry/add_embeddings."""
        store = EventStore.instance()
        embeddings: list[np.ndarray] = []
        photo_paths: list[str] = []
        for item in items:
            event_id = item.data(Qt.ItemDataRole.UserRole)
            blob = store.get_embedding(event_id)
            if not blob:
                continue
            embeddings.append(np.frombuffer(blob, dtype=np.float32))
            photo_paths.append(item.data(Qt.ItemDataRole.UserRole + 1) or "")
        return embeddings, photo_paths

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

    @staticmethod
    def _format_ts(ts: str) -> str:
        try:
            return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts
