"""Cấu hình camera đã chọn cho 3 cửa sổ kiosk (Check In / Check Out -
pages/gate_kiosk_page.py::GateWindow, VÀ Face App -
pages/face_attendance_page.py::FaceAttendanceWindow). Mỗi kiosk lưu 1 file
JSON riêng ({account_dir}/gate_checkin.json, gate_checkout.json,
gate_faceapp.json) - RIÊNG cho tài khoản đang đăng nhập (core/account_context.py,
tránh tài khoản khác dùng chung máy thấy nhầm camera đã chọn) - chỉ lưu
camera đã chọn (device_id), để lần mở sau không phải chọn lại. Vạch đếm
(counting_line, chỉ Gate kiosk cần) KHÔNG lưu riêng ở đây - luôn đọc trực
tiếp từ CameraDevice.counting_line (đã vẽ sẵn ở Camera Config > tab ROI), để
không có 2 nguồn sự thật lệch nhau nếu người dùng vẽ lại vạch sau này. Cùng
pattern atomic-write (tmp + os.replace) với core/event_store.py/device_store.py."""
from __future__ import annotations

import json
import os
from typing import Literal, Optional

from core.account_context import account_dir

GateKind = Literal["checkin", "checkout", "faceapp"]


def _config_path(kind: GateKind) -> str:
    return os.path.join(account_dir(), f"gate_{kind}.json")


def load_gate_config(kind: GateKind) -> Optional[str]:
    """Trả về device_id đã lưu, hoặc None nếu chưa cấu hình lần nào (gọi bởi
    GateWindow/FaceAttendanceWindow lúc mở để quyết định có cần bật
    GateSetupDialog trước khi dùng camera hay không)."""
    path = _config_path(kind)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("device_id") or None
    except (json.JSONDecodeError, OSError, TypeError, KeyError):
        return None


def save_gate_config(kind: GateKind, device_id: str) -> None:
    # account_dir() tự makedirs(exist_ok=True) - không cần gọi lại ở đây.
    path = _config_path(kind)
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"device_id": device_id}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)
