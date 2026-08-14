"""
Model dữ liệu cho 1 sự kiện cảnh báo (Event Log) - ppe/fire/fall/stranger/
face_checkin, mỗi sự kiện kèm 1 ảnh bằng chứng (full frame lúc alert/nhận
diện được xác nhận).
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
    FACE_CHECKIN = "face_checkin"  # FaceApp nhận diện người quen - xem pages/face_attendance_page.py


# kind -> tên hiển thị (dùng chung cho event_log_page + mọi nơi khác cần label)
EVENT_KIND_LABELS: dict[EventKind, str] = {
    EventKind.PPE_VIOLATION: "PPE Violation",
    EventKind.FIRE_ALERT: "Fire / Smoke",
    EventKind.FALL_ALERT: "Fall",
    EventKind.STRANGER_ALERT: "Stranger",
    EventKind.FACE_CHECKIN: "Check-in",
}

# kind -> type_id gửi kèm Web_API.send_mobile_incident() - đã xác nhận với
# backend (khớp quy ước type_id của D:\APP_MIRAI_ver1, PPE chỉnh lại thành
# 1 - không dùng số 5 "PPE Compliance Check" ở 1 code path khác của MIRAI,
# đã xác nhận là không áp dụng). 1 nguồn sự thật duy nhất cho type_id, dùng
# chung cả core/camera_pipeline.py lẫn pages/gate_kiosk_page.py (stranger
# băng qua vạch) - tránh rải số ma thuật rời rạc như MIRAI.
EVENT_KIND_INCIDENT_TYPE_ID: dict[EventKind, int] = {
    EventKind.PPE_VIOLATION: 1,
    EventKind.STRANGER_ALERT: 2,
    EventKind.FALL_ALERT: 3,
    EventKind.FIRE_ALERT: 4,
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
