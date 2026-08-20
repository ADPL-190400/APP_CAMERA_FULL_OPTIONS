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
from dataclasses import dataclass

import cv2
import numpy as np
import torch
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage

from core.ai_model_manager import AIModelManager
from core.ai_settings import AISettings
from core.blacklist_store import BlacklistEntry, BlacklistStore
from core.deep_sort_pytorch.deep_sort import DeepSort
from core.deep_sort_pytorch.utils.parser import get_config
from core.event_dedup import PresenceDedup
from core.event_store import EventStore
from core.face_crop import crop_face_with_padding
from core.face_pose import estimate_face_frontal_ratio
from core.known_faces_store import KnownFacesStore
from core.line_crossing import ccw, segments_intersect
from core.models.camera_device import (
    parse_inference_imgsz,
    parse_points,
    parse_preview_max_width,
    parse_resolution_wh,
)
from core.models.event_record import EVENT_KIND_LABELS, EVENT_KIND_INCIDENT_TYPE_ID, EventKind
from core.path_manager import BASE_DIR
from ui.ui_menu.i18n import tr
from scr import Web_API

_DEEPSORT_YAML = os.path.join(BASE_DIR, "core", "deep_sort_pytorch", "configs", "deep_sort.yaml")
_REID_CKPT = os.path.join(
    BASE_DIR, "core", "deep_sort_pytorch", "deep_sort", "deep", "checkpoint", "ckpt.t7"
)

# Fall detection - port nguyên tham số từ Fall_detection.py của MIRAI.
# _FALL_BUFFER_LEN (cửa sổ làm mượt) và ngưỡng confidence của model
# fall_detection_new.pt giờ đọc động từ AISettings (chỉnh được qua UI - xem
# ui/dialogs/ai_settings_dialog.py) thay vì hằng số cố định ở đây.
_FALL_POSE_CONF_THRESHOLD = 0.3   # keypoint có conf thấp hơn -> bỏ qua người này (pose không đủ tin cậy)
_FALL_REQUIRED_KEYPOINTS = (5, 6, 11, 12, 15, 16)  # vai, hông, mắt cá (COCO-17) - phải thấy đủ mới xét ngã
_FALL_CROP_PADDING = 30

# Face recognition - port từ Face_detection.py của MIRAI.
_FACE_DET_SCORE_THRESHOLD = 0.5   # ngưỡng chất lượng detection, giống mọi model YOLO khác ở đây
_FACE_MAX_PER_FRAME = 10           # đám đông > 10 mặt/frame -> chỉ nhận diện 10 mặt gần/to nhất, tránh cả frame bị kéo chậm vì nhận diện hết

# Khoảng cách tâm mặt vừa detect<->tâm track tối đa để gán danh tính, tính
# theo % chiều rộng frame - PORT từ pages/gate_kiosk_page.py cùng giá trị
# (track ở đây LÀ bbox mặt, DeepSort track thẳng trên detect_faces, không
# qua body/đầu trung gian) nên 2 tâm gần như trùng nhau khi cùng 1 người;
# giữ ngưỡng nhỏ để không lẫn giữa 2 mặt đứng gần nhau trong khung đông người.
_IDENTITY_MATCH_MAX_DIST_RATIO = 0.08

# 4 trạng thái hiển thị/xử lý cho mỗi khuôn mặt phát hiện được - xem
# CameraPipeline._check_faces (docstring đầy đủ ở đó).
_FACE_STATUS_KNOWN = "known"
_FACE_STATUS_STRANGER = "stranger"
_FACE_STATUS_UNKNOWN = "unknown"
# Khớp BlacklistStore (core/blacklist_store.py) - ƯU TIÊN CAO NHẤT, đè lên cả
# 3 trạng thái kia (1 track dù trước đó là known/stranger/unknown, hễ khớp
# blacklist là chuyển thẳng sang trạng thái này, xem _bind_face_identities).
_FACE_STATUS_BLACKLIST = "blacklist"
_FACE_STATUS_COLORS = {  # BGR - xem _draw_overlay
    _FACE_STATUS_KNOWN: (0, 200, 0),      # xanh lá
    _FACE_STATUS_STRANGER: (0, 100, 255),  # cam/đỏ
    _FACE_STATUS_UNKNOWN: (0, 220, 255),   # vàng - chưa đủ căn cứ kết luận
    _FACE_STATUS_BLACKLIST: (0, 0, 255),   # đỏ THUẦN - cố ý khác hẳn cam/đỏ của Stranger để không lẫn lộn 2 mức độ nghiêm trọng
}

# 2 chế độ chống spam thông báo Người lạ (AIConfig.stranger_repeat_mode,
# chọn riêng từng camera qua Camera Config) - xem _capture_face_events.
# Giá trị PHẢI khớp đúng chuỗi canonical ở pages/camera_config_page.py
# (_TR_COMBO_ITEMS["combo_stranger_repeat_mode"]).
_STRANGER_REPEAT_ONCE = "Notify once per visit"
_STRANGER_REPEAT_GRACE_PERIOD = "Repeat after grace period"

# "Bộ nhớ tạm" khuôn mặt (self._face_memory) - CẦU NỐI qua những lúc track
# DeepSort chết (người quay đầu/cúi xuống đủ lâu để mất dấu, xem
# _get_face_tracker - MAX_AGE chỉ chịu được vài giây) rồi được cấp track_id
# MỚI khi xuất hiện lại. Không có bộ nhớ này thì mọi trạng thái theo track
# (_face_track_identity/_seen_well/_best_sim/_notified) mất trắng, khiến:
#   - Người LẠ: bị xác nhận + THÔNG BÁO LẶP LẠI dù là đúng 1 người (mỗi lần
#     quay đầu xong nhìn lại đủ lâu để track chết là 1 "người lạ mới").
#   - Người QUEN: phải "chứng minh lại" từ đầu (hiện "Unknown" 1 lúc dù đã
#     từng nhận diện được) mỗi khi track đổi, dù KnownFacesStore vẫn nhận ra
#     đúng tên ngay khi có 1 frame đủ tốt - bộ nhớ này chỉ giúp bắt kịp NGAY
#     lúc track vừa đổi, không cần chờ thêm 1 frame chất lượng tốt mới.
# Khớp theo COSINE SIMILARITY giữa embedding hiện tại và embedding đã lưu
# (KHÔNG phải track_id) - hoạt động được kể cả khi DeepSort đổi hẳn track_id,
# miễn khuôn mặt vẫn là CÙNG 1 người.
_FACE_MEMORY_TTL_SEC = 60.0        # quên hẳn sau 60s không thấy lại - đủ dài để bắt kịp lúc quay đầu/cúi xuống, đủ ngắn để không tồn đọng vô hạn
_FACE_MEMORY_MAX_ENTRIES = 50      # trần số người "đang nhớ" cùng lúc - tránh phình to vô hạn nếu camera thấy rất nhiều mặt khác nhau qua ngày dài


@dataclass
class _RememberedFace:
    """1 entry trong self._face_memory - xem hằng số _FACE_MEMORY_* phía
    trên. best_sim CHỈ có ý nghĩa khi name is None (ứng viên/đã xác nhận
    Stranger). notified (đã ghi Event Log/thông báo hay chưa, chế độ "once"
    - xem _should_notify_face) có ý nghĩa cho CẢ 3 - người quen, người lạ,
    VÀ Blacklist. blacklist_entry_id khác None nghĩa là track đã từng khớp
    Blacklist - ƯU TIÊN CAO NHẤT khi khôi phục (xem _recall_face_memory:
    khớp Blacklist thì bỏ qua name, không coi track mới khôi phục là known/
    stranger nữa)."""
    embedding: np.ndarray
    last_seen: float
    name: str | None
    best_sim: float = 0.0
    notified: bool = False
    blacklist_entry_id: str | None = None

# Event Log: cùng ngưỡng "đợt vi phạm mới" với Event Feed/System Alarms
# (dashboard_page.py/liveview_page.py) - tránh lưu ảnh spam liên tục trong
# lúc 1 điều kiện vẫn còn đúng.
_EVENT_LOG_GRACE_SEC = 5.0

# Crowd heatmap (AIConfig.crowd_heatmap_threshold) - lưới nhiệt tích luỹ có
# suy giảm theo thời gian, đo MẬT ĐỘ CỤC BỘ thay vì chỉ đếm tổng số người
# (_count_occupancy) - xem docstring đầy đủ ở _update_crowd_heatmap. Kích
# thước lưới CỐ ĐỊNH bất kể resolution camera (mỗi ô tự co giãn theo kích
# thước frame thật ở _update_crowd_heatmap) - đủ thô để rẻ, đủ mịn để phân
# biệt được các góc khác nhau trong 1 ROI.
_HEATMAP_GRID_ROWS = 12
_HEATMAP_GRID_COLS = 16
# Nhiệt 1 ô giảm còn 1 nửa sau mỗi khoảng này (giây) nếu không có thêm ai
# đứng ở đó - KHÔNG tính theo số lượt AI (ai_fps_limit đổi được từng
# camera) để tốc độ "nguội" luôn nhất quán theo thời gian thật.
_HEATMAP_HALF_LIFE_SEC = 3.0
# Chặn trần 1 ô - tránh tích luỹ vô hạn ở chỗ luôn đông liên tục hàng giờ,
# giữ thang đo threshold có ý nghĩa ổn định để người dùng dễ chỉnh.
_HEATMAP_CELL_MAX = 20.0
# Ô nóng nhất dưới mức này (so với crowd_heatmap_threshold, tỉ lệ 0..1) coi
# như "chưa có gì đáng vẽ" -> bỏ qua HẲN bước vẽ overlay (_blend_heatmap) -
# đa số thời gian thực tế không ai tụ tập nên nhánh này chạy hầu hết các
# lượt, tránh phí công vẽ 1 lớp phủ gần như trong suốt hoàn toàn không ai
# nhìn thấy khác biệt. Xem _draw_overlay.
_HEATMAP_DRAW_EPSILON = 0.05
# Kernel 3x3 "vẩy" nhiệt quanh ô trung tâm mỗi khi có 1 người đứng đó - làm
# mượt lưới (đỡ trông "vuông vức"/giật khi người đứng lệch ranh giới 2 ô),
# tổng các trọng số = 1.0 nên mỗi người luôn đóng góp ĐÚNG "1 đơn vị nhiệt"/
# lượt bất kể vị trí trong ô.
_HEATMAP_KERNEL = np.array(
    [
        [0.05, 0.10, 0.05],
        [0.10, 0.40, 0.10],
        [0.05, 0.10, 0.05],
    ],
    dtype=np.float32,
)

# Bước chờ giữa các lần thử reconnect (xem _reconnect) - đủ nhỏ để stop()
# luôn có hiệu lực trong vòng thời gian DeviceManager.stop_device() chờ
# (wait(2000)), đủ lớn để không busy-loop tốn CPU.
_RECONNECT_POLL_MS = 200


class CameraPipeline(QThread):
    frame_ready = pyqtSignal(str, QImage)   # device_id, frame (chỉ emit khi có viewer)
    error_occurred = pyqtSignal(str, str)   # device_id, message
    ai_result_ready = pyqtSignal(str, dict)  # device_id, {"num_people","num_in","num_out","ppe_violation","fire_alert","fall_alert","occupancy_alert","crowd_alert","stranger_alert","stranger_track_ids","blacklist_alert","blacklist_track_ids","known_faces"}

    def __init__(
        self,
        device_id: str,
        source: str | int,
        device_name: str = "",
        web_camera_id: str = "",
        ai_enabled: bool = False,
        reconnect_timeout: int = 10,
        ai_fps_limit: int = 10,
        counting_line: str = "",
        roi_polygons: list[str] | None = None,
        enable_counting: bool = False,
        enable_occupancy: bool = False,
        occupancy_threshold: int = 0,
        crowd_heatmap_threshold: float = 0.0,
        enable_ppe: bool = False,
        enable_fire: bool = False,
        enable_fall: bool = False,
        enable_face_recognition: bool = False,
        stranger_repeat_mode: str = _STRANGER_REPEAT_ONCE,
        show_bbox: bool = True,
        show_label: bool = True,
        show_roi: bool = False,
        show_tracking_id: bool = False,
        preview_max_width: int = 0,
        capture_resolution: tuple[int, int] | None = None,
        display_fps_limit: int = 30,
        inference_quality: str = "Balanced (480px)",
        parent=None,
    ):
        super().__init__(parent)
        self._device_id = device_id
        self._device_name = device_name or device_id
        # camera_id THẬT của server (Web_API.send_mobile_incident) - đã tra
        # + lưu sẵn vào CameraDevice.web_camera_id lúc Save/Apply ở
        # camera_config_page.py (xem CameraDevice.web_camera_id), đọc 1 LẦN
        # lúc khởi tạo ở đây, KHÔNG đưa vào update_ai_settings() như các cờ
        # AI khác (giống capture_resolution) - đổi MAC/Save lại lúc camera
        # đang chạy cần Stop/Start lại mới áp dụng. Rỗng = camera này chưa
        # khớp với bên web, _capture_events() sẽ bỏ qua bước gửi (không lỗi).
        self._web_camera_id = web_camera_id
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
        self._last_fall_bbox: tuple[int, int, int, int] | None = None
        self._last_stranger_alert = False
        self._last_blacklist_alert = False
        # x1,y1,x2,y2,label,status (_FACE_STATUS_*),track_id,in_roi
        self._last_face_boxes: list[tuple[int, int, int, int, str, str, int, bool]] = []

        # Lưới nhiệt đám đông cục bộ (xem hằng số _HEATMAP_*/_update_crowd_heatmap)
        # - khởi tạo lazy (None) vì cần biết kích thước frame thật (chỉ có từ
        # _run_ai trở đi) để chia ô cho khớp. _heatmap_last_ts dùng tính dt
        # thực tế giữa 2 lượt cập nhật (ai_fps_limit đổi được, không cố định)
        # cho tốc độ suy giảm luôn đúng theo thời gian thật.
        self._heatmap_grid: np.ndarray | None = None
        self._heatmap_last_ts: float = 0.0

        # Face recognition: tracker DeepSort RIÊNG cho khuôn mặt (KHÁC
        # self._tracker ở trên - đó là tracker cho bbox ĐẦU/THÂN dùng cho
        # đếm vào/ra/occupancy/PPE, không liên quan) - PORT nguyên cơ chế từ
        # pages/gate_kiosk_page.py (_bind_identities/_track_seen_well/
        # _track_best_sim) để giải quyết đúng gốc vấn đề: không tracking qua
        # nhiều frame thì 1 người lạ/quen di chuyển/quay đầu bị đánh giá lại
        # từ đầu MỖI FRAME, dễ vừa báo nhầm "Stranger" (1 frame góc xấu)
        # VỪA spam lặp lại nhiều lần cho ĐÚNG 1 người (streak reset liên tục
        # + không có khái niệm "đây vẫn là người tôi đã thấy lúc trước").
        self._face_tracker: DeepSort | None = None
        # track_id -> tên người quen đã khớp (sticky - 1 khi đã khớp thì GIỮ
        # NGUYÊN cho tới khi track biến mất, không hạ cấp chỉ vì 1 lượt match
        # trượt do góc mặt xấu tạm thời) - None nghĩa là CHƯA từng khớp ai
        # (ứng viên Stranger/Unknown, xem _check_faces).
        self._face_track_identity: dict[int, str | None] = {}
        # Track đã từng có ÍT NHẤT 1 lượt vừa đủ rõ (stranger_confirm_min_score)
        # VỪA đủ thẳng (stranger_min_frontal_ratio, core/face_pose.py) - track
        # CHƯA có mặt trong set này thì chưa đủ điều kiện xác nhận Stranger.
        self._face_track_seen_well: set[int] = set()
        # Similarity CAO NHẤT từng đo được cho track (chỉ cập nhật khi CHƯA
        # khớp ra ai, xem _bind_face_identities) - "vùng xám": similarity
        # từng cao hơn stranger_ambiguous_max_sim ở BẤT KỲ lượt nào thì track
        # đó không bao giờ được xác nhận Stranger nữa (có nét giống 1 người
        # quen, dù chưa đủ khớp).
        self._face_track_best_sim: dict[int, float] = {}
        # Track (Stranger) đã từng được thông báo/ghi Event Log RỒI - chỉ
        # thông báo ĐÚNG 1 LẦN cho mỗi track, cho tới khi track đó thực sự
        # biến mất (bị prune - xem _prune_face_tracks), KHÔNG dùng grace
        # period theo giây như PPE/Fire/Fall (_event_dedup) - người lạ quay
        # đầu qua lại/che khuất thoáng qua trong lúc track vẫn còn sống
        # (DeepSort tự chịu được vài giây mất dấu) sẽ KHÔNG bị báo lại, dù
        # khoảng "im lặng" giữa 2 lần thấy rõ có dài hơn vài giây.
        self._face_track_notified: set[int] = set()
        # track_id -> BlacklistEntry đã khớp (sticky - giống _face_track_identity,
        # ƯU TIÊN CAO NHẤT: 1 khi track đã khớp Blacklist thì GIỮ NGUYÊN dù
        # lượt sau match trượt do góc xấu, KHÔNG bị hạ cấp xuống known/
        # stranger/unknown - xem _bind_face_identities/_check_faces). None/
        # vắng mặt trong dict = chưa từng khớp Blacklist.
        self._face_track_blacklist_entry: dict[int, BlacklistEntry] = {}
        # "Bộ nhớ tạm" bắc cầu qua lúc track chết (xem hằng số _FACE_MEMORY_*
        # và _recall_face_memory/_remember_face) - danh sách phẳng (không
        # cần key track_id, tự tra bằng cosine similarity embedding).
        self._face_memory: list[_RememberedFace] = []
        # track_id -> embedding gần nhất (cập nhật ở _bind_face_identities) -
        # CẦU NỐI để _capture_face_events cập nhật LẠI bộ nhớ tạm ĐÚNG lúc
        # 1 track vừa được đánh dấu "đã thông báo" (_face_track_notified),
        # vì lúc _bind_face_identities gọi _remember_face (bên trong
        # _check_faces) thì _capture_face_events CHƯA chạy tới - ghi lúc đó
        # sẽ chụp sai "chưa thông báo" cho bộ nhớ dù thực ra sắp thông báo
        # ngay trong cùng lượt AI này.
        self._face_track_last_embedding: dict[int, np.ndarray] = {}

        # Toàn bộ cờ enable/ROI/Line/Overlay được gom vào update_ai_settings()
        # - dùng chung cho cả lúc khởi tạo LẪN khi DeviceManager đẩy cấu hình
        # mới vào giữa lúc đang chạy (Save/Apply ở camera_config_page hoặc ROI
        # Editor) - không cần Stop/Start lại mới thấy hiệu lực.
        self.update_ai_settings(
            ai_enabled=ai_enabled,
            enable_counting=enable_counting,
            enable_occupancy=enable_occupancy,
            occupancy_threshold=occupancy_threshold,
            crowd_heatmap_threshold=crowd_heatmap_threshold,
            enable_ppe=enable_ppe,
            enable_fire=enable_fire,
            enable_fall=enable_fall,
            enable_face_recognition=enable_face_recognition,
            stranger_repeat_mode=stranger_repeat_mode,
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
        occupancy_threshold: int,
        crowd_heatmap_threshold: float,
        enable_ppe: bool,
        enable_fire: bool,
        enable_fall: bool,
        enable_face_recognition: bool,
        stranger_repeat_mode: str,
        counting_line: str,
        roi_polygons: list[str] | None,
        show_bbox: bool,
        show_label: bool,
        show_roi: bool,
        show_tracking_id: bool,
        preview_max_width: int = 0,
        display_fps_limit: int = 30,
        inference_quality: str = "Balanced (480px)",
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
        # 0 = tắt cảnh báo (xem AIConfig.occupancy_threshold/_run_ai).
        self._occupancy_threshold = occupancy_threshold
        # 0 = tắt cảnh báo/overlay đám đông cục bộ (xem
        # AIConfig.crowd_heatmap_threshold/_update_crowd_heatmap).
        self._crowd_heatmap_threshold = crowd_heatmap_threshold
        self._enable_ppe = enable_ppe
        self._enable_fire = enable_fire
        self._enable_fall = enable_fall
        self._enable_face_recognition = enable_face_recognition
        # "once"/"grace_period" - xem AIConfig.stranger_repeat_mode/
        # _capture_face_events. Không rơi vào giá trị lạ (vd config cũ
        # trước khi field này tồn tại) -> coi như "once" (mặc định, chặt
        # nhất) thay vì crash hay im lặng theo hành vi grace_period.
        self._stranger_repeat_mode = (
            stranger_repeat_mode if stranger_repeat_mode == _STRANGER_REPEAT_GRACE_PERIOD else _STRANGER_REPEAT_ONCE
        )

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
        self._fall_buffer: deque[bool] = deque(maxlen=AISettings.instance().fall_confirm_window)
        self._fall_confirmed = False

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
            self.error_occurred.emit(self._device_id, tr("Could not open video source: {source}").format(source=self._source))
            return

        try:
            while self._running:
                # cap.read() TỰ THÂN cũng có thể raise (không chỉ trả về
                # ok=False) với 1 số stream RTSP hỏng giữa chừng - bọc riêng,
                # coi như mất kết nối, đi qua ĐÚNG luồng reconnect có sẵn bên
                # dưới thay vì để lỗi thoát thẳng ra ngoài.
                try:
                    ok, frame = cap.read()
                except Exception as exc:  # noqa: BLE001 - lỗi decode/kết nối từ chính OpenCV, không phải bug logic ở đây
                    print(f"[CameraPipeline {self._device_id}] cap.read() lỗi, coi như mất kết nối: {exc}")
                    ok, frame = False, None

                if not ok:
                    cap.release()
                    cap = self._reconnect()
                    if cap is None:
                        return
                    continue

                self._last_frame_ts = time.monotonic()

                # QUAN TRỌNG: bọc riêng phần xử lý (AI + hiển thị) - đây là
                # nơi tổng hợp TOÀN BỘ code chạy mỗi frame (detect mặt/người/
                # lửa/té ngã, DeepSort, blacklist, heatmap, vẽ overlay, convert
                # QImage...), rủi ro cao nhất gặp lỗi bất ngờ (frame hỏng/thiếu
                # channel do glitch đường truyền, model lỗi thoáng qua, GPU
                # hiccup...). TRƯỚC bản sửa này, 1 lỗi bất kỳ ở đây sẽ THOÁT
                # KHỎI run() luôn - QThread chết LẶNG LẼ (không exception nào
                # nổi lên UI, không phải process crash vì Python thread lỗi
                # không tự sập cả tiến trình) - camera "đứng hình" vĩnh viễn
                # dù kết nối mạng/camera vẫn ổn, và DeviceManager.is_pipeline_running()
                # (chỉ kiểm tra có trong dict, KHÔNG kiểm tra thread còn sống)
                # vẫn báo "đang chạy" sai. Giờ: log lại rồi BỎ QUA đúng 1
                # frame lỗi, giữ nguyên kết nối cap hiện tại, đọc tiếp frame
                # kế - không cần reconnect (bản thân kết nối không có vấn đề).
                try:
                    if self._ai_enabled:
                        self._run_ai(frame)

                    if self._viewer_count > 0 and self._should_emit_frame():
                        if self._ai_enabled:
                            self._draw_overlay(frame)
                        frame = self._apply_preview_downscale(frame)
                        image = self._to_qimage(frame)
                        if image is not None:
                            self.frame_ready.emit(self._device_id, image)
                except Exception as exc:  # noqa: BLE001 - xem ghi chú ở trên, cố tình bắt rộng để 1 frame lỗi không giết cả pipeline
                    print(f"[CameraPipeline {self._device_id}] Lỗi xử lý 1 frame (đã bỏ qua, tiếp tục chạy): {exc}")
        finally:
            # cap có thể là None ở đây (bug đã gặp thật, không liên quan bản
            # sửa ở trên): _reconnect() trả None khi bị stop() ngay lúc đang
            # chờ kết nối lại (mất mạng/camera reboot rồi user bấm Stop) ->
            # "cap = self._reconnect(); if cap is None: return" khiến return
            # thoát qua ĐÚNG finally này với cap=None - gọi .release() thẳng
            # sẽ AttributeError, làm thread chết vì lỗi thay vì thoát sạch
            # theo đúng ý stop().
            if cap is not None:
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

        fire_alert, fire_boxes = self._check_fire(frame) if self._enable_fire else (False, [])
        known_faces, stranger_alert = (
            self._check_faces(frame) if self._enable_face_recognition else ([], False)
        )
        # track_id của MỖI người lạ "đã xác nhận" riêng biệt trong lượt này,
        # CHỈ trong vùng ROI nếu camera có cấu hình (box[7], xem _check_faces
        # - self._last_face_boxes đã có sẵn từ _check_faces) - cho phép
        # SYSTEM ALARMS/Event Feed (liveview_page.py/dashboard_page.py) phân
        # biệt 2 người lạ khác nhau xuất hiện gần nhau về thời gian, không
        # dồn chung thành 1 dòng log như khi chỉ có 1 boolean stranger_alert.
        stranger_track_ids = [
            box[6] for box in self._last_face_boxes if box[5] == _FACE_STATUS_STRANGER and box[7]
        ]
        # Y hệt stranger_track_ids ở trên, cho trạng thái Blacklist (mức độ
        # nghiêm trọng cao hơn, xem EventKind.BLACKLIST_ALERT) - phân biệt
        # nhiều người trong blacklist xuất hiện gần nhau về thời gian.
        blacklist_track_ids = [
            box[6] for box in self._last_face_boxes if box[5] == _FACE_STATUS_BLACKLIST and box[7]
        ]
        blacklist_alert = bool(blacklist_track_ids)

        # Đếm vào/ra, Occupancy, PPE chỉ cần BBOX (không cần keypoints) nên
        # dùng human.pt (detector thuần, ~7ms/frame - nhẹ hơn nhiều so với
        # yolov8x-pose 17-41ms/frame). Fall là tính năng DUY NHẤT thực sự
        # cần keypoints nên vẫn gọi riêng pose model (detect_bodies) - xem
        # AIModelManager.detect_humans/detect_bodies.
        need_person = self._enable_counting or self._enable_occupancy or self._enable_ppe
        need_pose = self._enable_fall

        num_people = 0
        ppe_violation = False
        ppe_boxes: list[tuple[int, int, int, int]] = []
        occupancy_boxes: list[tuple[int, int, int, int]] = []
        if need_person:
            person_result = AIModelManager.instance().detect_humans(frame, imgsz=self._inference_imgsz)
            boxes = person_result.boxes
            need_tracking = self._enable_counting or self._enable_occupancy

            if boxes is None or len(boxes) == 0:
                if need_tracking:
                    self._last_tracks = []
                    self._prune_track_history(active_ids=set())
                    # Vẫn phải cập nhật (decay) lưới nhiệt dù KHÔNG có ai -
                    # nhiệt cần "nguội" đúng theo thời gian thật kể cả lúc
                    # khung hình trống, không chỉ lúc có người.
                    if self._enable_occupancy and self._crowd_heatmap_threshold > 0:
                        self._update_crowd_heatmap([], frame.shape)
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
                        # Bbox TỪNG người đang track - dùng để vẽ lên ảnh
                        # bằng chứng Occupancy (không lọc riêng theo ROI như
                        # num_people - ROI đã có viền riêng, vẽ hết cho dễ
                        # đối chiếu ai đang có mặt lúc vượt ngưỡng).
                        occupancy_boxes = [(int(x1), int(y1), int(x2), int(y2)) for x1, y1, x2, y2, _tid, _c in outputs]
                        if self._crowd_heatmap_threshold > 0:
                            self._update_crowd_heatmap(outputs, frame.shape)
                if self._enable_ppe:
                    ppe_violation = self._check_ppe(frame, boxes)
                    ppe_boxes = [tuple(int(v) for v in xyxy) for xyxy in boxes.xyxy.cpu().numpy()]

        fall_alert = False
        fall_bbox = None
        if need_pose:
            pose_result = AIModelManager.instance().detect_bodies(frame, imgsz=self._inference_imgsz)
            fall_alert, fall_bbox = self._check_fall(frame, pose_result)

        # Ngưỡng số người (tab AI, chỉ có ý nghĩa khi Occupancy đang bật -
        # num_people ở trên = 0 nếu enable_occupancy tắt, nên occupancy_alert
        # tự động luôn False trong trường hợp đó). 0 = không giới hạn/tắt.
        occupancy_alert = (
            self._enable_occupancy and self._occupancy_threshold > 0 and num_people > self._occupancy_threshold
        )
        # Đám đông CỤC BỘ (heatmap) - KHÁC occupancy_alert (đếm tổng): dựa
        # trên Ô NÓNG NHẤT hiện tại của lưới, xem _update_crowd_heatmap.
        # self._heatmap_grid vẫn None nếu enable_occupancy chưa từng bật (lazy
        # init) - kiểm tra None trước để không lỗi.
        crowd_alert = (
            self._crowd_heatmap_threshold > 0
            and self._heatmap_grid is not None
            and float(self._heatmap_grid.max()) >= self._crowd_heatmap_threshold
        )

        self._capture_events(
            frame, ppe_violation, fire_alert, fall_alert, stranger_alert, occupancy_alert, crowd_alert,
            ppe_boxes=ppe_boxes, fire_boxes=fire_boxes, fall_bbox=fall_bbox, occupancy_boxes=occupancy_boxes,
        )

        self._emit_ai_result(
            num_people=num_people,
            ppe_violation=ppe_violation,
            fire_alert=fire_alert,
            fall_alert=fall_alert,
            fall_bbox=fall_bbox,
            occupancy_alert=occupancy_alert,
            crowd_alert=crowd_alert,
            known_faces=known_faces,
            stranger_alert=stranger_alert,
            stranger_track_ids=stranger_track_ids,
            blacklist_alert=blacklist_alert,
            blacklist_track_ids=blacklist_track_ids,
        )

    def _capture_events(
        self, frame, ppe_violation, fire_alert, fall_alert, stranger_alert, occupancy_alert, crowd_alert,
        ppe_boxes=(), fire_boxes=(), fall_bbox=None, occupancy_boxes=(),
    ) -> None:
        """Lưu ảnh bằng chứng (EventStore) cho mỗi ĐỢT cảnh báo MỚI - dedup
        qua PresenceDedup (cùng ngưỡng grace với Event Feed/System Alarms),
        không lưu lặp lại khi 1 điều kiện còn tiếp diễn liên tục. Chạy ngay
        trong thread của pipeline này (đã có sẵn frame full-res), không phụ
        thuộc có viewer đang xem preview hay không.

        Đây cũng chính là cơ chế chống spam thông báo cho occupancy_alert -
        vượt ngưỡng người rồi cứ đứng yên trên ngưỡng đó KHÔNG báo lại liên
        tục, chỉ báo lại khi tụt xuống dưới ngưỡng lâu hơn _EVENT_LOG_GRACE_SEC
        rồi vượt lại lần nữa (giống hệt cách PPE/Fire/Fall/Stranger đã hoạt
        động từ trước - không cần cơ chế cooldown riêng).

        Cùng 1 đợt "MỚI" này cũng là điểm gửi incident lên web server (nếu
        camera có mac_address) - tái dùng ĐÚNG dedup gate này thay vì viết
        thêm debounce riêng (khác MIRAI - mỗi feature tự có 1 kiểu debounce
        rời rạc: delay==3, interval theo giây...).

        ppe_boxes/fire_boxes/fall_bbox/occupancy_boxes - vẽ khung phát hiện
        LÊN ẢNH BẰNG CHỨNG (không chỉ vẽ ROI như trước) - bug đã gặp thật:
        xem lại Event Log ảnh cháy/té ngã chỉ thấy cả khung hình, không rõ
        VỊ TRÍ nào được phát hiện, phải đoán. fall_bbox chỉ 1 (đúng người
        vừa ngã), 3 cái còn lại là LIST (có thể nhiều vùng lửa/nhiều người
        cùng lúc) - xem _build_evidence_frame.

        Stranger/Face-recognized/Blacklist KHÔNG nằm trong "checks" ở đây
        (ảnh bằng chứng của 3 loại đó là CROP KHUÔN MẶT, không phải full-frame
        + ROI như PPE/Fire/Fall/Occupancy) - xem _capture_face_events."""
        # (is_active, kind, boxes cần vẽ, màu BGR, nhãn text) - màu khớp
        # đúng màu đã dùng cho từng loại ở _draw_overlay (Fall đỏ giống khung
        # fall preview, PPE/Occupancy xanh lá giống bbox người thường, Fire
        # cam/đỏ riêng vì chưa từng có màu preview cho fire trước đây).
        checks = (
            (ppe_violation, EventKind.PPE_VIOLATION, ppe_boxes, (0, 200, 0), "PPE"),
            (fire_alert, EventKind.FIRE_ALERT, fire_boxes, (0, 100, 255), "FIRE"),
            (fall_alert, EventKind.FALL_ALERT, [fall_bbox] if fall_bbox is not None else [], (0, 0, 255), "FALL"),
            (occupancy_alert, EventKind.OCCUPANCY_ALERT, occupancy_boxes, (0, 200, 0), ""),
            (crowd_alert, EventKind.CROWD_ALERT, [], (0, 0, 0), ""),
        )
        for is_active, kind, boxes_to_draw, box_color, box_label in checks:
            if is_active and self._event_dedup.is_new_occurrence(kind):
                # CROWD_ALERT CẦN thấy lớp phủ heatmap trong ảnh bằng chứng -
                # khác PPE/Fire/Fall/Occupancy (chỉ cần thấy CÓ vi phạm/đông
                # người), cảnh báo này ý nghĩa nằm ở VỊ TRÍ tụ tập CỤ THỂ
                # trong ROI, xem lại Event Log sau này mà không có overlay
                # thì không biết đông ở đâu, chỉ biết "có báo động".
                evidence_frame = self._build_evidence_frame(
                    frame, include_heatmap=(kind == EventKind.CROWD_ALERT),
                    boxes=boxes_to_draw, box_color=box_color, box_label=box_label,
                )
                EventStore.instance().add_event(self._device_id, self._device_name, kind, evidence_frame)
                self._send_incident(evidence_frame, kind)

        self._capture_face_events(frame)

    def _capture_face_events(self, frame) -> None:
        """Ghi Event Log cho khuôn mặt nhận diện được ở lượt AI này
        (self._last_face_boxes - đã có sẵn từ _check_faces, mỗi phần tử là
        (x1,y1,x2,y2,nhãn,status,track_id) - status là 1 trong
        _FACE_STATUS_BLACKLIST/_KNOWN/_STRANGER/_UNKNOWN) - ảnh bằng chứng là ẢNH CROP
        KHUÔN MẶT (core/face_crop.py), giống hệt cách Gate Kiosk đã làm
        (pages/gate_kiosk_page.py::_on_presence_confirmed), KHÔNG phải cả
        frame - xem lại nhanh đúng mặt ai mà không cần phóng to.

        Người QUEN (status == known) VÀ Người LẠ (status == stranger, ĐÃ
        qua đủ gate xác nhận nhờ tracking - xem _check_faces/
        _bind_face_identities) dùng CHUNG 1 trong 2 CHẾ ĐỘ chống spam chọn
        riêng từng camera (AIConfig.stranger_repeat_mode, Camera Config tab
        AI - tên field còn giữ "stranger" vì lịch sử, NHƯNG áp dụng cho CẢ
        2 loại từ khi thêm chế độ "once") - xem _should_notify_face:
          - "once"         - CHỈ thông báo 1 LẦN DUY NHẤT cho mỗi track
                             (self._face_track_notified), tới khi track đó
                             biến mất khỏi khung hình hẳn - không phụ thuộc
                             mốc thời gian nào. Có bắc cầu qua bộ nhớ tạm
                             (_face_memory) nếu track chết rồi được cấp
                             track_id mới cho ĐÚNG người đó.
          - "grace_period" - thông báo lại nếu track đó "im lặng" (không có
                             lượt nào xác nhận) lâu hơn _EVENT_LOG_GRACE_SEC
                             giây rồi xác nhận lại (self._event_dedup, giống
                             PPE/Fire/Fall/Occupancy) - người quen dedup
                             theo TÊN (không phải track_id, xem docstring
                             cũ), người lạ dedup theo track_id.

        in_roi (xem _check_faces) - CHỈ ghi Event Log cho khuôn mặt trong
        vùng ROI (camera có cấu hình) - người ngoài vùng quan tâm không tạo
        thông báo/không ghi log dù vẫn hiện đúng trên preview."""
        for x1, y1, x2, y2, name, status, track_id, in_roi in self._last_face_boxes:
            if not in_roi:
                continue
            if status == _FACE_STATUS_KNOWN:
                if self._should_notify_face(track_id, grace_key=(EventKind.FACE_RECOGNIZED, name)):
                    evidence = crop_face_with_padding(frame, (x1, y1, x2, y2))
                    EventStore.instance().add_event(
                        self._device_id, self._device_name, EventKind.FACE_RECOGNIZED, evidence, detail=name
                    )
            elif status == _FACE_STATUS_STRANGER:
                if self._should_notify_face(track_id, grace_key=(EventKind.STRANGER_ALERT, track_id)):
                    evidence = crop_face_with_padding(frame, (x1, y1, x2, y2))
                    embedding = self._face_track_last_embedding.get(track_id)
                    EventStore.instance().add_event(
                        self._device_id, self._device_name, EventKind.STRANGER_ALERT, evidence,
                        embedding=embedding.tobytes() if embedding is not None else None,
                    )
                    self._send_incident(evidence, EventKind.STRANGER_ALERT)
            elif status == _FACE_STATUS_BLACKLIST:
                # detail=name - "name" ở đây LÀ label đã gán ở _check_faces
                # (= blacklist_entry.name, xem vòng lặp phân loại trạng thái)
                # - không cần tra lại BlacklistStore. embedding lưu kèm để
                # dùng làm nguồn ảnh cho luồng "Thêm ảnh từ lịch sử nhận
                # diện" sau này (core/blacklist_store.py, pages/blacklist_page.py).
                if self._should_notify_face(track_id, grace_key=(EventKind.BLACKLIST_ALERT, track_id)):
                    evidence = crop_face_with_padding(frame, (x1, y1, x2, y2))
                    embedding = self._face_track_last_embedding.get(track_id)
                    EventStore.instance().add_event(
                        self._device_id, self._device_name, EventKind.BLACKLIST_ALERT, evidence, detail=name,
                        embedding=embedding.tobytes() if embedding is not None else None,
                    )
                    self._send_incident(evidence, EventKind.BLACKLIST_ALERT)

    def _should_notify_face(self, track_id: int, grace_key) -> bool:
        """Quyết định có nên ghi Event Log/thông báo cho track này hay
        không - dùng CHUNG cho cả người quen, người lạ, VÀ Blacklist (xem
        _capture_face_events), theo đúng AIConfig.stranger_repeat_mode:
          - "grace_period" - self._event_dedup theo grace_key (khác nhau
                             giữa người quen/tên và người lạ/track_id - xem
                             2 nơi gọi).
          - "once" (mặc định) - self._face_track_notified theo track_id,
                             KHÔNG dùng grace_key. Ghi lại "đã thông báo"
                             vào bộ nhớ tạm (_remember_face) NGAY lúc này
                             (không đợi lượt AI sau) - lúc _bind_face_identities
                             ghi bộ nhớ (trong _check_faces, TRƯỚC khi hàm
                             này chạy) thì track vẫn CHƯA được đánh dấu "đã
                             thông báo", nên bản ghi cũ còn notified=False -
                             phải sửa lại ngay, nếu không track chết ngay
                             sau lượt thông báo ĐẦU TIÊN sẽ để lại bộ nhớ
                             SAI, làm mất tác dụng chống spam khi xuất hiện
                             lại."""
        if self._stranger_repeat_mode == _STRANGER_REPEAT_GRACE_PERIOD:
            return self._event_dedup.is_new_occurrence(grace_key)
        if track_id in self._face_track_notified:
            return False
        self._face_track_notified.add(track_id)
        last_embedding = self._face_track_last_embedding.get(track_id)
        if last_embedding is not None:
            track_blacklist_entry = self._face_track_blacklist_entry.get(track_id)
            self._remember_face(
                last_embedding,
                name=self._face_track_identity.get(track_id),
                best_sim=self._face_track_best_sim.get(track_id, 0.0),
                notified=True,
                blacklist_entry_id=track_blacklist_entry.id if track_blacklist_entry is not None else None,
            )
        return True

    def _send_incident(self, evidence_frame, kind: EventKind) -> None:
        """Gửi lên web qua Web_API.send_mobile_incident - CHỈ khi camera đã
        có camera_id server đã lưu sẵn (self._web_camera_id rỗng = chưa nhập
        MAC hoặc chưa tra được lúc Save, im lặng bỏ qua, không lỗi - không tự
        gọi mạng để tra ở đây). Gọi ĐỒNG BỘ ngay trong QThread của pipeline
        này (không bọc thêm threading.Thread như MIRAI - pipeline đã tự chạy
        trong 1 QThread riêng rồi); Web_API tự try/except nên không cần bọc
        thêm ở đây.

        Kind không có mặt trong EVENT_KIND_INCIDENT_TYPE_ID (hiện chỉ có
        OCCUPANCY_ALERT - xem event_record.py) -> bỏ qua bước gửi web, vẫn
        đã lưu Event Log/SYSTEM ALARMS ở _capture_events rồi."""
        if not self._web_camera_id or kind not in EVENT_KIND_INCIDENT_TYPE_ID:
            return
        details = f"{EVENT_KIND_LABELS[kind]} at {self._device_name}"
        Web_API.send_mobile_incident(
            evidence_frame, details, EVENT_KIND_INCIDENT_TYPE_ID[kind], self._web_camera_id
        )

    def _build_evidence_frame(
        self, frame, include_heatmap: bool = False,
        boxes=(), box_color: tuple[int, int, int] = (0, 200, 0), box_label: str = "",
    ):
        """Ảnh bằng chứng = frame gốc + vẽ vùng ROI (nếu camera có cấu hình)
        + khung CÁC VỊ TRÍ đã phát hiện (boxes, nếu có) để biết rõ vùng làm
        việc/khu vực VÀ vị trí cụ thể liên quan tới cảnh báo. Vẽ trên 1 BẢN
        SAO, không đụng tới frame gốc (vẫn được dùng tiếp cho overlay preview
        ngay sau _run_ai trong run()).

        boxes - danh sách (x1,y1,x2,y2) vẽ khung box_color (BGR) + nhãn
        box_label (rỗng = không vẽ text, dùng cho Occupancy có nhiều bbox
        cùng lúc, vẽ text từng box sẽ rối) - bug đã gặp thật: ảnh bằng chứng
        PPE/Fire/Fall/Occupancy trước đây CHỈ có ROI (nếu có) hoặc CHỈ full
        frame trơn, không rõ AI phát hiện ở vị trí nào, phải tự đoán khi xem
        lại Event Log - xem _capture_events (nơi TRUYỀN boxes tương ứng từng
        loại cảnh báo).

        include_heatmap=True (CHỈ CROWD_ALERT dùng, xem _capture_events) -
        vẽ THÊM lớp phủ heatmap (_blend_heatmap, cùng hàm dùng cho preview
        LiveView) TRƯỚC khi vẽ viền ROI/boxes - giữ ĐÚNG thứ tự lớp như
        _draw_overlay (heatmap dưới cùng, ROI/box vẽ đè lên trên cho rõ nét) -
        để xem lại Event Log sau này thấy được CHÍNH XÁC khu vực nào đang
        tụ tập lúc cảnh báo được ghi, không chỉ biết chung chung "có báo
        động"."""
        if not self._roi_polygons and not include_heatmap and not boxes:
            return frame
        evidence = frame.copy()
        if include_heatmap and self._heatmap_grid is not None and self._crowd_heatmap_threshold > 0:
            self._blend_heatmap(evidence)
        for polygon in self._roi_polygons:
            cv2.polylines(evidence, [polygon], isClosed=True, color=(120, 200, 0), thickness=2)
        for x1, y1, x2, y2 in boxes:
            cv2.rectangle(evidence, (x1, y1), (x2, y2), box_color, 2)
            if box_label:
                cv2.putText(
                    evidence, box_label, (x1, max(15, y1 - 8)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, box_color, 1, cv2.LINE_AA,
                )
        return evidence

    def _check_fire(self, frame) -> tuple[bool, list[tuple[int, int, int, int]]]:
        """Fire detection port từ YOLO_FIRE.py: chạy trên TOÀN khung hình,
        độc lập với Body/Pose - không cần ROI, không cần có người. Không
        làm mượt/debounce thêm - giữ nguyên hành vi gốc (mỗi frame AI có
        box là báo động ngay, bản gốc chỉ throttle việc GỬI alert ra ngoài
        chứ không throttle chính giá trị phát hiện).

        fire_detection_new.pt có 2 lớp {0: Fire, 1: Smoke} nhưng dùng CHUNG
        1 ngưỡng AISettings.fire_conf (lọc ngay trong AIModelManager.detect_fire,
        classes=[0, 1]) - box nào lọt qua model() là đủ điều kiện báo động,
        không cần lọc lại ở đây.

        Trả về THÊM danh sách bbox (CÓ THỂ nhiều vùng lửa/khói cùng lúc,
        khác Fall chỉ 1 người) - dùng để vẽ khung lên ảnh bằng chứng Event
        Log (_build_evidence_frame), xem _capture_events."""
        result = AIModelManager.instance().detect_fire(frame, imgsz=self._inference_imgsz)
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return False, []
        fire_boxes = [tuple(int(v) for v in xyxy) for xyxy in boxes.xyxy.cpu().numpy()]
        return True, fire_boxes

    def _check_faces(self, frame) -> tuple[list[str], bool]:
        """Face recognition port từ Face_detection.py của MIRAI, NÂNG CẤP
        thêm TRACKING qua nhiều frame (DeepSort riêng cho mặt - xem
        self._face_tracker/_bind_face_identities) - PORT nguyên cơ chế từ
        pages/gate_kiosk_page.py để sửa đúng gốc 2 bug đã gặp thật:
          (1) chỉ quay nghiêng mặt 1 chút cũng lập tức bị coi là "Stranger"
              (không tracking -> mỗi frame đánh giá lại từ đầu, 1 frame góc
              xấu đủ để nhìn similarity tụt xuống ngưỡng Stranger).
          (2) 1 người lạ đứng lâu quay đầu qua lại bị spam thông báo NHIỀU
              LẦN (mỗi lần trạng thái "tắt/bật" lại qua grace period bị
              tính là người lạ MỚI, do không có khái niệm "đây vẫn là
              đúng 1 người tôi đã thấy lúc trước").
        Tracking giải quyết cả 2: 1 track ổn định xuyên suốt cả lúc người đó
        quay đầu/di chuyển (DeepSort tự chịu được vài frame mất dấu), nên chỉ
        cần ĐÚNG 1 lần nhìn rõ+thẳng là "seen well" mãi mãi cho track đó
        (không mất vì mấy frame sau quay đầu), và similarity xét theo CAO
        NHẤT từng đo được của track (không phải riêng frame này).

        Trả về (list tên người quen thấy trong frame này, có ít nhất 1
        khuôn mặt "Stranger đã xác nhận" trong frame này hay không - dùng
        cho SYSTEM ALARMS/camera card badge, xem _emit_ai_result).

        4 TRẠNG THÁI cho mỗi khuôn mặt/track (self._last_face_boxes, xem
        _FACE_STATUS_*):
          - "blacklist" - track đã khớp ra 1 entry trong BlacklistStore
                         (sticky, ƯU TIÊN CAO NHẤT - đè lên cả 3 trạng thái
                         dưới đây dù track đó trước đó/đồng thời cũng khớp
                         known hay đủ gate Stranger - xem _bind_face_identities/
                         core/blacklist_store.py) -> tên/nhãn entry.
          - "known"    - track đã khớp ra 1 người quen (sticky - xem
                         _bind_face_identities) -> tên thật.
          - "stranger" - CHƯA từng khớp ai VÀ đã qua đủ CẢ 2 gate: track
                         từng có ÍT NHẤT 1 lượt nhìn đủ rõ + đủ THẲNG
                         (_face_track_seen_well, gate stranger_confirm_min_score
                         + stranger_min_frontal_ratio - core/face_pose.py),
                         VÀ similarity CAO NHẤT từng đo được của track vẫn
                         đủ thấp (_face_track_best_sim <= stranger_ambiguous_max_sim,
                         "vùng xám" - 1 lần similarity cao hơn mức này ở BẤT
                         KỲ lúc nào thì track đó không bao giờ được xác nhận
                         Stranger nữa) - CHỈ trạng thái này mới góp phần vào
                         cảnh báo/Event Log.
          - "unknown"  - CHƯA từng khớp ai NHƯNG chưa đủ 1 trong 2 gate ở
                         trên (chưa từng nhìn đủ rõ/thẳng, HOẶC có nét giống
                         người quen nhưng chưa đủ) - hiện nhãn "Unknown"
                         (KHÔNG PHẢI "Stranger"), không góp phần vào cảnh
                         báo nào - chỉ chờ lượt sau nhìn rõ/thẳng hơn.
        Mọi ngưỡng/gate đều chỉnh được qua UI "AI Setting", áp dụng NGAY
        toàn hệ thống.

        ROI (tab ROI, nếu camera có vẽ ít nhất 1 vùng) - giống hệt cách Gate
        Kiosk giới hạn theo vùng "cổng" (pages/gate_kiosk_page.py): CHỈ
        khuôn mặt có TÂM bbox nằm TRONG ROI mới được DETECT + TRACK + NHẬN
        DIỆN (lọc ngay từ bước gọi AIModelManager.detect_faces - truyền
        self._roi_polygons vào, xem docstring hàm đó) - khuôn mặt ngoài
        ROI bị loại NGAY TỪ ĐẦU, không hiện trên preview, không tốn công
        nhận diện/tracking, không chiếm "suất" _FACE_MAX_PER_FRAME của mặt
        thật sự trong ROI (bug đã gặp thật: đám đông NGOÀI ROI to hơn/gần
        tâm khung hình hơn từng chiếm hết 10 "suất" theo heuristic mặc định
        của insightface, khiến mặt THẬT SỰ trong ROI không bao giờ lọt vào
        để mà nhận diện dù camera vẫn "thấy" họ). Camera CHƯA vẽ ROI nào
        (roi_polygons rỗng) -> KHÔNG giới hạn, xét toàn khung hình như
        trước (giữ nguyên hành vi cũ cho camera chưa cấu hình ROI).

        in_roi trong self._last_face_boxes (xem _capture_face_events) giờ
        LUÔN True (mọi mặt lọt qua detect_faces đã chắc chắn trong ROI rồi,
        hoặc camera không có ROI nào để lọc) - CHỦ Ý giữ lại field/lượt kiểm
        tra này thay vì bỏ đi, làm lớp phòng vệ rẻ tiền phòng trường hợp
        logic lọc ở detect_faces có sai sót sau này, không phải để lọc gì
        thêm ở đây nữa."""
        # roi_polygons truyền vào ĐÂY để chính insightface ƯU TIÊN chọn mặt
        # trong ROI trước khi cắt còn max_num (xem AIModelManager.detect_faces)
        # - không phải lọc SAU khi đã chọn (lúc đó có thể mặt trong ROI đã bị
        # loại mất từ vòng chọn top max_num rồi, không cách nào lấy lại).
        faces = AIModelManager.instance().detect_faces(
            frame, max_num=_FACE_MAX_PER_FRAME, roi_polygons=self._roi_polygons
        )
        good_faces = [f for f in faces if f.det_score >= _FACE_DET_SCORE_THRESHOLD]

        # QUAN TRỌNG: LUÔN gọi tracker.update() dù good_faces RỖNG (bbox
        # rỗng) - KHÔNG tự ý coi "1 lượt AI không có mặt đạt ngưỡng" là
        # "track biến mất" rồi prune ngay lập tức (bug đã gặp thật: người
        # lạ/quen chỉ cúi xuống/che khuất mặt 1 CHÚT khiến det_score rớt
        # dưới _FACE_DET_SCORE_THRESHOLD đúng 1-2 lượt AI là bị xoá SẠCH
        # _face_track_seen_well/_best_sim/_identity/_notified ngay, hiện lại
        # "Unknown" dù DeepSort đáng lẽ vẫn "nhớ" track đó thêm nhiều frame
        # nữa - bộ nhớ tạm theo embedding chỉ bắc cầu được khi track ĐÃ THỰC
        # SỰ chết, không cứu được nếu bị prune oan ngay từ 1 frame mờ tạm
        # thời). DeepSort.update() với detection rỗng vẫn AN TOÀN (tự bỏ
        # qua bước trích đặc trưng - core/deep_sort_pytorch/deep_sort/deep_sort.py::_get_features)
        # - vẫn chạy Kalman predict + tự đếm time_since_update cho từng
        # track, dùng ĐÚNG max_age nội bộ của chính nó để quyết định khi
        # nào 1 track thực sự biến mất (không còn trong outputs).
        if good_faces:
            bbox_xywh = torch.Tensor([self._xyxy_to_xywh(f.bbox) for f in good_faces])
            confidences = torch.Tensor([float(f.det_score) for f in good_faces])
            classes = [0] * len(good_faces)  # 1 "lớp" duy nhất (mặt) - DeepSort cần tham số này nhưng không dùng để phân biệt gì thêm ở đây
        else:
            bbox_xywh = torch.empty(0, 4)
            confidences = torch.empty(0)
            classes = []
        outputs = self._get_face_tracker().update(bbox_xywh, confidences, classes, frame)

        if good_faces:
            self._bind_face_identities(outputs, good_faces, frame.shape[1])

        if len(outputs) == 0:
            self._prune_face_tracks(active_ids=set())
            self._last_face_boxes = []
            return [], False

        settings = AISettings.instance()
        known_faces: list[str] = []
        any_confirmed_stranger = False
        face_boxes: list[tuple[int, int, int, int, str, str, int, bool]] = []
        active_ids: set[int] = set()

        for x1, y1, x2, y2, track_id, _cls in outputs:
            track_id = int(track_id)
            active_ids.add(track_id)
            in_roi = not self._roi_polygons or self._face_center_in_roi((x1, y1, x2, y2))
            blacklist_entry = self._face_track_blacklist_entry.get(track_id)
            name = self._face_track_identity.get(track_id)
            if blacklist_entry is not None:
                # ƯU TIÊN CAO NHẤT - đè lên known/stranger/unknown, KHÔNG góp
                # vào known_faces (danh sách đó dùng cho "Recognized" - ý
                # nghĩa khác hẳn, không nên lẫn Blacklist vào đó).
                status, label = _FACE_STATUS_BLACKLIST, blacklist_entry.name
            elif name is not None:
                status, label = _FACE_STATUS_KNOWN, name
                if in_roi:
                    known_faces.append(name)
            elif (
                track_id in self._face_track_seen_well
                and self._face_track_best_sim.get(track_id, 0.0) <= settings.stranger_ambiguous_max_sim
            ):
                status, label = _FACE_STATUS_STRANGER, "Stranger"
                if in_roi:
                    any_confirmed_stranger = True
            else:
                status, label = _FACE_STATUS_UNKNOWN, "Unknown"
            face_boxes.append((int(x1), int(y1), int(x2), int(y2), label, status, track_id, in_roi))

        self._prune_face_tracks(active_ids)
        self._last_face_boxes = face_boxes
        return known_faces, any_confirmed_stranger

    def _face_center_in_roi(self, bbox) -> bool:
        x1, y1, x2, y2 = bbox
        center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
        return any(cv2.pointPolygonTest(polygon, center, False) >= 0 for polygon in self._roi_polygons)

    def _get_face_tracker(self) -> DeepSort:
        """Tracker DeepSort RIÊNG cho khuôn mặt - KHÁC self._get_tracker()
        (bbox đầu/thân, dùng cho đếm vào/ra/occupancy/PPE) - 2 tracker độc
        lập hoàn toàn, không chia sẻ track_id/state gì với nhau. Cùng
        cấu hình DEEPSORT_YAML/REID_CKPT với tracker kia (không cần model
        riêng - DeepSort chỉ dùng ReID để bám theo 1 vùng ảnh liên tục qua
        các frame, không quan tâm đó là mặt hay cả người)."""
        if self._face_tracker is None:
            cfg = get_config()
            cfg.merge_from_file(_DEEPSORT_YAML)
            cfg.DEEPSORT.REID_CKPT = _REID_CKPT
            self._face_tracker = DeepSort(
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
        return self._face_tracker

    def _bind_face_identities(self, outputs, good_faces, frame_width: int) -> None:
        """Gán/giữ danh tính cho từng track mặt - PORT từ
        pages/gate_kiosk_page.py::_bind_identities (xem docstring gốc ở đó
        về lý do "sticky" - track_id do DeepSort gán liền mạch cho 1 vùng
        ảnh đang bám theo, gần như chắc chắn vẫn là CÙNG 1 người trong suốt
        vòng đời track đó, nên 1 lượt match trượt do góc mặt xấu tạm thời
        KHÔNG được hạ cấp 1 track đã từng khớp ra người quen xuống lại
        "chưa rõ").

        Track VỪA xuất hiện lần đầu (mới tạo, HOẶC track cũ vừa chết vì mất
        dấu quá lâu - DeepSort cấp track_id KHÁC cho ĐÚNG người đó khi họ
        quay lại) - thử khôi phục trạng thái từ "bộ nhớ tạm"
        (_recall_face_memory, theo embedding KHÔNG phải track_id) trước khi
        coi là người hoàn toàn mới - xem hằng số _FACE_MEMORY_*."""
        if not good_faces or len(outputs) == 0:
            return
        max_dist = _IDENTITY_MATCH_MAX_DIST_RATIO * frame_width
        store = KnownFacesStore.instance()
        blacklist_store = BlacklistStore.instance()
        settings = AISettings.instance()
        for face in good_faces:
            fx1, fy1, fx2, fy2 = face.bbox
            face_center = ((fx1 + fx2) / 2, (fy1 + fy2) / 2)
            best_track_id, best_dist = None, max_dist
            for x1, y1, x2, y2, track_id, _cls in outputs:
                center = ((x1 + x2) / 2, (y1 + y2) / 2)
                dist = ((center[0] - face_center[0]) ** 2 + (center[1] - face_center[1]) ** 2) ** 0.5
                if dist < best_dist:
                    best_dist = dist
                    best_track_id = int(track_id)
            if best_track_id is None:
                continue

            if best_track_id not in self._face_track_identity:
                remembered = self._recall_face_memory(face.normed_embedding)
                if remembered is not None:
                    self._face_track_identity[best_track_id] = remembered.name
                    # "đã thông báo" áp dụng cho CẢ 3 - người quen, người lạ,
                    # Blacklist (chế độ "once" - xem _should_notify_face),
                    # khôi phục bất kể remembered.name có hay không.
                    if remembered.notified:
                        self._face_track_notified.add(best_track_id)
                    if remembered.blacklist_entry_id is not None:
                        entry = blacklist_store.get_entry(remembered.blacklist_entry_id)
                        if entry is not None:
                            self._face_track_blacklist_entry[best_track_id] = entry
                    if remembered.name is None:
                        self._face_track_seen_well.add(best_track_id)
                        self._face_track_best_sim[best_track_id] = remembered.best_sim

            if (
                face.det_score >= settings.stranger_confirm_min_score
                and estimate_face_frontal_ratio(face.kps) >= settings.stranger_min_frontal_ratio
            ):
                self._face_track_seen_well.add(best_track_id)

            # Blacklist - ƯU TIÊN CAO NHẤT, kiểm tra ĐỘC LẬP với known/stranger
            # bên dưới (không ảnh hưởng lẫn nhau). Sticky đơn giản hơn known
            # (không cần "best_sim vùng xám" gì cả) - chỉ GÁN khi khớp, KHÔNG
            # BAO GIỜ xoá khi trượt (track đã khớp Blacklist 1 lần là giữ mãi
            # cho tới khi track chết - xem _prune_face_tracks).
            blacklist_entry, _blacklist_sim = blacklist_store.match(
                face.normed_embedding, threshold=settings.blacklist_match_threshold
            )
            if blacklist_entry is not None:
                self._face_track_blacklist_entry[best_track_id] = blacklist_entry

            name, sim = store.match(face.normed_embedding, threshold=settings.face_similarity_threshold)
            matched_name = None if name == "Stranger" else name
            # Track ĐÃ có danh tính biết trước đó (dù từ 1 match trước hay
            # vừa khôi phục từ bộ nhớ tạm ở trên) - 1 lượt match trượt do
            # góc xấu NGAY LÚC VỪA khôi phục không được phép ghi đè lại
            # best_sim/xoá danh tính đó (sticky, giống hệt lý do docstring
            # ở trên, chỉ mở rộng thêm cho trường hợp vừa khôi phục).
            already_known = self._face_track_identity.get(best_track_id) is not None
            if matched_name is None and not already_known:
                self._face_track_best_sim[best_track_id] = max(
                    sim, self._face_track_best_sim.get(best_track_id, 0.0)
                )
            elif matched_name is not None:
                self._face_track_best_sim.pop(best_track_id, None)
            # Chỉ ghi đè khi CÓ khớp, hoặc track này CHƯA từng xuất hiện -
            # track đã có trong dict (dù đang là None) mà lượt này lại
            # trượt (matched_name is None) thì GIỮ NGUYÊN giá trị cũ (sticky).
            if matched_name is not None or best_track_id not in self._face_track_identity:
                self._face_track_identity[best_track_id] = matched_name

            self._face_track_last_embedding[best_track_id] = face.normed_embedding
            track_blacklist_entry = self._face_track_blacklist_entry.get(best_track_id)
            self._remember_face(
                face.normed_embedding,
                name=self._face_track_identity.get(best_track_id),
                best_sim=self._face_track_best_sim.get(best_track_id, 0.0),
                notified=best_track_id in self._face_track_notified,
                blacklist_entry_id=track_blacklist_entry.id if track_blacklist_entry is not None else None,
            )

    def _recall_face_memory(self, embedding: np.ndarray) -> "_RememberedFace | None":
        """Tìm trong self._face_memory 1 entry có embedding khớp ĐỦ CHẶT
        (AISettings.face_memory_match_threshold, cosine similarity - cả 2
        vector đã normed nên chỉ cần dot product) VÀ chưa quá hạn
        (_FACE_MEMORY_TTL_SEC) - trả về entry tốt nhất, None nếu không có
        entry nào đạt. Không tự xoá entry hết hạn ở đây (chỉ bỏ qua) - việc
        dọn dẹp chủ động do _prune_face_tracks lo, tránh 2 nơi cùng sửa
        list này lúc đang lặp."""
        now = time.monotonic()
        threshold = AISettings.instance().face_memory_match_threshold
        best_entry, best_sim = None, threshold
        for entry in self._face_memory:
            if now - entry.last_seen > _FACE_MEMORY_TTL_SEC:
                continue
            sim = float(np.dot(embedding, entry.embedding))
            if sim > best_sim:
                best_sim, best_entry = sim, entry
        return best_entry

    def _remember_face(
        self, embedding: np.ndarray, name: str | None, best_sim: float, notified: bool,
        blacklist_entry_id: str | None = None,
    ) -> None:
        """Ghi/cập nhật 1 khuôn mặt vào self._face_memory - tìm entry KHỚP
        gần nhất trước (cùng ngưỡng với _recall_face_memory) để CẬP NHẬT ĐÈ
        (không tạo entry mới mỗi frame cho ĐÚNG 1 người đang đứng yên/di
        chuyển liên tục - danh sách chỉ tăng khi có mặt THỰC SỰ mới), không
        có thì thêm entry mới (giới hạn _FACE_MEMORY_MAX_ENTRIES, bỏ entry
        cũ nhất khi đầy)."""
        now = time.monotonic()
        threshold = AISettings.instance().face_memory_match_threshold
        for entry in self._face_memory:
            if float(np.dot(embedding, entry.embedding)) > threshold:
                entry.embedding = embedding
                entry.last_seen = now
                entry.name = name
                entry.best_sim = best_sim
                entry.notified = notified
                entry.blacklist_entry_id = blacklist_entry_id
                return
        self._face_memory.append(_RememberedFace(embedding, now, name, best_sim, notified, blacklist_entry_id))
        if len(self._face_memory) > _FACE_MEMORY_MAX_ENTRIES:
            self._face_memory.pop(0)

    def _prune_face_tracks(self, active_ids: set[int]) -> None:
        for track_id in list(self._face_track_identity):
            if track_id not in active_ids:
                del self._face_track_identity[track_id]
        for track_id in list(self._face_track_blacklist_entry):
            if track_id not in active_ids:
                del self._face_track_blacklist_entry[track_id]
        self._face_track_seen_well &= active_ids
        for track_id in list(self._face_track_best_sim):
            if track_id not in active_ids:
                del self._face_track_best_sim[track_id]
        # Track biến mất thật (DeepSort hết chịu được, xem MAX_AGE) -> xoá
        # khỏi "đã thông báo" luôn, để nếu 1 track_id SAU NÀY được cấp lại
        # cho 1 người lạ hoàn toàn khác thì không bị "miễn thông báo" oan vì
        # trùng số track_id cũ (DeepSort tái sử dụng ID sau khi track cũ
        # chết hẳn).
        self._face_track_notified &= active_ids
        for track_id in list(self._face_track_last_embedding):
            if track_id not in active_ids:
                del self._face_track_last_embedding[track_id]
        # Dọn entry hết hạn khỏi bộ nhớ tạm (_FACE_MEMORY_TTL_SEC) - lười
        # (chỉ chạy mỗi khi có track biến mất, không phải mỗi frame), tránh
        # danh sách tồn đọng vô hạn entry đã hết hạn nếu camera chạy rất lâu
        # mà track ít biến mất (_recall_face_memory/_remember_face chỉ BỎ
        # QUA entry hết hạn khi tra, không tự xoá).
        now = time.monotonic()
        self._face_memory = [e for e in self._face_memory if now - e.last_seen <= _FACE_MEMORY_TTL_SEC]

    def _check_fall(self, frame, result) -> tuple[bool, tuple[int, int, int, int] | None]:
        """Fall detection port từ Fall_detection.py: với mỗi người có đủ 6
        keypoint tin cậy (vai/hông/mắt cá, COCO-17) - dùng RAW detection
        giống PPE, không qua track - crop quanh bbox (+30px) rồi chạy
        fall_detection.pt (ngưỡng conf = AISettings.fall_conf, chỉnh được
        qua UI). Alert cuối cùng cần 2 tầng: phát hiện tức thời (frame này)
        VÀ majority-vote xác nhận từ AISettings.fall_confirm_window frame AI
        gần nhất (cần ít nhất fall_confirm_min_count lượt "đang ngã").

        Trả về (fall_alert, bbox) - bbox (toạ độ NGƯỜI, chưa padding) của
        người đang ngã CHỈ khi fall_alert đã được xác nhận (2 tầng ở trên),
        None nếu chưa - CameraPipeline._draw_overlay chỉ vẽ khung fall khi
        có bbox, tức không vẽ khung dựa trên 1 lượt phát hiện đơn lẻ chưa
        qua xác nhận."""
        settings = AISettings.instance()
        boxes = result.boxes
        keypoints = result.keypoints
        is_falling = False
        candidate_bbox: tuple[int, int, int, int] | None = None

        if boxes is not None and keypoints is not None and len(boxes) > 0:
            h, w = frame.shape[:2]
            for i in range(len(boxes)):
                kpt_conf = keypoints.conf[i].cpu().numpy()
                if any(kpt_conf[idx] < _FALL_POSE_CONF_THRESHOLD for idx in _FALL_REQUIRED_KEYPOINTS):
                    continue

                px1, py1, px2, py2 = boxes.xyxy[i].cpu().numpy()
                cx1 = max(0, int(px1) - _FALL_CROP_PADDING)
                cy1 = max(0, int(py1) - _FALL_CROP_PADDING)
                cx2 = min(w, int(px2) + _FALL_CROP_PADDING)
                cy2 = min(h, int(py2) + _FALL_CROP_PADDING)
                crop = frame[cy1:cy2, cx1:cx2]
                if crop.size == 0:
                    continue

                if AIModelManager.instance().check_fall(crop, imgsz=self._inference_imgsz) > 0.0:
                    is_falling = True
                    candidate_bbox = (int(px1), int(py1), int(px2), int(py2))

        # Cửa sổ làm mượt (deque) đổi kích thước ngay khi người dùng chỉnh
        # AISettings.fall_confirm_window qua UI - tạo lại deque MỚI (giữ lại
        # tối đa maxlen mục cuối cùng, deque() tự cắt bớt phần dư) thay vì
        # đợi restart pipeline.
        if self._fall_buffer.maxlen != settings.fall_confirm_window:
            self._fall_buffer = deque(self._fall_buffer, maxlen=settings.fall_confirm_window)

        fall_alert = is_falling and self._fall_confirmed
        self._fall_buffer.append(is_falling)
        self._fall_confirmed = sum(self._fall_buffer) >= settings.fall_confirm_min_count
        return fall_alert, (candidate_bbox if fall_alert else None)

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

    def _update_crowd_heatmap(self, outputs, frame_shape) -> None:
        """Cập nhật lưới nhiệt đám đông CỤC BỘ (self._heatmap_grid, xem hằng
        số _HEATMAP_*) - bổ sung cho _count_occupancy (đếm TỔNG số người):
        đo được người có đang TỤ TẬP dồn vào 1 vùng nhỏ hay không, dù tổng số
        người trong ROI chưa vượt occupancy_threshold.

        Cơ chế (gọi mỗi lượt AI khi enable_occupancy + crowd_heatmap_threshold
        > 0, xem _run_ai):
          1. SUY GIẢM (decay) toàn bộ lưới trước - nhân theo hệ số
             0.5 ** (dt / _HEATMAP_HALF_LIFE_SEC), dt = thời gian THẬT trôi
             qua kể từ lượt cập nhật trước (không phải số lượt AI, vì
             ai_fps_limit đổi được từng camera) -> nhiệt "nguội" đúng theo
             thời gian thật kể cả khi outputs rỗng (không có ai).
          2. CỘNG nhiệt cho mỗi người đang active - lấy tâm bbox ĐẦU (cùng
             điểm _count_occupancy dùng, khớp đúng ROI vẽ theo vị trí đầu
             người đứng), "vẩy" theo kernel 3x3 quanh ô chứa điểm đó
             (_HEATMAP_KERNEL, tổng trọng số 1.0 -> 1 người = đúng 1 đơn vị
             nhiệt/lượt, không phụ thuộc số người khác đang có).
          3. CHẶN TRẦN mỗi ô ở _HEATMAP_CELL_MAX - tránh nhiệt tích luỹ vô
             hạn ở chỗ luôn đông liên tục hàng giờ.

        Có ROI -> CHỈ cộng nhiệt cho người có tâm đầu nằm TRONG ROI (giống
        _count_occupancy) - người ngoài ROI không góp phần vào lưới. Không có
        ROI -> xét toàn khung hình.

        Ô "nóng nhất" hiện tại (self._heatmap_grid.max()) là căn cứ cảnh báo
        crowd_alert ở _run_ai - so với crowd_heatmap_threshold, KHÁC hẳn
        occupancy_alert (so TỔNG num_people)."""
        height, width = frame_shape[:2]
        if self._heatmap_grid is None:
            self._heatmap_grid = np.zeros((_HEATMAP_GRID_ROWS, _HEATMAP_GRID_COLS), dtype=np.float32)
            self._heatmap_last_ts = time.monotonic()

        now = time.monotonic()
        dt = max(0.0, now - self._heatmap_last_ts)
        self._heatmap_last_ts = now
        self._heatmap_grid *= 0.5 ** (dt / _HEATMAP_HALF_LIFE_SEC)

        cell_w = width / _HEATMAP_GRID_COLS
        cell_h = height / _HEATMAP_GRID_ROWS
        for x1, y1, x2, y2, _track_id, _cls in outputs:
            head_center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            if self._roi_polygons and not any(
                cv2.pointPolygonTest(polygon, head_center, False) >= 0 for polygon in self._roi_polygons
            ):
                continue

            col = min(max(int(head_center[0] // cell_w), 0), _HEATMAP_GRID_COLS - 1)
            row = min(max(int(head_center[1] // cell_h), 0), _HEATMAP_GRID_ROWS - 1)
            for ky in range(-1, 2):
                ry = row + ky
                if ry < 0 or ry >= _HEATMAP_GRID_ROWS:
                    continue
                for kx in range(-1, 2):
                    rx = col + kx
                    if rx < 0 or rx >= _HEATMAP_GRID_COLS:
                        continue
                    self._heatmap_grid[ry, rx] += _HEATMAP_KERNEL[ky + 1, kx + 1]

        np.clip(self._heatmap_grid, 0.0, _HEATMAP_CELL_MAX, out=self._heatmap_grid)

    def _draw_overlay(self, frame) -> None:
        """Vẽ overlay lên frame TRƯỚC khi emit - theo cấu hình tab Overlay
        (show_bbox/show_label/show_roi/show_tracking_id) + cảnh báo PPE/Fire/
        Fall gần nhất. Dùng self._last_tracks (không phải kết quả AI-tick vừa
        rồi) vì AI bị throttle theo ai_fps_limit trong khi frame emit ở mọi
        vòng lặp capture - giữa 2 lần AI chạy, vẫn vẽ theo vị trí track cũ."""
        # Heatmap vẽ TRƯỚC (dưới cùng) - ROI/bbox/label vẽ đè lên sau vẫn rõ
        # nét, không bị lớp tint heatmap làm mờ. Chỉ vẽ khi tính năng đang
        # BẬT (threshold > 0), đã có ít nhất 1 lượt cập nhật lưới
        # (self._heatmap_grid khác None - camera vừa bật tính năng nhưng
        # chưa qua lượt AI nào thì chưa có gì để vẽ), VÀ lưới có nhiệt ĐÁNG
        # KỂ (_HEATMAP_DRAW_EPSILON) - hàm này chạy trên MỌI frame emit (theo
        # display FPS, KHÔNG throttle theo ai_fps_limit như phần tính lưới -
        # xem docstring _draw_overlay), nên bỏ qua sớm lúc không ai tụ tập
        # (đa số thời gian thực tế) tránh phí CPU vẽ 1 lớp gần như trong
        # suốt hoàn toàn, không ai nhìn ra khác biệt.
        if (
            self._crowd_heatmap_threshold > 0
            and self._heatmap_grid is not None
            and float(self._heatmap_grid.max()) >= _HEATMAP_DRAW_EPSILON * self._crowd_heatmap_threshold
        ):
            self._blend_heatmap(frame)

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

        for x1, y1, x2, y2, name, status, _track_id, _in_roi in self._last_face_boxes:
            # BGR: xanh lá = quen, cam/đỏ = Stranger ĐÃ XÁC NHẬN, vàng = chưa
            # đủ căn cứ kết luận (unknown - xem _check_faces) - CHỦ Ý khác
            # màu Stranger để không gây hiểu lầm là đã xác nhận người lạ chỉ
            # vì 1 góc mặt/chất lượng chưa đủ.
            color = _FACE_STATUS_COLORS.get(status, (0, 200, 0))
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                frame, name, (x1, max(15, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
            )

        # Khung fall (đỏ) CHỈ vẽ khi self._last_fall_bbox có giá trị -
        # _check_fall() chỉ trả bbox khi fall_alert đã qua đủ 2 tầng xác
        # nhận (majority-vote AISettings.fall_confirm_window/fall_confirm_min_count),
        # KHÔNG vẽ dựa trên 1 lượt phát hiện đơn lẻ chưa xác nhận.
        if self._last_fall_bbox is not None:
            fx1, fy1, fx2, fy2 = self._last_fall_bbox
            cv2.rectangle(frame, (fx1, fy1), (fx2, fy2), (0, 0, 255), 3)
            cv2.putText(
                frame, "FALL", (fx1, max(15, fy1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA,
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
        if self._last_blacklist_alert:
            alerts.append("BLACKLIST")
        if alerts:
            cv2.putText(
                frame, " | ".join(alerts), (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2, cv2.LINE_AA,
            )

    def _blend_heatmap(self, frame) -> None:
        """Vẽ lớp phủ heatmap lên frame (tại chỗ, giống mọi hàm vẽ overlay
        khác) - phóng to lưới thô self._heatmap_grid (_HEATMAP_GRID_ROWS x
        _HEATMAP_GRID_COLS) lên đúng kích thước frame bằng nội suy tuyến
        tính, tô màu kiểu "nhiệt" (JET: xanh dương nhạt -> đỏ đậm), rồi trộn
        theo alpha RIÊNG TỪNG PIXEL (chỗ không có nhiệt phải TRONG SUỐT hoàn
        toàn, không tô màu gì - không dùng cv2.addWeighted vì hàm đó chỉ hỗ
        trợ 1 alpha đồng nhất cho cả ảnh).

        HIỆU NĂNG (đã đo thật, xem lịch sử sửa hàm này - bản đầu tiên dùng
        frame.astype(np.float32) rồi nhân/cộng broadcast bằng numpy thuần
        chậm KHỦNG KHIẾP, ~70-80ms/frame ở 1080p, đủ để giật lag rõ rệt vì
        hàm này chạy trên MỌI frame emit theo display FPS, KHÔNG throttle
        theo ai_fps_limit như phần tính lưới _update_crowd_heatmap). 2 tối
        ưu ở đây (đã benchmark, ~7-10 lần nhanh hơn, còn ~6-12ms/frame ở
        1080p):
          1. Trộn bằng cv2.multiply/cv2.add (uint8 + scale, KHÔNG chuyển
             sang float32) thay vì numpy broadcast - OpenCV có SIMD/vector
             hoá native cho các phép toán mảng uint8 này, numpy broadcasting
             với mảng lớn (đặc biệt shape (h,w,1) broadcast lên (h,w,3)) lại
             CHẬM hơn hẳn dù về lý thuyết cùng khối lượng phép toán.
          2. Có ROI -> chỉ trộn trong đúng BOUNDING BOX của ROI (nhiệt luôn
             = 0 ngoài ROI, trộn cả phần đó chỉ tốn công vô ích) - vẫn phải
             resize lưới ra ĐỦ KÍCH THƯỚC FRAME GỐC trước rồi mới cắt vùng
             (không resize thẳng xuống kích thước bounding box) để giữ ĐÚNG
             ánh xạ toạ độ ô lưới <-> điểm ảnh (self._update_crowd_heatmap
             tính cell_w/cell_h theo kích thước FRAME, không phải theo ROI).

        Chuẩn hoá theo crowd_heatmap_threshold (không phải theo max thực tế
        của lưới) - ý nghĩa trực quan: đỏ đậm/mờ đục nhất (alpha tối đa) ĐÚNG
        LÚC ô đó chạm ngưỡng cảnh báo, giúp người xem đoán được "còn cách báo
        động bao xa" thay vì chỉ thấy màu tương đối giữa các ô với nhau."""
        height, width = frame.shape[:2]
        heat_norm = np.clip(self._heatmap_grid / self._crowd_heatmap_threshold, 0.0, 1.0)
        heat_resized = cv2.resize(heat_norm, (width, height), interpolation=cv2.INTER_LINEAR)

        if self._roi_polygons:
            bx, by, bw, bh = cv2.boundingRect(np.concatenate(self._roi_polygons, axis=0))
            x0, y0 = max(0, bx), max(0, by)
            x1, y1 = min(width, bx + bw), min(height, by + bh)
            if x1 <= x0 or y1 <= y0:
                return
        else:
            x0, y0, x1, y1 = 0, 0, width, height

        heat_crop = heat_resized[y0:y1, x0:x1]
        colored_crop = cv2.applyColorMap((heat_crop * 255).astype(np.uint8), cv2.COLORMAP_JET)
        # tối đa 50% mờ đục - vẫn thấy rõ người/vật bên dưới lớp phủ.
        alpha_3ch = cv2.cvtColor((heat_crop * 0.5 * 255).astype(np.uint8), cv2.COLOR_GRAY2BGR)
        inv_alpha_3ch = cv2.bitwise_not(alpha_3ch)

        region = frame[y0:y1, x0:x1]
        term_frame = cv2.multiply(region, inv_alpha_3ch, scale=1.0 / 255.0)
        term_color = cv2.multiply(colored_crop, alpha_3ch, scale=1.0 / 255.0)
        frame[y0:y1, x0:x1] = cv2.add(term_frame, term_color)

    def _emit_ai_result(
        self,
        num_people: int,
        ppe_violation: bool = False,
        fire_alert: bool = False,
        fall_alert: bool = False,
        fall_bbox: tuple[int, int, int, int] | None = None,
        occupancy_alert: bool = False,
        crowd_alert: bool = False,
        known_faces: list[str] | None = None,
        stranger_alert: bool = False,
        stranger_track_ids: list[int] | None = None,
        blacklist_alert: bool = False,
        blacklist_track_ids: list[int] | None = None,
    ) -> None:
        # Cache lại cho _draw_overlay() dùng - overlay vẽ trên MỌI frame emit
        # (kể cả frame không trùng nhịp AI chạy), nên cần giữ trạng thái cảnh
        # báo gần nhất thay vì tính lại.
        self._last_ppe_violation = ppe_violation
        self._last_fire_alert = fire_alert
        self._last_fall_alert = fall_alert
        self._last_fall_bbox = fall_bbox
        self._last_stranger_alert = stranger_alert
        self._last_blacklist_alert = blacklist_alert
        self.ai_result_ready.emit(
            self._device_id,
            {
                "num_people": num_people,
                "num_in": self._people_in,
                "num_out": self._people_out,
                "ppe_violation": ppe_violation,
                "fire_alert": fire_alert,
                "fall_alert": fall_alert,
                "occupancy_alert": occupancy_alert,
                "crowd_alert": crowd_alert,
                "known_faces": known_faces or [],
                "stranger_alert": stranger_alert,
                # track_id của TỪNG người lạ/Blacklist đã xác nhận trong lượt
                # này - xem pages/liveview_page.py::_log_alarms/
                # pages/dashboard_page.py (phân biệt nhiều người khác nhau,
                # không dồn chung 1 dòng log).
                "stranger_track_ids": stranger_track_ids or [],
                "blacklist_alert": blacklist_alert,
                "blacklist_track_ids": blacklist_track_ids or [],
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
        # Webcam USB (self._source là int) -> ép dùng backend DirectShow
        # (CAP_DSHOW) thay vì để OpenCV tự dò backend mặc định - trên
        # Windows, backend mặc định (MSMF) khởi tạo RẤT chậm với nhiều webcam
        # (có thể mất 5-10s+ mỗi lần mở), DSHOW mở gần như ngay lập tức (cùng
        # bug "mở camera rất lâu" gặp ở pages/face_attendance_page.py). IP/
        # RTSP (self._source là str URL) không dùng được CAP_DSHOW (chỉ dành
        # cho thiết bị capture cục bộ) nên giữ nguyên backend mặc định.
        if isinstance(self._source, int):
            cap = cv2.VideoCapture(self._source, cv2.CAP_DSHOW)
        else:
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
        hoặc bị stop().

        Chờ theo từng bước nhỏ (_RECONNECT_POLL_MS) thay vì 1 lần msleep dài
        bằng cả reconnect_timeout_ms (có thể tới hàng chục giây) - msleep
        không thể bị ngắt giữa chừng, nên nếu stop() được gọi đúng lúc đang
        msleep dài, DeviceManager.stop_device() chờ wait(2000) hết hạn rồi bỏ
        đi trong khi thread C++ vẫn còn sống -> Python GC huỷ luôn object
        CameraPipeline -> Qt abort process với "QThread: Destroyed while
        thread is still running" (bug đã gặp: crash khi Logout lúc có camera
        đang ở trạng thái chờ reconnect)."""
        while self._running:
            waited_ms = 0
            while waited_ms < self._reconnect_timeout_ms and self._running:
                self.msleep(min(_RECONNECT_POLL_MS, self._reconnect_timeout_ms - waited_ms))
                waited_ms += _RECONNECT_POLL_MS
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
