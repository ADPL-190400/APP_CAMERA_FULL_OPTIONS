"""
CameraPipeline: luồng xử lý NỀN cho 1 camera - độc lập với việc có trang
nào đang mở/xem hay không.

Vòng đời:
    DeviceManager.start_device(id)  -> tạo & start 1 CameraPipeline
    DeviceManager.stop_device(id)   -> stop & huỷ pipeline đó

Trong lúc đang chạy, pipeline luôn:
    1. Đọc frame liên tục từ nguồn (RTSP/HTTP cho IP camera, index cho USB).
    2. Chạy AI trên từng frame NẾU camera có bật AI (device.ai.enabled) -
       hiện tại là Body/Pose detection (AIModelManager, model dùng chung
       mọi camera) + DeepSort tracking (tracker riêng từng camera) + đếm
       vào/ra + occupancy (theo ROI) + PPE detection (theo working-area
       ROI, port từ Safety_Area.py) + Fire detection (toàn khung hình,
       port từ YOLO_FIRE.py) + Fall detection (crop quanh người, port từ
       Fall_detection.py).
Việc đọc frame + chạy AI này chạy BẤT KỂ có ai đang xem preview hay không
(đúng yêu cầu "AI vẫn thực thi" dù không hiện hình).

Chỉ riêng việc PHÁT hình (convert sang QImage + emit frame_ready) mới cần
có ít nhất 1 "viewer" đang theo dõi (camera_config_page khi bật nút
preview, hoặc 1 CameraCard trong liveview_page khi camera được tick chọn
hiển thị) - dùng add_viewer()/remove_viewer() để tăng/giảm đếm. Camera nào
không ai xem thì bỏ qua bước convert/emit để giảm tải CPU, nhưng vòng lặp
đọc frame + AI vẫn chạy bình thường.
"""
from __future__ import annotations

import os
import time
from collections import deque

import cv2
import numpy as np
import torch
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from core.ai_model_manager import AIModelManager
from core.deep_sort_pytorch.deep_sort import DeepSort
from core.deep_sort_pytorch.utils.parser import get_config
from core.event_dedup import PresenceDedup
from core.event_store import EventStore
from core.known_faces_store import KnownFacesStore
from core.line_crossing import ccw, segments_intersect
from core.models.camera_device import (
    parse_inference_imgsz,
    parse_points,
    parse_preview_max_width,
    parse_resolution_wh,
)
from core.models.event_record import EventKind
from core.path_manager import BASE_DIR

_DEEPSORT_YAML = os.path.join(BASE_DIR, "core", "deep_sort_pytorch", "configs", "deep_sort.yaml")
_REID_CKPT = os.path.join(
    BASE_DIR, "core", "deep_sort_pytorch", "deep_sort", "deep", "checkpoint", "ckpt.t7"
)

# Fall detection - port nguyên tham số từ Fall_detection.py của MIRAI.
_FALL_BUFFER_LEN = 10             # làm mượt trên 10 frame AI (~0.3-0.5s ở ai_fps_limit gốc)
_FALL_POSE_CONF_THRESHOLD = 0.3   # keypoint có conf thấp hơn -> bỏ qua người này (pose không đủ tin cậy)
_FALL_CONF_THRESHOLD = 0.7        # confidence model fall_detection.pt phải vượt mới coi là "đang ngã"
_FALL_REQUIRED_KEYPOINTS = (5, 6, 11, 12, 15, 16)  # vai, hông, mắt cá (COCO-17) - phải thấy đủ mới xét ngã
_FALL_CROP_PADDING = 30

# Face recognition - port từ Face_detection.py của MIRAI.
_FACE_DET_SCORE_THRESHOLD = 0.5   # ngưỡng chất lượng detection, giống mọi model YOLO khác ở đây
_STRANGER_STREAK_REQUIRED = 3      # cần 3 lượt AI liên tiếp thấy "Stranger" mới báo động (tránh nhiễu 1 frame)

# Event Log: cùng ngưỡng "đợt vi phạm mới" với Event Feed/System Alarms
# (dashboard_page.py/liveview_page.py) - tránh lưu ảnh spam liên tục trong
# lúc 1 điều kiện vẫn còn đúng.
_EVENT_LOG_GRACE_SEC = 5.0


class CameraPipeline(QThread):
    frame_ready = pyqtSignal(str, QImage)   # device_id, frame (chỉ emit khi có viewer)
    error_occurred = pyqtSignal(str, str)   # device_id, message
    ai_result_ready = pyqtSignal(str, dict)  # device_id, {"num_people","num_in","num_out","ppe_violation","fire_alert","fall_alert"}

    def __init__(
        self,
        device_id: str,
        source: str | int,
        device_name: str = "",
        ai_enabled: bool = False,
        reconnect_timeout: int = 10,
        ai_fps_limit: int = 10,
        counting_line: str = "",
        roi_polygons: list[str] | None = None,
        enable_counting: bool = False,
        enable_occupancy: bool = False,
        enable_ppe: bool = False,
        enable_fire: bool = False,
        enable_fall: bool = False,
        enable_face_recognition: bool = False,
        show_bbox: bool = True,
        show_label: bool = True,
        show_roi: bool = False,
        show_tracking_id: bool = False,
        preview_max_width: int = 0,
        capture_resolution: tuple[int, int] | None = None,
        display_fps_limit: int = 30,
        inference_quality: str = "Balanced (480px - khuyến nghị)",
        parent=None,
    ):
        super().__init__(parent)
        self._device_id = device_id
        self._device_name = device_name or device_id
        self._event_dedup = PresenceDedup(_EVENT_LOG_GRACE_SEC)
        # USB camera lưu dưới dạng "0", "1"... -> cv2 cần int index.
        self._source = int(source) if isinstance(source, str) and source.isdigit() else source
        self._ai_fps_limit = max(1, ai_fps_limit)
        self._reconnect_timeout_ms = max(1, reconnect_timeout) * 1000
        self._running = True
        self._viewer_count = 0
        # Viewer nào cần frame FULL-RES thật (vd ROIEditorDialog - toạ độ ROI
        # phải khớp đúng hệ toạ độ frame mà AI/occupancy/PPE dùng, không được
        # lấy theo frame đã downscale để hiển thị) - xem _apply_preview_downscale().
        self._full_res_viewer_count = 0

        # Yêu cầu USB camera capture ĐÚNG resolution này (tab Basic) - chỉ áp
        # dụng lúc mở capture (_open_capture), không live-update được như các
        # cờ khác vì đổi resolution 1 VideoCapture đang chạy không an toàn -
        # đổi Resolution cho camera USB đang chạy cần Stop/Start lại mới có
        # tác dụng. Không có tác dụng với IP/RTSP (server quyết định resolution).
        self._capture_resolution = capture_resolution
        self._last_emit_ts = 0.0

        # Thời điểm (monotonic) đọc frame THẬT gần nhất từ camera - cập nhật
        # ngay trong vòng lặp run(), KHÔNG phụ thuộc _viewer_count (frame_ready
        # chỉ emit khi có viewer xem preview). DeviceManager dùng giá trị này
        # làm bằng chứng "đang thực sự có video" đáng tin hơn 1 lần probe TCP
        # độc lập của StatusCheckWorker - đọc/ghi 1 float đơn giữa 2 thread
        # không cần lock (an toàn nhờ GIL, giống self._running).
        self._last_frame_ts = 0.0

        # AI: model Body/Pose dùng CHUNG (AIModelManager), tracker DeepSort
        # RIÊNG cho camera này (không share state track giữa các camera).
        self._tracker: DeepSort | None = None
        self._last_ai_ts = 0.0
        self._last_tracks = []  # [[x1,y1,x2,y2,track_id,cls], ...]
        self._track_history: dict[int, list[tuple[int, int]]] = {}
        self._people_in = 0
        self._people_out = 0
        self._last_ppe_violation = False
        self._last_fire_alert = False
        self._last_fall_alert = False
        self._last_stranger_alert = False
        self._last_face_boxes: list[tuple[int, int, int, int, str, bool]] = []  # x1,y1,x2,y2,name,is_stranger

        # Toàn bộ cờ enable/ROI/Line/Overlay được gom vào update_ai_settings()
        # - dùng chung cho cả lúc khởi tạo LẪN khi DeviceManager đẩy cấu hình
        # mới vào giữa lúc đang chạy (Save/Apply ở camera_config_page hoặc ROI
        # Editor) - không cần Stop/Start lại mới thấy hiệu lực.
        self.update_ai_settings(
            ai_enabled=ai_enabled,
            enable_counting=enable_counting,
            enable_occupancy=enable_occupancy,
            enable_ppe=enable_ppe,
            enable_fire=enable_fire,
            enable_fall=enable_fall,
            enable_face_recognition=enable_face_recognition,
            counting_line=counting_line,
            roi_polygons=roi_polygons,
            show_bbox=show_bbox,
            show_label=show_label,
            show_roi=show_roi,
            show_tracking_id=show_tracking_id,
            preview_max_width=preview_max_width,
            display_fps_limit=display_fps_limit,
            inference_quality=inference_quality,
        )

    def update_ai_settings(
        self,
        ai_enabled: bool,
        enable_counting: bool,
        enable_occupancy: bool,
        enable_ppe: bool,
        enable_fire: bool,
        enable_fall: bool,
        enable_face_recognition: bool,
        counting_line: str,
        roi_polygons: list[str] | None,
        show_bbox: bool,
        show_label: bool,
        show_roi: bool,
        show_tracking_id: bool,
        preview_max_width: int = 0,
        display_fps_limit: int = 30,
        inference_quality: str = "Balanced (480px - khuyến nghị)",
    ) -> None:
        """Cập nhật cấu hình AI/ROI/Line/Overlay của pipeline NGAY LẬP TỨC, kể
        cả khi đang chạy - gọi bởi DeviceManager mỗi khi Save/Apply (hoặc ROI
        Editor Accept). Trước đây các cờ này chỉ đọc 1 LẦN lúc khởi tạo
        CameraPipeline, nên tắt "Enable AI"/đổi ROI/bật thêm PPE... trong lúc
        camera đang chạy không có tác dụng gì cho tới khi Stop/Start lại -
        đây chính là điều làm người dùng tưởng nhầm là các tính năng "không
        hoạt động". Việc gán lại các thuộc tính đơn giản (bool/list) ở đây an
        toàn khi gọi từ thread khác (main thread) trong khi vòng lặp run()
        đang đọc chúng ở 1 QThread riêng - CPython gán thuộc tính là 1 bước
        nguyên tử (atomic), không cần Lock.
        """
        self._ai_enabled = ai_enabled

        # Camera có thể bật NHIỀU tính năng AI cùng lúc (checkbox multi-select
        # ở tab AI) - mỗi cờ dưới đây gate riêng 1 tính năng ở _run_ai(). Vẫn
        # giữ thêm lớp an toàn "không có ROI/Line thì không làm gì" bên trong
        # từng hàm _check_*/_update_counting/_count_occupancy - bật cờ mà
        # thiếu cấu hình chỉ đơn giản là no-op, không lỗi.
        self._enable_counting = enable_counting
        self._enable_occupancy = enable_occupancy
        self._enable_ppe = enable_ppe
        self._enable_fire = enable_fire
        self._enable_fall = enable_fall
        self._enable_face_recognition = enable_face_recognition

        # Overlay (tab Overlay của camera_config_page) - vẽ TRỰC TIẾP lên
        # frame trước khi emit, để Basic tab preview lẫn LiveView card đều
        # thấy overlay "miễn phí" (không cần vẽ lại ở từng nơi hiển thị).
        # show_confidence không áp dụng được ở đây vì DeepSort (vendored) chỉ
        # trả về bbox+track_id+class, không giữ lại confidence gốc theo track.
        self._show_bbox = show_bbox
        self._show_label = show_label
        self._show_roi = show_roi
        self._show_tracking_id = show_tracking_id

        # Giới hạn độ phân giải HIỂN THỊ (tab Basic, dropdown Resolution) -
        # chỉ áp dụng cho frame gửi đi hiển thị (_apply_preview_downscale),
        # KHÔNG đụng tới frame AI dùng để detect (vẫn full-res gốc). 0/không
        # parse được = không giới hạn.
        self._preview_max_width = preview_max_width

        # Giới hạn tốc độ EMIT hình cho viewer (tab Basic, spin FPS) - khác
        # AI FPS Limit (throttle việc CHẠY AI ở _run_ai): cái này throttle
        # việc convert/gửi hình hiển thị (_should_emit_frame), giảm CPU
        # cvtColor/QImage/emit khi camera nguồn fps cao hơn nhiều so với nhu
        # cầu xem thực tế. Live-update được vì chỉ là so sánh thời gian,
        # không đụng gì tới VideoCapture đang mở (khác capture_resolution).
        self._display_fps_limit = max(1, display_fps_limit)

        # Kích thước ảnh đưa vào model YOLO (pose/ppe/fire/fall) - tab AI,
        # dropdown Detection Quality. Giảm xuống Fast/Balanced tăng tốc đáng
        # kể khi nhiều camera cùng chạy AI (xem parse_inference_imgsz để biết
        # số đo thực tế) - live-update được, chỉ là tham số truyền mỗi lần
        # gọi model, không phải cấu hình cố định của model.
        self._inference_imgsz = parse_inference_imgsz(inference_quality)

        # Đếm vào/ra: đổi Counting Line giữa chừng KHÔNG reset num_in/num_out
        # đã đếm được - chỉ áp dụng đường mới cho các lượt băng qua từ lúc
        # này trở đi.
        line_points = parse_points(counting_line)
        self._counting_line = (line_points[0], line_points[1]) if len(line_points) == 2 else None

        # Occupancy: vùng ROI (polygon) để tính số người hiện tại; không có
        # ROI nào -> đếm tất cả track đang active, không giới hạn vùng.
        self._roi_polygons = [
            np.array(pts, dtype=np.int32)
            for pts in (parse_points(p) for p in (roi_polygons or []))
            if len(pts) >= 3
        ]

        # Reset trạng thái debounce (PPE streak, Fall buffer) mỗi khi cấu hình
        # đổi - tránh mang state cũ (ví dụ streak dở dang từ trước khi tắt
        # PPE) áp dụng nhầm cho cấu hình mới.
        self._ppe_violation_streak = 0
        self._fall_buffer: deque[bool] = deque(maxlen=_FALL_BUFFER_LEN)
        self._fall_confirmed = False
        self._stranger_streak = 0

    # ------------------------------------------------------------------ #
    # Điều khiển từ bên ngoài (main thread)
    # ------------------------------------------------------------------ #
    def stop(self) -> None:
        self._running = False

    def add_viewer(self, need_full_resolution: bool = False) -> None:
        self._viewer_count += 1
        if need_full_resolution:
            self._full_res_viewer_count += 1

    def remove_viewer(self, need_full_resolution: bool = False) -> None:
        self._viewer_count = max(0, self._viewer_count - 1)
        if need_full_resolution:
            self._full_res_viewer_count = max(0, self._full_res_viewer_count - 1)

    @property
    def has_viewers(self) -> bool:
        return self._viewer_count > 0

    @property
    def last_frame_ts(self) -> float:
        """monotonic() lần đọc frame thành công gần nhất từ camera (0.0 nếu
        chưa từng đọc được frame nào) - xem DeviceManager._has_recent_frame."""
        return self._last_frame_ts

    # ------------------------------------------------------------------ #
    # Vòng lặp chạy nền
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        cap = self._open_capture()
        if cap is None:
            self.error_occurred.emit(self._device_id, f"Không thể mở nguồn video: {self._source}")
            return

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    cap.release()
                    cap = self._reconnect()
                    if cap is None:
                        return
                    continue

                self._last_frame_ts = time.monotonic()

                if self._ai_enabled:
                    self._run_ai(frame)

                if self._viewer_count > 0 and self._should_emit_frame():
                    if self._ai_enabled:
                        self._draw_overlay(frame)
                    frame = self._apply_preview_downscale(frame)
                    image = self._to_qimage(frame)
                    if image is not None:
                        self.frame_ready.emit(self._device_id, image)
        finally:
            cap.release()

    def _run_ai(self, frame) -> None:
        """Chạy đúng những tính năng AI được BẬT cho camera này (checkbox
        multi-select ở tab AI) - không chạy Body/Pose (tốn nhất, cần
        AIModelManager Lock dùng chung) nếu không tính năng nào cần tới nó.
        Throttle theo ai_fps_limit - không chạy AI trên MỌI frame capture."""
        now = time.monotonic()
        if now - self._last_ai_ts < 1.0 / self._ai_fps_limit:
            return
        self._last_ai_ts = now

        fire_alert = self._check_fire(frame) if self._enable_fire else False
        known_faces, stranger_alert = (
            self._check_faces(frame) if self._enable_face_recognition else ([], False)
        )

        # Đếm vào/ra, Occupancy, PPE chỉ cần BBOX (không cần keypoints) nên
        # dùng human.pt (detector thuần, ~7ms/frame - nhẹ hơn nhiều so với
        # yolov8x-pose 17-41ms/frame). Fall là tính năng DUY NHẤT thực sự
        # cần keypoints nên vẫn gọi riêng pose model (detect_bodies) - xem
        # AIModelManager.detect_humans/detect_bodies.
        need_person = self._enable_counting or self._enable_occupancy or self._enable_ppe
        need_pose = self._enable_fall

        num_people = 0
        ppe_violation = False
        if need_person:
            person_result = AIModelManager.instance().detect_humans(frame, imgsz=self._inference_imgsz)
            boxes = person_result.boxes
            need_tracking = self._enable_counting or self._enable_occupancy

            if boxes is None or len(boxes) == 0:
                if need_tracking:
                    self._last_tracks = []
                    self._prune_track_history(active_ids=set())
                if self._enable_ppe:
                    self._ppe_violation_streak = 0
            else:
                if need_tracking:
                    bbox_xywh = torch.Tensor([self._xyxy_to_xywh(b) for b in boxes.xyxy.cpu().numpy()])
                    confidences = torch.Tensor(boxes.conf.cpu().numpy())
                    classes = boxes.cls.cpu().numpy().astype(int).tolist()

                    outputs = self._get_tracker().update(bbox_xywh, confidences, classes, frame)
                    self._last_tracks = outputs
                    if self._enable_counting:
                        self._update_counting(outputs)
                    if self._enable_occupancy:
                        num_people = self._count_occupancy(outputs)
                if self._enable_ppe:
                    ppe_violation = self._check_ppe(frame, boxes)

        fall_alert = False
        if need_pose:
            pose_result = AIModelManager.instance().detect_bodies(frame, imgsz=self._inference_imgsz)
            fall_alert = self._check_fall(frame, pose_result)

        self._capture_events(frame, ppe_violation, fire_alert, fall_alert, stranger_alert)

        self._emit_ai_result(
            num_people=num_people,
            ppe_violation=ppe_violation,
            fire_alert=fire_alert,
            fall_alert=fall_alert,
            known_faces=known_faces,
            stranger_alert=stranger_alert,
        )

    def _capture_events(self, frame, ppe_violation, fire_alert, fall_alert, stranger_alert) -> None:
        """Lưu ảnh bằng chứng (EventStore) cho mỗi ĐỢT cảnh báo MỚI - dedup
        qua PresenceDedup (cùng ngưỡng grace với Event Feed/System Alarms),
        không lưu lặp lại khi 1 điều kiện còn tiếp diễn liên tục. Chạy ngay
        trong thread của pipeline này (đã có sẵn frame full-res), không phụ
        thuộc có viewer đang xem preview hay không."""
        checks = (
            (ppe_violation, EventKind.PPE_VIOLATION),
            (fire_alert, EventKind.FIRE_ALERT),
            (fall_alert, EventKind.FALL_ALERT),
            (stranger_alert, EventKind.STRANGER_ALERT),
        )
        for is_active, kind in checks:
            if is_active and self._event_dedup.is_new_occurrence(kind):
                evidence_frame = self._build_evidence_frame(frame)
                EventStore.instance().add_event(self._device_id, self._device_name, kind, evidence_frame)

    def _build_evidence_frame(self, frame):
        """Ảnh bằng chứng = frame gốc + vẽ vùng ROI (nếu camera có cấu hình)
        để biết rõ vùng làm việc/khu vực liên quan tới cảnh báo. Vẽ trên 1
        BẢN SAO, không đụng tới frame gốc (vẫn được dùng tiếp cho overlay
        preview ngay sau _run_ai trong run())."""
        if not self._roi_polygons:
            return frame
        evidence = frame.copy()
        for polygon in self._roi_polygons:
            cv2.polylines(evidence, [polygon], isClosed=True, color=(120, 200, 0), thickness=2)
        return evidence

    def _check_fire(self, frame) -> bool:
        """Fire detection port từ YOLO_FIRE.py: chạy trên TOÀN khung hình,
        độc lập với Body/Pose - không cần ROI, không cần có người. Không
        làm mượt/debounce thêm - giữ nguyên hành vi gốc (mỗi frame AI có
        box là báo động ngay, bản gốc chỉ throttle việc GỬI alert ra ngoài
        chứ không throttle chính giá trị phát hiện)."""
        result = AIModelManager.instance().detect_fire(frame, imgsz=self._inference_imgsz)
        boxes = result.boxes
        return boxes is not None and len(boxes) > 0

    def _check_faces(self, frame) -> tuple[list[str], bool]:
        """Face recognition port từ Face_detection.py của MIRAI: chạy trên
        TOÀN khung hình, độc lập Body/Pose (giống Fire). Mỗi face detect
        được so với KnownFacesStore (dùng chung mọi camera, tự lấy từ
        Web_API) - khớp thì trả về tên người quen, không khớp thì "Stranger".
        Trả về (list tên người quen thấy trong frame này, có báo động người
        lạ hay không - đã debounce qua _stranger_streak giống PPE, tránh
        báo nhầm vì 1 frame nhiễu/góc mặt xấu)."""
        faces = AIModelManager.instance().detect_faces(frame)
        store = KnownFacesStore.instance()

        known_faces: list[str] = []
        any_stranger = False
        face_boxes: list[tuple[int, int, int, int, str, bool]] = []

        for face in faces:
            if face.det_score < _FACE_DET_SCORE_THRESHOLD:
                continue
            name, _sim = store.match(face.normed_embedding)
            is_stranger = name == "Stranger"
            if is_stranger:
                any_stranger = True
            else:
                known_faces.append(name)
            x1, y1, x2, y2 = map(int, face.bbox)
            face_boxes.append((x1, y1, x2, y2, name, is_stranger))

        self._last_face_boxes = face_boxes
        self._stranger_streak = self._stranger_streak + 1 if any_stranger else 0
        stranger_alert = self._stranger_streak >= _STRANGER_STREAK_REQUIRED
        return known_faces, stranger_alert

    def _check_fall(self, frame, result) -> bool:
        """Fall detection port từ Fall_detection.py: với mỗi người có đủ 6
        keypoint tin cậy (vai/hông/mắt cá, COCO-17) - dùng RAW detection
        giống PPE, không qua track - crop quanh bbox (+30px) rồi chạy
        fall_detection.pt. Alert cuối cùng cần 2 tầng: phát hiện tức thời
        (frame này) VÀ majority-vote xác nhận từ 10 frame AI trước đó."""
        boxes = result.boxes
        keypoints = result.keypoints
        is_falling = False

        if boxes is not None and keypoints is not None and len(boxes) > 0:
            h, w = frame.shape[:2]
            for i in range(len(boxes)):
                kpt_conf = keypoints.conf[i].cpu().numpy()
                if any(kpt_conf[idx] < _FALL_POSE_CONF_THRESHOLD for idx in _FALL_REQUIRED_KEYPOINTS):
                    continue

                x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
                x1 = max(0, int(x1) - _FALL_CROP_PADDING)
                y1 = max(0, int(y1) - _FALL_CROP_PADDING)
                x2 = min(w, int(x2) + _FALL_CROP_PADDING)
                y2 = min(h, int(y2) + _FALL_CROP_PADDING)
                crop = frame[y1:y2, x1:x2]
                if crop.size == 0:
                    continue

                if AIModelManager.instance().check_fall(crop, imgsz=self._inference_imgsz) > _FALL_CONF_THRESHOLD:
                    is_falling = True

        fall_alert = is_falling and self._fall_confirmed
        self._fall_buffer.append(is_falling)
        self._fall_confirmed = sum(self._fall_buffer) >= (_FALL_BUFFER_LEN // 2)
        return fall_alert

    def _check_ppe(self, frame, boxes) -> bool:
        """PPE zone-check: đếm SỐ NGƯỜI có tâm bbox ĐẦU (detect_humans() dùng
        best_re_final.pt - chỉ detect vùng đầu) nằm trong ROI working-area,
        rồi chạy PPE ensemble (AIModelManager.check_ppe) trên TOÀN KHUNG HÌNH
        (không crop/ước lượng riêng từng người) lấy SỐ vest/helmet phát hiện
        được. Số vest HOẶC số helmet KHÁC số người trong vùng -> coi là vi
        phạm (thiếu đồ, kể cả khi có ít nhất 1 người đã mặc đủ) - chính xác
        hơn cách cũ chỉ kiểm tra "có ít nhất 1 vest/1 helmet trong khung hình
        hay không" (không phát hiện được N người nhưng chỉ 1 người có đủ đồ).
        boxes: kết quả detect_humans() (chỉ có bbox đầu).

        Lưu ý: vest/helmet được đếm trên TOÀN khung hình, không giới hạn
        trong ROI - nếu có người NGOÀI vùng cũng đang đội mũ/mặc vest trong
        cùng khung hình, số đếm có thể lệch so với số người TRONG vùng."""
        if not self._roi_polygons:
            self._ppe_violation_streak = 0
            return False

        if boxes is None or len(boxes) == 0:
            self._ppe_violation_streak = 0
            return False

        people_in_zone = 0
        for i in range(len(boxes)):
            x1, y1, x2, y2 = boxes.xyxy[i].cpu().numpy()
            head_center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            if any(cv2.pointPolygonTest(polygon, head_center, False) >= 0 for polygon in self._roi_polygons):
                people_in_zone += 1

        if people_in_zone == 0:
            self._ppe_violation_streak = 0
            return False

        vest_count, helmet_count = AIModelManager.instance().check_ppe(frame, imgsz=self._inference_imgsz)
        frame_has_violation = vest_count != people_in_zone or helmet_count != people_in_zone

        self._ppe_violation_streak = self._ppe_violation_streak + 1 if frame_has_violation else 0
        return self._ppe_violation_streak >= 3

    def _update_counting(self, outputs) -> None:
        """Đếm vào/ra: so 2 điểm tâm gần nhất của mỗi track với counting_line
        (thuật toán ccw/intersect - port từ Safety_Area.py của MIRAI)."""
        active_ids = set()
        for x1, y1, x2, y2, track_id, _cls in outputs:
            track_id = int(track_id)
            active_ids.add(track_id)
            center = (int((x1 + x2) / 2), int((y1 + y2) / 2))

            history = self._track_history.setdefault(track_id, [])
            history.append(center)

            if len(history) >= 2 and self._counting_line is not None:
                prev_pos, curr_pos = history[-2], history[-1]
                p1, p2 = self._counting_line
                if segments_intersect(prev_pos, curr_pos, p1, p2):
                    if ccw(curr_pos, p1, p2):
                        self._people_in += 1
                    else:
                        self._people_out += 1

            if len(history) > 10:
                history.pop(0)

        self._prune_track_history(active_ids)

    def _prune_track_history(self, active_ids: set[int]) -> None:
        for track_id in list(self._track_history):
            if track_id not in active_ids:
                del self._track_history[track_id]

    def _count_occupancy(self, outputs) -> int:
        """Số người hiện tại = số track đang active trong ROI (nếu có cấu
        hình ROI), hoặc tổng số track active nếu camera không có ROI nào.
        Cải tiến so với MIRAI (vốn debounce raw-detection-count): dùng track
        ID persistent nên không bị giật khi người che nhau thoáng qua.

        Test tâm bbox ĐẦU (detect_humans() dùng best_re_final.pt - chỉ detect
        vùng đầu) thay vì foot-point như bản cũ (dựa full-body bbox) - ROI
        cần được vẽ khớp vị trí đầu người đứng trong khu vực, không phải khu
        vực sàn."""
        if not self._roi_polygons:
            return len(outputs)

        count = 0
        for x1, y1, x2, y2, _track_id, _cls in outputs:
            head_center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            if any(
                cv2.pointPolygonTest(polygon, head_center, False) >= 0
                for polygon in self._roi_polygons
            ):
                count += 1
        return count

    def _draw_overlay(self, frame) -> None:
        """Vẽ overlay lên frame TRƯỚC khi emit - theo cấu hình tab Overlay
        (show_bbox/show_label/show_roi/show_tracking_id) + cảnh báo PPE/Fire/
        Fall gần nhất. Dùng self._last_tracks (không phải kết quả AI-tick vừa
        rồi) vì AI bị throttle theo ai_fps_limit trong khi frame emit ở mọi
        vòng lặp capture - giữa 2 lần AI chạy, vẫn vẽ theo vị trí track cũ."""
        if self._show_roi:
            # Xanh lá (BGR) - khớp màu viền ROI dùng trong ROI Editor
            # (roi_editor_dialog.py: _ROI_OUTLINE = QColor(0, 200, 120)).
            for polygon in self._roi_polygons:
                cv2.polylines(frame, [polygon], isClosed=True, color=(120, 200, 0), thickness=2)

        if self._counting_line is not None:
            cv2.line(frame, self._counting_line[0], self._counting_line[1], (255, 255, 255), 2)

        if self._show_bbox or self._show_label or self._show_tracking_id:
            for x1, y1, x2, y2, track_id, _cls in self._last_tracks:
                x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
                if self._show_bbox:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 0), 2)

                label_parts = []
                if self._show_label:
                    label_parts.append("Person")
                if self._show_tracking_id:
                    label_parts.append(f"ID {int(track_id)}")
                if label_parts:
                    cv2.putText(
                        frame, " ".join(label_parts), (x1, max(15, y1 - 8)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 200, 0), 1, cv2.LINE_AA,
                    )

        for x1, y1, x2, y2, name, is_stranger in self._last_face_boxes:
            color = (0, 100, 255) if is_stranger else (0, 200, 0)  # BGR: cam/đỏ = lạ, xanh lá = quen
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame, name, (x1, max(15, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
            )

        alerts = []
        if self._last_ppe_violation:
            alerts.append("PPE VIOLATION")
        if self._last_fire_alert:
            alerts.append("FIRE")
        if self._last_fall_alert:
            alerts.append("FALL")
        if self._last_stranger_alert:
            alerts.append("STRANGER")
        if alerts:
            cv2.putText(
                frame, " | ".join(alerts), (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA,
            )

    def _emit_ai_result(
        self,
        num_people: int,
        ppe_violation: bool = False,
        fire_alert: bool = False,
        fall_alert: bool = False,
        known_faces: list[str] | None = None,
        stranger_alert: bool = False,
    ) -> None:
        # Cache lại cho _draw_overlay() dùng - overlay vẽ trên MỌI frame emit
        # (kể cả frame không trùng nhịp AI chạy), nên cần giữ trạng thái cảnh
        # báo gần nhất thay vì tính lại.
        self._last_ppe_violation = ppe_violation
        self._last_fire_alert = fire_alert
        self._last_fall_alert = fall_alert
        self._last_stranger_alert = stranger_alert
        self.ai_result_ready.emit(
            self._device_id,
            {
                "num_people": num_people,
                "num_in": self._people_in,
                "num_out": self._people_out,
                "ppe_violation": ppe_violation,
                "fire_alert": fire_alert,
                "fall_alert": fall_alert,
                "known_faces": known_faces or [],
                "stranger_alert": stranger_alert,
            },
        )

    def _get_tracker(self) -> DeepSort:
        if self._tracker is None:
            cfg = get_config()
            cfg.merge_from_file(_DEEPSORT_YAML)
            cfg.DEEPSORT.REID_CKPT = _REID_CKPT
            self._tracker = DeepSort(
                cfg.DEEPSORT.REID_CKPT,
                max_dist=cfg.DEEPSORT.MAX_DIST,
                min_confidence=cfg.DEEPSORT.MIN_CONFIDENCE,
                nms_max_overlap=cfg.DEEPSORT.NMS_MAX_OVERLAP,
                max_iou_distance=cfg.DEEPSORT.MAX_IOU_DISTANCE,
                max_age=cfg.DEEPSORT.MAX_AGE,
                n_init=cfg.DEEPSORT.N_INIT,
                nn_budget=cfg.DEEPSORT.NN_BUDGET,
                use_cuda=torch.cuda.is_available(),
            )
        return self._tracker

    @staticmethod
    def _xyxy_to_xywh(bbox_xyxy) -> list[float]:
        x1, y1, x2, y2 = bbox_xyxy
        w = x2 - x1
        h = y2 - y1
        return [x1 + w / 2, y1 + h / 2, w, h]

    def _open_capture(self) -> cv2.VideoCapture | None:
        cap = cv2.VideoCapture(self._source)
        if not cap.isOpened():
            cap.release()
            return None
        # Yêu cầu resolution capture ĐÚNG (tab Basic) - chỉ có tác dụng khi
        # nguồn là USB (self._source đã normalize thành int ở __init__; IP/
        # RTSP luôn là str nên không rơi vào đây). Nhiều webcam UVC im lặng
        # bỏ qua nếu không hỗ trợ mode này - _apply_preview_downscale() vẫn
        # là lưới an toàn phía sau nếu capture thực tế vẫn ra resolution cao.
        if isinstance(self._source, int) and self._capture_resolution is not None:
            width, height = self._capture_resolution
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        return cap

    def _reconnect(self) -> cv2.VideoCapture | None:
        """Mất kết nối giữa chừng (rớt mạng, camera reboot...) -> thử mở lại
        định kỳ theo device.advanced.reconnect_timeout, tới khi thành công
        hoặc bị stop()."""
        while self._running:
            self.msleep(self._reconnect_timeout_ms)
            if not self._running:
                return None
            cap = self._open_capture()
            if cap is not None:
                return cap
        return None

    def _should_emit_frame(self) -> bool:
        """Giới hạn tốc độ EMIT hình cho viewer theo FPS đã cấu hình (tab
        Basic) - cùng cơ chế throttle với AI FPS Limit (_run_ai) nhưng áp
        dụng cho nhánh hiển thị: vòng đọc frame (cap.read()) phía trên vẫn
        chạy đủ nhanh để không bị trễ buffer/mất frame, chỉ bỏ bớt việc
        convert/emit những frame đến sớm hơn mức cần thiết - giảm CPU cho
        cvtColor/QImage copy/gửi qua Qt signal khi camera nguồn có fps cao
        hơn nhiều so với nhu cầu xem thực tế."""
        now = time.monotonic()
        if now - self._last_emit_ts < 1.0 / self._display_fps_limit:
            return False
        self._last_emit_ts = now
        return True

    def _apply_preview_downscale(self, frame):
        """Giảm kích thước frame TRƯỚC KHI chuyển QImage/gửi hiển thị, theo
        giới hạn Resolution đã chọn (tab Basic) - đây là bước tốn kém nhất
        khi camera nguồn có độ phân giải rất cao (4K...): BGR->RGB convert,
        copy buffer QImage, gửi qua Qt signal, rồi scale lại để vừa khung
        hiển thị (luôn nhỏ hơn nhiều so với 4K) đều tỉ lệ thuận với số pixel.
        Không đụng gì tới frame AI dùng để detect (hàm này chỉ gọi trên
        nhánh hiển thị, sau khi _run_ai/_draw_overlay đã xong).

        Chỉ resize khi frame THỰC SỰ rộng hơn giới hạn - chọn "4K" (hoặc
        preview_max_width <= 0/không parse được) nghĩa là không giới hạn.

        Bỏ qua HOÀN TOÀN nếu đang có viewer cần full-res (vd ROIEditorDialog
        đang mở, xem add_viewer/remove_viewer) - toạ độ ROI/Counting Line
        được click theo hệ toạ độ frame NỀN hiển thị trong editor; nếu nền đó
        bị downscale thì toạ độ lưu lại sẽ lệch tỉ lệ so với frame full-res
        thật mà AI/occupancy/PPE dùng để test - đúng bug "ROI hiện sai vị trí,
        tỉ lệ nhỏ hơn" đã gặp. An toàn hơn tạm ngưng tối ưu display trong lúc
        đang sửa ROI (thường ngắn) còn hơn để sai toạ độ vĩnh viễn."""
        if self._full_res_viewer_count > 0:
            return frame
        if self._preview_max_width <= 0:
            return frame
        h, w = frame.shape[:2]
        if w <= self._preview_max_width:
            return frame
        scale = self._preview_max_width / w
        new_size = (self._preview_max_width, max(1, int(round(h * scale))))
        return cv2.resize(frame, new_size, interpolation=cv2.INTER_AREA)

    @staticmethod
    def _to_qimage(frame) -> QImage | None:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        # .copy() để QImage có buffer riêng, tránh tham chiếu treo vào bộ nhớ
        # của frame (sẽ bị ghi đè/giải phóng ở vòng lặp đọc frame kế tiếp).
        return image.copy()
