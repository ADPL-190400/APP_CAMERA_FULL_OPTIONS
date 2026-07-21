"""
DeviceManager: nguồn dữ liệu DUY NHẤT cho toàn bộ app về danh sách camera.

Vì sao cần lớp này:
- device_management_page cần thêm/xoá/start/stop camera.
- camera_config_page cần đọc & sửa thông tin 1 camera.
- Sau này có thể có thêm trang livestream, playback... cũng cần danh sách camera.

=> Nếu để mỗi trang tự giữ list riêng thì rất khó đồng bộ (sửa ở trang A,
trang B không biết). Giải pháp: tất cả các trang chỉ thao tác qua
DeviceManager.instance(), và lắng nghe signal để tự cập nhật UI của mình.

Lớp này cũng tự động:
1. Load danh sách camera từ core/device_store.py khi app khởi động.
2. Lưu lại xuống đĩa mỗi khi danh sách thay đổi (add/remove/update/scan)
   -> tắt app xong mở lại không mất danh sách, không phải quét lại.
3. Định kỳ kiểm tra Online/Offline cho từng camera ở nền (QThread),
   không cần bấm "Online Device" hay "Refresh" thủ công.

Cách dùng ở 1 trang bất kỳ:
    from core.device_manager import DeviceManager
    self.device_manager = DeviceManager.instance()
    self.device_manager.devices_changed.connect(self.reload_table)
"""
from __future__ import annotations

import os
import time
from typing import Optional
from PyQt6.QtCore import QObject, QTimer, pyqtSignal
from PyQt6.QtGui import QImage

from core.account_context import account_dir
from core.models.camera_device import (
    CameraDevice,
    DeviceStatus,
    parse_inference_imgsz,
    parse_preview_max_width,
    parse_resolution_wh,
)
from core.status_checker import StatusCheckWorker
from core.camera_pipeline import CameraPipeline
from core import device_store

DEFAULT_STATUS_CHECK_INTERVAL_MS = 15_000  # 15 giây

# StatusCheckWorker chỉ probe TCP thô (1 giây) tới cổng 554/80 - có thể bị
# camera từ chối do giới hạn session RTSP đồng thời (pipeline đang giữ 1
# session để stream) dù video vẫn đang chạy tốt. Nếu pipeline vừa đọc được
# frame THẬT trong khoảng grace này thì đó là bằng chứng kết nối đáng tin
# hơn kết quả probe - xem _has_recent_frame()/_apply_status_results().
_FRAME_LIVENESS_GRACE_SEC = 8.0


class DeviceManager(QObject):
    _instance: Optional["DeviceManager"] = None

    # --- Signals để các trang khác lắng nghe, tự refresh UI của mình ---
    device_added = pyqtSignal(str)                 # device_id
    device_removed = pyqtSignal(str)                # device_id
    device_updated = pyqtSignal(str)                 # device_id (đổi info / trạng thái)
    device_status_changed = pyqtSignal(str, str)      # device_id, status
    device_running_changed = pyqtSignal(str, bool)     # device_id, is_running
    devices_changed = pyqtSignal()                      # thay đổi hàng loạt (ví dụ sau khi scan)

    # --- Pipeline nền (capture + AI) - broadcast cho mọi "viewer" đang subscribe ---
    pipeline_frame_ready = pyqtSignal(str, QImage)  # device_id, frame
    pipeline_error = pyqtSignal(str, str)           # device_id, message
    ai_result_ready = pyqtSignal(str, dict)         # device_id, {"num_people","num_in","num_out","ppe_violation","fire_alert","fall_alert"}

    def __init__(self):
        super().__init__()
        self._devices: dict[str, CameraDevice] = {}
        self._pipelines: dict[str, CameraPipeline] = {}
        self._status_worker: StatusCheckWorker | None = None

        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._run_status_check)

        self._load_from_disk()

    @classmethod
    def instance(cls) -> "DeviceManager":
        if cls._instance is None:
            cls._instance = DeviceManager()
        return cls._instance

    # ---------------- Persistence ----------------
    @staticmethod
    def _devices_json_path() -> str:
        # RIÊNG cho tài khoản đang đăng nhập (core/account_context.py) -
        # tránh tài khoản này thấy/ghi đè camera của tài khoản khác đã đăng
        # nhập trên cùng máy trước đó (MAC/web_camera_id gắn với account
        # khác không tương thích chéo).
        return os.path.join(account_dir(), "devices.json")

    def _load_from_disk(self) -> None:
        for device in device_store.load_devices(self._devices_json_path()):
            # Sau khi mở lại app, camera chưa chắc còn thực sự đang chạy
            # -> reset is_running, để status checker tự xác định lại Online/Offline.
            device.is_running = False
            device.status = DeviceStatus.UNKNOWN
            self._devices[device.id] = device

    def save_to_disk(self) -> None:
        device_store.save_devices(self.all_devices(), self._devices_json_path())

    # ---------------- CRUD ----------------
    def all_devices(self) -> list[CameraDevice]:
        return list(self._devices.values())

    def get_device(self, device_id: str) -> Optional[CameraDevice]:
        return self._devices.get(device_id)

    def add_device(self, device: CameraDevice) -> str:
        self._devices[device.id] = device
        self.device_added.emit(device.id)
        self.devices_changed.emit()
        self.save_to_disk()
        return device.id

    def remove_device(self, device_id: str) -> None:
        if device_id in self._devices:
            del self._devices[device_id]
            self.device_removed.emit(device_id)
            self.devices_changed.emit()
            self.save_to_disk()

    def remove_devices(self, device_ids: list[str]) -> None:
        for device_id in device_ids:
            self._devices.pop(device_id, None)
            self.device_removed.emit(device_id)
        self.devices_changed.emit()
        self.save_to_disk()

    def update_device(self, device_id: str, **fields) -> None:
        """Dùng bởi camera_config_page khi Save/Apply cấu hình (hoặc ROI
        Editor Accept). Nếu camera đang chạy nền, đẩy cấu hình AI/ROI/Line/
        Overlay mới nhất vào pipeline NGAY - không bắt người dùng phải
        Stop/Start lại mới thấy "Enable AI"/PPE/ROI mới có tác dụng."""
        device = self._devices.get(device_id)
        if device is None:
            return
        for key, value in fields.items():
            if hasattr(device, key):
                setattr(device, key, value)
        self._sync_running_pipeline(device_id)
        self.device_updated.emit(device_id)
        self.devices_changed.emit()
        self.save_to_disk()

    def _sync_running_pipeline(self, device_id: str) -> None:
        pipeline = self._pipelines.get(device_id)
        device = self._devices.get(device_id)
        if pipeline is None or device is None:
            return
        pipeline.update_ai_settings(
            ai_enabled=device.ai.enabled,
            enable_counting=device.ai.enable_counting,
            enable_occupancy=device.ai.enable_occupancy,
            enable_ppe=device.ai.enable_ppe,
            enable_fire=device.ai.enable_fire,
            enable_fall=device.ai.enable_fall,
            enable_face_recognition=device.ai.enable_face_recognition,
            counting_line=device.counting_line,
            roi_polygons=[roi.points for roi in device.roi_regions],
            show_bbox=device.overlay.show_bbox,
            show_label=device.overlay.show_label,
            show_roi=device.overlay.show_roi,
            show_tracking_id=device.overlay.show_tracking_id,
            preview_max_width=parse_preview_max_width(device.resolution),
            display_fps_limit=device.fps,
            inference_quality=device.ai.inference_quality,
        )

    def merge_discovered_devices(self, found: list[CameraDevice]) -> None:
        """Gộp kết quả scan (Online Device) vào danh sách hiện có.

        Nếu camera đã tồn tại (so khớp theo ip_address/usb_index) -> chỉ update
        trạng thái Online, không tạo bản ghi trùng, không mất cấu hình đã sửa.
        """
        for found_dev in found:
            existing = self._find_matching(found_dev)
            if existing:
                existing.status = DeviceStatus.ONLINE
                existing.serial_no = existing.serial_no or found_dev.serial_no
                existing.mac_address = existing.mac_address or found_dev.mac_address
                self.device_status_changed.emit(existing.id, existing.status.value)
            else:
                found_dev.status = DeviceStatus.ONLINE
                self._devices[found_dev.id] = found_dev
                self.device_added.emit(found_dev.id)
        self.devices_changed.emit()
        self.save_to_disk()

    def _find_matching(self, other: CameraDevice) -> Optional[CameraDevice]:
        for dev in self._devices.values():
            if dev.device_type != other.device_type:
                continue
            if dev.device_type.value == "USB" and dev.usb_index == other.usb_index:
                return dev
            if dev.device_type.value == "IP" and dev.ip_address == other.ip_address:
                return dev
        return None

    # ---------------- Start / Stop (pipeline nền: capture + AI) ----------------
    def start_device(self, device_id: str) -> None:
        """Bấm Start ở tab Basic (hoặc device_management_page) -> mở 1
        CameraPipeline chạy nền cho camera này (capture liên tục + chạy AI
        nếu device.ai.enabled). Pipeline này SỐNG ĐỘC LẬP với bất kỳ trang
        nào đang mở - tắt trang không làm dừng nó, phải bấm Stop mới dừng."""
        device = self._devices.get(device_id)
        if device is None or device_id in self._pipelines:
            return

        source = device.display_source()
        if not source:
            self.pipeline_error.emit(device_id, "Camera chưa cấu hình nguồn video (IP/Stream URL/USB index).")
            return

        pipeline = CameraPipeline(
            device_id,
            device.pipeline_source(),
            device_name=device.name,
            web_camera_id=device.web_camera_id,
            ai_enabled=device.ai.enabled,
            reconnect_timeout=device.advanced.reconnect_timeout,
            ai_fps_limit=device.ai.ai_fps_limit,
            counting_line=device.counting_line,
            roi_polygons=[roi.points for roi in device.roi_regions],
            enable_counting=device.ai.enable_counting,
            enable_occupancy=device.ai.enable_occupancy,
            enable_ppe=device.ai.enable_ppe,
            enable_fire=device.ai.enable_fire,
            enable_fall=device.ai.enable_fall,
            enable_face_recognition=device.ai.enable_face_recognition,
            show_bbox=device.overlay.show_bbox,
            show_label=device.overlay.show_label,
            show_roi=device.overlay.show_roi,
            show_tracking_id=device.overlay.show_tracking_id,
            preview_max_width=parse_preview_max_width(device.resolution),
            capture_resolution=parse_resolution_wh(device.resolution),
            display_fps_limit=device.fps,
            inference_quality=device.ai.inference_quality,
        )
        pipeline.frame_ready.connect(self.pipeline_frame_ready)
        pipeline.error_occurred.connect(self.pipeline_error)
        pipeline.ai_result_ready.connect(self.ai_result_ready)
        self._pipelines[device_id] = pipeline
        pipeline.start()

        device.is_running = True
        self.device_running_changed.emit(device_id, True)

    def stop_device(self, device_id: str) -> None:
        device = self._devices.get(device_id)
        pipeline = self._pipelines.pop(device_id, None)
        if pipeline is not None:
            pipeline.stop()
            pipeline.wait(2000)
        if device is None or not device.is_running:
            return
        device.is_running = False
        self.device_running_changed.emit(device_id, False)

    def start_devices(self, device_ids: list[str]) -> None:
        for device_id in device_ids:
            self.start_device(device_id)

    def stop_devices(self, device_ids: list[str]) -> None:
        for device_id in device_ids:
            self.stop_device(device_id)

    # ---------------- Xem preview (subscribe/unsubscribe) ----------------
    def subscribe_preview(self, device_id: str, need_full_resolution: bool = False) -> bool:
        """Gọi bởi 1 'viewer' (camera_config_page, 1 ô lưới liveview_page...)
        muốn xem hình camera này. Trả về False nếu camera chưa Start (không
        có gì để xem). Nhiều viewer có thể subscribe cùng lúc 1 camera.

        need_full_resolution=True (vd ROIEditorDialog) -> pipeline tạm ngưng
        downscale frame hiển thị trong lúc viewer này còn subscribe, để toạ
        độ ROI/Counting Line vẽ trên đó khớp đúng hệ toạ độ frame full-res mà
        AI/occupancy/PPE dùng để tính - xem CameraPipeline._apply_preview_downscale."""
        pipeline = self._pipelines.get(device_id)
        if pipeline is None:
            return False
        pipeline.add_viewer(need_full_resolution=need_full_resolution)
        return True

    def unsubscribe_preview(self, device_id: str, need_full_resolution: bool = False) -> None:
        pipeline = self._pipelines.get(device_id)
        if pipeline is not None:
            pipeline.remove_viewer(need_full_resolution=need_full_resolution)

    def is_pipeline_running(self, device_id: str) -> bool:
        return device_id in self._pipelines

    def shutdown(self) -> None:
        """Gọi khi thoát app - dừng sạch mọi pipeline đang chạy nền, tránh
        cảnh báo/crash do QThread bị huỷ khi đang chạy."""
        for device_id in list(self._pipelines.keys()):
            self.stop_device(device_id)

    # ---------------- Auto status check (nền) ----------------
    def start_auto_status_check(self, interval_ms: int = DEFAULT_STATUS_CHECK_INTERVAL_MS) -> None:
        """Gọi 1 lần khi app khởi động (ví dụ trong DeviceManagementPage.__init__).
        Gọi nhiều lần cũng an toàn - không tạo timer trùng."""
        if not self._status_timer.isActive():
            self._status_timer.start(interval_ms)
            self._run_status_check()  # chạy kiểm tra ngay lần đầu, không đợi hết interval

    def stop_auto_status_check(self) -> None:
        self._status_timer.stop()

    def _run_status_check(self) -> None:
        if self._status_worker is not None and self._status_worker.isRunning():
            return  # lượt kiểm tra trước chưa xong -> bỏ qua lượt này, tránh chồng thread
        devices_snapshot = self.all_devices()
        if not devices_snapshot:
            return
        self._status_worker = StatusCheckWorker(devices_snapshot)
        self._status_worker.result_ready.connect(self._apply_status_results)
        self._status_worker.start()

    def _has_recent_frame(self, device_id: str) -> bool:
        pipeline = self._pipelines.get(device_id)
        if pipeline is None or pipeline.last_frame_ts <= 0.0:
            return False
        return (time.monotonic() - pipeline.last_frame_ts) < _FRAME_LIVENESS_GRACE_SEC

    def _apply_status_results(self, results: dict) -> None:
        changed = False
        for device_id, status in results.items():
            device = self._devices.get(device_id)
            if device is None:
                continue
            if status == DeviceStatus.OFFLINE and self._has_recent_frame(device_id):
                status = DeviceStatus.ONLINE
            if device.status != status:
                device.status = status
                self.device_status_changed.emit(device_id, status.value)
                changed = True
        if changed:
            self.devices_changed.emit()