"""
Controller cho event_log_page.ui - danh sách toàn bộ sự kiện cảnh báo
(PPE/Fire/Fall/Stranger) kèm ảnh bằng chứng, đọc từ EventStore (persist qua
SQLite - xem core/event_store.py). Ảnh được CameraPipeline lưu ngay lúc
alert được xác nhận (streak/dedup), không phụ thuộc trang này có đang mở
hay không.

Phân trang (_PAGE_SIZE/trang): lọc + LIMIT/OFFSET được đẩy xuống tầng
EventStore (SQL, có index) thay vì tự lọc/tải hết bằng Python như bản cũ -
chi phí mỗi lần load 1 trang không phụ thuộc TỔNG số event đã có trong log,
chỉ phụ thuộc _PAGE_SIZE (kể cả việc decode ảnh thumbnail, xem reload_events)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from PyQt6 import uic, QtWidgets
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtWidgets import QHeaderView, QTableWidgetItem, QDialog, QVBoxLayout, QLabel

from core.device_manager import DeviceManager
from core.event_store import EventStore
from core.models.event_record import EventKind, EVENT_KIND_LABELS
from core.path_manager import BASE_DIR
from ui.ui_menu.i18n import LanguageManager, tr

COL_IMAGE = 0
COL_TIME = 1
COL_CAMERA = 2
COL_KIND = 3
COL_DETAIL = 4

_THUMB_SIZE = QSize(158, 89)  # +~20% nữa so với 132x74 (gốc 96x54), vẫn giữ đúng tỉ lệ 16:9

# Chiều rộng cột (px) - Fixed cho COL_IMAGE (đúng khít _THUMB_SIZE, không
# cần người dùng tự kéo), Interactive cho các cột nội dung ngắn/vừa (vẫn
# kéo tay chỉnh lại được nếu muốn), COL_DETAIL (cột cuối) tự giãn lấp phần
# còn lại nhờ horizontalHeaderStretchLastSection (xem event_log_page.ui) -
# không cần khai báo width riêng cho cột đó.
_COL_WIDTHS = {
    COL_IMAGE: _THUMB_SIZE.width() + 14,
    COL_TIME: 150,
    COL_CAMERA: 150,
    COL_KIND: 130,
}

# Danh sách khớp ĐÚNG thứ tự item trong combo_filter_time/combo_filter_kind
# (xem retranslate_ui) - dùng INDEX làm cầu nối thay vì currentText(), vì
# text hiển thị của item bị tr() dịch theo ngôn ngữ hiện tại nên không còn
# dùng làm key tra cứu được (bug đã gặp ở nhiều combobox khác trong app).
_TIME_FILTER_KEYS = ["All time", "Today", "Last 7 days", "Last 30 days"]
_TIME_FILTER_VALUES: list[timedelta | None] = [
    None, timedelta(days=1), timedelta(days=7), timedelta(days=30),
]

_KIND_FILTER_KEYS = [
    "All types", "PPE Violation", "Fire / Smoke", "Fall", "Stranger", "Check-in", "Check-out", "Overcrowding",
    "Recognized", "Crowd Density",
]
_KIND_FILTER_VALUES: list[EventKind | None] = [
    None,
    EventKind.PPE_VIOLATION,
    EventKind.FIRE_ALERT,
    EventKind.FALL_ALERT,
    EventKind.STRANGER_ALERT,
    EventKind.FACE_CHECKIN,
    EventKind.FACE_CHECKOUT,
    EventKind.OCCUPANCY_ALERT,
    EventKind.FACE_RECOGNIZED,
    EventKind.CROWD_ALERT,
]

_PAGE_SIZE = 50


class EventLogPage(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(BASE_DIR, "ui", "event_log_page.ui")
        uic.loadUi(ui_path, self)

        self.device_manager = DeviceManager.instance()
        self.event_store = EventStore.instance()
        self._current_page = 0  # reset về 0 mỗi khi đổi filter - xem _on_filter_changed

        self.table_events.setIconSize(_THUMB_SIZE)
        header = self.table_events.horizontalHeader()
        header.setSectionResizeMode(COL_IMAGE, QHeaderView.ResizeMode.Fixed)
        for col in (COL_TIME, COL_CAMERA, COL_KIND):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        for col, width in _COL_WIDTHS.items():
            self.table_events.setColumnWidth(col, width)
        self.table_events.setMouseTracking(True)
        self.table_events.cellEntered.connect(self._on_cell_entered)
        self.table_events.itemClicked.connect(self._on_row_clicked)
        self.btn_refresh_event_log.clicked.connect(self.reload_events)
        self.combo_filter_camera.currentIndexChanged.connect(self._on_filter_changed)
        self.combo_filter_kind.currentIndexChanged.connect(self._on_filter_changed)
        self.combo_filter_time.currentIndexChanged.connect(self._on_filter_changed)
        self.btn_prev_page.clicked.connect(self._on_prev_page)
        self.btn_next_page.clicked.connect(self._on_next_page)

        self.device_manager.devices_changed.connect(self._reload_camera_filter)
        # event_added chạy từ thread của CameraPipeline nhưng Qt tự queue
        # sang main thread khi slot ở đây (giống ai_result_ready). CHỈ tự
        # refresh khi đang xem trang mới nhất (trang 0) - event mới sẽ đẩy
        # lệch offset của các trang cũ hơn, refresh giữa chừng lúc đang xem
        # trang cũ sẽ làm nhảy/lặp dòng, gây khó chịu hơn là hữu ích.
        self.event_store.event_added.connect(self._on_event_added)

        self._reload_camera_filter()
        self.reload_events()

        self.retranslate_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    # ------------------------------------------------------------------ #
    # i18n
    # ------------------------------------------------------------------ #
    def retranslate_ui(self, _lang: str = "") -> None:
        self.lbl_title.setText(tr("Event Log"))
        self.btn_refresh_event_log.setText(tr("↻  Refresh"))
        self.btn_prev_page.setText(tr("◀ Prev"))
        self.btn_next_page.setText(tr("Next ▶"))
        self.table_events.setHorizontalHeaderLabels(
            [tr("Image"), tr("Time"), tr("Camera"), tr("Event Type"), tr("Detail")]
        )
        self.combo_filter_camera.setItemText(0, tr("All cameras"))
        for combo, keys in (
            (self.combo_filter_kind, _KIND_FILTER_KEYS),
            (self.combo_filter_time, _TIME_FILTER_KEYS),
        ):
            current = combo.currentIndex()
            combo.blockSignals(True)
            for i, key in enumerate(keys):
                combo.setItemText(i, tr(key))
            combo.blockSignals(False)
            combo.setCurrentIndex(current)
        self.reload_events()

    # ------------------------------------------------------------------ #
    # Filters
    # ------------------------------------------------------------------ #
    def _reload_camera_filter(self) -> None:
        current = self.combo_filter_camera.currentText()
        self.combo_filter_camera.blockSignals(True)
        self.combo_filter_camera.clear()
        self.combo_filter_camera.addItem(tr("All cameras"))
        for device in self.device_manager.all_devices():
            self.combo_filter_camera.addItem(device.name)
        idx = self.combo_filter_camera.findText(current)
        self.combo_filter_camera.setCurrentIndex(idx if idx >= 0 else 0)
        self.combo_filter_camera.blockSignals(False)

    # ------------------------------------------------------------------ #
    # Table / phân trang
    # ------------------------------------------------------------------ #
    def _current_filters(self) -> dict:
        camera_filter = (
            self.combo_filter_camera.currentText() if self.combo_filter_camera.currentIndex() != 0 else None
        )
        kind_filter = _KIND_FILTER_VALUES[self.combo_filter_kind.currentIndex()]
        time_delta = _TIME_FILTER_VALUES[self.combo_filter_time.currentIndex()]
        since = datetime.now() - time_delta if time_delta is not None else None
        return {"camera_name": camera_filter, "kind": kind_filter, "since": since}

    def _on_filter_changed(self) -> None:
        self._current_page = 0
        self.reload_events()

    def _on_prev_page(self) -> None:
        if self._current_page > 0:
            self._current_page -= 1
            self.reload_events()

    def _on_next_page(self) -> None:
        total = self.event_store.count_events(**self._current_filters())
        if (self._current_page + 1) * _PAGE_SIZE < total:
            self._current_page += 1
            self.reload_events()

    def _on_event_added(self, _record) -> None:
        if self._current_page == 0:
            self.reload_events()

    def reload_events(self) -> None:
        filters = self._current_filters()
        total = self.event_store.count_events(**filters)
        total_pages = max(1, (total + _PAGE_SIZE - 1) // _PAGE_SIZE)
        self._current_page = min(self._current_page, total_pages - 1)
        events = self.event_store.query_events(
            **filters, limit=_PAGE_SIZE, offset=self._current_page * _PAGE_SIZE
        )

        self.lbl_event_count.setText(tr("{n} events").format(n=total))
        self.lbl_page_info.setText(
            tr("Page {page} / {total}").format(page=self._current_page + 1, total=total_pages)
        )
        self.btn_prev_page.setEnabled(self._current_page > 0)
        self.btn_next_page.setEnabled(self._current_page + 1 < total_pages)

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
                row, COL_KIND, QTableWidgetItem(tr(EVENT_KIND_LABELS.get(event.kind, event.kind.value)))
            )
            table.setItem(row, COL_DETAIL, QTableWidgetItem(event.detail))

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
        dialog.setWindowTitle(tr("Evidence Image"))
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
    def _format_ts(ts: str) -> str:
        try:
            return datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            return ts
