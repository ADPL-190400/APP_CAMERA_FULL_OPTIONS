"""AISettings: ngưỡng confidence + tham số xác nhận cho các model AI dùng
CHUNG (core/ai_model_manager.py) - chỉnh được qua UI (ui/dialogs/ai_settings_dialog.py,
mở từ nút "⚙ Settings" ở sidebar - pages/menu_window.py), lưu cục bộ
config/ai_settings.json, áp dụng NGAY cho mọi camera đang chạy (model dùng
chung 1 instance qua AIModelManager, đọc giá trị mới nhất ở mỗi lượt gọi -
không cần restart pipeline/app).

Tách riêng khỏi AIModelManager: AIModelManager là nơi LOAD + CHẠY model
(torch/insightface, nặng) - dialog cấu hình chỉ cần biết tới AISettings, một
module nhẹ không kéo theo các dependency AI nặng đó."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from typing import ClassVar, Optional

from core.path_manager import BASE_DIR

_SETTINGS_PATH = os.path.join(BASE_DIR, "config", "ai_settings.json")


@dataclass
class AISettings:
    # Ngưỡng confidence khi gọi từng model YOLO (tham số "conf") - core/ai_model_manager.py.
    pose_conf: float = 0.4
    human_conf: float = 0.5
    ppe_conf: float = 0.5
    fire_conf: float = 0.5
    fall_conf: float = 0.75

    # "Xác nhận té ngã" (core/camera_pipeline.py::_check_fall): trong
    # fall_confirm_window lượt AI GẦN NHẤT, phải có ÍT NHẤT
    # fall_confirm_min_count lượt phát hiện "đang ngã" (fall_conf ở trên đã
    # lọc từng lượt) mới thực sự chốt cảnh báo/vẽ khung - tránh báo động chỉ
    # vì 1 lượt nhận diện sai (tư thế bất thường thoáng qua, nhiễu ánh
    # sáng...). fall_confirm_min_count PHẢI <= fall_confirm_window.
    fall_confirm_window: int = 10
    fall_confirm_min_count: int = 5

    _instance: ClassVar[Optional["AISettings"]] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def instance(cls) -> "AISettings":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    settings = cls()
                    settings._load()
                    cls._instance = settings
        return cls._instance

    def _load(self) -> None:
        """Đọc config/ai_settings.json (nếu có) đè lên default - thiếu
        file/lỗi đọc/field lạ -> bỏ qua, giữ nguyên default cho field đó
        (không crash app vì 1 file cấu hình hỏng)."""
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        valid_names = {f.name for f in fields(self)}
        for key, value in saved.items():
            if key in valid_names:
                setattr(self, key, value)

    def save(self) -> None:
        """Ghi TOÀN BỘ giá trị hiện tại xuống config/ai_settings.json - gọi
        sau khi UI (ai_settings_dialog.py) set xong các field mới."""
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
