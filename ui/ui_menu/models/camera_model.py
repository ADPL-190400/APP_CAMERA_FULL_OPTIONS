"""
ui/models/camera_model.py
=========================
Data model cho một camera.  Tách hoàn toàn khỏi UI.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class CameraModel:
    """
    Represents one physical/virtual camera in the system.
    Thay đổi thuộc tính → gọi on_changed callback để UI tự refresh.
    """
    cam_id: str               # "01" .. "16"
    name: str = ""
    ip: str = ""
    port: int = 554
    fps: int = 0
    ai_enabled: bool = False
    recording: bool = False
    online: bool = True
    ai_class: str = ""        # Last detected class
    ai_confidence: float = 0.0

    # Kết quả AI mới nhất (từ DeviceManager.ai_result_ready) - đếm người,
    # vào/ra, và 3 cảnh báo độc lập (PPE/Fire/Fall).
    num_people: int = 0
    num_in: int = 0
    num_out: int = 0
    ppe_violation: bool = False
    fire_alert: bool = False
    fall_alert: bool = False
    stranger_alert: bool = False
    occupancy_alert: bool = False

    # Internal – UI callback
    _on_changed: Optional[Callable] = field(default=None, repr=False, compare=False)

    def update(self, **kwargs) -> None:
        """Update fields và trigger UI refresh."""
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        if self._on_changed:
            self._on_changed(self)

    def bind(self, callback: Callable) -> None:
        self._on_changed = callback

    def unbind(self) -> None:
        """Gỡ callback hiện tại - PHẢI gọi trước khi widget đang bind (vd
        CameraCard) bị huỷ (deleteLater), nếu không update() sau đó sẽ gọi
        vào 1 widget C++ đã bị xoá -> RuntimeError "wrapped C/C++ object...
        has been deleted". model.update() vẫn cập nhật field bình thường,
        chỉ bỏ qua bước gọi callback khi không có ai đang bind (_on_changed
        is None)."""
        self._on_changed = None
