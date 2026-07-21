"""
Lưu / đọc danh sách camera ra file JSON trên đĩa.
Nhờ vậy khi mở lại app, danh sách camera (IP, USB, cấu hình từng tab...)
được tự động load lại, không phải "Online Device" quét lại từ đầu mỗi lần.
"""
from __future__ import annotations

import json
import os

from core.models.camera_device import CameraDevice

try:
    from core.path_manager import BASE_DIR
except ImportError:
    # Fallback nếu chưa có path_manager trong project (chỉ để chạy độc lập/test)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DEFAULT_STORE_PATH = os.path.join(BASE_DIR, "config", "devices.json")


def save_devices(devices: list[CameraDevice], path: str = DEFAULT_STORE_PATH) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = [d.to_dict() for d in devices]

    # Ghi ra file tạm rồi rename (atomic) để tránh hỏng file devices.json
    # nếu app bị tắt/crash đúng lúc đang ghi.
    tmp_path = path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def load_devices(path: str = DEFAULT_STORE_PATH) -> list[CameraDevice]:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [CameraDevice.from_dict(item) for item in raw]
    except (json.JSONDecodeError, OSError, TypeError, KeyError, ValueError):
        # File hỏng/không đọc được -> coi như chưa có dữ liệu, không crash app.
        return []