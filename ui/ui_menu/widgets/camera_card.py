"""
ui/widgets/camera_card.py
=========================
CameraCard – widget hiển thị một camera trong lưới Live View.

THAY ĐỔI SO VỚI PHIÊN BẢN CŨ
──────────────────────────────
• Xóa hoàn toàn inline setStyleSheet() hardcode màu.
• Dùng Qt dynamic properties ("cameraCard", "cardRole", "offline",
  "online", "aiOn") để QSS selector trong theme_*.qss match.
• Gọi _refresh_properties() sau mỗi lần cập nhật model để
  Qt biết cần repaint theo theme hiện tại.

Quy tắc:
  - Chỉ setProperty() / setObjectName() ở đây.
  - Tất cả màu sắc → theme_dark.qss / theme_light.qss.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QFrame, QWidget, QLabel, QPushButton,
    QVBoxLayout, QHBoxLayout, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QMouseEvent

from ui.ui_menu.models.camera_model import CameraModel


def _repaint(widget: QWidget) -> None:
    """Force QSS re-evaluation after dynamic property change."""
    widget.style().unpolish(widget)
    widget.style().polish(widget)
    widget.update()


class CameraCard(QFrame):
    """
    Một camera card trong grid Live View.

    Signals:
        fullscreen_requested(cam_id: str)
        snapshot_requested(cam_id: str)
        card_double_clicked(cam_id: str)
    """

    fullscreen_requested = pyqtSignal(str)
    snapshot_requested   = pyqtSignal(str)
    card_double_clicked  = pyqtSignal(str)

    def __init__(self, model: CameraModel, compact: bool = False, parent=None):
        super().__init__(parent)
        self._model   = model
        self._compact = compact
        self._has_frame = False   # đã nhận ít nhất 1 frame thật qua set_frame() chưa

        self.setObjectName(f"card_camera_{model.cam_id}")
        self.setProperty("cameraCard", True)          # QSS: QFrame[cameraCard="true"]
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(140 if compact else 180, 100 if compact else 140)

        self._build_ui()
        self._apply_model()

        # Bind model → auto-refresh when data changes
        model.bind(lambda _: self._apply_model())

    # ── Build UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        c = self._compact
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ──────────────────────────────────────────────────────────
        self._header = QWidget()
        self._header.setObjectName(f"cam_header_{self._model.cam_id}")
        self._header.setProperty("cardRole", "header")
        self._header.setFixedHeight(26 if c else 32)

        hh = QHBoxLayout(self._header)
        hh.setContentsMargins(6, 0, 6, 0)
        hh.setSpacing(4)

        self._dot = QLabel("●")
        self._dot.setProperty("cardRole", "dot")

        self._lbl_name = QLabel()
        self._lbl_name.setObjectName(f"lbl_cam_name_{self._model.cam_id}")
        self._lbl_name.setProperty("cardRole", "camName")

        self._lbl_ip = QLabel(self._model.ip)
        self._lbl_ip.setObjectName(f"lbl_cam_ip_{self._model.cam_id}")
        self._lbl_ip.setProperty("cardRole", "camIp")

        self._lbl_alert = QLabel()
        self._lbl_alert.setObjectName(f"lbl_cam_alert_{self._model.cam_id}")
        self._lbl_alert.setProperty("cardRole", "alert")
        self._lbl_alert.setVisible(False)

        hh.addWidget(self._dot)
        hh.addWidget(self._lbl_name)
        hh.addWidget(self._lbl_alert)
        hh.addStretch()
        hh.addWidget(self._lbl_ip)

        # ── Feed ────────────────────────────────────────────────────────────
        self._feed = QLabel()
        self._feed.setObjectName(f"lbl_cam_feed_{self._model.cam_id}")
        self._feed.setProperty("cardRole", "feed")
        self._feed.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._feed.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        # ── Footer ──────────────────────────────────────────────────────────
        self._footer = QWidget()
        self._footer.setObjectName(f"cam_footer_{self._model.cam_id}")
        self._footer.setProperty("cardRole", "footer")
        self._footer.setFixedHeight(24 if c else 32)

        fh = QHBoxLayout(self._footer)
        fh.setContentsMargins(6, 2, 6, 2)
        fh.setSpacing(4)

        self._lbl_fps = QLabel()
        self._lbl_fps.setObjectName(f"lbl_cam_fps_{self._model.cam_id}")
        self._lbl_fps.setProperty("cardRole", "fps")

        self._lbl_ai = QLabel()
        self._lbl_ai.setObjectName(f"lbl_cam_ai_{self._model.cam_id}")
        self._lbl_ai.setProperty("cardRole", "ai")

        self._lbl_people = QLabel()
        self._lbl_people.setObjectName(f"lbl_cam_people_{self._model.cam_id}")
        self._lbl_people.setProperty("cardRole", "people")
        self._lbl_people.setVisible(False)

        self._lbl_rec = QLabel("● REC")
        self._lbl_rec.setObjectName(f"lbl_cam_rec_{self._model.cam_id}")
        self._lbl_rec.setProperty("cardRole", "rec")

        self._btn_snap = QPushButton("📷")
        self._btn_snap.setObjectName(f"btn_cam_snapshot_{self._model.cam_id}")
        self._btn_snap.setProperty("cardRole", "snapBtn")
        self._btn_snap.setFixedSize(20, 20)
        self._btn_snap.clicked.connect(
            lambda: self.snapshot_requested.emit(self._model.cam_id)
        )

        self._btn_full = QPushButton("⛶")
        self._btn_full.setObjectName(f"btn_cam_fullscreen_{self._model.cam_id}")
        self._btn_full.setProperty("cardRole", "fullBtn")
        self._btn_full.setFixedSize(20, 20)
        self._btn_full.setToolTip("Phóng to")
        self._btn_full.clicked.connect(
            lambda: self.fullscreen_requested.emit(self._model.cam_id)
        )

        fh.addWidget(self._lbl_fps)
        fh.addWidget(self._lbl_ai)
        fh.addWidget(self._lbl_people)
        fh.addWidget(self._lbl_rec)
        fh.addStretch()
        fh.addWidget(self._btn_snap)
        fh.addWidget(self._btn_full)

        outer.addWidget(self._header)
        outer.addWidget(self._feed)
        outer.addWidget(self._footer)

    # ── Apply model → properties + text ──────────────────────────────────────

    def _apply_model(self) -> None:
        m = self._model
        online = m.online
        c = self._compact
        fs = "9px" if c else "11px"

        # ── Card-level properties (chỉ repaint khi thật sự đổi giá trị -
        # _apply_model() giờ chạy nhiều lần/giây theo ai_result_ready, repaint
        # vô điều kiện mỗi lần sẽ gây giật/tốn CPU dù giá trị không đổi) ──────
        if self.property("offline") != (not online):
            self.setProperty("offline", not online)
            _repaint(self)

        if self._dot.property("online") != online:
            self._dot.setProperty("online", online)
            _repaint(self._dot)

        # ── Name / feed text ────────────────────────────────────────────────
        self._lbl_name.setText(f"CAM-{m.cam_id}  {m.name}")
        # font-size varies by compact → keep as inline for size only (no color)
        self._lbl_name.setStyleSheet(f"font-size:{fs};")

        # Feed: CHỈ ghi text placeholder khi CHƯA có frame thật đang hiển thị.
        # setText() sẽ xoá QPixmap hiện tại - nếu gọi mỗi lần _apply_model()
        # chạy (tức mỗi lần ai_result_ready bắn ra, ~10-15 lần/giây) thì sẽ
        # đua với set_frame() (bắn theo FPS camera) làm hình bị chớp tắt liên
        # tục. Cố tình CHỈ xét self._has_frame (không xét thêm "online") -
        # "online" là trạng thái ping mạng định kỳ (StatusCheckWorker, ~15s/
        # lần) hoàn toàn tách biệt với việc pipeline có đang thực sự gửi frame
        # hay không, nên không dùng nó để quyết định có xoá pixmap hay không.
        if not self._has_frame:
            self._feed.setText("◉" if online else "✕  OFFLINE")
            self._feed.setStyleSheet(f"font-size:{'18' if c else '26'}px;")
            self._feed.setProperty("offline", not online)
            _repaint(self._feed)
        if not online:
            self._has_frame = False  # offline -> lần sau có frame mới mới thôi hiện placeholder

        # ── FPS label ───────────────────────────────────────────────────────
        self._lbl_fps.setText(f"{m.fps} FPS" if online else "--")
        # padding is structural → keep inline; color via QSS
        self._lbl_fps.setStyleSheet("padding:1px 5px;")

        # ── AI label ────────────────────────────────────────────────────────
        self._lbl_ai.setText("AI ON" if m.ai_enabled else "AI OFF")
        if self._lbl_ai.property("aiOn") != m.ai_enabled:
            self._lbl_ai.setProperty("aiOn", m.ai_enabled)
            _repaint(self._lbl_ai)
        self._lbl_ai.setStyleSheet("padding:1px 5px; font-size:9px;")

        # ── REC badge ───────────────────────────────────────────────────────
        self._lbl_rec.setVisible(m.recording and online)
        self._lbl_rec.setStyleSheet("padding:1px 5px;")

        # ── People-count badge (chỉ hiện khi AI đang đếm) ────────────────────
        show_people = online and m.ai_enabled and (m.num_people or m.num_in or m.num_out)
        self._lbl_people.setVisible(bool(show_people))
        if show_people:
            self._lbl_people.setText(f"👤{m.num_people}  ↓{m.num_in} ↑{m.num_out}")
        self._lbl_people.setStyleSheet("padding:1px 5px;")

        # ── Alert badge (PPE / Fire / Fall) ─────────────────────────────────
        alerts = []
        if m.fire_alert:
            alerts.append("🔥 CHÁY")
        if m.fall_alert:
            alerts.append("🚨 TÉ NGÃ")
        if m.ppe_violation:
            alerts.append("⚠ PPE")
        if m.stranger_alert:
            alerts.append("🧑‍❓ NGƯỜI LẠ")
        self._lbl_alert.setVisible(online and bool(alerts))
        if alerts:
            self._lbl_alert.setText("  ".join(alerts))
        self._lbl_alert.setStyleSheet("padding:1px 5px;")
        _repaint(self._lbl_alert)

    # ── Events ───────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self.card_double_clicked.emit(self._model.cam_id)
        super().mouseDoubleClickEvent(event)

    # ── Public ───────────────────────────────────────────────────────────────

    def set_frame(self, pixmap) -> None:
        """Đặt QPixmap từ camera stream vào feed label."""
        self._has_frame = True
        self._feed.setPixmap(
            pixmap.scaled(
                self._feed.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def set_fullscreen(self, is_fullscreen: bool) -> None:
        """Đổi icon nút phóng to <-> thu nhỏ - gọi bởi LiveViewPage sau mỗi
        lần rebuild grid (xem _on_cameras_rebuilt), phản ánh đúng camera nào
        (nếu có) đang ở chế độ phóng to 1x1."""
        self._btn_full.setText("🗗" if is_fullscreen else "⛶")
        self._btn_full.setToolTip("Thu nhỏ" if is_fullscreen else "Phóng to")

    @property
    def model(self) -> CameraModel:
        return self._model
