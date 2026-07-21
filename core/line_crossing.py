"""Hình học line-crossing dùng chung - tách từ CameraPipeline (port gốc từ
Safety_Area.py của MIRAI) để CameraPipeline (đếm người vào/ra) và các gate
kiosk chấm công (pages/gate_kiosk_page.py) dùng chung 1 bản, không lặp lại
thuật toán ccw/segment-intersect."""
from __future__ import annotations


def ccw(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> bool:
    """3 điểm A,B,C có theo thứ tự ngược chiều kim đồng hồ không."""
    return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])


def segments_intersect(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float], d: tuple[float, float]
) -> bool:
    """Đoạn AB có cắt đoạn CD không (dùng cho line-crossing counting)."""
    return ccw(a, c, d) != ccw(b, c, d) and ccw(a, b, c) != ccw(a, b, d)
