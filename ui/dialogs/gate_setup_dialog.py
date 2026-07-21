"""GateSetupDialog: chọn 1 camera ĐÃ ĐĂNG KÝ cho 1 cửa sổ kiosk (Check In/
Check Out - pages/gate_kiosk_page.py::GateWindow - LẪN Face App -
pages/face_attendance_page.py::FaceAttendanceWindow, dùng chung 1 dialog).
KHÔNG vẽ vạch/mở camera riêng ở đây - việc thêm camera, vẽ Counting Line
(tab ROI) và bật chạy (Start) đã có sẵn ở Camera Config/Device Management;
dialog này chỉ kiểm tra camera đã chọn có đủ điều kiện chưa (tuỳ theo
require_running/require_counting_line - Gate kiosk cần cả 2, Face App tự mở
camera riêng nên không cần cái nào) và báo cho người dùng nếu thiếu, không tự
làm thay."""
from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets

from core.device_manager import DeviceManager
from core.models.camera_device import CameraDevice, parse_points


class GateSetupDialog(QtWidgets.QDialog):
    def __init__(
        self,
        title: str,
        parent=None,
        require_running: bool = True,
        require_counting_line: bool = True,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)
        self._require_running = require_running
        self._require_counting_line = require_counting_line

        self._device: Optional[CameraDevice] = None
        self._build_ui()
        self._reload_devices()

    def _build_ui(self) -> None:
        layout = QtWidgets.QVBoxLayout(self)

        hint_text = "Chọn camera"
        if self._require_counting_line:
            hint_text += " (đã cấu hình Counting Line ở Camera Config > ROI)"
        layout.addWidget(QtWidgets.QLabel(hint_text + ":"))

        self.combo_device = QtWidgets.QComboBox()
        self.combo_device.currentIndexChanged.connect(self._refresh_hint)
        layout.addWidget(self.combo_device)

        self.lbl_hint = QtWidgets.QLabel()
        self.lbl_hint.setWordWrap(True)
        self.lbl_hint.setStyleSheet("font-size: 11px; padding: 4px 0;")
        layout.addWidget(self.lbl_hint)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    def _reload_devices(self) -> None:
        self.combo_device.clear()
        for device in DeviceManager.instance().all_devices():
            self.combo_device.addItem(f"{device.name} ({device.device_type.value})", userData=device.id)
        self._refresh_hint()

    def _selected_device(self) -> Optional[CameraDevice]:
        device_id = self.combo_device.currentData()
        return DeviceManager.instance().get_device(device_id) if device_id else None

    def _refresh_hint(self) -> None:
        device = self._selected_device()
        if device is None:
            self.lbl_hint.setText(
                "⚠ Chưa có camera nào được đăng ký - vào Device Management thêm camera trước."
            )
            return

        if self._require_running and not DeviceManager.instance().is_pipeline_running(device.id):
            self.lbl_hint.setText(
                f"⚠ Camera \"{device.name}\" chưa được Start - vào Camera Config hoặc "
                "Device Management để bật chạy trước."
            )
        elif self._require_counting_line and len(parse_points(device.counting_line)) != 2:
            self.lbl_hint.setText(
                f"⚠ Camera \"{device.name}\" chưa vẽ Counting Line - vào Camera Config > "
                "tab ROI để vẽ vạch trước."
            )
        else:
            self.lbl_hint.setText(f"✓ Camera \"{device.name}\" đã sẵn sàng.")

    # ------------------------------------------------------------------ #
    def _on_accept(self) -> None:
        device = self._selected_device()
        if device is None:
            QtWidgets.QMessageBox.warning(self, "Thiếu camera", "Chọn 1 camera trước.")
            return
        if self._require_running and not DeviceManager.instance().is_pipeline_running(device.id):
            QtWidgets.QMessageBox.warning(
                self, "Camera chưa chạy",
                f"Camera \"{device.name}\" chưa được Start.\n"
                "Vào Camera Config hoặc Device Management để bật chạy trước.",
            )
            return
        if self._require_counting_line and len(parse_points(device.counting_line)) != 2:
            QtWidgets.QMessageBox.warning(
                self, "Chưa có vạch",
                f"Camera \"{device.name}\" chưa vẽ Counting Line.\n"
                "Vào Camera Config > tab ROI để vẽ vạch trước.",
            )
            return
        self._device = device
        self.accept()

    def get_device(self) -> CameraDevice:
        return self._device
