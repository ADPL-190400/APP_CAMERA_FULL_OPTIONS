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
            item = QListWidgetItem(f"{device.name}   ·  {device.status.value}")
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
        self.combo_status.setCurrentText(device.status.value)
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

    def _apply_device_to_form(self, device: CameraDevice) -> None:
        # --- Basic ---
        self.edit_camera_name.setText(device.name)
        self.edit_camera_id.setText(device.id)
        self.combo_vendor.setCurrentText(device.vendor)
        self.edit_ip_address.setText(device.ip_address)
        self.edit_mac_address.setText(device.mac_address)
        self.edit_stream_url.setText(device.stream_url)
        self.edit_substream_url.setText(device.substream_url)
        self.check_use_substream.setChecked(device.use_substream)
        self.combo_status.setCurrentText(device.status.value)
        self.combo_resolution.setCurrentText(device.resolution)
        self.spin_fps.setValue(device.fps)
        self.lbl_ai_summary.clear()

        # --- AI ---
        self.check_enable_ai.setChecked(device.ai.enabled)
        self.spin_ai_fps_limit.setValue(device.ai.ai_fps_limit)
        self.combo_inference_quality.setCurrentText(device.ai.inference_quality)
        self.check_enable_counting.setChecked(device.ai.enable_counting)
        self.check_enable_occupancy.setChecked(device.ai.enable_occupancy)
        self.check_enable_ppe.setChecked(device.ai.enable_ppe)
        self.check_enable_fire.setChecked(device.ai.enable_fire)
        self.check_enable_fall.setChecked(device.ai.enable_fall)
        self.check_enable_face_recognition.setChecked(device.ai.enable_face_recognition)

        # --- ROI ---
        self.list_roi.clear()
        for roi in device.roi_regions:
            self.list_roi.addItem(f"{roi.name}   [{roi.points}]")
        self.lbl_counting_line_status.setText(
            f"Đã đặt: {device.counting_line}" if device.counting_line else "Chưa đặt"
        )

        # --- Trigger ---
        self.list_trigger_rules.clear()
        for rule in device.trigger_rules:
            self.list_trigger_rules.addItem(f"{rule.name}  —  IF {rule.condition} THEN {rule.action}")

        # --- Recording ---
        self.check_enable_recording.setChecked(device.recording.enabled)
        self.combo_recording_mode.setCurrentText(device.recording.mode)
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
        self.combo_gpu_device.setCurrentText(device.advanced.gpu_device)

    def _collect_form_updates(self) -> dict:
        """Đọc toàn bộ form -> dict field-name/value để gọi
        DeviceManager.update_device(**dict). Không đụng tới roi_regions /
        trigger_rules / counting_line vì 3 thứ đó được cập nhật ngay khi
        Add/Edit/Delete (hoặc qua ROI Editor), không đợi Save."""
        return dict(
            name=self.edit_camera_name.text().strip(),
            vendor=self.combo_vendor.currentText(),
            ip_address=self.edit_ip_address.text().strip(),
            mac_address=self.edit_mac_address.text().strip(),
            stream_url=self.edit_stream_url.text().strip(),
            substream_url=self.edit_substream_url.text().strip(),
            use_substream=self.check_use_substream.isChecked(),
            status=DeviceStatus(self.combo_status.currentText()),
            resolution=self.combo_resolution.currentText(),
            fps=self.spin_fps.value(),
            ai=AIConfig(
                enabled=self.check_enable_ai.isChecked(),
                ai_fps_limit=self.spin_ai_fps_limit.value(),
                inference_quality=self.combo_inference_quality.currentText(),
                enable_counting=self.check_enable_counting.isChecked(),
                enable_occupancy=self.check_enable_occupancy.isChecked(),
                enable_ppe=self.check_enable_ppe.isChecked(),
                enable_fire=self.check_enable_fire.isChecked(),
                enable_fall=self.check_enable_fall.isChecked(),
                enable_face_recognition=self.check_enable_face_recognition.isChecked(),
            ),
            recording=RecordingConfig(
                enabled=self.check_enable_recording.isChecked(),
                mode=self.combo_recording_mode.currentText(),
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
                gpu_device=self.combo_gpu_device.currentText(),
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
            QMessageBox.information(self, "Đã lưu", "Đã lưu cấu hình camera.")

    def _on_apply(self) -> None:
        # Apply giống Save nhưng không hiện thông báo, dùng khi muốn áp cấu
        # hình liên tục trong lúc chỉnh (ví dụ đang canh FPS/resolution).
        self._apply_form_to_device()

    def _apply_form_to_device(self) -> bool:
        if not self.current_device_id:
            QMessageBox.warning(self, "Chưa chọn camera", "Vui lòng chọn 1 camera ở danh sách bên trái.")
            return False
        if not self.edit_camera_name.text().strip():
            QMessageBox.warning(self, "Thiếu thông tin", "Camera Name không được để trống.")
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
            missing.append("Đếm người vào/ra cần vẽ Counting Line (tab ROI).")
        if ai.enable_occupancy and not device.roi_regions:
            missing.append("Occupancy cần vẽ ít nhất 1 ROI (tab ROI).")
        if ai.enable_ppe and not device.roi_regions:
            missing.append("PPE cần vẽ ít nhất 1 ROI (tab ROI).")
        if ai.enable_face_recognition and KnownFacesStore.instance().count == 0:
            missing.append(
                "Face Recognition chưa có known faces - mọi khuôn mặt sẽ bị coi là "
                "'Stranger' cho tới khi bấm 'Refresh Known Faces' thành công."
            )
        if missing:
            QMessageBox.warning(
                self,
                "Thiếu cấu hình ROI/Line",
                "Đã lưu, nhưng các tính năng sau sẽ CHƯA chạy cho tới khi cấu hình đủ:\n\n"
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
            self, "Export Config", f"{device.name}.json", "JSON Files (*.json)"
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(device.to_dict(), f, ensure_ascii=False, indent=2)
        QMessageBox.information(self, "Export Config", f"Đã xuất cấu hình ra:\n{path}")

    def _on_import_config(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Import Config", "", "JSON Files (*.json)")
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            imported = CameraDevice.from_dict(raw)
        except (json.JSONDecodeError, OSError, KeyError, ValueError, TypeError) as exc:
            QMessageBox.critical(self, "Import Config", f"File cấu hình không hợp lệ:\n{exc}")
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
            QMessageBox.information(self, "Import Config", "Đã áp cấu hình vào camera đang chọn.")
        else:
            # Không chọn camera nào -> import thành 1 camera mới.
            new_id = self.device_manager.add_device(imported)
            self.load_device(new_id)
            QMessageBox.information(self, "Import Config", "Đã tạo camera mới từ file cấu hình.")

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
            QMessageBox.warning(self, "Test Connection", "Vui lòng nhập IP Address trước.")
            return

        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            reachable = is_ip_camera_reachable(ip, timeout=1.5)
        finally:
            self.unsetCursor()

        if reachable:
            QMessageBox.information(self, "Test Connection", f"Kết nối tới {ip} thành công.")
        else:
            QMessageBox.warning(self, "Test Connection", f"Không thể kết nối tới {ip}.")

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
                self, "Camera Preview", "Vui lòng bấm Start camera trước khi xem preview."
            )
            self.btn_toggle_preview.blockSignals(True)
            self.btn_toggle_preview.setChecked(False)
            self.btn_toggle_preview.blockSignals(False)
            return
        self._preview_active = True
        self.btn_toggle_preview.setText("■  Close Preview")
        self.lbl_preview_placeholder.setText("Đang kết nối...")

    def _close_preview(self) -> None:
        if self._preview_active and self.current_device_id:
            self.device_manager.unsubscribe_preview(self.current_device_id)
        self._preview_active = False
        self.btn_toggle_preview.setText("▶  Open Preview")
        self.lbl_preview_placeholder.setPixmap(QPixmap())
        self.lbl_preview_placeholder.setText("No Preview")

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
        self.lbl_preview_placeholder.setText(f"Preview error:\n{message}")
        self.btn_toggle_preview.setChecked(False)

    def _on_ai_result(self, device_id: str, result: dict) -> None:
        """Camera này có thể đang chạy AI nền dù trang không mở Preview -
        vẫn cập nhật dòng tóm tắt AI ở tab Basic để người dùng thấy ngay,
        không cần bật Preview mới biết kết quả."""
        if device_id != self.current_device_id:
            return
        parts = [
            f"Người: {result.get('num_people', 0)}",
            f"Vào: {result.get('num_in', 0)}",
            f"Ra: {result.get('num_out', 0)}",
        ]
        known_faces = result.get("known_faces") or []
        if known_faces:
            parts.append(f"Nhận diện: {', '.join(known_faces)}")

        alerts = []
        if result.get("ppe_violation"):
            alerts.append("⚠ PPE VI PHẠM")
        if result.get("fire_alert"):
            alerts.append("🔥 CHÁY")
        if result.get("fall_alert"):
            alerts.append("🚨 TÉ NGÃ")
        if result.get("stranger_alert"):
            alerts.append("🧑‍❓ NGƯỜI LẠ")

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
            self.lbl_known_faces_status.setText(f"Known faces: lỗi tải ({store.last_error})")
        else:
            self.lbl_known_faces_status.setText(f"Known faces: {store.count} người")

    def _on_open_pipeline_config(self) -> None:
        # TODO: mở dialog cấu hình pipeline AI chi tiết (thứ tự các bước xử lý).
        QMessageBox.information(
            self, "Pipeline Config", "TODO: mở dialog cấu hình pipeline AI chi tiết."
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
            QMessageBox.warning(self, "ROI Editor", "Vui lòng chọn 1 camera trước.")
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
            QMessageBox.warning(self, "Trigger Rule", "Vui lòng chọn 1 camera trước.")
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
            QMessageBox.warning(self, "Trigger Rule", "Vui lòng chọn 1 rule trong danh sách để xoá.")
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
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu video")
        if folder:
            self.edit_save_path.setText(folder)

    def _on_open_schedule_config(self) -> None:
        # TODO: mở dialog cấu hình lịch ghi hình chi tiết (theo giờ/ngày trong tuần).
        QMessageBox.information(
            self, "Schedule Config", "TODO: mở dialog cấu hình lịch ghi hình chi tiết."
        )

    # ------------------------------------------------------------------ #
    # Tab Overlay
    # ------------------------------------------------------------------ #
    def _connect_overlay_tab(self) -> None:
        self.btn_open_overlay_settings.clicked.connect(self._on_open_overlay_settings)

    def _on_open_overlay_settings(self) -> None:
        # TODO: mở dialog chọn màu/độ dày viền/font cho từng loại overlay.
        QMessageBox.information(
            self, "Overlay Settings", "TODO: mở dialog cấu hình chi tiết màu sắc/kiểu overlay."
        )