"""
Controller cho liveview_page.ui.

Chỉ có nhiệm vụ HIỂN THỊ HÌNH: lấy danh sách camera đang chạy nền (thật,
qua DeviceManager.instance(), không còn dữ liệu giả) hiện ở panel bên phải
("Running Cameras"); người dùng tick chọn camera nào thì camera đó được
xếp vào 1 ô lưới còn trống để xem hình. Camera đang chạy nền nhưng KHÔNG
được tick thì không tốn công decode/hiển thị (giảm tải), nhưng pipeline
capture + AI của nó (DeviceManager) vẫn tiếp tục chạy bình thường.
"""
from __future__ import annotations

import os
from datetime import datetime

from PyQt6 import uic, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QImage, QPixmap
from PyQt6.QtWidgets import QListWidgetItem

from core.path_manager import BASE_DIR
from core.device_manager import DeviceManager
from core.event_dedup import PresenceDedup
from core.models.camera_device import CameraDevice, DeviceStatus
from ui.ui_menu.models.camera_model import CameraModel
from ui.ui_menu.controllers.grid_controller import GridController, GridMode
from ui.ui_menu.i18n import LanguageManager, tr

# Nhãn hiển thị cho từng loại cảnh báo trong panel SYSTEM ALARMS - key khớp
# với field tương ứng trong dict do CameraPipeline.ai_result_ready phát ra.
_ALARM_KINDS = [
    ("ppe_violation", "⚠ PPE violation"),
    ("fire_alert", "🔥 Fire"),
    ("fall_alert", "🚨 Fall"),
    ("stranger_alert", "🧑‍❓ Stranger"),
]

# Gián đoạn phát hiện ngắn hơn mức này vẫn tính là "đang tiếp diễn" (không
# log lại) - tránh list_alarms/list_realtime_detections nhảy text liên tục
# trong khi 1 cảnh báo/người vẫn còn đó qua nhiều lượt ai_result_ready (bắn
# nhiều lần/giây theo ai_fps_limit). Chỉ log lại khi thực sự biến mất >5s
# rồi xuất hiện lại (1 lượt/sự kiện mới).
_PRESENCE_GRACE_SEC = 5.0
_MAX_LOG_ITEMS = 100

_TR_TEXT_MAP = {
    "lbl_page_title": "Live View",
    "lbl_panel_section_running": "DISPLAY CAMERAS",
    "lbl_panel_section_detections": "REAL-TIME DETECTION",
    "lbl_panel_section_alarms": "SYSTEM ALARMS",
}
_TR_TOOLTIP_MAP = {
    "btn_grid_1x1": "1 column × 1 row  (view 1 camera)",
    "btn_grid_2x3": "2 columns × 3 rows  (6 cameras)",
    "btn_grid_2x4": "2 columns × 4 rows  (8 cameras)",
    "btn_grid_4x4": "4 columns × 4 rows  (16 cameras)",
}


class LiveViewPage(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(BASE_DIR, "ui", "liveview_page.ui")
        uic.loadUi(ui_path, self)

        self.device_manager = DeviceManager.instance()
        self._selected_ids: list[str] = []       # camera được tick "hiện hình", giữ thứ tự chọn
        self._subscribed_ids: set[str] = set()   # camera đang thực sự có card hiển thị (đã subscribe)
        self._models: dict[str, CameraModel] = {}  # device_id -> model đang gắn với 1 card hiện hình

        # Phóng to 1 camera (nút ⛶ trên card) - xem _on_fullscreen_requested.
        self._fullscreen_device_id: str | None = None
        self._pre_fullscreen_mode: GridMode | None = None
        # True trong lúc CHÍNH LiveViewPage đang gọi set_cameras_and_mode() để
        # vào/thoát phóng to - phân biệt với người dùng bấm thẳng nút chọn
        # grid mode (2x3/2x4/4x4/1x1) ở toolbar trong lúc đang phóng to, xem
        # _on_grid_mode_changed().
        self._applying_grid_transition = False

        # Dedup cho 2 panel log (SYSTEM ALARMS / REAL-TIME DETECTION) - key
        # (device_id, "ppe_violation"/... hoặc tên người quen).
        self._alarm_dedup = PresenceDedup(_PRESENCE_GRACE_SEC)
        self._detection_dedup = PresenceDedup(_PRESENCE_GRACE_SEC)

        self.grid_ctrl = GridController(
            live_page=self,
            cameras=[],
            default_mode=GridMode.G2x3,
            parent=self,
        )
        self.grid_ctrl.cameras_rebuilt.connect(self._on_cameras_rebuilt)
        self.grid_ctrl.fullscreen_requested.connect(self._on_fullscreen_requested)
        self.grid_ctrl.grid_mode_changed.connect(self._on_grid_mode_changed)

        self.list_running_cameras.itemChanged.connect(self._on_running_item_changed)
        self.device_manager.devices_changed.connect(self._reload_running_list)
        self.device_manager.device_running_changed.connect(lambda *_: self._reload_running_list())
        self.device_manager.device_status_changed.connect(lambda *_: self._reload_running_list())
        self.device_manager.pipeline_frame_ready.connect(self._on_pipeline_frame)
        self.device_manager.ai_result_ready.connect(self._on_ai_result)

        self._reload_running_list()

        self.retranslate_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    # ------------------------------------------------------------------ #
    # i18n
    # ------------------------------------------------------------------ #
    def retranslate_ui(self, _lang: str = "") -> None:
        for attr, key in _TR_TEXT_MAP.items():
            getattr(self, attr).setText(tr(key))
        for attr, key in _TR_TOOLTIP_MAP.items():
            getattr(self, attr).setToolTip(tr(key))
        self._reload_running_list()

    # ------------------------------------------------------------------ #
    # Danh sách "Running Cameras" (panel bên phải)
    # ------------------------------------------------------------------ #
    def _reload_running_list(self) -> None:
        running = [d for d in self.device_manager.all_devices() if d.is_running]
        running_ids = {d.id for d in running}

        # Camera đang chọn hiện hình mà giờ đã bị Stop -> bỏ khỏi lựa chọn.
        removed = [cid for cid in self._selected_ids if cid not in running_ids]
        for cid in removed:
            self._selected_ids.remove(cid)

        self.list_running_cameras.blockSignals(True)
        self.list_running_cameras.clear()
        for device in running:
            item = QListWidgetItem(tr("{name}   ·  {status}").format(name=device.name, status=tr(device.status.value)))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(
                Qt.CheckState.Checked if device.id in self._selected_ids else Qt.CheckState.Unchecked
            )
            item.setData(Qt.ItemDataRole.UserRole, device.id)
            self.list_running_cameras.addItem(item)
        self.list_running_cameras.blockSignals(False)

        if removed:
            self._apply_selection()

    def _on_running_item_changed(self, item: QListWidgetItem) -> None:
        device_id = item.data(Qt.ItemDataRole.UserRole)
        checked = item.checkState() == Qt.CheckState.Checked
        if checked and device_id not in self._selected_ids:
            self._selected_ids.append(device_id)
        elif not checked and device_id in self._selected_ids:
            self._selected_ids.remove(device_id)
        self._apply_selection()

    def _apply_selection(self) -> None:
        self.grid_ctrl.set_cameras(self._build_selected_models())

    def _build_selected_models(self) -> list[CameraModel]:
        """Dựng lại self._models + trả về list model theo đúng self._selected_ids
        (giữ thứ tự chọn) - dùng chung bởi _apply_selection() và
        _exit_fullscreen()/_on_grid_mode_changed() (thoát phóng to phải khôi
        phục lại đúng toàn bộ camera đang chọn, không chỉ camera vừa phóng to)."""
        models = []
        self._models = {}
        for device_id in self._selected_ids:
            device = self.device_manager.get_device(device_id)
            if device is not None:
                model = self._to_camera_model(device)
                self._models[device_id] = model
                models.append(model)
        return models

    @staticmethod
    def _to_camera_model(device: CameraDevice) -> CameraModel:
        return CameraModel(
            cam_id=device.id,
            name=device.name,
            ip=device.ip_address,
            port=device.port,
            fps=device.fps,
            ai_enabled=device.ai.enabled,
            recording=device.recording.enabled,
            online=device.status == DeviceStatus.ONLINE,
        )

    # ------------------------------------------------------------------ #
    # Subscribe/unsubscribe preview đúng theo camera thực sự đang hiện
    # hình trong lưới (kể cả khi lưới đổi mode 2x3/2x4/4x4 làm rớt bớt ô).
    # ------------------------------------------------------------------ #
    def _on_cameras_rebuilt(self) -> None:
        visible_ids = set(self.grid_ctrl.active_cards.keys())

        for device_id in self._subscribed_ids - visible_ids:
            self.device_manager.unsubscribe_preview(device_id)
        for device_id in visible_ids - self._subscribed_ids:
            self.device_manager.subscribe_preview(device_id)

        self._subscribed_ids = visible_ids

        for card_device_id, card in self.grid_ctrl.active_cards.items():
            card.set_fullscreen(card_device_id == self._fullscreen_device_id)

    # ------------------------------------------------------------------ #
    # Phóng to / thu nhỏ 1 camera (nút ⛶ trên CameraCard) - phóng to hiện
    # camera đó ở mode 1x1 (giống bấm nút "⊞ 1x1" nhưng chỉ áp dụng tạm thời
    # cho riêng camera này); thu nhỏ khôi phục lại đúng danh sách camera đang
    # chọn + grid mode trước khi phóng to.
    # ------------------------------------------------------------------ #
    def _on_fullscreen_requested(self, device_id: str) -> None:
        if self._fullscreen_device_id == device_id:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen(device_id)

    def _enter_fullscreen(self, device_id: str) -> None:
        model = self._models.get(device_id)
        if model is None:
            return
        if self._fullscreen_device_id is None:
            # Chỉ nhớ mode gốc ở lần phóng to đầu tiên.
            self._pre_fullscreen_mode = self.grid_ctrl.current_mode
        self._fullscreen_device_id = device_id
        self._applying_grid_transition = True
        try:
            self.grid_ctrl.set_cameras_and_mode([model], GridMode.G1x1)
        finally:
            self._applying_grid_transition = False

    def _exit_fullscreen(self) -> None:
        restore_mode = self._pre_fullscreen_mode or GridMode.G2x3
        self._fullscreen_device_id = None
        self._pre_fullscreen_mode = None
        self._applying_grid_transition = True
        try:
            self.grid_ctrl.set_cameras_and_mode(self._build_selected_models(), restore_mode)
        finally:
            self._applying_grid_transition = False

    def _on_grid_mode_changed(self, _mode_value: str) -> None:
        if self._applying_grid_transition or self._fullscreen_device_id is None:
            return
        # Người dùng bấm thẳng nút chọn grid mode ở toolbar (2x3/2x4/4x4/1x1)
        # trong lúc đang phóng to 1 camera - GridController đã tự đổi mode và
        # rebuild rồi, nhưng với danh sách camera cũ (lúc phóng to chỉ có 1
        # camera) -> phải khôi phục lại đúng toàn bộ camera đang chọn cho
        # mode người dùng vừa chọn, không để mắc kẹt chỉ hiện 1 camera.
        self._fullscreen_device_id = None
        self._pre_fullscreen_mode = None
        self.grid_ctrl.set_cameras(self._build_selected_models())

    def _on_pipeline_frame(self, device_id: str, image: QImage) -> None:
        card = self.grid_ctrl.active_cards.get(device_id)
        if card is None:
            return
        card.set_frame(QPixmap.fromImage(image))

    def _on_ai_result(self, device_id: str, result: dict) -> None:
        """Camera không hiện hình (không có card) vẫn nhận signal này (AI vẫn
        chạy nền) - log alarm/detection vẫn phải chạy cho camera đó (đúng ý
        "hiện đang có cảnh báo gì" bất kể có đang xem hình hay không), chỉ
        cập nhật CameraModel (badge trên card) nếu camera đang hiện trong lưới."""
        self._log_alarms(device_id, result)
        self._log_detections(device_id, result)

        model = self._models.get(device_id)
        if model is None:
            return
        model.update(
            num_people=result.get("num_people", 0),
            num_in=result.get("num_in", 0),
            num_out=result.get("num_out", 0),
            ppe_violation=result.get("ppe_violation", False),
            fire_alert=result.get("fire_alert", False),
            fall_alert=result.get("fall_alert", False),
            stranger_alert=result.get("stranger_alert", False),
        )

    # ------------------------------------------------------------------ #
    # SYSTEM ALARMS / REAL-TIME DETECTION (panel bên phải) - log các sự
    # kiện rời rạc, KHÔNG phải hiện trạng thái liên tục (khác với CameraModel/
    # CameraCard chỉ hiện badge "đang bật/tắt"). ai_result_ready bắn nhiều
    # lần/giây (theo ai_fps_limit) nên phải dedup, nếu không list sẽ nhảy
    # text liên tục trong khi 1 cảnh báo/người vẫn còn đó.
    # ------------------------------------------------------------------ #
    def _log_alarms(self, device_id: str, result: dict) -> None:
        for key, label in _ALARM_KINDS:
            if result.get(key) and self._alarm_dedup.is_new_occurrence((device_id, key)):
                self._append_log(self.list_alarms, device_id, tr(label), is_alarm=True)

    def _log_detections(self, device_id: str, result: dict) -> None:
        for name in result.get("known_faces", []):
            if self._detection_dedup.is_new_occurrence((device_id, name)):
                self._append_log(self.list_realtime_detections, device_id, tr("👤 Recognized {name}").format(name=name))

    def _append_log(self, list_widget: QtWidgets.QListWidget, device_id: str, text: str, is_alarm: bool = False) -> None:
        device = self.device_manager.get_device(device_id)
        cam_name = device.name if device else device_id
        timestamp = datetime.now().strftime("%H:%M:%S")
        item = QListWidgetItem(f"[{timestamp}] {cam_name}: {text}")
        if is_alarm:
            item.setForeground(QColor("#ff5555"))
        list_widget.insertItem(0, item)
        while list_widget.count() > _MAX_LOG_ITEMS:
            list_widget.takeItem(list_widget.count() - 1)

