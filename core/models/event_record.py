"""
Model dữ liệu cho 1 sự kiện cảnh báo (Event Log) - ppe/fire/fall/stranger,
mỗi sự kiện kèm 1 ảnh bằng chứng (full frame lúc alert được xác nhận).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
import uuid


class EventKind(str, Enum):
    PPE_VIOLATION = "ppe_violation"
    FIRE_ALERT = "fire_alert"
    FALL_ALERT = "fall_alert"
    STRANGER_ALERT = "stranger_alert"


# kind -> tên hiển thị (dùng chung cho event_log_page + mọi nơi khác cần label)
EVENT_KIND_LABELS: dict[EventKind, str] = {
    EventKind.PPE_VIOLATION: "PPE vi phạm",
    EventKind.FIRE_ALERT: "Cháy / Khói",
    EventKind.FALL_ALERT: "Té ngã",
    EventKind.STRANGER_ALERT: "Người lạ",
}


@dataclass
class EventRecord:
    id: str
    device_id: str
    camera_name: str          # lưu kèm tên lúc xảy ra - camera có thể bị đổi tên/xoá sau này
    kind: EventKind
    timestamp: str             # ISO format datetime.now().isoformat()
    image_path: str            # đường dẫn tuyệt đối tới file ảnh bằng chứng

    @staticmethod
    def new(device_id: str, camera_name: str, kind: EventKind, image_path: str) -> "EventRecord":
        from datetime import datetime

        return EventRecord(
            id=str(uuid.uuid4())[:8],
            device_id=device_id,
            camera_name=camera_name,
            kind=kind,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            image_path=image_path,
        )

    def to_dict(self) -> dict:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @staticmethod
    def from_dict(d: dict) -> "EventRecord":
        return EventRecord(
            id=d["id"],
            device_id=d["device_id"],
            camera_name=d["camera_name"],
            kind=EventKind(d["kind"]),
            timestamp=d["timestamp"],
            image_path=d["image_path"],
        )
