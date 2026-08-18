"""FaceAttendanceWindow: kiosk nhận diện/đăng ký khuôn mặt cho mục
ATTENDANCE (sidebar menu_window) - cửa sổ ĐỘC LẬP (không phải page trong
stackedPages). Người dùng CHỌN 1 camera đã đăng ký (GateSetupDialog, dùng
chung với pages/gate_kiosk_page.py, require_running=False/require_counting_line=False
vì Face App tự mở cv2.VideoCapture riêng, không cần camera đã Start sẵn qua
Camera Config như Gate kiosk) - lựa chọn được lưu lại (core/gate_config.py,
kind="faceapp") để lần mở sau không phải chọn lại.

Luồng:
    Webcam -> FaceCaptureWorker (detect + match KnownFacesStore liên tục)
    -> mặt lạ: nút "Đăng ký" | mặt quen: nút "Sửa thông tin"
    -> EmployeeFormDialog (điền/sửa thông tin)
    -> FaceCaptureWizardDialog (chụp 3 tư thế: thẳng/trái/phải)
    -> EnrollWorker (gộp embedding, POST lên backend qua Web_API.post_employee,
       lưu avatar cục bộ, refresh KnownFacesStore)

Đây chính là "lối enroll" mà core/known_faces_store.py nói là không có sẵn
trong app này (comment đầu file đó) - nối vào ĐÚNG backend mà KnownFacesStore
đang đọc, không tạo kho dữ liệu cục bộ riêng.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from typing import Optional

import cv2
import numpy as np
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QImage

from core.ai_model_manager import AIModelManager
from core.account_context import account_dir
from core.device_manager import DeviceManager
from core.event_dedup import PresenceDedup
from core.event_store import EventStore
from core.gate_config import load_gate_config, save_gate_config
from core.known_faces_store import KnownFacesStore
from core.models.camera_device import CameraDevice
from core.models.event_record import EventKind
from scr import Web_API
from ui.dialogs.employee_form_dialog import EmployeeFormDialog
from ui.dialogs.face_capture_wizard_dialog import FaceCaptureWizardDialog
from ui.dialogs.face_scan_view import FaceScanView, RingState
from ui.dialogs.gate_setup_dialog import GateSetupDialog
from ui.ui_menu.i18n import LanguageManager, tr

# Cùng ngưỡng chất lượng detection với CameraPipeline._check_faces.
_FACE_DET_SCORE_THRESHOLD = 0.5

# Số lượt detect liên tiếp cùng 1 trạng thái (mặt lạ / cùng 1 người quen)
# trước khi đổi nút Đăng ký/Sửa thông tin - chống nhấp nháy do 1 frame
# detect nhiễu, giống _STRANGER_STREAK_REQUIRED trong camera_pipeline.py.
_STATE_STREAK_REQUIRED = 5
_DETECT_INTERVAL_SEC = 0.2  # ~5 lượt detect/giây, đủ mượt cho kiosk 1 người

# Thời gian tối thiểu giữa 2 lần tự động điểm danh liên tiếp CHO CÙNG 1 người
# (PresenceDedup: chỉ tính "đợt mới" nếu vắng mặt liên tục quá khoảng này).
_ATTENDANCE_COOLDOWN_SEC = 60.0


class FaceCaptureWorker(QThread):
    """Vòng lặp nền: đọc webcam + detect/match khuôn mặt liên tục, độc lập
    UI thread - giống hình dạng CameraPipeline nhưng đơn giản hơn nhiều (1
    webcam cố định, chỉ cần face recognition, không tracking/PPE/fire/fall)."""

    frame_ready = pyqtSignal(QImage)
    # dict {"employee": dict|None, "stable": bool} mô tả người đang đứng
    # trước cam, hoặc None nếu không thấy mặt nào.
    face_state_changed = pyqtSignal(object)
    camera_error = pyqtSignal(str)

    def __init__(self, source: str | int = 0, web_camera_id: str = "", device_id: str = "", device_name: str = ""):
        super().__init__()
        self._source = source
        # camera_id THẬT của server (CameraDevice.web_camera_id, đã tra +
        # lưu sẵn lúc Save/Apply ở camera_config_page.py) - rỗng nghĩa là
        # camera chưa nhập MAC/chưa tra được, _checkin() sẽ bỏ qua bước gửi
        # web (giữ nguyên hành vi local: vẫn nhận diện/chấm công UI bình
        # thường, chỉ không gửi lên server).
        self._web_camera_id = web_camera_id
        # device_id/device_name nội bộ (CameraDevice.id/.name, khác
        # web_camera_id ở trên) - dùng để ghi Event Log (EventStore), giống
        # CameraPipeline._capture_events (core/camera_pipeline.py).
        self._device_id = device_id
        self._device_name = device_name
        self._running = True
        self._attendance_enabled = True

        # Đọc bởi FaceCaptureWizardDialog lúc bấm "Chụp" - gán thuộc tính
        # đơn giản (numpy array) an toàn giữa 2 thread nhờ GIL, giống cách
        # CameraPipeline._last_frame_ts được dùng (core/camera_pipeline.py).
        self.latest_frame: Optional[np.ndarray] = None

        self._last_detect_ts = 0.0
        self._stranger_streak = 0
        self._known_streak = 0
        self._known_employee_id = None
        self._attendance_dedup = PresenceDedup(_ATTENDANCE_COOLDOWN_SEC)

    def stop(self) -> None:
        self._running = False

    def set_attendance_enabled(self, enabled: bool) -> None:
        """Main window gọi để tạm ngưng tự động điểm danh trong lúc đang mở
        form/wizard đăng ký-sửa CHO CHÍNH người đang đứng trước cam - tránh
        vừa auto check-in vừa đăng ký cùng lúc."""
        self._attendance_enabled = enabled

    def _open_capture(self) -> cv2.VideoCapture:
        """Webcam USB (self._source là int) -> ép dùng backend DirectShow
        (CAP_DSHOW) thay vì để OpenCV tự dò backend mặc định - trên Windows,
        backend mặc định (MSMF) khởi tạo RẤT chậm với nhiều webcam (đo thực
        tế có thể mất 5-10s+ mỗi lần mở), trong khi DSHOW mở gần như ngay lập
        tức (bug "mở camera rất lâu" đã gặp thực tế). IP/RTSP (self._source
        là str URL) KHÔNG dùng được CAP_DSHOW (chỉ dành cho thiết bị capture
        cục bộ) nên giữ nguyên backend mặc định (FFMPEG)."""
        if isinstance(self._source, int):
            return cv2.VideoCapture(self._source, cv2.CAP_DSHOW)
        return cv2.VideoCapture(self._source)

    def run(self) -> None:
        cap = self._open_capture()
        if not cap.isOpened():
            self.camera_error.emit(tr("Could not open camera: {source}").format(source=self._source))
            return

        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    self.msleep(200)
                    continue

                # latest_frame giữ NGUYÊN frame gốc (không overlay) - đây là
                # frame FaceCaptureWizardDialog dùng để tính embedding lúc
                # bấm "Chụp", vẽ đè lên sẽ làm hỏng chất lượng embedding.
                self.latest_frame = frame

                now = time.monotonic()
                if now - self._last_detect_ts >= _DETECT_INTERVAL_SEC:
                    self._last_detect_ts = now
                    self._run_detect(frame)

                # Frame emit KHÔNG vẽ đè gì lên - phản hồi trực quan (ring,
                # tên...) do FaceScanView/Qt widget vẽ ở lớp trên, không phải
                # baked vào pixel như cv2 overlay bản trước (xem plan: cũng
                # né được cv2.putText không hiện dấu tiếng Việt).
                image = self._to_qimage(frame)
                if image is not None:
                    self.frame_ready.emit(image)
        finally:
            cap.release()

    def _run_detect(self, frame: np.ndarray) -> None:
        # max_num=1: kiosk giả định 1 người thao tác tại 1 thời điểm, nên chỉ
        # cần insightface trả về đúng 1 mặt (nó tự ưu tiên mặt lớn/gần tâm
        # khung hình nhất - xem AIModelManager.detect_faces) thay vì detect +
        # nhận diện HẾT mọi mặt trong khung rồi mới lọc lấy 1 - tránh bị
        # chậm nếu có người đi ngang qua phía sau (đám đông) trong lúc kiosk
        # đang chờ người thao tác quét mặt.
        faces = AIModelManager.instance().detect_faces(frame, max_num=1)
        good_faces = [f for f in faces if f.det_score >= _FACE_DET_SCORE_THRESHOLD]

        if not good_faces:
            self._stranger_streak = 0
            self._known_streak = 0
            self._known_employee_id = None
            self.face_state_changed.emit(None)
            return

        face = good_faces[0]
        bbox = tuple(int(v) for v in face.bbox)
        frame_w = frame.shape[1]
        face_ratio = (bbox[2] - bbox[0]) / frame_w if frame_w else 0.0
        yaw = self._estimate_yaw(face.kps) if face.kps is not None else 0.0

        employee, _sim = KnownFacesStore.instance().match_employee(face.normed_embedding)

        if employee is None:
            self._known_streak = 0
            self._known_employee_id = None
            self._stranger_streak += 1
            stable = self._stranger_streak >= _STATE_STREAK_REQUIRED
        else:
            emp_id = employee.get("id")
            if emp_id != self._known_employee_id:
                self._known_streak = 0
                self._known_employee_id = emp_id
            self._known_streak += 1
            self._stranger_streak = 0
            stable = self._known_streak >= _STATE_STREAK_REQUIRED
            if stable and self._attendance_enabled and emp_id is not None:
                if self._attendance_dedup.is_new_occurrence(emp_id):
                    self._checkin(frame, emp_id, employee)

        self.face_state_changed.emit({
            "employee": employee,
            "stable": stable,
            "bbox": bbox,
            "embedding": face.normed_embedding,
            "yaw": yaw,
            "face_ratio": face_ratio,
        })

    @staticmethod
    def _estimate_yaw(kps) -> float:
        """Ước lượng góc quay ngang (yaw) từ 5 điểm landmark insightface trả
        về sẵn kèm detection (mắt trái/phải, mũi, khoé miệng trái/phải - xem
        core/ai_model_manager.py, allowed_modules=["detection","recognition"]
        đã có kps mà không cần load model landmark riêng).

        Heuristic: khi nhìn thẳng, mũi nằm giữa 2 mắt theo trục X. Khi quay
        đầu, mũi lệch về phía đối diện hướng quay (do phối cảnh). Lệch được
        chuẩn hoá theo khoảng cách 2 mắt để không phụ thuộc khoảng cách tới
        camera. Kết quả ~0 = thẳng, dương/âm = lệch 1 chiều - CHIỀU CỤ THỂ
        (trái/phải) và ngưỡng "lệch bao nhiêu là đủ" cần hiệu chỉnh với
        camera/gương mặt thật (xem _YAW_* trong face_capture_wizard_dialog.py)."""
        left_eye, right_eye, nose = kps[0], kps[1], kps[2]
        eye_dist = float(right_eye[0] - left_eye[0])
        if abs(eye_dist) < 1e-3:
            return 0.0
        mid_x = (left_eye[0] + right_eye[0]) / 2.0
        return float((nose[0] - mid_x) / eye_dist)

    def _checkin(self, frame: np.ndarray, employee_id, employee: dict) -> None:
        # Ghi Event Log (SQLite, cục bộ) TRƯỚC, không phụ thuộc có gửi web
        # được hay không - vẫn muốn có lịch sử điểm danh cục bộ dù camera
        # chưa nhập MAC/chưa tra được web_camera_id. detail = tên hiển thị
        # trên Event Log (cột "Detail"), không phải khoá tra cứu - chỉ để
        # xem lại nhanh ai vừa điểm danh mà không cần mở ảnh.
        name = f"{employee.get('last_name') or ''} {employee.get('first_name') or ''}".strip()
        EventStore.instance().add_event(
            self._device_id, self._device_name, EventKind.FACE_CHECKIN, frame, detail=name
        )

        if not self._web_camera_id:
            print("[FaceApp] _web_camera_id rỗng - bỏ qua gửi web (chưa tra được camera_id từ MAC, xem Camera Config)")
            return
        try:
            Web_API.send_mobile_employee(frame, employee_id, self._web_camera_id, datetime.now())
        except Exception as exc:  # noqa: BLE001 - lỗi mạng không được làm crash worker
            print(f"[FaceApp] Lỗi ghi nhận điểm danh: {exc}")

    @staticmethod
    def _to_qimage(frame: np.ndarray) -> Optional[QImage]:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        return image.copy()


class EnrollWorker(QThread):
    """POST employee lên backend AIoT (network, không được chặn UI thread) -
    cùng khuôn với KnownFacesRefreshWorker (core/known_faces_store.py)."""

    finished_ok = pyqtSignal(bool, str)

    def __init__(
        self, employee_data: dict, embeddings: list, pose_samples: dict, avatar_frame, avatar_bbox, parent=None
    ):
        super().__init__(parent)
        self._employee_data = employee_data
        self._embeddings = embeddings
        self._pose_samples = pose_samples
        self._avatar_frame = avatar_frame
        self._avatar_bbox = avatar_bbox

    def run(self) -> None:
        avg_embedding = np.mean(self._embeddings, axis=0)
        self._employee_data["identifier_code"] = json.dumps(avg_embedding.tolist())

        try:
            Web_API.post_employee(self._employee_data)
        except Exception as exc:  # noqa: BLE001
            self.finished_ok.emit(False, tr("Failed to save information to server: {exc}").format(exc=exc))
            return

        self._save_avatar()
        self._save_local_embeddings()
        self.finished_ok.emit(True, tr("Employee information saved successfully."))

    def _save_avatar(self) -> None:
        """Ảnh đại diện cục bộ - chỉ để quản trị viên xem lại, KHÔNG dùng để
        nhận diện (nhận diện dùng identifier_code đã gửi lên backend). Lỗi ở
        đây không nên chặn kết quả đăng ký chính."""
        if self._avatar_frame is None or self._avatar_bbox is None:
            return
        try:
            code = self._employee_data.get("code") or "unknown"
            folder = os.path.join(account_dir(), "faces", str(code))
            os.makedirs(folder, exist_ok=True)

            x1, y1, x2, y2 = self._avatar_bbox
            h, w = self._avatar_frame.shape[:2]
            pad = int(0.4 * max(x2 - x1, y2 - y1))
            x1, y1 = max(0, x1 - pad), max(0, y1 - pad)
            x2, y2 = min(w, x2 + pad), min(h, y2 + pad)
            crop = self._avatar_frame[y1:y2, x1:x2]
            if crop.size:
                cv2.imwrite(os.path.join(folder, "avatar.png"), crop)
        except Exception as exc:  # noqa: BLE001
            print(f"[FaceApp] Không lưu được avatar: {exc}")

    def _save_local_embeddings(self) -> None:
        """Lưu CỤC BỘ (trên máy đang chạy app này, KHÔNG gửi backend - giữ
        identifier_code gửi lên backend đúng như cũ, tương thích MIRAI) 1
        vector trung bình RIÊNG cho từng góc mặt (thẳng/trái/phải) đã chụp ở
        FaceCaptureWizardDialog - core/known_faces_store.py đọc thêm các
        vector này để so khớp đa góc (thay vì chỉ 1 vector trung bình 3 góc
        như identifier_code) - xem known_faces_store.py:_load_local_embeddings.
        Lỗi ở đây không nên chặn kết quả đăng ký chính (giống _save_avatar)."""
        if not self._pose_samples:
            return
        try:
            code = self._employee_data.get("code") or "unknown"
            folder = os.path.join(account_dir(), "faces", str(code))
            os.makedirs(folder, exist_ok=True)
            pose_vectors = {
                pose: np.mean(samples, axis=0).tolist()
                for pose, samples in self._pose_samples.items()
                if samples
            }
            with open(os.path.join(folder, "embeddings.json"), "w", encoding="utf-8") as f:
                json.dump(pose_vectors, f)
        except Exception as exc:  # noqa: BLE001
            print(f"[FaceApp] Không lưu được embeddings cục bộ: {exc}")


_MAIN_HINT_DEFAULT = "Stand facing the camera, keep your face within the frame"
_MAIN_MIN_FACE_RATIO = 0.12  # bbox mặt < 12% bề rộng khung hình -> gợi ý lại gần hơn


class FaceAttendanceWindow(QtWidgets.QMainWindow):
    """Cửa sổ THƯỜNG (title bar/minimize/maximize/close chuẩn hệ điều hành,
    có trong taskbar) - KHÔNG fullscreen/frameless, để người dùng vẫn chuyển
    qua lại được MenuWindow (Alt+Tab, taskbar, hoặc chỉ cần kéo/thu nhỏ cửa
    sổ này) trong lúc Face App đang mở. UI dựng thẳng bằng code (không qua
    .ui) vì cần widget vẽ tay (FaceScanView) - cùng tinh thần với các QDialog
    khác trong ui/dialogs/ (vd add_device_dialog.py)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Face App - Attendance"))

        self._current_state: Optional[dict] = None
        self._enroll_worker: Optional[EnrollWorker] = None
        self._device: Optional[CameraDevice] = None
        self._worker: Optional[FaceCaptureWorker] = None

        self._build_ui()
        self._center_on_screen(1300, 1080)

        if not self._start_from_saved_config():
            self._open_setup()

        self.btn_action.clicked.connect(self._on_action_clicked)

        LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    # ── i18n ─────────────────────────────────────────────────────────────
    def retranslate_ui(self, _lang: str = "") -> None:
        self.setWindowTitle(tr("Face App - Attendance"))
        self.lbl_title.setText(tr("🪪  FACE ATTENDANCE"))
        self.btn_change_camera.setText(tr("⚙  Change Camera"))
        # lbl_status/lbl_hint/btn_action phản ánh trạng thái NGAY LÚC NÀY
        # (đang tìm mặt/đã khoá 1 người...) - vẽ lại theo state hiện có thay
        # vì set cứng 1 câu, tránh đè mất thông tin đang hiển thị đúng.
        self._on_face_state(self._current_state)

    # ── Chọn camera ──────────────────────────────────────────────────────
    def _start_from_saved_config(self) -> bool:
        device_id = load_gate_config("faceapp")
        if device_id is None:
            return False
        device = DeviceManager.instance().get_device(device_id)
        if device is None:
            return False
        self._start_worker(device)
        return True

    def _open_setup(self) -> None:
        had_device = self._device
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
            self._worker = None

        # require_running=False/require_counting_line=False: Face App tự mở
        # cv2.VideoCapture riêng (không mượn frame từ CameraPipeline như Gate
        # kiosk), chỉ cần camera đã ĐĂNG KÝ, không cần Start sẵn/vẽ vạch.
        dialog = GateSetupDialog(
            tr("Select camera for Face App"), parent=self,
            require_running=False, require_counting_line=False,
        )
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            if had_device is not None:
                self._start_worker(had_device)
            else:
                self.close()
            return

        device = dialog.get_device()
        save_gate_config("faceapp", device.id)
        self._start_worker(device)

    def _start_worker(self, device: CameraDevice) -> None:
        """Tạo + start 1 FaceCaptureWorker MỚI - gọi lúc khởi tạo cửa sổ LẪN
        lúc mở lại (showEvent) sau khi đã Close 1 lần. MenuWindow giữ
        FaceAttendanceWindow như singleton (chỉ tạo 1 lần, lần mở sau chỉ
        show() lại - xem menu_window.py::_on_open_attendance), trong khi
        closeEvent() bên dưới stop() hẳn worker cũ (nhả webcam) - không tạo
        worker mới ở đây thì mở lại cửa sổ sẽ thấy hình đứng im/đen vĩnh
        viễn vì webcam không bao giờ được mở lại (bug đã gặp)."""
        self._device = device
        source = device.pipeline_source()
        source = int(source) if source.isdigit() else source

        self._worker = FaceCaptureWorker(
            source=source, web_camera_id=device.web_camera_id,
            device_id=device.id, device_name=device.name,
        )
        self._worker.frame_ready.connect(self._on_frame)
        self._worker.face_state_changed.connect(self._on_face_state)
        self._worker.camera_error.connect(self._on_camera_error)
        self._worker.start()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._worker is not None and not self._worker.isRunning():
            self._start_worker(self._device)

    def _center_on_screen(self, width: int, height: int) -> None:
        screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            self.resize(width, height)
            return
        geo = screen.availableGeometry()
        # Kẹp theo màn hình thật (trừ biên) - tránh cửa sổ to hơn màn hình
        # (laptop 1366×768...) bị tràn ra ngoài/mất nút phía dưới.
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
        central.setObjectName("centralWidget")  # nền tối sẵn có từ ui/themes/theme_dark.qss
        self.setCentralWidget(central)

        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 40)
        root.setSpacing(14)

        self.lbl_title = QtWidgets.QLabel(tr("🪪  FACE ATTENDANCE"))
        self.lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_title.setStyleSheet("color: #3a5070; font-size: 13px; font-weight: 700; letter-spacing: 3px;")
        root.addWidget(self.lbl_title)

        root.addStretch(1)

        self.scan_view = FaceScanView()
        scan_row = QtWidgets.QHBoxLayout()
        scan_row.addStretch(1)
        scan_row.addWidget(self.scan_view)
        scan_row.addStretch(1)
        root.addLayout(scan_row)

        self.lbl_status = QtWidgets.QLabel(tr("Searching for face..."))
        self.lbl_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_status.setStyleSheet("color: #e0e6f0; font-size: 26px; font-weight: 700;")
        root.addWidget(self.lbl_status)

        self.lbl_hint = QtWidgets.QLabel(tr(_MAIN_HINT_DEFAULT))
        self.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hint.setStyleSheet("color: #7a8aaa; font-size: 13px;")
        root.addWidget(self.lbl_hint)

        root.addStretch(1)

        self.btn_action = QtWidgets.QPushButton(tr("➕  Register"))
        self.btn_action.setMinimumSize(260, 52)
        self.btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_action.setStyleSheet(
            "QPushButton { background-color: #0e2040; color: #00d4ff; border: 1px solid #00d4ff;"
            " border-radius: 26px; font-size: 16px; font-weight: 700; }"
            "QPushButton:hover { background-color: #00d4ff; color: #06141f; }"
            "QPushButton:disabled { background-color: #151c2a; color: #3a5070; border-color: #1a2030; }"
        )
        self.btn_action.setVisible(False)
        action_row = QtWidgets.QHBoxLayout()
        action_row.addStretch(1)
        action_row.addWidget(self.btn_action)
        action_row.addStretch(1)
        root.addLayout(action_row)

        self.btn_change_camera = QtWidgets.QPushButton(tr("⚙  Change Camera"))
        self.btn_change_camera.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_change_camera.clicked.connect(self._open_setup)
        change_camera_row = QtWidgets.QHBoxLayout()
        change_camera_row.addStretch(1)
        change_camera_row.addWidget(self.btn_change_camera)
        root.addLayout(change_camera_row)

    # ── Live feed ────────────────────────────────────────────────────────
    def _on_frame(self, image: QImage) -> None:
        self.scan_view.set_frame(image)

    def _on_camera_error(self, message: str) -> None:
        self.lbl_status.setText(tr("⚠ {message}").format(message=message))
        self.lbl_hint.setText("")
        self.btn_action.setVisible(False)

    def _on_face_state(self, state: Optional[dict]) -> None:
        self._current_state = state
        if state is None:
            self.lbl_status.setText(tr("Searching for face..."))
            self.lbl_hint.setText(tr(_MAIN_HINT_DEFAULT))
            self.btn_action.setVisible(False)
            self.scan_view.set_state(RingState.SEARCHING)
            return

        employee = state.get("employee")
        stable = bool(state.get("stable"))
        face_ratio = state.get("face_ratio", 1.0)
        self.lbl_hint.setText(
            tr("Move a bit closer to the camera") if face_ratio < _MAIN_MIN_FACE_RATIO else tr(_MAIN_HINT_DEFAULT)
        )

        if employee is not None:
            name = f"{employee.get('last_name') or ''} {employee.get('first_name') or ''}".strip()
            self.lbl_status.setText(tr("Hello, {name}").format(name=name or '?'))
            self.btn_action.setText(tr("✎  Edit Info"))
            self.scan_view.set_state(RingState.LOCKED_KNOWN if stable else RingState.SEARCHING)
        else:
            self.lbl_status.setText(tr("Not recognized - new person"))
            self.btn_action.setText(tr("➕  Register"))
            self.scan_view.set_state(RingState.LOCKED_NEW if stable else RingState.SEARCHING)
        self.btn_action.setVisible(stable)

    # ── Đăng ký / Sửa thông tin ──────────────────────────────────────────
    def _on_action_clicked(self) -> None:
        employee = self._current_state.get("employee") if self._current_state else None

        # Tạm ngưng auto điểm danh trong lúc form/wizard đang mở CHO CHÍNH
        # người này - bật lại ở mọi lối thoát (Cancel/Huỷ/xong) bên dưới.
        self._worker.set_attendance_enabled(False)

        form = EmployeeFormDialog(employee=employee, parent=self)
        if form.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            self._worker.set_attendance_enabled(True)
            return

        employee_data = form.get_data()
        if employee:
            employee_data["id"] = employee.get("id")

        wizard = FaceCaptureWizardDialog(self._worker, parent=self)
        if wizard.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            self._worker.set_attendance_enabled(True)
            return

        self._start_enroll(
            employee_data, wizard.embeddings, wizard.pose_samples, wizard.avatar_frame, wizard.avatar_bbox
        )

    def _start_enroll(
        self, employee_data: dict, embeddings: list, pose_samples: dict, avatar_frame, avatar_bbox
    ) -> None:
        self.btn_action.setEnabled(False)
        self.lbl_status.setText(tr("⏳ Saving information..."))
        self._enroll_worker = EnrollWorker(employee_data, embeddings, pose_samples, avatar_frame, avatar_bbox, parent=self)
        self._enroll_worker.finished_ok.connect(self._on_enroll_finished)
        self._enroll_worker.start()

    def _on_enroll_finished(self, success: bool, message: str) -> None:
        self.btn_action.setEnabled(True)
        self._worker.set_attendance_enabled(True)
        if success:
            KnownFacesStore.instance().refresh_async()
            QtWidgets.QMessageBox.information(self, tr("Success"), message)
        else:
            QtWidgets.QMessageBox.warning(self, tr("Error"), message)

    # ── Shutdown ─────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        if self._worker is not None:
            self._worker.stop()
            self._worker.wait(2000)
        super().closeEvent(event)
