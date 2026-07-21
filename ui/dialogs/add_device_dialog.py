"""Dialog thêm camera (IP hoặc USB) thủ công cho nút '+ Add'."""
from __future__ import annotations

from PyQt6 import QtWidgets

from core.models.camera_device import CameraDevice, DeviceType


class AddDeviceDialog(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm camera")
        self.setMinimumWidth(360)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)

        self.edit_name = QtWidgets.QLineEdit()
        self.edit_name.setPlaceholderText("e.g. Main Entrance")
        layout.addRow("Camera Name", self.edit_name)

        self.combo_type = QtWidgets.QComboBox()
        self.combo_type.addItems(["IP", "USB"])
        self.combo_type.currentTextChanged.connect(self._on_type_changed)
        layout.addRow("Device Type", self.combo_type)

        self.combo_vendor = QtWidgets.QComboBox()
        self.combo_vendor.addItems(["Unknown", "Hikvision", "Dahua", "Axis", "Bosch", "Other"])
        layout.addRow("Vendor", self.combo_vendor)

        self.edit_ip = QtWidgets.QLineEdit()
        self.edit_ip.setPlaceholderText("192.168.1.100")
        layout.addRow("IP Address", self.edit_ip)

        self.edit_mac = QtWidgets.QLineEdit()
        self.edit_mac.setPlaceholderText("AA:BB:CC:DD:EE:FF")
        self.edit_mac.setToolTip(
            "Định danh camera này bên web server - để trống nếu chưa biết, "
            "có thể nhập/sửa sau ở Camera Config."
        )
        layout.addRow("MAC Address", self.edit_mac)

        self.edit_stream_url = QtWidgets.QLineEdit()
        self.edit_stream_url.setPlaceholderText("rtsp://user:pass@192.168.1.100/stream")
        layout.addRow("Stream URL", self.edit_stream_url)

        self.spin_usb_index = QtWidgets.QSpinBox()
        self.spin_usb_index.setRange(0, 10)
        layout.addRow("USB Index", self.spin_usb_index)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        self._on_type_changed(self.combo_type.currentText())

    def _on_type_changed(self, device_type: str) -> None:
        is_ip = device_type == "IP"
        self.edit_ip.setEnabled(is_ip)
        self.edit_stream_url.setEnabled(is_ip)
        self.spin_usb_index.setEnabled(not is_ip)

    def get_device(self) -> CameraDevice:
        device_type = DeviceType.IP if self.combo_type.currentText() == "IP" else DeviceType.USB
        return CameraDevice(
            name=self.edit_name.text().strip() or "New Camera",
            device_type=device_type,
            vendor=self.combo_vendor.currentText(),
            ip_address=self.edit_ip.text().strip(),
            mac_address=self.edit_mac.text().strip(),
            stream_url=self.edit_stream_url.text().strip(),
            usb_index=self.spin_usb_index.value(),
        )
