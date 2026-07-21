"""
StatusCheckWorker: kiểm tra nhanh xem từng camera còn kết nối được không
(Online/Offline), chạy trên QThread riêng để không đứng UI.

Được DeviceManager gọi định kỳ (mỗi N giây) -> tự động cập nhật cột
Status trong bảng, không cần người dùng bấm Refresh/Online Device thủ công.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QThread, pyqtSignal

from core.models.camera_device import CameraDevice, DeviceType, DeviceStatus
from core.network_utils import is_ip_camera_reachable, is_usb_camera_available

_CHECK_TIMEOUT = 1.0


class StatusCheckWorker(QThread):
    result_ready = pyqtSignal(dict)  # {device_id: DeviceStatus}

    def __init__(self, devices: list[CameraDevice], parent=None):
        super().__init__(parent)
        # Chụp snapshot dữ liệu cần thiết, không giữ tham chiếu object gốc
        # vì object có thể bị sửa/xoá từ thread chính trong lúc worker đang chạy.
        self._targets = [
            (d.id, d.device_type, d.ip_address, d.usb_index) for d in devices
        ]

    def run(self) -> None:
        results: dict[str, DeviceStatus] = {}
        with ThreadPoolExecutor(max_workers=16) as executor:
            future_map = {
                executor.submit(self._check_one, device_type, ip, usb_index): device_id
                for device_id, device_type, ip, usb_index in self._targets
            }
            for future, device_id in future_map.items():
                results[device_id] = future.result()

        self.result_ready.emit(results)

    @staticmethod
    def _check_one(device_type: DeviceType, ip_address: str, usb_index: int) -> DeviceStatus:
        if device_type == DeviceType.USB:
            ok = is_usb_camera_available(usb_index)
        else:
            ok = is_ip_camera_reachable(ip_address, timeout=_CHECK_TIMEOUT)
        return DeviceStatus.ONLINE if ok else DeviceStatus.OFFLINE