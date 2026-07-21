"""
Controller cho event_log_page.ui - danh sách toàn bộ sự kiện cảnh báo
(PPE/Fire/Fall/Stranger) kèm ảnh bằng chứng, đọc từ EventStore (persist qua
data/events.json - xem core/event_store.py). Ảnh được CameraPipeline lưu
ngay lúc alert được xác nhận (streak/dedup), không phụ thuộc trang này có
đang mở hay không.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from PyQt6 import uic, QtWidgets
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QTableWidgetItem, QDialog, QVBoxLayout, QLabel

from core.device_manager import DeviceManager
from core.event_store import EventStore
from core.models.event_record import EventKind, EVENT_KIND_LABELS
from core.path_manager import BASE_DIR

COL_IMAGE = 0
COL_TIME = 1
COL_CAMERA = 2
COL_KIND = 3

_THUMB_SIZE = QSize(96, 54)

_TIME_FILTERS: dict[str, timedelta | None] = {
    "Toàn bộ thời gian": None,
    "Hôm nay": timedelta(days=1),
    "7 ngày gần đây": timedelta(days=7),
    "30 ngày gần đây": timedelta(days=30),
}

_KIND_FILTERS: dict[str, EventKind | None] = {
    "Tất cả loại": None,
    "PPE vi phạm": EventKind.PPE_VIOLATION,
    "Cháy / Khói": EventKind.FIRE_ALERT,
    "Té ngã": EventKind.FALL_ALERT,
    "Người lạ": EventKind.STRANGER_ALERT,
}


class EventLogPage(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(BASE_DIR, "ui", "event_log_page.ui")
        uic.loadUi(ui_path, self)

        self.device_manager = DeviceManager.instance()
        self.event_store = EventStore.instance()

        self.table_events.setIconSize(_THUMB_SIZE)
        self.table_events.setMouseTracking(True)
        self.table_events.cellEntered.connect(self._on_cell_entered)
        self.table_events.itemClicked.connect(self._on_row_clicked)
        self.btn_refresh_event_log.clicked.connect(self.reload_events)
        self.combo_filter_camera.currentIndexChanged.connect(self.reload_events)
        self.combo_filter_kind.currentIndexChanged.connect(self.reload_events)
        self.combo_filter_time.currentIndexChanged.connect(self.reload_events)

        self.device_manager.devices_changed.connect(self._reload_camera_filter)
        # event_added chạy từ thread của CameraPipeline nhưng Qt tự queue
        # sang main thread khi slot ở đây (giống ai_result_ready).
        self.event_store.event_added.connect(lambda _record: self.reload_events())

        self._reload_camera_filter()
        self.reload_events()

    # ------------------------------------------------------------------ #
    # Filters
    # ------------------------------------------------------------------ #
    def _reload_camera_filter(self) -> None:
        current = self.combo_filter_camera.currentText()
        self.combo_filter_camera.blockSignals(True)
        self.combo_filter_camera.clear()
        self.combo_filter_camera.addItem("Tất cả camera")
        for device in self.device_manager.all_devices():
            self.combo_filter_camera.addItem(device.name)
        idx = self.combo_filter_camera.findText(current)
        self.combo_filter_camera.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_filter_camera.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Table
    # ------------------------------------------------------------------ #
    def reload_events(self) -> None:
        events = self.event_store.all_events()

        camera_filter = self.combo_filter_camera.currentText()
        if camera_filter and camera_filter != "Tất cả camera":
            events = [e for e in events if e.camera_name == camera_filter]

        kind_filter = _KIND_FILTERS.get(self.combo_filter_kind.currentText())
        if kind_filter is not None:
            events = [e for e in events if e.kind == kind_filter]

        time_delta = _TIME_FILTERS.get(self.combo_filter_time.currentText())
        if time_delta is not None:
            cutoff = datetime.now() - time_delta
            events = [e for e in events if self._parse_ts(e.timestamp) >= cutoff]

        self.lbl_event_count.setText(f"{len(events)} sự kiện")

        table = self.table_events
        table.setRowCount(0)
        for event in events:
            row = table.rowCount()
            table.insertRow(row)
            table.setRowHeight(row, _THUMB_SIZE.height() + 8)

            img_item = QTableWidgetItem()
            pixmap = self._load_thumbnail(event.image_path)
            if pixmap is not None:
                img_item.setIcon(QIcon(pixmap))
            img_item.setData(Qt.ItemDataRole.UserRole, event.image_path)
            table.setItem(row, COL_IMAGE, img_item)

            table.setItem(row, COL_TIME, QTableWidgetItem(self._format_ts(event.timestamp)))
            table.setItem(row, COL_CAMERA, QTableWidgetItem(event.camera_name))
            table.setItem(
                row, COL_KIND, QTableWidgetItem(EVENT_KIND_LABELS.get(event.kind, event.kind.value))
            )

    def _on_cell_entered(self, row: int, column: int) -> None:
        cursor = Qt.CursorShape.PointingHandCursor if column == COL_IMAGE else Qt.CursorShape.ArrowCursor
        self.table_events.viewport().setCursor(cursor)

    def _on_row_clicked(self, item: QTableWidgetItem) -> None:
        if item.column() != COL_IMAGE:
            return
        image_path = item.data(Qt.ItemDataRole.UserRole)
        if not image_path or not os.path.exists(image_path):
            return
        self._show_image_dialog(image_path)

    def _show_image_dialog(self, image_path: str) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Ảnh bằng chứng")
        layout = QVBoxLayout(dialog)
        label = QLabel()
        pixmap = QPixmap(image_path)
        if not pixmap.isNull():
            pixmap = pixmap.scaled(
                900, 700, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
        label.setPixmap(pixmap)
        layout.addWidget(label)
        dialog.exec()

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
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
    def _parse_ts(ts: str) -> datetime:
        try:
            return datetime.fromisoformat(ts)
        except ValueError:
            return datetime.min

    @staticmethod
    def _format_ts(ts: str) -> str:
        try:
            return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts
