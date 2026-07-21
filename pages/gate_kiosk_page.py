"""GateCaptureWorker + GateVideoView + GateWindow: 2 cửa sổ kiosk chấm công
theo VẠCH ẢO (Check In / Check Out), mở từ sidebar ATTENDANCE
(pages/menu_window.py).

Khác FaceAttendanceWindow (kiosk 1 người, tự mở 1 webcam riêng qua
cv2.VideoCapture): ở đây camera đã được cấu hình/Start SẴN ở Camera Config
(nguồn video, Counting Line ở tab ROI, bật chạy pipeline) - gate window
KHÔNG tự mở camera, chỉ "mượn" lại frame full-res từ CameraPipeline ĐANG
CHẠY qua DeviceManager.subscribe_preview() (giống cách ROIEditorDialog lấy
hình nền), và tự chạy thêm AI của riêng nó trên frame mượn được:
    - Nhận diện MẶT (AIModelManager.detect_faces + KnownFacesStore) mỗi
      lượt AI - lấy luôn bbox mặt + danh tính (không cần detect body/đầu
      riêng như tính năng "Đếm người vào/ra" của camera thường).
    - Track TRỰC TIẾP bbox mặt qua nhiều frame bằng DeepSort (cùng tracker
      core/camera_pipeline.py dùng, chỉ khác input là bbox mặt thay vì bbox
      đầu) - đọc vạch từ chính CameraDevice.counting_line đã vẽ sẵn.
    - Khi 1 track BĂNG QUA vạch đúng hướng cấu hình cho cửa sổ này
      (core/line_crossing.py), chốt sự kiện chấm công bằng danh tính đã gắn
      cho track đó.
Nếu camera chưa được Start (hoặc bị Stop giữa chừng) - KHÔNG tự Start giùm,
chỉ báo cho người dùng biết và tự nối lại khi camera chạy trở lại
(DeviceManager.device_running_changed).

2 nút Check In/Check Out dùng CHUNG 1 GateWindow, chỉ khác tham số
`direction` ("in"/"out") - tránh nhân đôi code gần như giống hệt nhau.

Backend (Web_API.send_mobile_employee) hiện KHÔNG có field phân biệt check-
in/check-out - camera_id truyền vào là id camera đã chọn cho CỔNG này (2
cổng = 2 camera_id khác nhau), đủ để backend/báo cáo sau này suy ra hướng
theo camera cho tới khi có field riêng."""
from __future__ import annotations

import time
from datetime import datetime
from typing import Literal, Optional

import cv2
import numpy as np
import torch
from PyQt6 import QtWidgets
from PyQt6.QtCore import QPointF, QRectF, Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen, QPixmap

from core.ai_model_manager import AIModelManager
from core.deep_sort_pytorch.deep_sort import DeepSort
from core.deep_sort_pytorch.utils.parser import get_config
from core.device_manager import DeviceManager
from core.event_dedup import PresenceDedup
from core.face_crop import crop_face_with_padding
from core.gate_config import GateKind, load_gate_config, save_gate_config
from core.known_faces_store import KnownFacesStore
from core.line_crossing import ccw, segments_intersect
from core.models.camera_device import CameraDevice, parse_points
from core.path_manager import BASE_DIR
from scr import Web_API
from ui.dialogs.gate_setup_dialog import GateSetupDialog
from ui.ui_menu.widgets.face_card import FaceCard

import os

_DEEPSORT_YAML = os.path.join(BASE_DIR, "core", "deep_sort_pytorch", "configs", "deep_sort.yaml")
_REID_CKPT = os.path.join(
    BASE_DIR, "core", "deep_sort_pytorch", "deep_sort", "deep", "checkpoint", "ckpt.t7"
)

_FACE_DET_SCORE_THRESHOLD = 0.5
# ~10 lượt AI/giây - đủ mượt để bắt kịp người đi ngang qua cổng, tương đương
# ai_fps_limit mặc định của CameraPipeline (10).
_AI_INTERVAL_SEC = 0.1
# Vòng lặp poll frame mượn từ pipeline - chỉ để bắt kịp frame mới sớm, KHÔNG
# phải nhịp chạy AI thật (đã throttle riêng bằng _AI_INTERVAL_SEC ở trên).
_POLL_INTERVAL_MS = 15
# Khoảng cách tâm mặt vừa detect<->tâm track tối đa để gán danh tính, tính
# theo % chiều rộng frame - track ở đây LÀ bbox mặt (DeepSort track thẳng
# trên detect_faces, không qua body/đầu trung gian) nên 2 tâm gần như trùng
# nhau khi cùng 1 người; giữ ngưỡng nhỏ để không lẫn giữa 2 mặt đứng gần
# nhau trong khung hình đông người.
_IDENTITY_MATCH_MAX_DIST_RATIO = 0.08
# Ngắn hơn cooldown 60s của Face App (pages/face_attendance_page.py) vì đây
# là luồng người liên tục qua cổng, không phải 1 kiosk đứng yên 1 người.
_ATTENDANCE_COOLDOWN_SEC = 30.0
_MAX_GALLERY_CARDS = 50

# direction -> (label hiển thị, màu vạch/tiêu đề)
_DIRECTION_LABELS: dict[str, tuple[str, str]] = {
    "in": ("CHECK IN", "#00e676"),
    "out": ("CHECK OUT", "#ffaa00"),
}


def _qimage_to_bgr(image: QImage) -> np.ndarray:
    """Pipeline broadcast hình dạng QImage RGB888 (đã convert để hiển thị) -
    convert NGƯỢC lại numpy BGR để chạy AI (detect_faces kỳ vọng input BGR,
    giống mọi nơi khác trong app).

    Dùng bytesPerLine() THẬT thay vì giả định width*3 - Qt pad mỗi hàng lên
    bội số 4 byte, width*3 lẻ (không chia hết 4, vd 721px) sẽ có padding dư
    cuối mỗi hàng; bỏ qua bước cắt padding này làm ảnh bị lệch/nghiêng dần
    xuống dưới (đã kiểm chứng bằng round-trip test)."""
    rgb = image.convertToFormat(QImage.Format.Format_RGB888)
    w, h = rgb.width(), rgb.height()
    bytes_per_line = rgb.bytesPerLine()
    ptr = rgb.bits()
    ptr.setsize(h * bytes_per_line)
    arr = np.frombuffer(ptr, dtype=np.uint8).reshape(h, bytes_per_line)[:, : w * 3].reshape(h, w, 3)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _employee_display_name(employee: Optional[dict]) -> str:
    if employee is None:
        return "?"
    name = f"{employee.get('last_name') or ''} {employee.get('first_name') or ''}".strip()
    return name or "?"


class GateCaptureWorker(QThread):
    """Vòng lặp nền: nhận frame do GateWindow đẩy vào (mượn từ CameraPipeline
    đang chạy - xem set_frame()) + nhận diện + track TRỰC TIẾP bbox mặt
    (DeepSort, không qua body/đầu trung gian) + phát hiện cắt vạch đúng
    hướng. KHÔNG tự mở camera - khác FaceCaptureWorker của Face App."""

    crossing_event = pyqtSignal(object)  # dict {"employee": dict|None, "pixmap": QPixmap, "ts": datetime}
    # [(x1,y1,x2,y2,label,matched), ...] - bbox mặt của MỌI track đang thấy ở
    # lượt AI gần nhất, để GateVideoView vẽ đè lên video (phản hồi trực quan
    # ai đang được track/nhận diện, giống bbox debug CameraPipeline._draw_overlay
    # vẽ cho tính năng "Đếm người vào/ra" ở camera thường).
    tracks_ready = pyqtSignal(list)

    def __init__(
        self,
        line_points: list[tuple[int, int]],
        direction: Literal["in", "out"],
        gate_camera_id: str,
        parent=None,
    ):
        super().__init__(parent)
        self._line = (line_points[0], line_points[1])
        self._direction = direction
        self._gate_camera_id = gate_camera_id
        self._running = True

        self._pending_frame: Optional[np.ndarray] = None
        self._frame_seq = 0
        self._last_processed_seq = -1
        self._last_ai_ts = 0.0

        self._tracker: Optional[DeepSort] = None
        self._track_history: dict[int, list[tuple[int, int]]] = {}
        self._track_identity: dict[int, Optional[dict]] = {}
        self._crossed_tracks: set[int] = set()
        self._dedup = PresenceDedup(_ATTENDANCE_COOLDOWN_SEC)

    def set_frame(self, frame: np.ndarray) -> None:
        """Gọi từ main thread (GateWindow._on_pipeline_frame) mỗi khi
        DeviceManager phát 1 frame mới của camera đang theo dõi - CHỈ gán
        thuộc tính (an toàn nhờ GIL, giống FaceCaptureWorker.latest_frame ở
        pages/face_attendance_page.py), không cần lock/queue."""
        self._pending_frame = frame
        self._frame_seq += 1

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        while self._running:
            seq = self._frame_seq
            frame = self._pending_frame
            if frame is not None and seq != self._last_processed_seq:
                self._last_processed_seq = seq
                now = time.monotonic()
                if now - self._last_ai_ts >= _AI_INTERVAL_SEC:
                    self._last_ai_ts = now
                    self._run_ai(frame)
            self.msleep(_POLL_INTERVAL_MS)

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

    def _run_ai(self, frame: np.ndarray) -> None:
        faces = AIModelManager.instance().detect_faces(frame)
        good_faces = [f for f in faces if f.det_score >= _FACE_DET_SCORE_THRESHOLD]
        if not good_faces:
            self._prune_tracks(active_ids=set())
            self.tracks_ready.emit([])
            return

        bbox_xywh = torch.Tensor([self._xyxy_to_xywh(f.bbox) for f in good_faces])
        confidences = torch.Tensor([float(f.det_score) for f in good_faces])
        classes = [0] * len(good_faces)  # 1 "lớp" duy nhất (mặt) - DeepSort cần tham số này nhưng không dùng để phân biệt gì thêm ở đây
        outputs = self._get_tracker().update(bbox_xywh, confidences, classes, frame)

        self._bind_identities(outputs, good_faces, frame.shape[1])

        self.tracks_ready.emit([
            (
                int(x1), int(y1), int(x2), int(y2),
                _employee_display_name(self._track_identity.get(int(track_id))),
                self._track_identity.get(int(track_id)) is not None,
            )
            for x1, y1, x2, y2, track_id, _cls in outputs
        ])

        active_ids: set[int] = set()
        for x1, y1, x2, y2, track_id, _cls in outputs:
            track_id = int(track_id)
            active_ids.add(track_id)
            center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            history = self._track_history.setdefault(track_id, [])
            history.append(center)
            if len(history) > 10:
                history.pop(0)

            if len(history) >= 2 and track_id not in self._crossed_tracks:
                prev_pos, curr_pos = history[-2], history[-1]
                p1, p2 = self._line
                if segments_intersect(prev_pos, curr_pos, p1, p2):
                    crossed_in = ccw(curr_pos, p1, p2)
                    matches_direction = (crossed_in and self._direction == "in") or (
                        not crossed_in and self._direction == "out"
                    )
                    if matches_direction:
                        self._crossed_tracks.add(track_id)
                        bbox = (int(x1), int(y1), int(x2), int(y2))
                        self._on_crossing(track_id, frame, bbox)

        self._prune_tracks(active_ids)

    def _bind_identities(self, outputs, good_faces, frame_width: int) -> None:
        if not good_faces or len(outputs) == 0:
            return
        max_dist = _IDENTITY_MATCH_MAX_DIST_RATIO * frame_width
        store = KnownFacesStore.instance()
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
            if best_track_id is not None:
                employee, _sim = store.match_employee(face.normed_embedding)
                self._track_identity[best_track_id] = employee

    def _on_crossing(self, track_id: int, frame: np.ndarray, bbox: tuple[int, int, int, int]) -> None:
        employee = self._track_identity.get(track_id)
        dedup_key = employee.get("id") if employee else f"stranger-track-{track_id}"
        if not self._dedup.is_new_occurrence(dedup_key):
            return

        crop = crop_face_with_padding(frame, bbox)
        pixmap = self._crop_to_pixmap(crop)
        now = datetime.now()
        self.crossing_event.emit({"employee": employee, "pixmap": pixmap, "ts": now})

        if employee is not None:
            try:
                Web_API.send_mobile_employee(frame, employee["id"], self._gate_camera_id, now)
            except Exception as exc:  # noqa: BLE001 - lỗi mạng không được làm crash worker
                print(f"[Gate] Lỗi ghi nhận chấm công: {exc}")

    def _prune_tracks(self, active_ids: set[int]) -> None:
        for track_id in list(self._track_history):
            if track_id not in active_ids:
                del self._track_history[track_id]
                self._track_identity.pop(track_id, None)
                self._crossed_tracks.discard(track_id)

    @staticmethod
    def _xyxy_to_xywh(bbox_xyxy) -> list[float]:
        x1, y1, x2, y2 = bbox_xyxy
        w, h = x2 - x1, y2 - y1
        return [x1 + w / 2, y1 + h / 2, w, h]

    @staticmethod
    def _crop_to_pixmap(crop: np.ndarray) -> QPixmap:
        if crop.size == 0:
            return QPixmap()
        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        return QPixmap.fromImage(image)


class GateVideoView(QtWidgets.QWidget):
    """Video cổng hình chữ nhật + 1 vạch ảo cố định. Dùng contain-fit
    (letterbox, toàn bộ khung hình luôn hiển thị đủ) - CÙNG hệ toạ độ full-
    res mà pipeline dùng để tính counting_line, để vị trí vạch hiển thị đúng
    khớp toạ độ đã vẽ ở Camera Config > ROI (khác cover-fit vốn crop mất rìa
    khung hình, sẽ làm lệch vị trí vạch)."""

    def __init__(self, direction: Literal["in", "out"], parent=None):
        super().__init__(parent)
        self.setMinimumSize(720, 480)
        self._pixmap: Optional[QPixmap] = None
        self._line: Optional[tuple[tuple[int, int], tuple[int, int]]] = None
        self._tracks: list[tuple[int, int, int, int, str, bool]] = []
        label, color = _DIRECTION_LABELS[direction]
        self._label = label
        self._color = QColor(color)

    def set_frame(self, image: QImage) -> None:
        self._pixmap = QPixmap.fromImage(image)
        self.update()

    def set_line(self, line_points: list[tuple[int, int]]) -> None:
        self._line = (line_points[0], line_points[1]) if len(line_points) == 2 else None
        self.update()

    def set_tracks(self, tracks: list[tuple[int, int, int, int, str, bool]]) -> None:
        """tracks: [(x1,y1,x2,y2,label,matched), ...] toạ độ frame gốc (full-
        res) - vẽ bbox mặt của MỌI người đang được track/nhận diện, phản hồi
        trực quan cho người vận hành thấy AI đang bám đúng ai (xem
        GateCaptureWorker.tracks_ready)."""
        self._tracks = tracks
        self.update()

    def _draw_rect(self) -> QRectF:
        if self._pixmap is None or self._pixmap.isNull():
            return QRectF(self.rect())
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph) if pw and ph else 1.0
        dw, dh = pw * scale, ph * scale
        return QRectF((ww - dw) / 2, (wh - dh) / 2, dw, dh)

    def paintEvent(self, event) -> None:  # noqa: N802 - tên hàm bắt buộc bởi Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#06080c"))

        rect = self._draw_rect()
        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(rect, self._pixmap, QRectF(self._pixmap.rect()))
        else:
            painter.setPen(QColor("#3a5070"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Đang chờ hình từ camera...")

        has_pixmap = self._pixmap is not None and not self._pixmap.isNull()
        scale = (rect.width() / self._pixmap.width()) if has_pixmap and self._pixmap.width() else 1.0

        if self._line is not None and has_pixmap:
            p1 = QPointF(rect.x() + self._line[0][0] * scale, rect.y() + self._line[0][1] * scale)
            p2 = QPointF(rect.x() + self._line[1][0] * scale, rect.y() + self._line[1][1] * scale)
            painter.setPen(QPen(self._color, 3))
            painter.drawLine(p1, p2)

        if has_pixmap:
            for x1, y1, x2, y2, label, matched in self._tracks:
                box_color = QColor("#00e676") if matched else QColor("#ffaa00")
                box = QRectF(
                    rect.x() + x1 * scale, rect.y() + y1 * scale,
                    (x2 - x1) * scale, (y2 - y1) * scale,
                )
                painter.setPen(QPen(box_color, 2))
                painter.drawRect(box)
                painter.setPen(box_color)
                painter.drawText(QPointF(box.x(), max(12.0, box.y() - 6)), label)

        painter.setPen(QColor("#e0e6f0"))
        painter.drawText(14, 26, self._label)
        painter.end()


class GateWindow(QtWidgets.QMainWindow):
    """Cửa sổ THƯỜNG (title bar/minimize/maximize/close chuẩn, có trong
    taskbar) - dùng CHUNG cho cả 2 nút Check In/Check Out (pages/menu_window.py),
    chỉ khác tham số `direction`. Camera phải được cấu hình/Start SẴN ở
    Camera Config trước - cửa sổ này chỉ CHỌN camera, không tự thêm/vẽ
    vạch/Start giùm (xem module docstring)."""

    def __init__(self, direction: Literal["in", "out"], parent=None):
        super().__init__(parent)
        self._direction = direction
        self._kind: GateKind = "checkin" if direction == "in" else "checkout"
        label, _color = _DIRECTION_LABELS[direction]
        self.setWindowTitle(f"Gate Kiosk - {label}")

        self._device: Optional[CameraDevice] = None
        self._subscribed_device_id: Optional[str] = None
        self._worker: Optional[GateCaptureWorker] = None
        self._cards: list[FaceCard] = []
        self._total_count = 0

        self._build_ui()
        self._center_on_screen(1300, 940)

        DeviceManager.instance().pipeline_frame_ready.connect(self._on_pipeline_frame)
        DeviceManager.instance().device_running_changed.connect(self._on_device_running_changed)
        DeviceManager.instance().device_updated.connect(self._on_device_updated)

        if not self._start_from_saved_config():
            self._open_setup()

    # ------------------------------------------------------------------ #
    def _center_on_screen(self, width: int, height: int) -> None:
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            self.resize(width, height)
            return
        geo = screen.availableGeometry()
        width = min(width, geo.width() - 40)
        height = min(height, geo.height() - 40)
        self.setGeometry(
            geo.x() + (geo.width() - width) // 2,
            geo.y() + (geo.height() - height) // 2,
            width,
            height,
        )

    def _build_ui(self) -> None:
        central = QtWidgets.QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(10)

        label, color = _DIRECTION_LABELS[self._direction]
        title = QtWidgets.QLabel(f"🚪  {label}")
        title.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: 700;")
        root.addWidget(title)

        self.lbl_status = QtWidgets.QLabel("")
        self.lbl_status.setStyleSheet("color:#ffaa00; font-size:12px; font-weight:600;")
        root.addWidget(self.lbl_status)

        self.video_view = GateVideoView(self._direction)
        root.addWidget(self.video_view, 1)

        self.lbl_count = QtWidgets.QLabel("Đã chấm công: 0")
        self.lbl_count.setStyleSheet("color:#7a8aaa; font-size:12px;")
        root.addWidget(self.lbl_count)

        self.gallery_scroll = QtWidgets.QScrollArea()
        self.gallery_scroll.setWidgetResizable(True)
        self.gallery_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.gallery_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gallery_scroll.setFixedHeight(250)

        gallery_content = QtWidgets.QWidget()
        self.gallery_layout = QtWidgets.QHBoxLayout(gallery_content)
        self.gallery_layout.setContentsMargins(4, 4, 4, 4)
        self.gallery_layout.setSpacing(8)
        self.gallery_layout.addStretch(1)
        self.gallery_scroll.setWidget(gallery_content)
        root.addWidget(self.gallery_scroll)

        btn_setup = QtWidgets.QPushButton("⚙  Đổi camera")
        btn_setup.clicked.connect(self._open_setup)
        root.addWidget(btn_setup, alignment=Qt.AlignmentFlag.AlignRight)

    # ── Chọn camera + subscribe frame từ pipeline đang chạy ─────────────────
    def _start_from_saved_config(self) -> bool:
        device_id = load_gate_config(self._kind)
        if device_id is None:
            return False
        device = DeviceManager.instance().get_device(device_id)
        if device is None:
            return False
        self._start_watching(device)
        return True

    def _open_setup(self) -> None:
        had_device = self._device
        self._stop_watching()

        label, _color = _DIRECTION_LABELS[self._direction]
        dialog = GateSetupDialog(f"Thiết lập cổng {label}", parent=self)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            if had_device is not None:
                self._start_watching(had_device)
            else:
                self.close()
            return

        device = dialog.get_device()
        save_gate_config(self._kind, device.id)
        self._start_watching(device)

    def _start_watching(self, device: CameraDevice) -> None:
        """Chọn xong 1 camera - KHÔNG tự mở/Start camera, chỉ mượn frame nếu
        pipeline của nó đang chạy sẵn (xem module docstring). Nếu chưa chạy
        (hoặc chưa vẽ vạch), chỉ hiện thông báo - tự nối lại khi
        device_running_changed/device_updated báo camera đã sẵn sàng."""
        self._stop_watching()
        self._device = device

        line_points = parse_points(device.counting_line)
        self.video_view.set_line(line_points)
        self.video_view.set_tracks([])
        if len(line_points) != 2:
            self.lbl_status.setText(
                f"⚠ Camera \"{device.name}\" chưa vẽ Counting Line - vào Camera Config > tab ROI để vẽ vạch."
            )
            return

        self._worker = GateCaptureWorker(line_points, self._direction, device.id)
        self._worker.crossing_event.connect(self._on_crossing_event)
        self._worker.tracks_ready.connect(self.video_view.set_tracks)
        self._worker.start()

        if DeviceManager.instance().subscribe_preview(device.id, need_full_resolution=True):
            self._subscribed_device_id = device.id
            self.lbl_status.setText("")
        else:
            self.lbl_status.setText(
                f"⚠ Camera \"{device.name}\" chưa được Start - vào Camera Config hoặc Device Management để bật chạy."
            )

    def _stop_watching(self) -> None:
        if self._subscribed_device_id is not None:
            DeviceManager.instance().unsubscribe_preview(self._subscribed_device_id, need_full_resolution=True)
            self._subscribed_device_id = None
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None
        self._device = None
        self.video_view.set_tracks([])

    # ── Nhận frame/trạng thái từ DeviceManager (broadcast toàn app) ────────
    def _on_pipeline_frame(self, device_id: str, image: QImage) -> None:
        if self._device is None or device_id != self._device.id:
            return
        self.video_view.set_frame(image)
        if self._worker is not None:
            self._worker.set_frame(_qimage_to_bgr(image))

    def _on_device_running_changed(self, device_id: str, running: bool) -> None:
        if self._device is None or device_id != self._device.id:
            return
        if running:
            self._start_watching(self._device)
        else:
            self._subscribed_device_id = None
            self.lbl_status.setText(f"⚠ Camera \"{self._device.name}\" đã dừng - vào Camera Config để Start lại.")

    def _on_device_updated(self, device_id: str) -> None:
        """Camera đang chờ (thiếu vạch/chưa chạy) - người dùng vừa sửa cấu
        hình ở Camera Config (vd vẽ lại Counting Line) trong lúc cửa sổ này
        vẫn đang mở -> thử nối lại luôn, không bắt đóng/mở lại cửa sổ.

        CHỈ xét khi đang ở trạng thái CHỜ (self._subscribed_device_id is
        None) - cố tình KHÔNG tự restart worker nếu đang subscribe bình
        thường, vì device_updated bắn cho MỌI thay đổi cấu hình (kể cả đổi
        tên, đổi FPS...), restart vô điều kiện sẽ làm mất state DeepSort/
        cooldown đang tích luỹ dở chỉ vì 1 chỉnh sửa không liên quan tới
        Counting Line. Nếu người dùng vẽ lại vạch TRONG LÚC cửa sổ đang chạy
        bình thường, cần bấm "Đổi camera" (chọn lại đúng camera đó) để nạp
        vạch mới - biết đây là hạn chế, chấp nhận được vì là use-case hiếm."""
        if self._device is None or device_id != self._device.id or self._subscribed_device_id is not None:
            return
        updated = DeviceManager.instance().get_device(device_id)
        if updated is not None:
            self._start_watching(updated)

    # ── Gallery ──────────────────────────────────────────────────────────
    def _on_crossing_event(self, data: dict) -> None:
        employee = data["employee"]
        name = _employee_display_name(employee) if employee is not None else "Người lạ"
        card = FaceCard(name, data["ts"].strftime("%H:%M:%S"), data["pixmap"], matched=employee is not None)

        self.gallery_layout.insertWidget(self.gallery_layout.count() - 1, card)
        self._cards.append(card)
        if len(self._cards) > _MAX_GALLERY_CARDS:
            oldest = self._cards.pop(0)
            self.gallery_layout.removeWidget(oldest)
            oldest.deleteLater()

        self._total_count += 1
        self.lbl_count.setText(f"Đã chấm công: {self._total_count}")

        QTimer.singleShot(0, self._scroll_gallery_to_end)

    def _scroll_gallery_to_end(self) -> None:
        bar = self.gallery_scroll.horizontalScrollBar()
        bar.setValue(bar.maximum())

    # ── Shutdown ─────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        self._stop_watching()
        super().closeEvent(event)
