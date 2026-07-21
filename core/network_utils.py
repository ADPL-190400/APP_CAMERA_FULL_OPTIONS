"""Hàm dùng chung để kiểm tra kết nối camera (dùng lại ở discovery + status checker)."""
from __future__ import annotations

import re
import socket
import subprocess

# Cổng thường dùng cho camera IP (RTSP / HTTP quản trị)
CAMERA_PORTS = (554, 80)


def is_port_open(ip: str, port: int, timeout: float = 0.5) -> bool:
    if not ip:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            return sock.connect_ex((ip, port)) == 0
    except OSError:
        return False


def is_ip_camera_reachable(ip: str, timeout: float = 0.5) -> bool:
    return any(is_port_open(ip, port, timeout=timeout) for port in CAMERA_PORTS)


def is_usb_camera_available(index: int) -> bool:
    try:
        import cv2
    except ImportError:
        return False

    cap = cv2.VideoCapture(index)
    ok = cap is not None and cap.isOpened()
    if cap is not None:
        cap.release()
    return ok


def get_mac_address(ip: str, timeout: float = 1.0) -> str:
    """Tra MAC address của 1 IP trong cùng mạng LAN qua bảng ARP của hệ điều
    hành ("arp -a") - chỉ có tác dụng nếu host vừa giao tiếp với IP đó (ARP
    cache có entry). Gọi hàm này SAU khi đã is_port_open()/is_ip_camera_reachable()
    tới IP đó (như trong DeviceDiscoveryWorker._scan_network) để đảm bảo ARP
    cache vừa được populate. Không tìm được (IP ngoài LAN, arp lỗi...) -> trả
    về "" thay vì lỗi, vì đây chỉ là thông tin bổ sung, không bắt buộc."""
    try:
        output = subprocess.run(
            ["arp", "-a", ip], capture_output=True, text=True, timeout=timeout,
        ).stdout
    except Exception:  # noqa: BLE001 - không có lệnh arp/timeout đều coi như "không tìm được"
        return ""
    match = re.search(r"([0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}", output)
    if not match:
        return ""
    return match.group(0).upper().replace("-", ":")


def get_local_subnet_prefix() -> str | None:
    """Trả về 3 octet đầu của IP LAN hiện tại, ví dụ '192.168.1'."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            local_ip = sock.getsockname()[0]
        return ".".join(local_ip.split(".")[:3])
    except OSError:
        return None