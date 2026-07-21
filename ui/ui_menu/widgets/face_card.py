"""FaceCard: 1 thẻ ảnh trong gallery của GateWindow (pages/gate_kiosk_page.py)
- ảnh crop mặt + tên + giờ chấm công + badge trạng thái (khớp/người lạ).
Snapshot tĩnh (dựng 1 lần lúc có sự kiện băng qua vạch, không bind/update
lại sau đó) nên đơn giản hơn CameraCard (không cần model reactive) - nhưng
theo đúng tinh thần cùng file: dynamic property + QSS thay vì setStyleSheet
màu sắc hardcode (xem ui/ui_menu/widgets/camera_card.py, ui/themes/theme_dark.qss
khối QFrame[cameraCard="true"])."""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QFrame, QLabel, QVBoxLayout, QSizePolicy

_THUMB_SIZE = 150


class FaceCard(QFrame):
    def __init__(self, name: str, time_text: str, pixmap: QPixmap | None, matched: bool, parent=None):
        super().__init__(parent)
        self.setProperty("faceCard", True)  # QSS: QFrame[faceCard="true"]
        self.setProperty("matched", matched)
        self.setFixedSize(174, 230)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self._lbl_thumb = QLabel()
        self._lbl_thumb.setProperty("cardRole", "faceThumb")
        self._lbl_thumb.setFixedSize(_THUMB_SIZE, _THUMB_SIZE)
        self._lbl_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if pixmap is not None and not pixmap.isNull():
            self._lbl_thumb.setPixmap(
                pixmap.scaled(
                    _THUMB_SIZE, _THUMB_SIZE,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            self._lbl_thumb.setText("?")

        self._lbl_name = QLabel(name)
        self._lbl_name.setProperty("cardRole", "faceName")
        self._lbl_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_name.setWordWrap(True)

        self._lbl_time = QLabel(time_text)
        self._lbl_time.setProperty("cardRole", "faceTime")
        self._lbl_time.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._lbl_badge = QLabel("✓ Khớp" if matched else "?  Người lạ")
        self._lbl_badge.setProperty("cardRole", "faceBadge")
        self._lbl_badge.setProperty("matched", matched)
        self._lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)

        outer.addWidget(self._lbl_thumb, alignment=Qt.AlignmentFlag.AlignHCenter)
        outer.addWidget(self._lbl_name)
        outer.addWidget(self._lbl_time)
        outer.addWidget(self._lbl_badge)
