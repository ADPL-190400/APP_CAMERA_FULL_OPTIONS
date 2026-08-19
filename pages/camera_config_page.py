"""
Controller cho camera_config_page.ui.

Cũng như device_management_page, trang này KHÔNG tự giữ dữ liệu camera.
Mọi đọc/ghi đều qua DeviceManager.instance() -> sửa ở đây thì
device_management_page tự cập nhật lại (và ngược lại) nhờ signal, không
cần gọi qua lại giữa 2 trang.
"""
from __future__ import annotations

import dataclasses
import json
import os

from PyQt6 import uic, QtWidgets
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QMessageBox, QFileDialog, QListWidgetItem

from core.path_manager import BASE_DIR
from core.device_manager import DeviceManager
from core.known_faces_store import KnownFacesStore
from core.network_utils import is_ip_camera_reachable
from scr import Web_API
from core.models.camera_device import (
    CameraDevice,
    DeviceStatus,
    AIConfig,
    RecordingConfig,
    OverlayConfig,
    AdvancedConfig,
)
from ui.dialogs.roi_editor_dialog import ROIEditorDialog
from ui.dialogs.trigger_rule_dialog import TriggerRuleDialog
from ui.ui_menu.i18n import LanguageManager, tr

_TR_TEXT_MAP = {
    "lbl_camera_name": "Camera Name",
    "lbl_camera_id": "Camera ID",
    "lbl_vendor": "Vendor",
    "lbl_ip_address": "IP Address",
    "lbl_stream_url": "Stream URL",
    "lbl_substream_url": "Substream URL",
    "check_use_substream": "Prefer the substream",
    "lbl_status": "Status",
    "lbl_mac_address": "MAC Address",
    "lbl_resolution": "Resolution",
    "lbl_fps": "FPS",
    "lbl_preview_title": "Camera Preview",
    "btn_refresh_camera": "↻  Refresh",
    "btn_test_connection": "Test Connection",
    "btn_start_device": "▶  Start",
    "btn_stop_device": "■  Stop",
    "lbl_enable_ai": "Enable AI",
    "lbl_ai_fps_limit": "AI FPS Limit",
    "lbl_inference_quality": "Detection Quality",
    "check_enable_counting": "Count people in/out  (requires drawing a Counting Line)",
    "check_enable_occupancy": "Monitor current occupancy  (ROI recommended)",
    "lbl_occupancy_threshold": "Alert if occupancy exceeds",
    "lbl_crowd_heatmap_threshold": "Alert on localized crowd density",
    "check_enable_ppe": "PPE monitoring  (requires drawing an ROI)",
    "check_enable_fire": "Fire Detection",
    "check_enable_fall": "Fall Detection",
    "check_enable_face_recognition": "Face recognition - alert on strangers / recognize known people",
    "lbl_stranger_repeat_mode": "Repeat notifications",
    "btn_refresh_known_faces": "🔄  Refresh Known Faces",
    "btn_open_pipeline_config": "⚙  Open Pipeline Config",
    "lbl_roi_preview_placeholder": "Click \"Open ROI Editor…\" to draw ROI/Counting Line directly on the camera feed",
    "btn_open_roi_editor": "✏  Open ROI Editor…",
    "lbl_enable_trigger": "Enable Trigger",
    "btn_add_trigger_rule": "＋  Add Rule",
    "btn_edit_trigger_rule": "✏  Edit Rule",
    "btn_delete_trigger_rule": "🗑  Delete Rule",
    "lbl_trigger_note": "Double-click a rule to edit it in the Rule Editor dialog.",
    "lbl_enable_recording": "Enable Recording",
    "lbl_recording_mode": "Recording Mode",
    "lbl_save_path": "Save Path",
    "btn_browse_save_path": "Browse…",
    "lbl_retention_days": "Retention (days)",
    "btn_open_schedule_config": "📅  Schedule Config…",
    "lbl_show_bbox": "Show Bounding Box",
    "lbl_show_label": "Show Label",
    "lbl_show_confidence": "Show Confidence",
    "lbl_show_roi": "Show ROI",
    "lbl_show_tracking_id": "Show Tracking ID",
    "btn_open_overlay_settings": "🎨  Overlay Settings…",
    "lbl_frame_queue_size": "Frame Queue Size",
    "lbl_reconnect_timeout": "Reconnect Timeout (s)",
    "lbl_decoder_backend": "Decoder Backend",
    "lbl_hw_accel": "Hardware Acceleration",
    "lbl_gpu_device": "GPU Device",
    "btn_save": "💾  Save",
    "btn_apply": "✔  Apply",
    "btn_reset": "↺  Reset",
    "btn_export_config": "↑  Export Config",
    "btn_import_config": "↓  Import Config",
}
_TR_TITLE_MAP = {
    "group_basic_identity": "Camera Identity",
    "group_basic_connection": "Connection",
    "group_basic_stream": "Stream Settings",
    "group_ai_enable": "AI Processing",
    "group_ai_features": "AI Features",
    "group_roi_list": "Regions of Interest",
    "group_counting_line": "Counting Line (count people in/out)",
    "group_trigger_rules": "Trigger Rules",
    "group_recording": "Recording Settings",
    "group_overlay": "Overlay Visibility",
    "group_adv_pipeline": "Pipeline",
    "group_adv_hardware": "Hardware & Decoder",
}
_TR_TOOLTIP_MAP = {
    "combo_stranger_repeat_mode": (
        "How to handle the SAME person (known or stranger) being seen again after briefly turning away/"
        "being partly hidden. \"Notify once\" only alerts/logs the first time until they leave the frame "
        "entirely. \"Repeat after grace period\" alerts/logs again if they go quiet for a while and get "
        "reconfirmed - same behavior as PPE/Fire/Fall/Overcrowding."
    ),
    "edit_camera_id": (
        "App-generated internal ID used as the lookup key for this camera in DeviceManager - not editable, "
        "and NOT the camera_id sent to the web server (see the \"MAC Address\" field below for that)."
    ),
    "edit_substream_url": (
        "Low-resolution substream used for AI + live preview instead of the Stream URL - reduces bandwidth/"
        "decode CPU, doesn't affect AI accuracy since frames are auto-resized to <=640px anyway. Leave empty "
        "to use the Stream URL (mainstream) as before."
    ),
    "check_use_substream": (
        "Uncheck to temporarily fall back to the Stream URL (mainstream) without deleting the saved "
        "Substream URL."
    ),
    "edit_mac_address": (
        "This is the actual camera_id sent to the web server (matches the camera already registered there "
        "by MAC, DIFFERENT from the internal \"Camera ID\" above) - auto-filled when scanning ARP (IP camera), "
        "or entered manually if scanning isn't possible / USB camera. Leave empty = events/attendance from "
        "this camera won't be sent to the web."
    ),
    "combo_resolution": (
        "Limits the maximum DISPLAY resolution (does not change the resolution AI uses for detection). If "
        "the source camera's resolution is higher than the selected value, it will be downscaled before "
        "display to reduce lag - choose 4K = no limit. For USB cameras, this also requests that the camera "
        "capture at this exact resolution (requires Stop/Start to take effect); for IP/RTSP, the camera "
        "server decides this and it can't be set here."
    ),
    "spin_fps": (
        "Limits the DISPLAY frame rate (frames per second sent for viewing) - does not limit the AI "
        "processing rate (see \"AI FPS Limit\" in the AI tab). Takes effect immediately, no need to Stop/Start."
    ),
    "combo_inference_quality": (
        "Image size fed into the AI model (pose/PPE/fire/fall) - does not affect the display resolution. "
        "Fast/Balanced run much smoother when AI runs on multiple cameras at once, at the cost of slightly "
        "lower accuracy for small or distant people/objects."
    ),
    "list_roi": "View-only list - draw/edit/delete via the ROI Editor",
    "spin_occupancy_threshold": (
        "0 = no alert (unlimited). When the number of people currently in view goes above this number, an "
        "alert is raised (SYSTEM ALARMS + Event Log) - it will not repeat while the count stays above the "
        "threshold continuously, only again after it drops back down and exceeds it again."
    ),
    "spin_crowd_heatmap_threshold": (
        "0 = off. Unlike \"Alert if occupancy exceeds\" (total headcount), this tracks LOCALIZED density - "
        "people clustering in the same small area of the ROI, even if the total count is still under the "
        "occupancy limit. Builds up the longer people linger in one spot, cools down a few seconds after "
        "they leave. When set above 0, a heatmap overlay is also shown on the live view."
    ),
}
_TR_COMBO_ITEMS = {
    "combo_vendor": ["Unknown", "Hikvision", "Dahua", "Axis", "Bosch", "Other"],
    "combo_status": ["Online", "Offline", "Error"],
    "combo_inference_quality": ["Fast (320px)", "Balanced (480px)", "Accurate (640px)"],
    "combo_recording_mode": ["Continuous", "On Motion", "On Trigger", "Scheduled"],
    "combo_gpu_device": ["GPU 0 (default)", "GPU 1", "CPU Fallback"],
    "combo_stranger_repeat_mode": ["Notify once per visit", "Repeat after grace period"],
}
_TR_TAB_TITLES = ["Basic", "AI", "ROI", "Trigger", "Recording", "Overlay", "Advanced"]


class CameraConfigPage(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(BASE_DIR, "ui", "camera_config_page.ui")
        uic.loadUi(ui_path, self)

        self.device_manager = DeviceManager.instance()
        self.current_device_id: str | None = None
        self._preview_active: bool = False  # trang này có đang subscribe xem preview không

        self._setup_sidebar()
        self._connect_action_bar()
        self._connect_basic_tab()
        self._connect_ai_tab()
        self._connect_roi_tab()
        self._connect_trigger_tab()
        self._connect_recording_tab()
        self._connect_overlay_tab()
        self._connect_device_manager_signals()

        self._set_form_enabled(False)
        self.reload_sidebar()

        self.retranslate_ui()
        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    # ------------------------------------------------------------------ #
    # i18n
    # ------------------------------------------------------------------ #
    def retranslate_ui(self, _lang: str = "") -> None:
        for attr, key in _TR_TEXT_MAP.items():
            getattr(self, attr).setText(tr(key))
        for attr, key in _TR_TITLE_MAP.items():
            getattr(self, attr).setTitle(tr(key))
        for attr, key in _TR_TOOLTIP_MAP.items():
            getattr(self, attr).setToolTip(tr(key))
        self.spin_occupancy_threshold.setSpecialValueText(tr("Off"))
        self.spin_crowd_heatmap_threshold.setSpecialValueText(tr("Off"))
        self.edit_search_camera.setPlaceholderText(tr("Search camera…"))
        for attr, keys in _TR_COMBO_ITEMS.items():
            combo = getattr(self, attr)
            current = combo.currentIndex()
            combo.blockSignals(True)
            for i, key in enumerate(keys):
                combo.setItemText(i, tr(key))
            combo.blockSignals(False)
            combo.setCurrentIndex(current)
        for i, key in enumerate(_TR_TAB_TITLES):
            self.tab_camera_config.setTabText(i, tr(key))
        self.reload_sidebar()
        # Trạng thái động phụ thuộc device đang chọn - vẽ lại nếu có.
        if self.current_device_id:
            device = self.device_manager.get_device(self.current_device_id)
            if device is not None:
                self.lbl_counting_line_status.setText(
                    tr("Set: {value}").format(value=device.counting_line) if device.counting_line else tr("Not set")
                )
        else:
            self.lbl_counting_line_status.setText(tr("Not set"))
        self._on_known_faces_updated()
        if self.btn_toggle_preview.isChecked():
            self.btn_toggle_preview.setText(tr("■  Close Preview"))
        else:
            self.btn_toggle_preview.setText(tr("▶  Open Preview"))
            self.lbl_preview_placeholder.setText(tr("No Preview"))

    # ------------------------------------------------------------------ #
    # Sidebar (danh sách camera bên trái)
    # ------------------------------------------------------------------ #
    def _setup_sidebar(self) -> None:
        self.list_camera_config.itemClicked.connect(self._on_sidebar_item_clicked)
        self.edit_search_camera.textChanged.connect(lambda _text: self.reload_sidebar())
        self.btn_refresh_camera.clicked.connect(self.reload_sidebar)

    def reload_sidebar(self) -> None:
        keyword = self.edit_search_camera.text().strip().lower()
        self.list_camera_config.clear()

        for device in self.device_manager.all_devices():
            if keyword and keyword not in device.name.lower() and keyword not in device.ip_address.lower():
                continue
            item = QListWidgetItem(tr("{name}   ·  {status}").format(name=device.name, status=tr(device.status.value)))
            item.setData(Qt.ItemDataRole.UserRole, device.id)
            self.list_camera_config.addItem(item)
            if device.id == self.current_device_id:
                item.setSelected(True)

    def _on_sidebar_item_clicked(self, item: QListWidgetItem) -> None:
        self.load_device(item.data(Qt.ItemDataRole.UserRole))

    def _connect_device_manager_signals(self) -> None:
        self.device_manager.devices_changed.connect(self.reload_sidebar)
        self.device_manager.device_status_changed.connect(lambda *_: self.reload_sidebar())
        self.device_manager.device_running_changed.connect(self._on_running_changed)
        self.device_manager.pipeline_frame_ready.connect(self._on_preview_frame)
        self.device_manager.pipeline_error.connect(self._on_preview_error)
        self.device_manager.ai_result_ready.connect(self._on_ai_result)

    def _on_running_changed(self, device_id: str, is_running: bool) -> None:
        if device_id != self.current_device_id:
            return
        device = self.device_manager.get_device(device_id)
        if device is None:
            return
        self._combo_set_canonical(self.combo_status, "combo_status", device.status.value)
        # Camera có thể được Stop từ device_management_page (không qua trang
        # này) -> nếu đang xem preview, pipeline không còn nữa thì phải tắt
        # theo, không thể tiếp tục "xem" 1 pipeline đã bị huỷ.
        if not is_running and self._preview_active:
            self.btn_toggle_preview.setChecked(False)

    # ------------------------------------------------------------------ #
    # Load / Save form <-> CameraDevice
    # ------------------------------------------------------------------ #
    def load_device(self, device_id: str) -> None:
        """Gọi bởi MainWindow khi nhận signal
        device_management_page.open_camera_config(device_id), hoặc khi
        người dùng click 1 camera trong sidebar."""
        device = self.device_manager.get_device(device_id)
        if device is None:
            return
        if self.current_device_id != device_id and self._preview_active:
            # Đổi sang camera khác -> tắt preview đang xem của camera cũ,
            # bắt người dùng bấm "Open Preview" lại cho camera mới (tránh
            # nhầm lẫn đang xem nhầm camera).
            self.btn_toggle_preview.setChecked(False)
        self.current_device_id = device_id
        self._apply_device_to_form(device)
        self._set_form_enabled(True)
        self.reload_sidebar()

    def _set_form_enabled(self, enabled: bool) -> None:
        self.tab_camera_config.setEnabled(enabled)
        self.btn_save.setEnabled(enabled)
        self.btn_apply.setEnabled(enabled)
        self.btn_reset.setEnabled(enabled)
        self.btn_export_config.setEnabled(enabled)

    @staticmethod
    def _combo_set_canonical(combo: QtWidgets.QComboBox, attr: str, value: str) -> None:
        """Chọn item theo GIÁ TRỊ TIẾNG ANH GỐC (canonical, xem
        _TR_COMBO_ITEMS) thay vì currentText() - text hiển thị của item đã bị
        tr() dịch theo ngôn ngữ hiện tại nên KHÔNG còn khớp giá trị tiếng Anh
        lưu trong CameraDevice (device.status.value, ai.inference_quality...).
        Dùng index cố định (thứ tự _TR_COMBO_ITEMS khớp đúng thứ tự item
        trong .ui) làm cầu nối, tách biệt hoàn toàn "giá trị lưu" khỏi
        "text hiển thị hiện tại" - bug đã gặp: đổi ngôn ngữ xong Save lại thì
        DeviceStatus()/parse_inference_imgsz() nhận nhầm chuỗi đã dịch."""
        keys = _TR_COMBO_ITEMS[attr]
        index = keys.index(value) if value in keys else 0
        combo.setCurrentIndex(index)

    @staticmethod
    def _combo_get_canonical(combo: QtWidgets.QComboBox, attr: str) -> str:
        keys = _TR_COMBO_ITEMS[attr]
        index = combo.currentIndex()
        return keys[index] if 0 <= index < len(keys) else combo.currentText()

    def _apply_device_to_form(self, device: CameraDevice) -> None:
        # --- Basic ---
        self.edit_camera_name.setText(device.name)
        self.edit_camera_id.setText(device.id)
        self._combo_set_canonical(self.combo_vendor, "combo_vendor", device.vendor)
        self.edit_ip_address.setText(device.ip_address)
        self.edit_mac_address.setText(device.mac_address)
        self.edit_stream_url.setText(device.stream_url)
        self.edit_substream_url.setText(device.substream_url)
        self.check_use_substream.setChecked(device.use_substream)
        self._combo_set_canonical(self.combo_status, "combo_status", device.status.value)
        self.combo_resolution.setCurrentText(device.resolution)
        self.spin_fps.setValue(device.fps)
        self.lbl_ai_summary.clear()

        # --- AI ---
        self.check_enable_ai.setChecked(device.ai.enabled)
        self.spin_ai_fps_limit.setValue(device.ai.ai_fps_limit)
        self._combo_set_canonical(self.combo_inference_quality, "combo_inference_quality", device.ai.inference_quality)
        self.check_enable_counting.setChecked(device.ai.enable_counting)
        self.check_enable_occupancy.setChecked(device.ai.enable_occupancy)
        self.spin_occupancy_threshold.setValue(device.ai.occupancy_threshold)
        self.spin_crowd_heatmap_threshold.setValue(device.ai.crowd_heatmap_threshold)
        self.check_enable_ppe.setChecked(device.ai.enable_ppe)
        self.check_enable_fire.setChecked(device.ai.enable_fire)
        self.check_enable_fall.setChecked(device.ai.enable_fall)
        self.check_enable_face_recognition.setChecked(device.ai.enable_face_recognition)
        self._combo_set_canonical(
            self.combo_stranger_repeat_mode, "combo_stranger_repeat_mode", device.ai.stranger_repeat_mode
        )

        # --- ROI ---
        self.list_roi.clear()
        for roi in device.roi_regions:
            self.list_roi.addItem(f"{roi.name}   [{roi.points}]")
        self.lbl_counting_line_status.setText(
            tr("Set: {value}").format(value=device.counting_line) if device.counting_line else tr("Not set")
        )

        # --- Trigger ---
        self.list_trigger_rules.clear()
        for rule in device.trigger_rules:
            self.list_trigger_rules.addItem(f"{rule.name}  —  IF {rule.condition} THEN {rule.action}")

        # --- Recording ---
        self.check_enable_recording.setChecked(device.recording.enabled)
        self._combo_set_canonical(self.combo_recording_mode, "combo_recording_mode", device.recording.mode)
        self.edit_save_path.setText(device.recording.save_path)
        self.spin_retention_days.setValue(device.recording.retention_days)

        # --- Overlay ---
        self.check_show_bbox.setChecked(device.overlay.show_bbox)
        self.check_show_label.setChecked(device.overlay.show_label)
        self.check_show_confidence.setChecked(device.overlay.show_confidence)
        self.check_show_roi.setChecked(device.overlay.show_roi)
        self.check_show_tracking_id.setChecked(device.overlay.show_tracking_id)

        # --- Advanced ---
        self.spin_frame_queue_size.setValue(device.advanced.frame_queue_size)
        self.spin_reconnect_timeout.setValue(device.advanced.reconnect_timeout)
        self.combo_decoder_backend.setCurrentText(device.advanced.decoder_backend)
        self.check_hw_accel.setChecked(device.advanced.hw_accel)
        self._combo_set_canonical(self.combo_gpu_device, "combo_gpu_device", device.advanced.gpu_device)

    def _collect_form_updates(self) -> dict:
        """Đọc toàn bộ form -> dict field-name/value để gọi
        DeviceManager.update_device(**dict). Không đụng tới roi_regions /
        trigger_rules / counting_line vì 3 thứ đó được cập nhật ngay khi
        Add/Edit/Delete (hoặc qua ROI Editor), không đợi Save."""
        return dict(
            name=self.edit_camera_name.text().strip(),
            vendor=self._combo_get_canonical(self.combo_vendor, "combo_vendor"),
            ip_address=self.edit_ip_address.text().strip(),
            mac_address=self.edit_mac_address.text().strip(),
            stream_url=self.edit_stream_url.text().strip(),
            substream_url=self.edit_substream_url.text().strip(),
            use_substream=self.check_use_substream.isChecked(),
            status=DeviceStatus(self._combo_get_canonical(self.combo_status, "combo_status")),
            resolution=self.combo_resolution.currentText(),
            fps=self.spin_fps.value(),
            ai=AIConfig(
                enabled=self.check_enable_ai.isChecked(),
                ai_fps_limit=self.spin_ai_fps_limit.value(),
                inference_quality=self._combo_get_canonical(self.combo_inference_quality, "combo_inference_quality"),
                enable_counting=self.check_enable_counting.isChecked(),
                enable_occupancy=self.check_enable_occupancy.isChecked(),
                occupancy_threshold=self.spin_occupancy_threshold.value(),
                crowd_heatmap_threshold=self.spin_crowd_heatmap_threshold.value(),
                enable_ppe=self.check_enable_ppe.isChecked(),
                enable_fire=self.check_enable_fire.isChecked(),
                enable_fall=self.check_enable_fall.isChecked(),
                enable_face_recognition=self.check_enable_face_recognition.isChecked(),
                stranger_repeat_mode=self._combo_get_canonical(
                    self.combo_stranger_repeat_mode, "combo_stranger_repeat_mode"
                ),
            ),
            recording=RecordingConfig(
                enabled=self.check_enable_recording.isChecked(),
                mode=self._combo_get_canonical(self.combo_recording_mode, "combo_recording_mode"),
                save_path=self.edit_save_path.text().strip(),
                retention_days=self.spin_retention_days.value(),
            ),
            overlay=OverlayConfig(
                show_bbox=self.check_show_bbox.isChecked(),
                show_label=self.check_show_label.isChecked(),
                show_confidence=self.check_show_confidence.isChecked(),
                show_roi=self.check_show_roi.isChecked(),
                show_tracking_id=self.check_show_tracking_id.isChecked(),
            ),
            advanced=AdvancedConfig(
                frame_queue_size=self.spin_frame_queue_size.value(),
                reconnect_timeout=self.spin_reconnect_timeout.value(),
                decoder_backend=self.combo_decoder_backend.currentText(),
                hw_accel=self.check_hw_accel.isChecked(),
                gpu_device=self._combo_get_canonical(self.combo_gpu_device, "combo_gpu_device"),
            ),
        )

    # ------------------------------------------------------------------ #
    # Action bar: Save / Apply / Reset / Export / Import
    # ------------------------------------------------------------------ #
    def _connect_action_bar(self) -> None:
        self.btn_save.clicked.connect(self._on_save)
        self.btn_apply.clicked.connect(self._on_apply)
        self.btn_reset.clicked.connect(self._on_reset)
        self.btn_export_config.clicked.connect(self._on_export_config)
        self.btn_import_config.clicked.connect(self._on_import_config)

    def _on_save(self) -> None:
        if self._apply_form_to_device():
            QMessageBox.information(self, tr("Saved"), tr("Camera configuration saved."))

    def _on_apply(self) -> None:
        # Apply giống Save nhưng không hiện thông báo, dùng khi muốn áp cấu
        # hình liên tục trong lúc chỉnh (ví dụ đang canh FPS/resolution).
        self._apply_form_to_device()

    def _apply_form_to_device(self) -> bool:
        if not self.current_device_id:
            QMessageBox.warning(self, tr("No camera selected"), tr("Please select a camera from the list on the left."))
            return False
        if not self.edit_camera_name.text().strip():
            QMessageBox.warning(self, tr("Missing information"), tr("Camera Name cannot be empty."))
            return False

        updates = self._collect_form_updates()
        updates["web_camera_id"] = self._resolve_web_camera_id(updates["mac_address"])
        device = self._current_device()
        if device is not None:
            self._warn_ai_feature_prereqs(updates["ai"], device)
        self.device_manager.update_device(self.current_device_id, **updates)
        return True

    @staticmethod
    def _resolve_web_camera_id(mac_address: str) -> str:
        """Tra camera_id THẬT của server ứng với MAC vừa nhập (Web_API.
        resolve_camera_id, có cache theo MAC) - chạy ngay lúc Save/Apply
        (blocking UI 1 chút, chấp nhận được vì đây là hành động bấm nút chủ
        động, giống lúc get_api() block lúc đăng nhập), rồi LƯU LẠI kết quả
        vào CameraDevice.web_camera_id - CameraPipeline/gate kiosk chỉ đọc
        giá trị đã lưu này, không tự gọi mạng nữa lúc gửi sự kiện. MAC rỗng
        hoặc chưa tra được (web chưa có camera này/mất mạng) -> rỗng, camera
        đó tạm thời không gửi sự kiện lên web cho tới lần Save kế tiếp
        (không tự retry nền)."""
        if not mac_address:
            return ""
        camera_id = Web_API.resolve_camera_id(mac_address)
        return str(camera_id) if camera_id is not None else ""

    def _warn_ai_feature_prereqs(self, ai: AIConfig, device: CameraDevice) -> None:
        """Cảnh báo NHẸ (không chặn Save) nếu bật tính năng AI nhưng chưa vẽ
        ROI/Counting Line tương ứng - tính năng đó sẽ không lỗi, chỉ đơn giản
        không chạy cho tới khi cấu hình đủ qua ROI Editor."""
        missing = []
        if ai.enable_counting and not device.counting_line:
            missing.append(tr("Count In/Out requires drawing a Counting Line (ROI tab)."))
        if ai.enable_occupancy and not device.roi_regions:
            missing.append(tr("Occupancy requires at least 1 ROI (ROI tab)."))
        if ai.enable_ppe and not device.roi_regions:
            missing.append(tr("PPE requires at least 1 ROI (ROI tab)."))
        if ai.enable_face_recognition and KnownFacesStore.instance().count == 0:
            missing.append(
                tr(
                    "Face Recognition has no known faces yet - every face will be treated "
                    "as 'Stranger' until 'Refresh Known Faces' succeeds."
                )
            )
        if missing:
            QMessageBox.warning(
                self,
                tr("Missing ROI/Line configuration"),
                tr("Saved, but the following features will NOT run until fully configured:\n\n")
                + "\n".join(f"• {m}" for m in missing),
            )

    def _on_reset(self) -> None:
        # Bỏ mọi thay đổi chưa lưu, load lại nguyên trạng từ DeviceManager.
        if self.current_device_id:
            self.load_device(self.current_device_id)

    def _on_export_config(self) -> None:
        if not self.current_device_id:
            return
        device = self.device_manager.get_device(self.current_device_id)
        if device is None:
            return

        path, _ = QFileDialog.getSaveFileName(
            self, tr("Export Config"), f"{device.name}.json", "JSON Files (*.json)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(device.to_dict(), f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, tr("Export Config"), tr("Configuration exported to:\n{path}").format(path=path))

    def _on_import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Import Config"), "", "JSON Files (*.json)")
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            imported = CameraDevice.from_dict(raw)
        except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, tr("Import Config"), tr("Invalid configuration file:\n{exc}").format(exc=exc))
            return

        if self.current_device_id:
            # Áp nội dung cấu hình vào camera đang chọn, GIỮ NGUYÊN id/device_type
            # hiện tại (không cho import đè id sang 1 camera khác).
            exclude = {"id", "device_type"}
            updates = {
                f.name: getattr(imported, f.name)
                for f in dataclasses.fields(imported)
                if f.name not in exclude
            }
            self.device_manager.update_device(self.current_device_id, **updates)
            self.load_device(self.current_device_id)
            QMessageBox.information(self, tr("Import Config"), tr("Configuration applied to the selected camera."))
        else:
            # Không chọn camera nào -> import thành 1 camera mới.
            new_id = self.device_manager.add_device(imported)
            self.load_device(new_id)
            QMessageBox.information(self, tr("Import Config"), tr("New camera created from the configuration file."))

    # ------------------------------------------------------------------ #
    # Tab Basic
    # ------------------------------------------------------------------ #
    def _connect_basic_tab(self) -> None:
        self.btn_test_connection.clicked.connect(self._on_test_connection)
        self.btn_start_device.clicked.connect(self._on_start_device)
        self.btn_stop_device.clicked.connect(self._on_stop_device)
        self.btn_toggle_preview.toggled.connect(self._on_toggle_preview)

    def _on_test_connection(self) -> None:
        ip = self.edit_ip_address.text().strip()
        if not ip:
            QMessageBox.warning(self, tr("Test Connection"), tr("Please enter an IP Address first."))
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            reachable = is_ip_camera_reachable(ip, timeout=1.5)
        finally:
            self.unsetCursor()

        if reachable:
            QMessageBox.information(self, tr("Test Connection"), tr("Successfully connected to {ip}.").format(ip=ip))
        else:
            QMessageBox.warning(self, tr("Test Connection"), tr("Could not connect to {ip}.").format(ip=ip))

    def _on_start_device(self) -> None:
        """Start = cho camera này chạy NỀN (capture liên tục + AI nếu có bật)
        - không tự động mở preview. Muốn xem hình phải bấm riêng nút
        "Open Preview" ở dưới."""
        device = self._current_device()
        if device is None:
            return
        self.device_manager.start_device(device.id)

    def _on_stop_device(self) -> None:
        """Stop = dừng hẳn pipeline nền (capture + AI) của camera này.
        Preview (nếu đang mở) sẽ tự tắt theo qua _on_running_changed."""
        if self.current_device_id:
            self.device_manager.stop_device(self.current_device_id)

    # ------------------------------------------------------------------ #
    # Camera Preview (tab Basic) - subscribe xem hình từ pipeline nền
    # ------------------------------------------------------------------ #
    def _on_toggle_preview(self, checked: bool) -> None:
        if checked:
            self._open_preview()
        else:
            self._close_preview()

    def _open_preview(self) -> None:
        device = self._current_device()
        if device is None or not self.device_manager.subscribe_preview(device.id):
            QMessageBox.warning(
                self, tr("Camera Preview"), tr("Please click Start on the camera before viewing the preview.")
            )
            self.btn_toggle_preview.blockSignals(True)
            self.btn_toggle_preview.setChecked(False)
            self.btn_toggle_preview.blockSignals(False)
            return
        self._preview_active = True
        self.btn_toggle_preview.setText(tr("■  Close Preview"))
        self.lbl_preview_placeholder.setText(tr("Connecting..."))

    def _close_preview(self) -> None:
        if self._preview_active and self.current_device_id:
            self.device_manager.unsubscribe_preview(self.current_device_id)
        self._preview_active = False
        self.btn_toggle_preview.setText(tr("▶  Open Preview"))
        self.lbl_preview_placeholder.setPixmap(QPixmap())
        self.lbl_preview_placeholder.setText(tr("No Preview"))

    def _on_preview_frame(self, device_id: str, image: QImage) -> None:
        if not self._preview_active or device_id != self.current_device_id:
            return  # frame của camera khác (đang chạy nền) hoặc mình chưa/hết xem -> bỏ qua
        pixmap = QPixmap.fromImage(image)
        self.lbl_preview_placeholder.setPixmap(
            pixmap.scaled(
                self.lbl_preview_placeholder.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _on_preview_error(self, device_id: str, message: str) -> None:
        if not self._preview_active or device_id != self.current_device_id:
            return
        self.lbl_preview_placeholder.setText(tr("Preview error:\n{message}").format(message=message))
        self.btn_toggle_preview.setChecked(False)

    def _on_ai_result(self, device_id: str, result: dict) -> None:
        """Camera này có thể đang chạy AI nền dù trang không mở Preview -
        vẫn cập nhật dòng tóm tắt AI ở tab Basic để người dùng thấy ngay,
        không cần bật Preview mới biết kết quả."""
        if device_id != self.current_device_id:
            return
        parts = [
            tr("People: {n}").format(n=result.get('num_people', 0)),
            tr("In: {n}").format(n=result.get('num_in', 0)),
            tr("Out: {n}").format(n=result.get('num_out', 0)),
        ]
        known_faces = result.get("known_faces") or []
        if known_faces:
            parts.append(tr("Recognized: {names}").format(names=', '.join(known_faces)))

        alerts = []
        if result.get("ppe_violation"):
            alerts.append(tr("⚠ PPE VIOLATION"))
        if result.get("fire_alert"):
            alerts.append(tr("🔥 FIRE"))
        if result.get("fall_alert"):
            alerts.append(tr("🚨 FALL"))
        if result.get("stranger_alert"):
            alerts.append(tr("🧑‍❓ STRANGER"))

        text = "   ".join(parts)
        if alerts:
            text += "   |   " + "   ".join(alerts)
        self.lbl_ai_summary.setText(text)
        self.lbl_ai_summary.setStyleSheet(
            "font-weight:600; color:#e53935;" if alerts else "font-weight:600;"
        )

    # ------------------------------------------------------------------ #
    # Tab AI
    # ------------------------------------------------------------------ #
    def _connect_ai_tab(self) -> None:
        self.btn_open_pipeline_config.clicked.connect(self._on_open_pipeline_config)
        self.btn_refresh_known_faces.clicked.connect(KnownFacesStore.instance().refresh_async)
        KnownFacesStore.instance().updated.connect(self._on_known_faces_updated)
        self._on_known_faces_updated()  # hiện trạng thái hiện có ngay khi mở trang, không đợi refresh

    def _on_known_faces_updated(self) -> None:
        store = KnownFacesStore.instance()
        if store.last_error:
            self.lbl_known_faces_status.setText(tr("Known faces: load error ({error})").format(error=store.last_error))
        else:
            self.lbl_known_faces_status.setText(tr("Known faces: {n} people").format(n=store.count))

    def _on_open_pipeline_config(self) -> None:
        # TODO: mở dialog cấu hình pipeline AI chi tiết (thứ tự các bước xử lý).
        QMessageBox.information(
            self, tr("Pipeline Config"), tr("TODO: open detailed AI pipeline configuration dialog.")
        )

    # ------------------------------------------------------------------ #
    # Tab ROI
    # ------------------------------------------------------------------ #
    def _connect_roi_tab(self) -> None:
        self.btn_open_roi_editor.clicked.connect(self._on_open_roi_editor)

    def _current_device(self) -> CameraDevice | None:
        if not self.current_device_id:
            return None
        return self.device_manager.get_device(self.current_device_id)

    def _on_open_roi_editor(self) -> None:
        device = self._current_device()
        if device is None:
            QMessageBox.warning(self, tr("ROI Editor"), tr("Please select a camera first."))
            return
        dialog = ROIEditorDialog(self, device, self.device_manager)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            self.device_manager.update_device(
                device.id,
                roi_regions=dialog.get_roi_regions(),
                counting_line=dialog.get_counting_line(),
            )
            self._apply_device_to_form(self.device_manager.get_device(device.id))

    # ------------------------------------------------------------------ #
    # Tab Trigger
    # ------------------------------------------------------------------ #
    def _connect_trigger_tab(self) -> None:
        self.btn_add_trigger_rule.clicked.connect(self._on_add_trigger_rule)
        self.btn_edit_trigger_rule.clicked.connect(self._on_edit_trigger_rule)
        self.btn_delete_trigger_rule.clicked.connect(self._on_delete_trigger_rule)
        self.list_trigger_rules.itemDoubleClicked.connect(lambda _item: self._on_edit_trigger_rule())

    def _on_add_trigger_rule(self) -> None:
        device = self._current_device()
        if device is None:
            QMessageBox.warning(self, tr("Trigger Rule"), tr("Please select a camera first."))
            return
        dialog = TriggerRuleDialog(self)
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            device.trigger_rules.append(dialog.get_rule())
            self.device_manager.update_device(device.id, trigger_rules=device.trigger_rules)
            self._apply_device_to_form(device)

    def _on_edit_trigger_rule(self) -> None:
        device = self._current_device()
        row = self.list_trigger_rules.currentRow()
        if device is None or row < 0 or row >= len(device.trigger_rules):
            return
        dialog = TriggerRuleDialog(self, device.trigger_rules[row])
        if dialog.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            device.trigger_rules[row] = dialog.get_rule()
            self.device_manager.update_device(device.id, trigger_rules=device.trigger_rules)
            self._apply_device_to_form(device)

    def _on_delete_trigger_rule(self) -> None:
        device = self._current_device()
        row = self.list_trigger_rules.currentRow()
        if device is None or row < 0 or row >= len(device.trigger_rules):
            QMessageBox.warning(self, tr("Trigger Rule"), tr("Please select a rule from the list to delete."))
            return
        del device.trigger_rules[row]
        self.device_manager.update_device(device.id, trigger_rules=device.trigger_rules)
        self._apply_device_to_form(device)

    # ------------------------------------------------------------------ #
    # Tab Recording
    # ------------------------------------------------------------------ #
    def _connect_recording_tab(self) -> None:
        self.btn_browse_save_path.clicked.connect(self._on_browse_save_path)
        self.btn_open_schedule_config.clicked.connect(self._on_open_schedule_config)

    def _on_browse_save_path(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, tr("Select video save folder"))
        if folder:
            self.edit_save_path.setText(folder)

    def _on_open_schedule_config(self) -> None:
        # TODO: mở dialog cấu hình lịch ghi hình chi tiết (theo giờ/ngày trong tuần).
        QMessageBox.information(
            self, tr("Schedule Config"), tr("TODO: open detailed recording schedule configuration dialog.")
        )

    # ------------------------------------------------------------------ #
    # Tab Overlay
    # ------------------------------------------------------------------ #
    def _connect_overlay_tab(self) -> None:
        self.btn_open_overlay_settings.clicked.connect(self._on_open_overlay_settings)

    def _on_open_overlay_settings(self) -> None:
        # TODO: mở dialog chọn màu/độ dày viền/font cho từng loại overlay.
        QMessageBox.information(
            self, tr("Overlay Settings"), tr("TODO: open detailed overlay color/style configuration dialog.")
        )