"""
ui/controllers/grid_controller.py
==================================
GridController – quản lý toàn bộ logic grid switching cho Live Page.

Trách nhiệm:
  • Kết nối 3 nút btn_grid_* với switch_grid()
  • Rebuild CameraCard widgets trong cameraGridArea
  • Quản lý QButtonGroup để mutex nút active
  • Forward signals từ card ra ngoài (fullscreen, snapshot)

Không chứa bất kỳ business logic nào (stream, AI, recording).
"""

from __future__ import annotations
from enum import Enum
from typing import Callable, Dict, List, Optional

from PyQt6.QtWidgets import (
    QWidget, QPushButton, QButtonGroup, QGridLayout,
)
from PyQt6.QtCore import QObject, pyqtSignal, pyqtSlot

from ui.ui_menu.models.camera_model import CameraModel
from ui.ui_menu.widgets.camera_card import CameraCard


# ── Grid mode definition ──────────────────────────────────────────────────────

class GridMode(str, Enum):
    G1x1 = "1x1"   # 1 camera   → 1 cột × 1 hàng
    G2x3 = "2x3"   # 6 cameras  → 3 cột × 2 hàng
    G2x4 = "2x4"   # 8 cameras  → 4 cột × 2 hàng
    G4x4 = "4x4"   # 16 cameras → 4 cột × 4 hàng

    @property
    def cols(self) -> int:
        return {"1x1": 1, "2x3": 3, "2x4": 4, "4x4": 4}[self.value]

    @property
    def rows(self) -> int:
        return {"1x1": 1, "2x3": 2, "2x4": 2, "4x4": 4}[self.value]

    @property
    def count(self) -> int:
        return self.cols * self.rows

    @property
    def compact(self) -> bool:
        return self == GridMode.G4x4


# ── Controller ────────────────────────────────────────────────────────────────

class GridController(QObject):
    """
    Gắn vào live_page widget đã load từ .ui file.

    Sử dụng:
        cameras = [CameraModel(...) for ...]
        ctrl = GridController(live_page_widget, cameras)

        # Nhận signal từ card
        ctrl.fullscreen_requested.connect(self.open_fullscreen)
        ctrl.snapshot_requested.connect(self.save_snapshot)

        # Hoặc switch grid theo chương trình
        ctrl.switch_grid(GridMode.G4x4)
    """

    # Signals
    fullscreen_requested = pyqtSignal(str)   # cam_id
    snapshot_requested   = pyqtSignal(str)   # cam_id
    card_double_clicked  = pyqtSignal(str)   # cam_id
    grid_mode_changed    = pyqtSignal(str)   # GridMode.value
    cameras_rebuilt       = pyqtSignal()     # grid vừa build lại xong (đổi mode/danh sách camera)

    # Button active stylesheet
    _BTN_ACTIVE = (
        "background-color:#0e2040; color:#00d4ff; border:1px solid #00d4ff;"
        "border-radius:6px; padding:5px 12px; font-size:12px; font-weight:600;"
    )
    _BTN_NORMAL = (
        "background-color:#151c2a; color:#7a8aaa; border:1px solid #1a2030;"
        "border-radius:6px; padding:5px 12px; font-size:12px; font-weight:500;"
    )

    def __init__(
        self,
        live_page: QWidget,
        cameras: List[CameraModel],
        default_mode: GridMode = GridMode.G2x3,
        parent: Optional[QObject] = None,
    ):
        super().__init__(parent)

        self._page    = live_page
        self._cameras = cameras
        self._mode    = default_mode

        # Active cards: cam_id → CameraCard
        self._cards: Dict[str, CameraCard] = {}

        # Find required widgets from .ui
        self._grid_area = self._require(QWidget,      "cameraGridArea")
        self._btn_1x1   = self._require(QPushButton,  "btn_grid_1x1")
        self._btn_2x3   = self._require(QPushButton,  "btn_grid_2x3")
        self._btn_2x4   = self._require(QPushButton,  "btn_grid_2x4")
        self._btn_4x4   = self._require(QPushButton,  "btn_grid_4x4")

        # Replace whatever layout the .ui set on cameraGridArea
        self._grid_layout = QGridLayout()
        self._grid_layout.setSpacing(6)
        self._grid_layout.setContentsMargins(8, 8, 8, 8)

        old = self._grid_area.layout()
        if old:
            QWidget().setLayout(old)          # detach old layout safely
        self._grid_area.setLayout(self._grid_layout)

        # Button group: mutual exclusion (radio behaviour)
        self._btn_group = QButtonGroup(self)
        self._btn_group.setExclusive(True)
        self._btn_group.addButton(self._btn_2x3, 0)
        self._btn_group.addButton(self._btn_2x4, 1)
        self._btn_group.addButton(self._btn_4x4, 2)
        self._btn_group.addButton(self._btn_1x1, 3)
        self._btn_group.idClicked.connect(self._on_btn_group_clicked)

        # Apply initial grid
        self.switch_grid(default_mode)

    # ── Public API ─────────────────────────────────────────────────────────────

    @pyqtSlot()
    def switch_grid(self, mode: GridMode) -> None:
        """Switch to a new grid layout. Safe to call from any thread via Qt signal."""
        self._mode = mode
        self._update_btn_styles(mode)
        self._rebuild_grid(mode)
        self.grid_mode_changed.emit(mode.value)

    @property
    def current_mode(self) -> GridMode:
        return self._mode

    @property
    def active_cards(self) -> Dict[str, CameraCard]:
        return dict(self._cards)

    def add_camera(self, model: CameraModel) -> None:
        """Add a new camera model (e.g. after user connects a new camera)."""
        self._cameras.append(model)
        self._rebuild_grid(self._mode)

    def remove_camera(self, cam_id: str) -> None:
        self._cameras = [c for c in self._cameras if c.cam_id != cam_id]
        self._rebuild_grid(self._mode)

    def set_cameras(self, models: List[CameraModel]) -> None:
        """Thay toàn bộ danh sách camera hiển thị (ví dụ khi người dùng
        tick/bỏ tick camera nào hiện hình ở panel bên phải) rồi build lại
        grid ngay theo mode hiện tại."""
        self._cameras = list(models)
        self._rebuild_grid(self._mode)

    def set_cameras_and_mode(self, models: List[CameraModel], mode: GridMode) -> None:
        """Đổi CẢ danh sách camera hiển thị LẪN grid mode trong 1 lần rebuild
        duy nhất - dùng khi phóng to/thu nhỏ 1 camera (LiveViewPage): phóng to
        chỉ hiện đúng 1 camera ở mode 1x1, thu nhỏ khôi phục lại toàn bộ danh
        sách đang chọn + mode cũ. Gọi set_cameras() rồi switch_grid() riêng lẻ
        sẽ rebuild 2 lần liên tiếp (lãng phí, có thể gây chớp hình)."""
        self._cameras = list(models)
        self._mode = mode
        self._update_btn_styles(mode)
        self._rebuild_grid(mode)
        self.grid_mode_changed.emit(mode.value)

    # ── Private ────────────────────────────────────────────────────────────────

    def _require(self, widget_type, name: str):
        w = self._page.findChild(widget_type, name)
        if w is None:
            raise RuntimeError(
                f"GridController: '{name}' không tìm thấy trong live_page.\n"
                f"Hãy kiểm tra objectName trong live_page.ui."
            )
        return w

    def _on_btn_group_clicked(self, btn_id: int) -> None:
        mode_map = {0: GridMode.G2x3, 1: GridMode.G2x4, 2: GridMode.G4x4, 3: GridMode.G1x1}
        self.switch_grid(mode_map[btn_id])

    def _update_btn_styles(self, active: GridMode) -> None:
        for btn, mode in [
            (self._btn_1x1, GridMode.G1x1),
            (self._btn_2x3, GridMode.G2x3),
            (self._btn_2x4, GridMode.G2x4),
            (self._btn_4x4, GridMode.G4x4),
        ]:
            btn.setStyleSheet(
                self._BTN_ACTIVE if mode == active else self._BTN_NORMAL
            )

    def _rebuild_grid(self, mode: GridMode) -> None:
        layout = self._grid_layout

        # 1. Disconnect signals from old cards + gỡ model callback TRƯỚC khi
        # card bị deleteLater() (bước 2) - nếu không, camera nào rớt khỏi
        # danh sách hiển thị ở mode mới (vd chuyển sang 1x1 từ 1 mode có
        # nhiều ô) vẫn còn model.update() gọi vào callback trỏ tới card đã bị
        # huỷ -> "RuntimeError: wrapped C/C++ object ... has been deleted"
        # (model không tự biết card của nó đã bị xoá). Camera nào tiếp tục
        # hiển thị ở mode mới sẽ có card MỚI bind lại ngay bên dưới.
        for card in self._cards.values():
            card.fullscreen_requested.disconnect()
            card.snapshot_requested.disconnect()
            card.card_double_clicked.disconnect()
            card.model.unbind()

        # 2. Remove all widgets from layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._cards.clear()

        # 3. Reset stretch
        # Phải clear TẤT CẢ rows/cols cũ trước, không chỉ range của mode mới.
        # Nếu bỏ qua bước này, stretch của mode trước (vd 4x4 → 4 cols) vẫn còn
        # khiến layout không chia đều khi chuyển về mode ít cột hơn (vd 2x3).
        _MAX = 4  # số rows/cols tối đa có thể từng được set
        for r in range(_MAX):
            layout.setRowStretch(r, 0)
        for c in range(_MAX):
            layout.setColumnStretch(c, 0)
        for r in range(mode.rows):
            layout.setRowStretch(r, 1)
        for c in range(mode.cols):
            layout.setColumnStretch(c, 1)

        # 4. Create new cards
        visible_cams = self._cameras[:mode.count]
        for idx, model in enumerate(visible_cams):
            row, col = divmod(idx, mode.cols)
            card = CameraCard(model, compact=mode.compact)

            # Forward signals
            card.fullscreen_requested.connect(self.fullscreen_requested)
            card.snapshot_requested.connect(self.snapshot_requested)
            card.card_double_clicked.connect(self.card_double_clicked)

            layout.addWidget(card, row, col)
            self._cards[model.cam_id] = card

        self._grid_area.update()
        self.cameras_rebuilt.emit()