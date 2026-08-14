"""Wizard đăng ký khuôn mặt - 3 tư thế (nhìn thẳng / xoay trái / xoay phải),
TỰ ĐỘNG chụp kiểu Face ID: giữ đúng tư thế đủ lâu là tự chụp, không cần bấm
nút. Chỉ giữ 1 nút "Chụp thủ công" nhỏ làm lối thoát khi ước lượng góc mặt
không ăn (ánh sáng yếu, đeo kính...).

Dùng lại NGUYÊN state đã tính sẵn mỗi tick từ FaceCaptureWorker.face_state_changed
(bbox/embedding/yaw/face_ratio - xem pages/face_attendance_page.py) thay vì
tự gọi detect_faces() riêng - vừa đỡ tốn 1 lượt inference, vừa đảm bảo
embedding lưu lại đúng KHỚP với tick đã qua kiểm tra tư thế."""
from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QImage

from ui.dialogs.face_scan_view import FaceScanView, RingState
from ui.ui_menu.i18n import tr

# Ngưỡng |yaw| coi là "nhìn thẳng" / "đã quay đủ" 1 chiều - yaw ước lượng từ
# 5 điểm kps trong FaceCaptureWorker._estimate_yaw (~0 = thẳng). CHIỀU dấu
# ứng với trái/phải và các ngưỡng này CẦN hiệu chỉnh lại khi test với camera
# thật (xem ghi chú trong plan) - đổi số ở đây là đủ, không cần sửa logic.
_YAW_STRAIGHT_MAX = 0.12
_YAW_TURN_MIN = 0.28

# Số tick liên tiếp giữ ĐÚNG tư thế trước khi tự động chụp - worker tick với
# nhịp _DETECT_INTERVAL_SEC (~5 tick/giây) nên 5 tick ~ giữ yên 1 giây.
_HOLD_TICKS_REQUIRED = 5

# Băng "khoảng cách hợp lý" tới camera (face bbox width / frame width) - quá
# nhỏ (xa) hoặc quá lớn (sát cam) đều không tích luỹ tiến độ, chỉ hiện gợi ý.
_FACE_RATIO_MIN = 0.12
_FACE_RATIO_MAX = 0.55

_FLASH_MS = 500  # thời gian giữ ring xanh SUCCESS trước khi chuyển bước/kết thúc

# Số mẫu chụp liên tiếp mỗi bước (thay vì 1 mẫu/bước như trước) - lấy trung
# bình NHIỀU mẫu CÙNG 1 góc mặt giảm nhiễu do 1 frame chụp trúng lúc mờ/chớp
# mắt, KHÔNG trộn giữa các góc khác nhau (đó là core/known_faces_store.py
# xử lý riêng - xem EnrollWorker._save_local_embeddings). ~3 mẫu/bước x 3
# bước ~ 9-10 mẫu/người.
_SAMPLES_PER_STEP = 3

_STEPS = [
    ("straight", "Look straight at the camera", lambda yaw: abs(yaw) < _YAW_STRAIGHT_MAX),
    ("left", "Turn your head LEFT", lambda yaw: yaw > _YAW_TURN_MIN),
    ("right", "Turn your head RIGHT", lambda yaw: yaw < -_YAW_TURN_MIN),
]


class FaceCaptureWizardDialog(QtWidgets.QDialog):
    def __init__(self, worker, parent=None):
        super().__init__(parent)
        self._worker = worker
        self._step_index = 0
        self._hold_ticks = 0
        self._capturing = False  # True trong khoảng flash xanh giữa 2 bước - _on_state bỏ qua tick
        self._latest_state: Optional[dict] = None

        self.embeddings: list = []  # TẤT CẢ mẫu đã chụp (mọi bước) - dùng tính avg gửi backend (EnrollWorker), giữ đúng hành vi cũ
        # mẫu đã chụp CỦA BƯỚC ĐANG LÀM - gộp vào self.embeddings +
        # self.pose_samples[key] khi đủ _SAMPLES_PER_STEP (xem _collect_sample).
        self._step_samples: list = []
        # key bước ("straight"/"left"/"right") -> list mẫu riêng của bước đó -
        # dùng lưu cục bộ nhiều vector theo góc (EnrollWorker._save_local_embeddings),
        # KHÔNG trộn giữa các góc như self.embeddings (xem module docstring).
        self.pose_samples: dict[str, list] = {}
        # Frame + bbox của bước "straight" - dùng làm avatar (EnrollWorker),
        # không ảnh hưởng embedding (embedding tính từ cả 3 bước).
        self.avatar_frame = None
        self.avatar_bbox: Optional[tuple[int, int, int, int]] = None

        self.setWindowTitle(tr("Face Registration"))
        self.setMinimumSize(760, 960)
        self.setStyleSheet("QDialog { background-color: #0d0f14; }")
        self._build_ui()

        self._worker.frame_ready.connect(self._on_frame)
        self._worker.face_state_changed.connect(self._on_state)
        self._update_step_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setSpacing(12)

        self.lbl_instruction = QtWidgets.QLabel()
        self.lbl_instruction.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_instruction.setStyleSheet("color: #e0e6f0; font-size: 18px; font-weight: 700;")
        layout.addWidget(self.lbl_instruction)

        self.scan_view = FaceScanView()
        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.scan_view)
        row.addStretch(1)
        layout.addLayout(row)

        self.lbl_hint = QtWidgets.QLabel()
        self.lbl_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_hint.setStyleSheet("color: #8899bb; font-size: 13px;")
        layout.addWidget(self.lbl_hint)

        self.lbl_dots = QtWidgets.QLabel()
        self.lbl_dots.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_dots.setStyleSheet("color: #3a5070; font-size: 14px; letter-spacing: 6px;")
        layout.addWidget(self.lbl_dots)

        btn_row = QtWidgets.QHBoxLayout()
        btn_row.addStretch(1)

        def _secondary_style(hover: str) -> str:
            return (
                "QPushButton { background-color: transparent; color: #7a8aaa; border: 1px solid #1a2030;"
                " border-radius: 16px; padding: 6px 16px; font-size: 12px; }"
                f"QPushButton:hover {{ color: {hover}; border-color: {hover}; }}"
            )

        self.btn_manual = QtWidgets.QPushButton(tr("📸  Manual Capture"))
        self.btn_manual.setStyleSheet(_secondary_style("#00d4ff"))
        self.btn_manual.clicked.connect(self._on_manual_capture)
        btn_row.addWidget(self.btn_manual)

        self.btn_cancel = QtWidgets.QPushButton(tr("Cancel"))
        self.btn_cancel.setStyleSheet(_secondary_style("#ff4444"))
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

    def _update_step_ui(self) -> None:
        self._hold_ticks = 0
        self._step_samples = []
        _key, text, _check = _STEPS[self._step_index]
        self.lbl_instruction.setText(
            tr("Step {n}/{total}: {text}").format(n=self._step_index + 1, total=len(_STEPS), text=tr(text))
        )
        self.lbl_hint.setText(tr("Position your face in the frame"))
        self.lbl_dots.setText(" ".join(
            "●" if i < self._step_index else "○" for i in range(len(_STEPS))
        ))
        self.scan_view.set_state(RingState.PROGRESS, 0.0)

    # ------------------------------------------------------------------ #
    def _on_frame(self, image: QImage) -> None:
        self.scan_view.set_frame(image)

    def _on_state(self, state: Optional[dict]) -> None:
        self._latest_state = state
        if self._capturing:
            return  # đang flash xanh chuyển bước - bỏ qua tick, tránh đè lên hiệu ứng

        if state is None:
            self._hold_ticks = 0
            self.lbl_hint.setText(tr("Position your face in the frame"))
            self.scan_view.set_state(RingState.PROGRESS, 0.0)
            return

        face_ratio = state.get("face_ratio", 0.0)
        if face_ratio < _FACE_RATIO_MIN:
            self._hold_ticks = 0
            self.lbl_hint.setText(tr("Move closer to the camera"))
            self.scan_view.set_state(RingState.PROGRESS, 0.0)
            return
        if face_ratio > _FACE_RATIO_MAX:
            self._hold_ticks = 0
            self.lbl_hint.setText(tr("Step back a little"))
            self.scan_view.set_state(RingState.PROGRESS, 0.0)
            return

        _key, _text, pose_ok = _STEPS[self._step_index]
        if pose_ok(state.get("yaw", 0.0)):
            self._hold_ticks += 1
            self.lbl_hint.setText(
                tr("Hold still... ({n}/{total})").format(n=len(self._step_samples), total=_SAMPLES_PER_STEP)
                if self._step_samples else tr("Hold still...")
            )
        else:
            # KHÔNG xoá self._step_samples đã tích luỹ được ở đây - lỡ giữ
            # đúng tư thế 1-2 mẫu rồi lệch thoáng qua (vd chớp mắt/quay đầu
            # nhẹ) không nên mất tiến độ, chỉ cần giữ lại đủ tư thế lần nữa
            # là tiếp tục chụp cho đủ _SAMPLES_PER_STEP (xem _collect_sample).
            self._hold_ticks = 0
            self.lbl_hint.setText(tr("Adjust your pose according to the instructions above"))

        self.scan_view.set_state(RingState.PROGRESS, min(1.0, self._hold_ticks / _HOLD_TICKS_REQUIRED))

        if self._hold_ticks >= _HOLD_TICKS_REQUIRED:
            self._collect_sample(state)

    def _on_manual_capture(self) -> None:
        if self._capturing:
            return
        if self._latest_state is None:
            self.lbl_hint.setText(tr("No face detected, try again."))
            return
        # Lối thoát thủ công (ánh sáng yếu/đeo kính làm ước lượng góc không
        # ăn) - chụp ĐÚNG 1 mẫu rồi qua bước tiếp theo luôn, không bắt đủ
        # _SAMPLES_PER_STEP như luồng tự động (người dùng đã phải tự bấm vì
        # luồng tự động không nhận ra tư thế, không nên bắt bấm nhiều lần).
        self._collect_sample(self._latest_state, required=1)

    def _collect_sample(self, state: dict, required: int = _SAMPLES_PER_STEP) -> None:
        frame = self._worker.latest_frame
        if frame is None:
            return

        key, _text, _check = _STEPS[self._step_index]
        self._step_samples.append(state["embedding"])
        if key == "straight" and self.avatar_frame is None:
            self.avatar_frame = frame.copy()
            self.avatar_bbox = state["bbox"]

        if len(self._step_samples) < required:
            return  # còn thiếu mẫu cho bước này - tiếp tục ở tick sau (xem _on_state)

        self.embeddings.extend(self._step_samples)
        self.pose_samples[key] = list(self._step_samples)
        self._step_samples = []

        self._capturing = True
        self.scan_view.set_state(RingState.SUCCESS, 1.0)
        self._step_index += 1
        if self._step_index >= len(_STEPS):
            QTimer.singleShot(_FLASH_MS, self._finish)
        else:
            QTimer.singleShot(_FLASH_MS, self._advance_step)

    def _advance_step(self) -> None:
        self._capturing = False
        self._update_step_ui()

    def _finish(self) -> None:
        self._capturing = False
        self._disconnect_worker()
        self.accept()

    def _disconnect_worker(self) -> None:
        for signal, slot in (
            (self._worker.frame_ready, self._on_frame),
            (self._worker.face_state_changed, self._on_state),
        ):
            try:
                signal.disconnect(slot)
            except TypeError:
                pass  # đã disconnect rồi (vd Huỷ ngay sau khi vừa accept) - bỏ qua

    def reject(self) -> None:
        self._disconnect_worker()
        super().reject()
