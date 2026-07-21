"""Form thông tin nhân viên cho Face App (đăng ký mới / sửa thông tin) -
cùng khuôn với ui/dialogs/add_device_dialog.py (QDialog dựng thủ công,
không cần file .ui riêng cho 1 form đơn giản).

Field khớp đúng payload employee_data mà backend AIoT chấp nhận (xem
scr/Web_API.py:post_employee) - "code" ("employee_code"), "first_name",
"last_name" là bắt buộc; "phone"/"email"/"dob" tuỳ chọn (gửi None nếu để
trống, giống code gốc bên MIRAI)."""
from __future__ import annotations

from typing import Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import Qt

# Kiosk restyle - cùng bảng màu dark theme của app (ui/themes/theme_dark.qss)
# nhưng field/nút to hơn cho dễ chạm trên màn hình cảm ứng. KHÔNG đổi field/
# logic validate, chỉ thêm giao diện.
_DIALOG_QSS = """
QDialog { background-color: #0d0f14; }
QLabel { color: #c0ccdd; font-size: 13px; }
QLineEdit {
    background-color: #151c2a; color: #e0e6f0; border: 1px solid #1a2438;
    border-radius: 8px; padding: 10px 12px; font-size: 14px; min-height: 22px;
}
QLineEdit:focus { border-color: #00d4ff; }
QLineEdit:disabled { color: #3a5070; background-color: #0a0c12; }
"""
_OK_BTN_QSS = (
    "QPushButton { background-color: #0e2040; color: #00d4ff; border: 1px solid #00d4ff;"
    " border-radius: 10px; font-weight: 700; font-size: 14px; padding: 8px 22px; }"
    "QPushButton:hover { background-color: #00d4ff; color: #06141f; }"
)
_CANCEL_BTN_QSS = (
    "QPushButton { background-color: transparent; color: #7a8aaa; border: 1px solid #1a2030;"
    " border-radius: 10px; font-size: 14px; padding: 8px 22px; }"
    "QPushButton:hover { color: #ff4444; border-color: #ff4444; }"
)


class EmployeeFormDialog(QtWidgets.QDialog):
    def __init__(self, employee: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._is_edit = employee is not None
        self.setWindowTitle("Sửa thông tin nhân viên" if self._is_edit else "Đăng ký nhân viên mới")
        self.setMinimumWidth(440)
        self.setStyleSheet(_DIALOG_QSS)
        self._build_ui()
        if employee:
            self._fill(employee)

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setVerticalSpacing(14)
        layout.setHorizontalSpacing(16)

        self.edit_code = QtWidgets.QLineEdit()
        self.edit_code.setPlaceholderText("NV001")
        layout.addRow("Mã nhân viên *", self.edit_code)

        self.edit_first_name = QtWidgets.QLineEdit()
        layout.addRow("Tên *", self.edit_first_name)

        self.edit_last_name = QtWidgets.QLineEdit()
        layout.addRow("Họ *", self.edit_last_name)

        self.edit_phone = QtWidgets.QLineEdit()
        layout.addRow("Số điện thoại", self.edit_phone)

        self.edit_email = QtWidgets.QLineEdit()
        layout.addRow("Email", self.edit_email)

        self.edit_dob = QtWidgets.QLineEdit()
        self.edit_dob.setPlaceholderText("YYYY-MM-DD")
        layout.addRow("Ngày sinh", self.edit_dob)

        # Sửa thông tin nhân viên đã đăng ký -> không cho đổi mã nhân viên
        # (mã dùng để định danh thư mục ảnh + có thể là khoá tra cứu phía
        # backend), chỉ cho sửa các field còn lại.
        if self._is_edit:
            self.edit_code.setEnabled(False)

        buttons = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok
            | QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Ok)
        ok_btn.setText("OK")
        ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        ok_btn.setStyleSheet(_OK_BTN_QSS)
        cancel_btn = buttons.button(QtWidgets.QDialogButtonBox.StandardButton.Cancel)
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(_CANCEL_BTN_QSS)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def _fill(self, employee: dict) -> None:
        self.edit_code.setText(str(employee.get("code") or employee.get("employee_code") or ""))
        self.edit_first_name.setText(str(employee.get("first_name") or ""))
        self.edit_last_name.setText(str(employee.get("last_name") or ""))
        self.edit_phone.setText(str(employee.get("phone") or ""))
        self.edit_email.setText(str(employee.get("email") or ""))
        self.edit_dob.setText(str(employee.get("dob") or ""))

    def _on_accept(self) -> None:
        if not self.edit_code.text().strip() or not self.edit_first_name.text().strip() or not self.edit_last_name.text().strip():
            QtWidgets.QMessageBox.warning(self, "Thiếu thông tin", "Vui lòng điền Mã nhân viên, Tên và Họ.")
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "code": self.edit_code.text().strip(),
            "first_name": self.edit_first_name.text().strip(),
            "last_name": self.edit_last_name.text().strip(),
            "phone": self.edit_phone.text().strip() or None,
            "email": self.edit_email.text().strip() or None,
            "dob": self.edit_dob.text().strip() or None,
        }
