"""
ROIEditorDialog: vẽ trực tiếp ROI (vùng polygon dùng cho occupancy) và
Counting Line (2 điểm dùng đếm vào/ra) lên khung hình THẬT của camera, thay
cho việc gõ tay toạ độ "x1,y1;x2,y2;...".

Mở từ pages/camera_config_page.py khi bấm "Open ROI Editor" ở tab ROI.
Không hỗ trợ kéo-thả sửa từng đỉnh của 1 ROI/line đã có - muốn sửa thì xoá
rồi vẽ lại (đủ dùng cho mục tiêu "trực quan thay vì nhập toạ độ", không lấn
sang tính năng vertex-editing chưa được yêu cầu).
"""
from __future__ import annotations

import cv2
from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt, QPoint, QPointF, QRectF, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QKeyEvent, QMouseEvent, QPainter, QPen, QBrush, QPixmap, QPolygonF

from core.models.camera_device import CameraDevice, ROIRegion, parse_points
from ui.ui_menu.i18n import tr

_ROI_FILL = QColor(0, 200, 120, 60)
_ROI_OUTLINE = QColor(0, 200, 120, 220)
_ROI_OUTLINE_SELECTED = QColor(255, 210, 0, 230)
_LINE_COLOR = QColor(255, 255, 255, 230)
_LINE_IN_COLOR = QColor(0, 220, 0, 230)     # xanh lá - chiều tính "vào"
_LINE_OUT_COLOR = QColor(255, 60, 60, 230)  # đỏ - chiều tính "ra"
_DRAFT_COLOR = QColor(0, 170, 255, 230)
_POINT_RADIUS = 4


class ROICanvas(QtWidgets.QWidget):
    """Canvas vẽ ROI/Counting Line lên 1 QPixmap nền (frame camera thật)."""

    roi_added = pyqtSignal()
    line_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(640, 480)

        self._background: QPixmap | None = None
        self._draw_rect = QRectF()
        self._scale = 1.0

        self.rois: list[dict] = []  # [{"name": str, "points": [(x,y), ...]}]
        self.counting_line: list[tuple[int, int]] = []
        self.selected_roi_index: int | None = None

        self._mode: str | None = None  # None | "roi" | "line"
        self._draft_points: list[tuple[int, int]] = []
        self._hover_pos: tuple[int, int] | None = None

    # ------------------------------------------------------------------ #
    # Public API - điều khiển từ ROIEditorDialog
    # ------------------------------------------------------------------ #
    def set_background(self, pixmap: QPixmap) -> None:
        self._background = pixmap
        self.update()

    def start_new_roi(self) -> None:
        self._mode = "roi"
        self._draft_points = []
        self.update()

    def start_new_line(self) -> None:
        self._mode = "line"
        self._draft_points = []
        self.counting_line = []
        self.update()

    def cancel_draft(self) -> None:
        self._mode = None
        self._draft_points = []
        self.update()

    def delete_roi(self, index: int) -> None:
        if 0 <= index < len(self.rois):
            del self.rois[index]
            if self.selected_roi_index == index:
                self.selected_roi_index = None
            self.update()

    def delete_line(self) -> None:
        self.counting_line = []
        self.line_changed.emit()
        self.update()

    def flip_line_direction(self) -> None:
        """Đổi chiều IN/OUT bằng cách đảo thứ tự 2 điểm - _ccw() (cả ở đây
        lẫn CameraPipeline._update_counting()) tính "IN" dựa theo thứ tự
        p1->p2 lưu trong counting_line, nên đảo thứ tự là đủ để đảo chiều,
        không cần vẽ lại line theo hướng ngược."""
        if len(self.counting_line) == 2:
            self.counting_line = list(reversed(self.counting_line))
            self.line_changed.emit()
            self.update()

    # ------------------------------------------------------------------ #
    # Toạ độ: widget <-> pixel gốc của frame
    # ------------------------------------------------------------------ #
    def _update_draw_rect(self) -> None:
        if self._background is None or self._background.isNull():
            self._draw_rect = QRectF(self.rect())
            self._scale = 1.0
            return
        pw, ph = self._background.width(), self._background.height()
        ww, wh = self.width(), self.height()
        scale = min(ww / pw, wh / ph) if pw and ph else 1.0
        dw, dh = pw * scale, ph * scale
        self._draw_rect = QRectF((ww - dw) / 2, (wh - dh) / 2, dw, dh)
        self._scale = scale

    def _to_frame(self, widget_pos: QPoint) -> tuple[int, int] | None:
        if self._scale <= 0:
            return None
        x = (widget_pos.x() - self._draw_rect.x()) / self._scale
        y = (widget_pos.y() - self._draw_rect.y()) / self._scale
        if self._background is not None and not self._background.isNull():
            if x < 0 or y < 0 or x > self._background.width() or y > self._background.height():
                return None
        return (int(x), int(y))

    def _to_widget(self, frame_pos: tuple[int, int]) -> QPointF:
        return QPointF(
            self._draw_rect.x() + frame_pos[0] * self._scale,
            self._draw_rect.y() + frame_pos[1] * self._scale,
        )

    # ------------------------------------------------------------------ #
    # Paint
    # ------------------------------------------------------------------ #
    def paintEvent(self, event) -> None:
        self._update_draw_rect()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(30, 30, 30))

        if self._background is not None and not self._background.isNull():
            painter.drawPixmap(self._draw_rect, self._background, QRectF(self._background.rect()))
        else:
            painter.setPen(QColor(200, 200, 200))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, tr("No image"))

        for idx, roi in enumerate(self.rois):
            self._draw_polygon(painter, roi["points"], selected=(idx == self.selected_roi_index))
            if roi["points"]:
                self._draw_label(painter, self._to_widget(roi["points"][0]) + QPointF(4, -6), roi["name"])

        if len(self.counting_line) == 2:
            self._draw_line(painter, self.counting_line)

        if self._draft_points:
            self._draw_draft(painter)

        painter.end()

    def _draw_polygon(self, painter: QPainter, points: list[tuple[int, int]], selected: bool) -> None:
        if len(points) < 2:
            return
        poly = QPolygonF([self._to_widget(p) for p in points])
        painter.setBrush(QBrush(_ROI_FILL))
        painter.setPen(QPen(_ROI_OUTLINE_SELECTED if selected else _ROI_OUTLINE, 3 if selected else 2))
        painter.drawPolygon(poly)

    def _draw_line(self, painter: QPainter, points: list[tuple[int, int]]) -> None:
        p1, p2 = self._to_widget(points[0]), self._to_widget(points[1])
        painter.setPen(QPen(_LINE_COLOR, 3))
        painter.drawLine(p1, p2)

        # QUAN TRỌNG: xác định hướng "IN" hoàn toàn trong toạ độ FRAME gốc
        # (points[0], points[1]) - khớp đúng công thức CameraPipeline._ccw()
        # dùng lúc đếm thật. Không được trộn với toạ độ widget (p1, p2) ở
        # bước này: có scale + lệch letterbox giữa 2 hệ toạ độ, trộn lẫn sẽ
        # làm sai phép so sánh nửa mặt phẳng -> mũi tên không đổi chiều đúng
        # khi bấm "Đổi chiều IN/OUT" (bug đã gặp).
        fx1, fy1 = points[0]
        fx2, fy2 = points[1]
        fdx, fdy = fx2 - fx1, fy2 - fy1
        flen = max((fdx ** 2 + fdy ** 2) ** 0.5, 1e-6)
        nx, ny = -fdy / flen, fdx / flen  # vector đơn vị vuông góc, hệ toạ độ frame
        fmid = ((fx1 + fx2) / 2, (fy1 + fy2) / 2)
        if not self._ccw((fmid[0] + nx, fmid[1] + ny), points[0], points[1]):
            nx, ny = -nx, -ny

        # Scale giữa frame <-> widget là scale đều dương (không xoay/lật) nên
        # vector hướng (nx, ny) dùng thẳng được cho widget - chỉ toạ độ GỐC
        # để vẽ mũi tên mới cần quy đổi sang widget-space.
        mid_w = self._to_widget(fmid)
        self._draw_direction_arrow(painter, mid_w, (nx, ny), _LINE_IN_COLOR, tr("IN"))
        self._draw_direction_arrow(painter, mid_w, (-nx, -ny), _LINE_OUT_COLOR, tr("OUT"))

    @staticmethod
    def _draw_direction_arrow(
        painter: QPainter, origin: QPointF, direction: tuple[float, float], color: QColor, label: str
    ) -> None:
        nx, ny = direction
        arrow_len = 28
        tip = QPointF(origin.x() + nx * arrow_len, origin.y() + ny * arrow_len)
        painter.setPen(QPen(color, 3))
        painter.drawLine(origin, tip)
        left = QPointF(tip.x() - nx * 9 - ny * 7, tip.y() - ny * 9 + nx * 7)
        right = QPointF(tip.x() - nx * 9 + ny * 7, tip.y() - ny * 9 - nx * 7)
        painter.drawLine(tip, left)
        painter.drawLine(tip, right)
        ROICanvas._draw_label(painter, tip + QPointF(nx * 14, ny * 14 - 4), label, color)

    @staticmethod
    def _ccw(a: tuple[float, float], b: tuple[int, int], c: tuple[int, int]) -> bool:
        return (c[1] - a[1]) * (b[0] - a[0]) > (b[1] - a[1]) * (c[0] - a[0])

    def _draw_draft(self, painter: QPainter) -> None:
        pts = [self._to_widget(p) for p in self._draft_points]
        painter.setPen(QPen(_DRAFT_COLOR, 2))
        for p in pts:
            painter.drawEllipse(p, _POINT_RADIUS, _POINT_RADIUS)
        if len(pts) >= 2:
            painter.drawPolyline(QPolygonF(pts))
        if pts and self._hover_pos is not None:
            painter.setPen(QPen(_DRAFT_COLOR, 1, Qt.PenStyle.DashLine))
            painter.drawLine(pts[-1], self._to_widget(self._hover_pos))

    @staticmethod
    def _draw_label(painter: QPainter, pos: QPointF, text: str, color: QColor = QColor(255, 255, 255)) -> None:
        painter.setPen(QColor(0, 0, 0, 200))
        painter.drawText(pos + QPointF(1, 1), text)
        painter.setPen(color)
        painter.drawText(pos, text)

    # ------------------------------------------------------------------ #
    # Mouse / Keyboard
    # ------------------------------------------------------------------ #
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._mode is None or event.button() != Qt.MouseButton.LeftButton:
            return
        pos = self._to_frame(event.position().toPoint())
        if pos is None:
            return
        self._draft_points.append(pos)
        if self._mode == "line" and len(self._draft_points) == 2:
            self.counting_line = list(self._draft_points)
            self._draft_points = []
            self._mode = None
            self.line_changed.emit()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        self._hover_pos = self._to_frame(event.position().toPoint())
        if self._mode is not None:
            self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._mode == "roi":
            self._finish_roi()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_draft()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self._mode == "roi":
                self._finish_roi()
        elif event.key() == Qt.Key.Key_Backspace:
            if self._draft_points:
                self._draft_points.pop()
                self.update()
        else:
            super().keyPressEvent(event)

    def _finish_roi(self) -> None:
        if len(self._draft_points) < 3:
            QtWidgets.QMessageBox.warning(self, "ROI", tr("At least 3 points are required to create an ROI."))
            return
        name, ok = QtWidgets.QInputDialog.getText(
            self, tr("ROI Name"), tr("Name:"), text=f"ROI {len(self.rois) + 1}"
        )
        if not ok:
            return
        self.rois.append({
            "name": name.strip() or f"ROI {len(self.rois) + 1}",
            "points": list(self._draft_points),
        })
        self._draft_points = []
        self._mode = None
        self.update()
        self.roi_added.emit()


class ROIEditorDialog(QtWidgets.QDialog):
    def __init__(self, parent, device: CameraDevice, device_manager):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('ROI Editor')} — {device.name}")
        self.resize(1000, 650)

        self._device = device
        self._device_manager = device_manager
        self._subscribed = False

        self.canvas = ROICanvas(self)
        for roi in device.roi_regions:
            pts = parse_points(roi.points)
            if len(pts) >= 3:
                self.canvas.rois.append({"name": roi.name, "points": pts})
        line_pts = parse_points(device.counting_line)
        if len(line_pts) == 2:
            self.canvas.counting_line = line_pts

        self.canvas.roi_added.connect(self._reload_roi_list)
        self.canvas.line_changed.connect(self._refresh_line_status)

        self.list_rois = QtWidgets.QListWidget()
        self.list_rois.currentRowChanged.connect(self._on_roi_selected)

        btn_new_roi = QtWidgets.QPushButton(tr("＋  Draw New ROI"))
        btn_new_roi.clicked.connect(self.canvas.start_new_roi)
        btn_delete_roi = QtWidgets.QPushButton(tr("🗑  Delete Selected ROI"))
        btn_delete_roi.clicked.connect(self._on_delete_roi)

        self.lbl_line_status = QtWidgets.QLabel()
        btn_new_line = QtWidgets.QPushButton(tr("📏  Redraw Counting Line"))
        btn_new_line.clicked.connect(self._on_new_line)
        btn_flip_line = QtWidgets.QPushButton(tr("🔄  Flip IN/OUT Direction"))
        btn_flip_line.clicked.connect(self.canvas.flip_line_direction)
        btn_delete_line = QtWidgets.QPushButton(tr("🗑  Delete Line"))
        btn_delete_line.clicked.connect(self.canvas.delete_line)

        hint = QtWidgets.QLabel(
            tr(
                "Click to add a point.\n"
                "Double-click or Enter to close an ROI (≥ 3 points).\n"
                "Counting Line closes automatically after the 2nd point.\n"
                "Esc: cancel current drawing.   Backspace: remove last point.\n"
                "IN/OUT direction doesn't depend on draw order - use the\n"
                "\"Flip IN/OUT Direction\" button to reverse it if needed."
            )
        )
        hint.setWordWrap(True)

        group_roi = QtWidgets.QGroupBox(tr("ROI Regions (Occupancy)"))
        roi_layout = QtWidgets.QVBoxLayout(group_roi)
        roi_layout.addWidget(self.list_rois)
        # Xếp DỌC (không phải hàng ngang) - sidebar chỉ rộng cố định 240px
        # (xem side_widget.setFixedWidth bên dưới), 2 nút chung 1 hàng ngang
        # không đủ chỗ hiển thị hết text (bug đã gặp: text bị cắt/tràn ra
        # ngoài nút).
        roi_layout.addWidget(btn_new_roi)
        roi_layout.addWidget(btn_delete_roi)

        group_line = QtWidgets.QGroupBox(tr("Counting Line (In/Out)"))
        line_layout = QtWidgets.QVBoxLayout(group_line)
        line_layout.addWidget(self.lbl_line_status)
        line_layout.addWidget(btn_new_line)
        line_layout.addWidget(btn_delete_line)
        line_layout.addWidget(btn_flip_line)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        side_layout = QtWidgets.QVBoxLayout()
        side_layout.addWidget(group_roi)
        side_layout.addWidget(group_line)
        side_layout.addWidget(hint)
        side_layout.addStretch()
        side_layout.addWidget(buttons)
        side_widget = QtWidgets.QWidget()
        side_widget.setLayout(side_layout)
        side_widget.setFixedWidth(240)

        root = QtWidgets.QHBoxLayout(self)
        root.addWidget(self.canvas, 1)
        root.addWidget(side_widget)

        self._reload_roi_list()
        self._refresh_line_status()

        self.finished.connect(self._on_finished)
        self._load_background()

    # ------------------------------------------------------------------ #
    # Sidebar helpers
    # ------------------------------------------------------------------ #
    def _reload_roi_list(self) -> None:
        self.list_rois.clear()
        for roi in self.canvas.rois:
            self.list_rois.addItem(roi["name"])

    def _on_roi_selected(self, row: int) -> None:
        self.canvas.selected_roi_index = row if row >= 0 else None
        self.canvas.update()

    def _on_delete_roi(self) -> None:
        row = self.list_rois.currentRow()
        if row < 0:
            QtWidgets.QMessageBox.warning(self, "ROI", tr("Select an ROI from the list to delete."))
            return
        self.canvas.delete_roi(row)
        self._reload_roi_list()

    def _on_new_line(self) -> None:
        self.canvas.start_new_line()
        self._refresh_line_status()

    def _refresh_line_status(self) -> None:
        line = self.canvas.counting_line
        if len(line) == 2:
            self.lbl_line_status.setText(tr("Set: {value}").format(value=f"{line[0]} → {line[1]}"))
        else:
            self.lbl_line_status.setText(tr("Not set"))

    # ------------------------------------------------------------------ #
    # Lấy hình nền (live nếu camera đang chạy, snapshot đồng bộ nếu chưa)
    # ------------------------------------------------------------------ #
    def _load_background(self) -> None:
        if self._device_manager.is_pipeline_running(self._device.id):
            # need_full_resolution=True: toạ độ click ở đây phải khớp đúng
            # hệ toạ độ frame full-res mà AI/occupancy/PPE dùng để tính, nếu
            # không ROI sẽ bị lưu sai tỉ lệ/vị trí so với lúc pipeline áp
            # dụng thật (đã từng xảy ra khi nền là frame đã downscale để
            # hiển thị - xem CameraPipeline._apply_preview_downscale).
            if self._device_manager.subscribe_preview(self._device.id, need_full_resolution=True):
                self._subscribed = True
                self._device_manager.pipeline_frame_ready.connect(self._on_live_frame)
                return
        self._capture_snapshot()

    def _on_live_frame(self, device_id: str, image: QImage) -> None:
        if device_id != self._device.id:
            return
        self.canvas.set_background(QPixmap.fromImage(image))

    def _capture_snapshot(self) -> None:
        source = self._device.display_source()
        source = int(source) if source.isdigit() else source
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            cap = cv2.VideoCapture(source)
            ok, frame = cap.read() if cap.isOpened() else (False, None)
            cap.release()
        finally:
            self.unsetCursor()

        if not ok or frame is None:
            QtWidgets.QMessageBox.warning(
                self, tr("ROI Editor"),
                tr(
                    "Could not get a frame from the camera (not started and could not connect).\n"
                    "You can still draw ROI/Line on a blank background using estimated coordinates."
                ),
            )
            return

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        image = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
        self.canvas.set_background(QPixmap.fromImage(image))

    def _on_finished(self, _result: int) -> None:
        if self._subscribed:
            self._device_manager.pipeline_frame_ready.disconnect(self._on_live_frame)
            self._device_manager.unsubscribe_preview(self._device.id, need_full_resolution=True)
            self._subscribed = False

    # ------------------------------------------------------------------ #
    # Kết quả trả về cho caller (sau khi exec() == Accepted)
    # ------------------------------------------------------------------ #
    def get_roi_regions(self) -> list[ROIRegion]:
        return [
            ROIRegion(name=r["name"], points=self._points_to_string(r["points"]))
            for r in self.canvas.rois
        ]

    def get_counting_line(self) -> str:
        return self._points_to_string(self.canvas.counting_line)

    @staticmethod
    def _points_to_string(points: list[tuple[int, int]]) -> str:
        return ";".join(f"{x},{y}" for x, y in points)
