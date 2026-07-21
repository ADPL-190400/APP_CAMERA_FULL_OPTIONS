"""FaceScanView: widget vẽ video dạng hình tròn + 1 vòng ring động bao
quanh - "kiosk chrome" dùng CHUNG cho màn hình chính (FaceAttendanceWindow)
và wizard đăng ký (FaceCaptureWizardDialog), vẽ bằng QPainter giống cách
ui/dialogs/roi_editor_dialog.py vẽ ROI lên khung hình camera.

KHÔNG vẽ bbox đè lên mặt (khác bản cv2 overlay trước đó) - phản hồi hoàn
toàn qua ring + text bên ngoài (QLabel), giống Face ID thật: vẽ bbox trông
như debug/giám sát chứ không phải trải nghiệm đăng ký. Toàn bộ chữ vẫn nằm
trong QLabel nên tiếng Việt có dấu hiện đúng (khác cv2.putText)."""
from __future__ import annotations

from enum import Enum, auto
from typing import Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap


class RingState(Enum):
    SEARCHING = auto()     # chưa thấy mặt / chưa đủ streak ổn định - ring quét vòng quanh
    LOCKED_KNOWN = auto()   # đã nhận diện, người quen - ring xanh lá đứng yên
    LOCKED_NEW = auto()     # đã nhận diện, người lạ/mới - ring cam đứng yên
    PROGRESS = auto()       # đang giữ đúng tư thế trong wizard - ring cyan lấp đầy dần
    SUCCESS = auto()        # flash xanh khi hoàn tất 1 bước/cả wizard


_COLOR_DIM = QColor("#2a3550")
_COLOR_SEARCH = QColor("#00d4ff")
_COLOR_KNOWN = QColor("#00e676")
_COLOR_NEW = QColor("#ffaa00")
_COLOR_SUCCESS = QColor("#00e676")
_RING_WIDTH = 8
_SWEEP_SPAN_DEG = 70
_SWEEP_STEP_DEG = 4.0
_SWEEP_INTERVAL_MS = 30


class FaceScanView(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(680, 680)
        self._pixmap: Optional[QPixmap] = None
        self._state = RingState.SEARCHING
        self._progress = 0.0  # 0..1, chỉ dùng khi _state == PROGRESS

        self._sweep_angle = 0.0
        self._sweep_timer = QTimer(self)
        self._sweep_timer.timeout.connect(self._on_sweep_tick)
        self._sweep_timer.start(_SWEEP_INTERVAL_MS)

    def set_frame(self, image: QImage) -> None:
        self._pixmap = QPixmap.fromImage(image)
        self.update()

    def set_state(self, state: RingState, progress: float = 0.0) -> None:
        self._state = state
        self._progress = max(0.0, min(1.0, progress))
        self.update()

    def stop(self) -> None:
        self._sweep_timer.stop()

    # ------------------------------------------------------------------ #
    def _on_sweep_tick(self) -> None:
        self._sweep_angle = (self._sweep_angle + _SWEEP_STEP_DEG) % 360.0
        if self._state == RingState.SEARCHING:
            self.update()

    def _circle_rect(self) -> QRectF:
        side = min(self.width(), self.height()) - _RING_WIDTH * 2 - 8
        side = max(10, side)
        x = (self.width() - side) / 2
        y = (self.height() - side) / 2
        return QRectF(x, y, side, side)

    def paintEvent(self, event) -> None:  # noqa: N802 - tên hàm bắt buộc bởi Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self._circle_rect()

        clip_path = QPainterPath()
        clip_path.addEllipse(rect)
        painter.save()
        painter.setClipPath(clip_path)
        if self._pixmap is not None and not self._pixmap.isNull():
            painter.drawPixmap(rect.toRect(), self._cover_fit(self._pixmap, rect.size().toSize()))
        else:
            painter.fillRect(rect, QColor("#06080c"))
        painter.restore()

        self._draw_ring(painter, rect)
        painter.end()

    def _draw_ring(self, painter: QPainter, rect: QRectF) -> None:
        ring_rect = rect.adjusted(-_RING_WIDTH, -_RING_WIDTH, _RING_WIDTH, _RING_WIDTH)

        base_pen = QPen(_COLOR_DIM)
        base_pen.setWidth(_RING_WIDTH)
        base_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(base_pen)
        painter.drawEllipse(ring_rect)

        if self._state == RingState.SEARCHING:
            pen = QPen(_COLOR_SEARCH)
            pen.setWidth(_RING_WIDTH)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            painter.setPen(pen)
            # Qt: 0° = 3 giờ, dương = ngược chiều kim đồng hồ - trừ góc quét
            # để cung xoay THEO chiều kim đồng hồ (cảm giác "đang quét").
            start_angle = int((90 - self._sweep_angle) * 16)
            painter.drawArc(ring_rect, start_angle, int(-_SWEEP_SPAN_DEG * 16))
            return

        color = {
            RingState.LOCKED_KNOWN: _COLOR_KNOWN,
            RingState.LOCKED_NEW: _COLOR_NEW,
            RingState.SUCCESS: _COLOR_SUCCESS,
        }.get(self._state, _COLOR_SEARCH)

        pen = QPen(color)
        pen.setWidth(_RING_WIDTH)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        if self._state == RingState.PROGRESS:
            # Bắt đầu từ 12 giờ (90°), lấp đầy THEO chiều kim đồng hồ (span âm)
            # theo % tiến độ - quy ước loader tròn phổ biến nhất.
            span_deg = int(360 * self._progress)
            painter.drawArc(ring_rect, 90 * 16, int(-span_deg * 16))
        else:
            painter.drawEllipse(ring_rect)

    @staticmethod
    def _cover_fit(pixmap: QPixmap, target_size: QSize) -> QPixmap:
        """Scale + center-crop để pixmap LẤP ĐẦY target_size (giống CSS
        object-fit: cover) - frame webcam thường không vuông trong khi vùng
        hiển thị là hình tròn/vuông, scale theo cạnh nhỏ hơn rồi crop phần dư
        để không bị méo hình."""
        scaled = pixmap.scaled(
            target_size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - target_size.width()) // 2)
        y = max(0, (scaled.height() - target_size.height()) // 2)
        return scaled.copy(x, y, target_size.width(), target_size.height())
