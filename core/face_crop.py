"""Crop 1 khuôn mặt từ frame theo bbox + padding - tách từ
EnrollWorker._save_avatar (pages/face_attendance_page.py) để
FaceCard/gate_kiosk_page.py dùng chung, không lặp lại phép tính padding/clamp
biên."""
from __future__ import annotations

import numpy as np


def crop_face_with_padding(
    frame: np.ndarray, bbox: tuple[int, int, int, int], pad_ratio: float = 0.4
) -> np.ndarray:
    """bbox: (x1, y1, x2, y2). Mở rộng thêm pad_ratio * cạnh dài nhất của
    bbox mỗi phía (giữ thêm chút bối cảnh quanh mặt, giống avatar đăng ký),
    clamp trong biên frame. Trả về mảng rỗng (size 0) nếu bbox suy biến."""
    x1, y1, x2, y2 = bbox
    h, w = frame.shape[:2]
    pad = int(pad_ratio * max(x2 - x1, y2 - y1))
    x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
    x2, y2 = min(w, x2 + pad), min(h, y2 + pad)
    return frame[y1:y2, x1:x2]
