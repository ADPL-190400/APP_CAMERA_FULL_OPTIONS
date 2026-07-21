"""
PresenceDedup: dedup 1 "sự kiện đang tiếp diễn" (1 cảnh báo hay 1 người quen
vẫn còn trong khung hình) qua nhiều lượt tín hiệu liên tiếp (vd ai_result_ready
bắn nhiều lần/giây theo ai_fps_limit) - chỉ coi là "sự kiện MỚI" nếu chưa từng
thấy, hoặc đã biến mất lâu hơn grace_seconds rồi xuất hiện lại.

Dùng chung bởi pages/liveview_page.py (SYSTEM ALARMS / REAL-TIME DETECTION)
và pages/dashboard_page.py (Event Feed) - cả 2 nơi đều cần tránh log spam
liên tục trong khi 1 điều kiện vẫn còn đúng.
"""
from __future__ import annotations

import time
from typing import Hashable


class PresenceDedup:
    def __init__(self, grace_seconds: float = 5.0):
        self._grace_seconds = grace_seconds
        self._last_seen: dict[Hashable, float] = {}

    def is_new_occurrence(self, key: Hashable) -> bool:
        """Cập nhật last-seen cho key này; trả về True nếu đây là 1 đợt xuất
        hiện MỚI (nên log), False nếu vẫn đang trong 1 đợt đã log rồi."""
        now = time.monotonic()
        last_seen = self._last_seen.get(key)
        is_new = last_seen is None or (now - last_seen) > self._grace_seconds
        self._last_seen[key] = now
        return is_new

    def clear(self) -> None:
        self._last_seen.clear()
