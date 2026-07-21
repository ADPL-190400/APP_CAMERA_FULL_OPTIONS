"""
DeviceDiscoveryWorker: quét camera USB (webcam) và camera IP trong LAN.
Chạy trên QThread riêng vì scan mạng có thể mất vài giây -> không được
chặn giao diện chính.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from PyQt6.QtCore import QThread, pyqtSignal

from core.models.camera_device import CameraDevice, DeviceType, DeviceStatus
from core.network_utils import (
    is_ip_camera_reachable,
    is_usb_camera_available,
    get_local_subnet_prefix,
    get_mac_address,
)

_SCAN_TIMEOUT = 0.3


class DeviceDiscoveryWorker(QThread):
    progress = pyqtSignal(str)                 # thông báo tiến trình (hiện lên UI nếu muốn)
    finished_scan = pyqtSignal(list)             # list[CameraDevice] tìm được

    def __init__(self, scan_usb: bool = True, scan_network: bool = True, parent=None):
        super().__init__(parent)
        self.scan_usb = scan_usb
        self.scan_network = scan_network

    def run(self) -> None:
        found: list[CameraDevice] = []

        if self.scan_usb:
            self.progress.emit("Đang quét camera USB...")
            found.extend(self._scan_usb())

        if self.scan_network:
            self.progress.emit("Đang quét camera IP trong mạng LAN...")
            found.extend(self._scan_network())

        self.finished_scan.emit(found)

    # ---------------- USB ----------------
    def _scan_usb(self, max_index: int = 6) -> list[CameraDevice]:
        results: list[CameraDevice] = []
        for index in range(max_index):
            if is_usb_camera_available(index):
                results.append(
                    CameraDevice(
                        name=f"USB Camera {index}",
                        device_type=DeviceType.USB,
                        usb_index=index,
                        serial_no=f"USB-{index}",
                        status=DeviceStatus.ONLINE,
                    )
                )
        return results

    # ---------------- Network (IP camera) ----------------
    def _scan_network(self) -> list[CameraDevice]:
        subnet_prefix = get_local_subnet_prefix()
        if subnet_prefix is None:
            self.progress.emit("Không xác định được subnet mạng LAN.")
            return []

        hosts = [f"{subnet_prefix}.{i}" for i in range(1, 255)]
        found: list[CameraDevice] = []

        with ThreadPoolExecutor(max_workers=64) as executor:
            checks = executor.map(lambda ip: is_ip_camera_reachable(ip, _SCAN_TIMEOUT), hosts)
            for ip, is_camera in zip(hosts, checks):
                if is_camera:
                    found.append(
                        CameraDevice(
                            name=f"IP Camera {ip}",
                            device_type=DeviceType.IP,
                            ip_address=ip,
                            stream_url=f"rtsp://{ip}/stream1",
                            status=DeviceStatus.ONLINE,
                            # ARP cache vừa được populate bởi is_ip_camera_reachable()
                            # (connect thử tới ip) ở dòng trên - tra được luôn ở đây.
                            mac_address=get_mac_address(ip),
                        )
                    )
        return found