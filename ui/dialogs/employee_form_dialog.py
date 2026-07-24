"""Form thông tin nhân viên cho Face App (đăng ký mới / sửa thông tin) -
cùng khuôn với ui/dialogs/add_device_dialog.py (QDialog dựng thủ công,
không cần file .ui riêng cho 1 form đơn giản).

Field khớp đúng payload employee_data mà backend AIoT chấp nhận (xem
scr/Web_API.py:post_employee) - "code" ("employee_code"), "first_name",
"last_name" là bắt buộc; "phone"/"email"/"dob"/"gender"/"address" tuỳ chọn
(gửi None nếu để trống, giống code gốc bên MIRAI).

Hỗ trợ quét mã CCCD (đầu đọc barcode/QR USB kiểu "HID keyboard wedge" - gõ
thẳng chuỗi vào ô đang focus, không cần API/driver riêng): người dùng focus
vào ô "Quét mã CCCD" rồi quét thẻ, chuỗi chuẩn Bộ Công an
("so_cccd|so_cmnd_cu|ho_ten|ngay_sinh|gioi_tinh|dia_chi|ngay_cap||||") tự
nhận diện qua parse_cccd_scan() - KHÔNG dựa vào phím Enter (một số đầu đọc
không gửi), mà dựa thẳng vào cấu trúc chuỗi (12 số đầu + luôn kết thúc bằng
4 field rỗng "||||" - cố định trong chuẩn này) nên biết chắc đã quét xong
ngay khi ký tự cuối vừa "gõ" tới, không cần đợi thêm tín hiệu nào khác."""
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
_SCAN_HINT_QSS = "color: #7a8aaa; font-size: 11px;"
_SCAN_STATUS_OK_QSS = "color: #00e676; font-size: 11px; font-weight: 600;"

# Số field tối thiểu của chuỗi QR CCCD chuẩn (7 field có nghĩa - so_cccd,
# so_cmnd_cu, ho_ten, ngay_sinh, gioi_tinh, dia_chi, ngay_cap - cộng thêm
# các field rỗng phía sau nếu có).
_CCCD_MIN_FIELDS = 7


def parse_cccd_scan(raw: str) -> Optional[dict]:
    """Parse 1 chuỗi quét từ đầu đọc mã QR CCCD (chuẩn Bộ Công an, ví dụ
    "051084009698|212163684|Đặng Hồng Bảo|02081984|Nam|<địa chỉ>|23092024||||").
    Trả về None nếu raw CHƯA khớp cấu trúc này (còn đang gõ tay dở, hoặc
    không phải mã CCCD) - dùng làm tín hiệu "đã quét xong" luôn, không cần
    đợi thêm sự kiện nào khác.

    field[0] (số CCCD 12 số) CỐ TÌNH bỏ qua theo yêu cầu thực tế - "Mã nhân
    viên" lấy từ field[1] (số CMND cũ, 9 số) vì hệ thống hiện tại dùng đúng
    số này làm mã định danh nhân viên.
    "Tên"/"Họ" tách từ field[2] theo quy ước tiếng Việt: từ CUỐI CÙNG của họ
    tên đầy đủ là "Tên" (first_name), phần còn lại là "Họ" (last_name)."""
    parts = raw.split("|")
    if len(parts) < _CCCD_MIN_FIELDS:
        return None

    cccd_no = parts[0].strip()
    employee_code = parts[1].strip()
    if not (cccd_no.isdigit() and len(cccd_no) == 12):
        return None
    if not employee_code.isdigit():
        return None

    full_name = parts[2].strip()
    name_words = full_name.split()
    if not name_words:
        return None
    first_name = name_words[-1]
    last_name = " ".join(name_words[:-1])

    dob_raw = parts[3].strip()
    dob_iso = ""
    if len(dob_raw) == 8 and dob_raw.isdigit():
        dob_iso = f"{dob_raw[4:8]}-{dob_raw[2:4]}-{dob_raw[0:2]}"

    return {
        "code": employee_code,
        "first_name": first_name,
        "last_name": last_name,
        "dob": dob_iso,
        "gender": parts[4].strip() if len(parts) > 4 else "",
        "address": parts[5].strip() if len(parts) > 5 else "",
    }


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

        # ── Quét mã CCCD - focus vào đây rồi quét, các ô bên dưới tự điền ──
        self.edit_scan = QtWidgets.QLineEdit()
        self.edit_scan.setPlaceholderText("Focus vào đây rồi quét thẻ CCCD...")
        self.edit_scan.textChanged.connect(self._on_scan_text_changed)
        layout.addRow("Quét mã CCCD", self.edit_scan)

        self.lbl_scan_status = QtWidgets.QLabel(
            "Quét thẻ để tự điền Mã NV/Tên/Họ/Ngày sinh/Giới tính/Địa chỉ, hoặc tự nhập tay bên dưới."
        )
        self.lbl_scan_status.setStyleSheet(_SCAN_HINT_QSS)
        self.lbl_scan_status.setWordWrap(True)
        layout.addRow("", self.lbl_scan_status)

        self.edit_code = QtWidgets.QLineEdit()
        self.edit_code.setPlaceholderText("NV001")
        layout.addRow("Mã nhân viên *", self.edit_code)

        self.edit_first_name = QtWidgets.QLineEdit()
        layout.addRow("Tên *", self.edit_first_name)

        self.edit_last_name = QtWidgets.QLineEdit()
        layout.addRow("Họ *", self.edit_last_name)

        self.edit_gender = QtWidgets.QLineEdit()
        self.edit_gender.setPlaceholderText("Nam / Nữ")
        layout.addRow("Giới tính", self.edit_gender)

        self.edit_dob = QtWidgets.QLineEdit()
        self.edit_dob.setPlaceholderText("YYYY-MM-DD")
        layout.addRow("Ngày sinh", self.edit_dob)

        self.edit_address = QtWidgets.QLineEdit()
        layout.addRow("Địa chỉ", self.edit_address)

        self.edit_phone = QtWidgets.QLineEdit()
        layout.addRow("Số điện thoại", self.edit_phone)

        self.edit_email = QtWidgets.QLineEdit()
        layout.addRow("Email", self.edit_email)

        # Sửa thông tin nhân viên đã đăng ký -> không cho đổi mã nhân viên
        # (mã dùng để định danh thư mục ảnh + có thể là khoá tra cứu phía
        # backend), chỉ cho sửa các field còn lại. Quét thẻ lúc đang sửa
        # cũng KHÔNG được ghi đè mã (xem _apply_scanned_data) - tránh quét
        # nhầm thẻ người khác làm đổi luôn định danh nhân viên đang sửa.
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

    # ── Quét mã CCCD ─────────────────────────────────────────────────────
    def _on_scan_text_changed(self, text: str) -> None:
        parsed = parse_cccd_scan(text)
        if parsed is None:
            return
        self._apply_scanned_data(parsed)
        # Xoá ô quét NGAY để sẵn sàng cho lượt quét kế tiếp - block signal
        # lúc clear để không tự gọi lại handler này với chuỗi rỗng.
        self.edit_scan.blockSignals(True)
        self.edit_scan.clear()
        self.edit_scan.blockSignals(False)

    def _apply_scanned_data(self, data: dict) -> None:
        """Chuỗi quét MỚI (khác thẻ trước đó) -> GHI ĐÈ toàn bộ field liên
        quan, không merge/giữ lại giá trị dở dang trước đó - đúng yêu cầu
        "có chuỗi thông tin mới khác thông tin cũ thì xoá hiện tại và fill
        mới"."""
        if not self._is_edit:
            self.edit_code.setText(data["code"])
        self.edit_first_name.setText(data["first_name"])
        self.edit_last_name.setText(data["last_name"])
        self.edit_dob.setText(data["dob"])
        self.edit_gender.setText(data["gender"])
        self.edit_address.setText(data["address"])
        self.lbl_scan_status.setText("✓ Đã điền thông tin từ thẻ quét.")
        self.lbl_scan_status.setStyleSheet(_SCAN_STATUS_OK_QSS)

    # ── Sửa/điền tay ─────────────────────────────────────────────────────
    def _fill(self, employee: dict) -> None:
        self.edit_code.setText(str(employee.get("code") or employee.get("employee_code") or ""))
        self.edit_first_name.setText(str(employee.get("first_name") or ""))
        self.edit_last_name.setText(str(employee.get("last_name") or ""))
        self.edit_gender.setText(str(employee.get("gender") or ""))
        self.edit_dob.setText(str(employee.get("dob") or ""))
        self.edit_address.setText(str(employee.get("address") or ""))
        self.edit_phone.setText(str(employee.get("phone") or ""))
        self.edit_email.setText(str(employee.get("email") or ""))

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
            "gender": self.edit_gender.text().strip() or None,
            "dob": self.edit_dob.text().strip() or None,
            "address": self.edit_address.text().strip() or None,
            "phone": self.edit_phone.text().strip() or None,
            "email": self.edit_email.text().strip() or None,
        }
