"""
Model dữ liệu cho 1 sự kiện cảnh báo (Event Log) - ppe/fire/fall/stranger/
face_checkin/face_checkout/face_recognized/occupancy, mỗi sự kiện kèm 1 ảnh
bằng chứng (full frame lúc alert được xác nhận, RIÊNG stranger/
face_recognized/face_checkin/face_checkout dùng ảnh crop khuôn mặt - xem
CameraPipeline._capture_face_events/pages/gate_kiosk_page.py).
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
    FACE_CHECKIN = "face_checkin"  # FaceApp điểm danh VÀO/nhận diện người quen - xem pages/face_attendance_page.py
    # Gate Kiosk cổng RA (direction="out" - pages/gate_kiosk_page.py) - TÁCH
    # RIÊNG khỏi FACE_CHECKIN (cổng vào) để cột "Event Type" ở Event Log
    # phân biệt được đúng hướng, không phải đoán qua tên camera. Face App
    # (kiosk 1 hướng duy nhất, không có khái niệm vào/ra) không dùng kind này.
    FACE_CHECKOUT = "face_checkout"
    OCCUPANCY_ALERT = "occupancy_alert"  # vượt ngưỡng số người (AIConfig.occupancy_threshold)
    # Nhận diện được 1 người QUEN ở Live View/Dashboard (core/camera_pipeline.py -
    # camera bật "Face recognition" ở tab AI, KHÁC FACE_CHECKIN vốn là hành
    # động điểm danh thật của Face App/pages/face_attendance_page.py, có gửi
    # Web_API.send_mobile_employee) - đây chỉ là log "đã thấy người này qua
    # camera", không kèm hành động điểm danh nào.
    FACE_RECOGNIZED = "face_recognized"
    # Mật độ đông CỤC BỘ (heatmap lưới theo vùng ROI, xem
    # CameraPipeline._update_crowd_heatmap) - KHÁC OCCUPANCY_ALERT (đếm TỔNG
    # số người trong ROI): cảnh báo này bắt trường hợp người tụ tập dồn vào 1
    # góc nhỏ dù tổng số người chưa vượt ngưỡng occupancy.
    CROWD_ALERT = "crowd_alert"


# kind -> tên hiển thị (dùng chung cho event_log_page + mọi nơi khác cần label)
EVENT_KIND_LABELS: dict[EventKind, str] = {
    EventKind.PPE_VIOLATION: "PPE Violation",
    EventKind.FIRE_ALERT: "Fire / Smoke",
    EventKind.FALL_ALERT: "Fall",
    EventKind.STRANGER_ALERT: "Stranger",
    EventKind.FACE_CHECKIN: "Check-in",
    EventKind.FACE_CHECKOUT: "Check-out",
    EventKind.OCCUPANCY_ALERT: "Overcrowding",
    EventKind.FACE_RECOGNIZED: "Recognized",
    EventKind.CROWD_ALERT: "Crowd Density",
}

# kind -> type_id gửi kèm Web_API.send_mobile_incident() - đã xác nhận với
# backend (khớp quy ước type_id của D:\APP_MIRAI_ver1, PPE chỉnh lại thành
# 1 - không dùng số 5 "PPE Compliance Check" ở 1 code path khác của MIRAI,
# đã xác nhận là không áp dụng). 1 nguồn sự thật duy nhất cho type_id, dùng
# chung cả core/camera_pipeline.py lẫn pages/gate_kiosk_page.py (stranger
# băng qua vạch) - tránh rải số ma thuật rời rạc như MIRAI.
#
# OCCUPANCY_ALERT/CROWD_ALERT CHỦ Ý không có mặt ở đây - chưa có type_id nào
# được xác nhận với backend cho 2 cảnh báo này, nên chỉ hiện tại chỗ (Event
# Log/SYSTEM ALARMS), KHÔNG đẩy lên mobile app (xem CameraPipeline._capture_events -
# tự bỏ qua bước gửi web cho kind nào không có mặt trong dict này).
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
    # Thông tin phụ tuỳ loại sự kiện - hiện chỉ dùng cho FACE_RECOGNIZED/
    # FACE_CHECKIN/FACE_CHECKOUT (tên người quen được nhận diện, xem
    # CameraPipeline._capture_face_events/pages/face_attendance_page.py/
    # pages/gate_kiosk_page.py) - rỗng với các loại khác (PPE/Fire/Fall/
    # Stranger/Overcrowding không có danh tính cụ thể để hiện).
    detail: str = ""

    @staticmethod
    def new(device_id: str, camera_name: str, kind: EventKind, image_path: str, detail: str = "") -> "EventRecord":
        from datetime import datetime

        return EventRecord(
            id=str(uuid.uuid4())[:8],
            device_id=device_id,
            camera_name=camera_name,
            kind=kind,
            timestamp=datetime.now().isoformat(timespec="seconds"),
            image_path=image_path,
            detail=detail,
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
            detail=d.get("detail", ""),  # bản ghi cũ (trước khi có field này) -> rỗng
        )
