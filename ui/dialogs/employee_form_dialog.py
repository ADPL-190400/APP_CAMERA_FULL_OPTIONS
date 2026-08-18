"""Form thông tin nhân viên cho Face App (đăng ký mới / sửa thông tin) -
cùng khuôn với ui/dialogs/add_device_dialog.py (QDialog dựng thủ công,
không cần file .ui riêng cho 1 form đơn giản).

Field khớp đúng payload employee_data mà backend AIoT chấp nhận (xem
scr/Web_API.py:post_employee) - "code" ("employee_code"), "first_name",
"last_name" là bắt buộc; "phone"/"email"/"dob"/"gender"/"address" tuỳ chọn
(gửi None nếu để trống, giống code gốc bên MIRAI).

Hỗ trợ quét mã CCCD (đầu đọc barcode/QR USB kiểu "HID keyboard wedge" - gõ
thẳng ký tự như bàn phím thật) - KHÔNG cần bấm/focus vào ô nào cả (Qt tự
focus ô đầu tiên - edit_code - khi dialog mở).

Bản đầu tiên tự dựng lại chuỗi quét bằng cách bắt từng QKeyEvent thô (cài
event filter ở cấp QApplication) rồi tự nối ký tự lại - CÁCH NÀY SAI, đã bỏ
hẳn sau khi gặp bug thật: máy có cài phần mềm gõ tiếng Việt kiểu hook toàn
hệ thống (Unikey/GoTiengViet/EVKey...) chặn MỌI phím rồi tự bắn lại + tự
chèn thêm phím xoá/phím Telex thô để ghép dấu - khiến chuỗi tự dựng lại bị
sai (nhân đôi ký tự, hoặc mất chữ khi cố lọc trùng bằng thời gian). Trong
khi đó bản thân Ô QLineEdit đang focus vẫn luôn hiển thị ĐÚNG nội dung cuối
cùng (Windows/Unikey xử lý đúng ở tầng widget) - nên bản này đọc THẲNG từ
`.text()` của ô đang chứa chuỗi quét (qua signal textChanged, gắn cho các ô
QLineEdit trong form - KHÔNG gồm edit_gender/edit_dob, xem _build_ui) thay
vì tự dựng lại - không còn phụ thuộc việc "replay" đúng từng phím thô/IME
nữa.

Nhận diện điểm BẮT ĐẦU 1 mã CCCD trong text hiện tại của ô bằng NỘI DUNG
(tìm mẫu "12 số rồi tới dấu |" - _CCCD_START_RE - luôn lấy occurrence CUỐI
CÙNG, bỏ qua phần gõ tay/rác phía trước) rồi thử khớp parse_cccd_scan() -
"quét xong" là tự fill ngay, không cần đợi phím Enter (một số đầu đọc không
gửi) hay tín hiệu nào khác.

Sau khi quét THÀNH CÔNG (parse đủ cấu trúc CCCD), form CHUYỂN SANG CHỈ XEM
(_lock_scanned_fields) - các field lấy được từ CCCD bị khoá không cho sửa
tay nữa, tránh gõ nhầm đè lên dữ liệu đã quét đúng. Muốn nhập tay trở lại
phải bấm nút "Clear Scanned Info" (_on_clear_scan) để xoá sạch + mở khoá.

(Đã thử nghiệm đường quét thứ 2 qua cổng COM/Serial - đọc thẳng byte, không
qua bàn phím/IME - nhưng đầu đọc thực tế test (Tera HW0002) có bug firmware
thật: tự làm rớt mất một nhóm lớn ký tự tiếng Việt (nhóm ký tự có dấu "móc"
ư/ơ và nhóm chồng 2 dấu như ạ/ấ/ổ/ề/ệ) trước khi dữ liệu ra khỏi máy quét,
xảy ra giống nhau ở cả chế độ UTF-8 lẫn Raw data - không sửa được từ phía
phần mềm. Đã bỏ hướng này, quay lại dùng đúng 1 đường HID Keyboard wedge ở
trên.)"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import QDate, Qt

from ui.ui_menu.i18n import tr

# Kiosk restyle - cùng bảng màu dark theme của app (ui/themes/theme_dark.qss)
# nhưng field/nút to hơn cho dễ chạm trên màn hình cảm ứng. KHÔNG đổi field/
# logic validate, chỉ thêm giao diện.
_DIALOG_QSS = """
QDialog { background-color: #0d0f14; }
QLabel { color: #c0ccdd; font-size: 13px; }
QLineEdit, QComboBox, QDateEdit {
    background-color: #151c2a; color: #e0e6f0; border: 1px solid #1a2438;
    border-radius: 8px; padding: 10px 12px; font-size: 14px; min-height: 22px;
}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus { border-color: #00d4ff; }
QLineEdit:disabled, QComboBox:disabled, QDateEdit:disabled { color: #3a5070; background-color: #0a0c12; }
QComboBox::drop-down, QDateEdit::drop-down { border: none; width: 22px; }
QComboBox QAbstractItemView {
    background-color: #151c2a; color: #e0e6f0; border: 1px solid #1a2438;
    selection-background-color: #00d4ff; selection-color: #06141f;
}
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
_CLEAR_SCAN_BTN_QSS = (
    "QPushButton { background-color: transparent; color: #ffaa00; border: 1px solid #3a3010;"
    " border-radius: 8px; font-size: 12px; padding: 5px 12px; }"
    "QPushButton:hover { color: #06141f; background-color: #ffaa00; }"
)
_SCAN_HINT_QSS = "color: #7a8aaa; font-size: 11px;"
_SCAN_STATUS_OK_QSS = "color: #00e676; font-size: 11px; font-weight: 600;"
_SCAN_STATUS_LOCKED_QSS = "color: #ffaa00; font-size: 11px; font-weight: 600;"

# Số field tối thiểu của chuỗi QR CCCD chuẩn (7 field có nghĩa - so_cccd,
# so_cmnd_cu, ho_ten, ngay_sinh, gioi_tinh, dia_chi, ngay_cap - cộng thêm
# các field rỗng phía sau nếu có).
_CCCD_MIN_FIELDS = 7

# Mẫu đánh dấu điểm BẮT ĐẦU 1 mã CCCD trong text hiện tại của ô (12 số liền
# nhau rồi tới dấu "|") - xem _on_field_text_changed.
_CCCD_START_RE = re.compile(r"\d{12}\|")

# Bug đã xác định xong nguyên nhân (đầu đọc CCCD gửi thừa/gửi LẶP LẠI toàn
# bộ dữ liệu ngay sau khi đã gửi đủ - xem _locked_field/_on_field_text_changed)
# - TẮT debug, chỉ bật lại (True) nếu cần dò lỗi quét CCCD lần nữa.
_CCCD_DEBUG = False

# Gender: 2 lựa chọn cố định thay vì gõ tay tự do - value lưu/gửi backend
# LUÔN là tiếng Anh thường (không đổi theo ngôn ngữ hiển thị hiện tại),
# label hiển thị dịch qua tr() theo _GENDER_LABEL_KEYS. Xem _set_gender/_gender_value.
_GENDER_VALUES = ["male", "female"]
_GENDER_LABEL_KEYS = {"male": "Male", "female": "Female"}


def _normalize_gender(raw: str) -> str:
    """Chuẩn hoá 1 chuỗi gender bất kỳ (từ CCCD - "Nam"/"Nữ" tiếng Việt, hoặc
    từ backend - có thể đã lưu "male"/"female"/"Nam"/"Nữ" từ bản cũ khi field
    này còn là ô gõ tay tự do) về 1 trong 2 canonical value. Không khớp được
    -> "male" (an toàn, không rơi vào None/lỗi - mặc định cũng khớp giá trị
    đầu tiên trong _GENDER_VALUES)."""
    text = (raw or "").strip().lower()
    if text in ("female", "nữ", "nu", "f", "nữ giới", "woman"):
        return "female"
    return "male"


# Ngày sinh: QDateEdit không có khái niệm "rỗng" như QLineEdit - dùng
# _DOB_MIN_DATE làm "giá trị đặc biệt" (setSpecialValueText) để biểu diễn
# "chưa chọn ngày sinh", xem _build_ui/_dob_value.
_DOB_MIN_DATE = QDate(1900, 1, 1)


def _qdate_from_iso(dob_iso: str) -> QDate:
    """Backend trả "dob" theo ISO 8601 (có thể kèm giờ/timezone, vd
    "2000-04-19T00:00:00.000Z") khi sửa thông tin 1 nhân viên đã có sẵn -
    parse thành QDate để gán cho edit_dob. Không parse được/rỗng ->
    _DOB_MIN_DATE (hiển thị "Chưa chọn")."""
    text = (dob_iso or "").strip()
    if not text:
        return _DOB_MIN_DATE
    for fmt in ("%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(text, fmt)
            return QDate(dt.year, dt.month, dt.day)
        except ValueError:
            continue
    return _DOB_MIN_DATE


def _qdate_from_ddmmyyyy(dob_ddmmyyyy: str) -> QDate:
    """Ngày sinh lấy từ CCCD (parse_cccd_scan trả "DD/MM/YYYY") -> QDate."""
    try:
        dt = datetime.strptime((dob_ddmmyyyy or "").strip(), "%d/%m/%Y")
        return QDate(dt.year, dt.month, dt.day)
    except (ValueError, AttributeError):
        return _DOB_MIN_DATE


def _qdate_to_iso_or_none(date: QDate) -> Optional[str]:
    """Chiều ngược lại - QDate hiện tại của edit_dob -> ISO 8601 gửi backend
    (post_employee trả lỗi 400 nếu gửi sai định dạng). _DOB_MIN_DATE nghĩa
    là "chưa chọn" -> None (bỏ trường, giống hành vi để trống trước đây)."""
    if date == _DOB_MIN_DATE:
        return None
    return date.toString("yyyy-MM-dd")


def parse_cccd_scan(raw: str) -> Optional[dict]:
    """Parse 1 chuỗi quét từ đầu đọc mã QR CCCD (chuẩn Bộ Công an, ví dụ
    "051084009698|212163684|Đặng Hồng Bảo|02081984|Nam|<địa chỉ>|23092024||||").
    Trả về None nếu raw CHƯA khớp cấu trúc này (còn đang gõ tay dở, hoặc
    không phải mã CCCD) - dùng làm tín hiệu "đã quét xong" luôn, không cần
    đợi thêm sự kiện nào khác.

    "Mã nhân viên" lấy từ field[0] (số CCCD 12 số) - LƯU Ý: nhân viên đã
    đăng ký TRƯỚC bản này (mã = số CMND cũ, field[1], bản cũ) sẽ không khớp
    lại nếu quét lại thẻ, có thể tạo hồ sơ trùng - đã xác nhận đổi có chủ ý.
    field[1] (CMND cũ) chỉ còn dùng để validate đúng cấu trúc CCCD, không
    lấy giá trị.
    "Tên"/"Họ" tách từ field[2] theo quy ước tiếng Việt: từ CUỐI CÙNG của họ
    tên đầy đủ là "Tên" (first_name), phần còn lại là "Họ" (last_name)."""
    parts = raw.split("|")
    if len(parts) < _CCCD_MIN_FIELDS:
        return None

    cccd_no = parts[0].strip()
    if not (cccd_no.isdigit() and len(cccd_no) == 12):
        return None
    if not parts[1].strip().isdigit():
        return None

    full_name = parts[2].strip()
    name_words = full_name.split()
    if not name_words:
        return None
    first_name = name_words[-1]
    last_name = " ".join(name_words[:-1])

    # dd/mm/yyyy - parse thành QDate ở _apply_scanned_data (xem _qdate_from_ddmmyyyy).
    dob_raw = parts[3].strip()
    dob_formatted = ""
    if len(dob_raw) == 8 and dob_raw.isdigit():
        dob_formatted = f"{dob_raw[0:2]}/{dob_raw[2:4]}/{dob_raw[4:8]}"

    return {
        "code": cccd_no,
        "first_name": first_name,
        "last_name": last_name,
        "dob": dob_formatted,
        "gender": parts[4].strip() if len(parts) > 4 else "",
        "address": parts[5].strip() if len(parts) > 5 else "",
    }


class EmployeeFormDialog(QtWidgets.QDialog):
    def __init__(self, employee: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self._is_edit = employee is not None
        self.setWindowTitle(tr("Edit Employee Information") if self._is_edit else tr("Register New Employee"))
        self.setMinimumWidth(440)
        self.setStyleSheet(_DIALOG_QSS)

        # "Khoá" 1 ô vừa được fill đúng từ quét thẻ - xem _on_field_text_changed
        # (bug thật đã gặp: đầu đọc gửi THỪA/LẶP LẠI dữ liệu ngay sau khi đã
        # gửi đủ, ký tự thừa đó cứ nối tiếp vào ô đang focus làm sai giá trị
        # đã fill đúng trước đó).
        self._locked_field: Optional[QtWidgets.QLineEdit] = None
        self._locked_value: str = ""

        # True SAU KHI 1 lượt quét CCCD đã fill đủ thông tin - toàn bộ field
        # lấy từ CCCD chuyển sang chỉ xem (xem _lock_scanned_fields), chỉ mở
        # lại được bằng nút "Clear Scanned Info" (_on_clear_scan).
        self._scan_locked = False

        self._build_ui()
        if employee:
            self._fill(employee)

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setVerticalSpacing(14)
        layout.setHorizontalSpacing(16)

        self.lbl_scan_status = QtWidgets.QLabel(
            tr(
                "💳 Scan an ID card at any time to auto-fill "
                "Employee Code/First Name/Last Name/DOB/Gender/Address, or enter manually below."
            )
        )
        self.lbl_scan_status.setStyleSheet(_SCAN_HINT_QSS)
        self.lbl_scan_status.setWordWrap(True)
        layout.addRow(self.lbl_scan_status)

        self.btn_clear_scan = QtWidgets.QPushButton(tr("🗑  Clear Scanned Info"))
        self.btn_clear_scan.setStyleSheet(_CLEAR_SCAN_BTN_QSS)
        self.btn_clear_scan.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_clear_scan.clicked.connect(self._on_clear_scan)
        self.btn_clear_scan.setVisible(False)
        layout.addRow(self.btn_clear_scan)

        self.edit_code = QtWidgets.QLineEdit()
        self.edit_code.setPlaceholderText("NV001")
        layout.addRow(tr("Employee Code *"), self.edit_code)

        self.edit_last_name = QtWidgets.QLineEdit()
        layout.addRow(tr("Last Name *"), self.edit_last_name)

        self.edit_first_name = QtWidgets.QLineEdit()
        layout.addRow(tr("First Name *"), self.edit_first_name)

        self.edit_gender = QtWidgets.QComboBox()
        for value in _GENDER_VALUES:
            self.edit_gender.addItem(tr(_GENDER_LABEL_KEYS[value]), userData=value)
        layout.addRow(tr("Gender"), self.edit_gender)

        self.edit_dob = QtWidgets.QDateEdit()
        self.edit_dob.setDisplayFormat("dd/MM/yyyy")
        self.edit_dob.setCalendarPopup(True)
        self.edit_dob.setMinimumDate(_DOB_MIN_DATE)
        self.edit_dob.setMaximumDate(QDate.currentDate())
        self.edit_dob.setSpecialValueText(tr("Not set"))
        self.edit_dob.setDate(_DOB_MIN_DATE)
        layout.addRow(tr("Date of Birth"), self.edit_dob)

        self.edit_address = QtWidgets.QLineEdit()
        layout.addRow(tr("Address"), self.edit_address)

        self.edit_phone = QtWidgets.QLineEdit()
        layout.addRow(tr("Phone Number"), self.edit_phone)

        self.edit_email = QtWidgets.QLineEdit()
        layout.addRow(tr("Email"), self.edit_email)

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
        # QUAN TRỌNG: tắt auto-default - mặc định Qt sẽ coi OK là nút "default"
        # và TỰ BẤM nó khi có phím Enter/Return bay tới dù không ai click chuột
        # (đã kiểm chứng: nếu đầu đọc gửi thêm Enter sau chuỗi quét - hành vi
        # mặc định phổ biến của nhiều máy quét - dialog tự Accept ngay, người
        # dùng chưa kịp xem lại thông tin đã bị đẩy qua bước đăng ký). Tắt cả
        # 2 nút -> Enter (dù gõ tay hay từ máy quét) không còn tự submit được,
        # BẮT BUỘC phải bấm chuột/chạm vào đúng nút OK mới qua bước tiếp theo.
        ok_btn.setAutoDefault(False)
        ok_btn.setDefault(False)
        cancel_btn.setAutoDefault(False)
        cancel_btn.setDefault(False)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

        # Quét mã CCCD - xem module docstring: gắn textChanged cho các ô
        # QLineEdit trong form (đọc text ĐÃ được Qt/Windows xử lý xong, đúng
        # cả khi có IME tiếng Việt can thiệp, thay vì tự dựng lại từ
        # QKeyEvent thô). edit_gender (QComboBox)/edit_dob (QDateEdit) không
        # nhận text tự do nên không tham gia cơ chế này - luồng quét bình
        # thường luôn bắt đầu từ edit_code (Qt tự focus ô này khi mở dialog).
        for edit in (
            self.edit_code, self.edit_first_name, self.edit_last_name,
            self.edit_address, self.edit_phone, self.edit_email,
        ):
            edit.textChanged.connect(self._on_field_text_changed)

    def keyPressEvent(self, event) -> None:
        # Lưới an toàn THỨ 2 (setAutoDefault/setDefault ở trên KHÔNG ăn
        # chắc - đã kiểm chứng QDialogButtonBox tự set lại nút OK thành
        # "default" mỗi khi dialog show(), bất kể đã setDefault(False) lúc
        # dựng UI) - chặn THẲNG Enter/Return ở đây, không cho QDialog tự
        # accept() bao giờ. Máy quét gửi thêm Enter sau chuỗi (rất phổ biến)
        # tuyệt đối không được tự đóng dialog - bắt buộc người dùng bấm
        # chuột/chạm vào đúng nút OK mới qua bước đăng ký tiếp theo.
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            return
        super().keyPressEvent(event)

    # ── Quét mã CCCD (đọc text đã hoàn chỉnh của ô đang gõ - xem module
    # docstring, KHÔNG tự dựng lại từ QKeyEvent thô nữa) ─────────────────────
    def _on_field_text_changed(self, text: str) -> None:
        if self._scan_locked:
            return  # form đang ở chế độ chỉ xem sau 1 lượt quét - bỏ qua mọi thay đổi (xem _lock_scanned_fields)

        sender = self.sender()

        # Bảo vệ ô VỪA được fill đúng từ 1 lượt quét trước đó (khớp
        # self._locked_field) - bug thật đã gặp: đầu đọc CCCD gửi thừa/gửi
        # LẶP LẠI toàn bộ dữ liệu ngay sau khi đã gửi đủ (không phải lỗi
        # parse), ký tự thừa đó cứ nối tiếp vào ô đang focus (vẫn đúng ô vừa
        # fill) làm sai giá trị đã đúng (vd "079090028504" -> nối thêm
        # "22122021..." thành rác). Text rỗng (người dùng chủ động xoá
        # trắng) -> MỞ KHOÁ, cho gõ tay tự do trở lại. Text khác giá trị đã
        # khoá -> khôi phục lại ngay, bỏ qua ký tự thừa.
        if sender is self._locked_field:
            if not text:
                self._locked_field = None
            elif text != self._locked_value:
                sender.blockSignals(True)
                sender.setText(self._locked_value)
                sender.blockSignals(False)
                return

        if not text:
            return

        # Chỉ thử parse từ điểm BẮT ĐẦU mã CCCD gần nhất trong text hiện tại
        # (xem _CCCD_START_RE/module docstring) - bỏ qua phần gõ tay/rác phía
        # trước nếu có.
        start = None
        for m in _CCCD_START_RE.finditer(text):
            start = m.start()
        candidate = text[start:] if start is not None else text

        parsed = parse_cccd_scan(candidate)
        if _CCCD_DEBUG:
            field_names = {
                self.edit_code: "code", self.edit_first_name: "first_name",
                self.edit_last_name: "last_name", self.edit_address: "address",
                self.edit_phone: "phone", self.edit_email: "email",
            }
            print(f"[CCCD-DEBUG] field={field_names.get(sender, sender)!r} text={text!r}", flush=True)
            print(f"[CCCD-DEBUG] candidate={candidate!r}", flush=True)
            print(f"[CCCD-DEBUG] parse_cccd_scan -> {parsed!r}", flush=True)
        if parsed is None:
            return

        self._apply_scanned_data(parsed)
        # Phone/Email là 2 field DUY NHẤT _apply_scanned_data không đụng tới
        # - nếu lượt quét lỡ rơi vào 1 trong 2 ô này (focus nhầm trước khi
        # quét) thì xoá luôn, tránh sót lại rác quét. KHÔNG khoá 2 field này
        # (không đi qua nhánh bên dưới) - khoá vào giá trị "" sẽ làm 2 ô này
        # không bao giờ gõ tay được nữa (mọi ký tự gõ vào sau đó đều khác ""
        # nên bị hiểu nhầm là rác cần khôi phục).
        if sender in (self.edit_phone, self.edit_email):
            sender.blockSignals(True)
            sender.clear()
            sender.blockSignals(False)
            return

        # Khoá lại field VỪA fill đúng (code/first_name/last_name/address) -
        # xem đầu hàm. Chỉ còn 4 field text tham gia nhánh này (gender/dob
        # không còn là QLineEdit) nhưng cũng sắp bị khoá cứng luôn ngay sau
        # đây (_lock_scanned_fields), nên vô hại nếu sender không khớp field
        # nào trong list.
        self._locked_field = sender
        self._locked_value = sender.text()

    def _apply_scanned_data(self, data: dict) -> None:
        """Chuỗi quét MỚI (khác thẻ trước đó) -> GHI ĐÈ toàn bộ field liên
        quan, không merge/giữ lại giá trị dở dang trước đó - đúng yêu cầu
        "có chuỗi thông tin mới khác thông tin cũ thì xoá hiện tại và fill
        mới". Sau khi fill xong, form CHUYỂN SANG CHỈ XEM (_lock_scanned_fields) -
        quét lại thẻ khác trong lúc đang khoá là không thể (field bị disable
        không nhận text nữa), phải bấm "Clear Scanned Info" trước."""
        if not self._is_edit:
            self.edit_code.setText(data["code"])
        self.edit_first_name.setText(data["first_name"])
        self.edit_last_name.setText(data["last_name"])
        self.edit_dob.setDate(_qdate_from_ddmmyyyy(data["dob"]))
        self._set_gender(_normalize_gender(data["gender"]))
        self.edit_address.setText(data["address"])
        self._lock_scanned_fields()

    # ── Khoá / mở khoá sau khi quét ──────────────────────────────────────
    def _lock_scanned_fields(self) -> None:
        self._scan_locked = True
        self._locked_field = None
        self._locked_value = ""
        for widget in (self.edit_first_name, self.edit_last_name, self.edit_gender, self.edit_dob, self.edit_address):
            widget.setEnabled(False)
        if not self._is_edit:
            self.edit_code.setEnabled(False)
        self.btn_clear_scan.setVisible(True)
        self.lbl_scan_status.setText(
            tr("🔒 Information locked from the scanned card. Use \"Clear Scanned Info\" to edit manually.")
        )
        self.lbl_scan_status.setStyleSheet(_SCAN_STATUS_LOCKED_QSS)

    def _on_clear_scan(self) -> None:
        """Bấm "Clear Scanned Info" - xoá sạch các field lấy từ CCCD và mở
        khoá lại toàn bộ, đưa form về đúng trạng thái ban đầu (trống, có thể
        gõ tay hoặc quét lại thẻ khác)."""
        self._scan_locked = False
        self._locked_field = None
        self._locked_value = ""

        if not self._is_edit:
            self.edit_code.clear()
            self.edit_code.setEnabled(True)
        self.edit_first_name.clear()
        self.edit_last_name.clear()
        self._set_gender("male")
        self.edit_dob.setDate(_DOB_MIN_DATE)
        self.edit_address.clear()
        for widget in (self.edit_first_name, self.edit_last_name, self.edit_gender, self.edit_dob, self.edit_address):
            widget.setEnabled(True)

        self.btn_clear_scan.setVisible(False)
        self.lbl_scan_status.setText(
            tr(
                "💳 Scan an ID card at any time to auto-fill "
                "Employee Code/First Name/Last Name/DOB/Gender/Address, or enter manually below."
            )
        )
        self.lbl_scan_status.setStyleSheet(_SCAN_HINT_QSS)
        self.edit_code.setFocus()

    # ── Gender combobox helpers (value canonical tiếng Anh, không đổi theo
    # ngôn ngữ hiển thị - xem _GENDER_VALUES) ────────────────────────────
    def _set_gender(self, value: str) -> None:
        idx = self.edit_gender.findData(value)
        self.edit_gender.setCurrentIndex(idx if idx >= 0 else 0)

    def _gender_value(self) -> Optional[str]:
        return self.edit_gender.currentData()

    # ── Sửa/điền tay ─────────────────────────────────────────────────────
    def _fill(self, employee: dict) -> None:
        self.edit_code.setText(str(employee.get("code") or employee.get("employee_code") or ""))
        self.edit_first_name.setText(str(employee.get("first_name") or ""))
        self.edit_last_name.setText(str(employee.get("last_name") or ""))
        self._set_gender(_normalize_gender(str(employee.get("gender") or "")))
        self.edit_dob.setDate(_qdate_from_iso(str(employee.get("dob") or "")))
        self.edit_address.setText(str(employee.get("address") or ""))
        self.edit_phone.setText(str(employee.get("phone") or ""))
        self.edit_email.setText(str(employee.get("email") or ""))

        # Nhân viên ĐÃ đăng ký - danh tính (Họ/Tên/Ngày sinh/Giới tính) không
        # cho sửa tay trong màn "Sửa thông tin" nữa, chỉ còn Địa chỉ/SĐT/Email
        # sửa được (edit_code đã bị khoá cứng từ _build_ui rồi, không cần lặp
        # lại ở đây). KHÔNG dùng chung _lock_scanned_fields() - cơ chế đó còn
        # khoá cả Address + hiện nút "Clear Scanned Info" để XOÁ TRẮNG, không
        # hợp với ngữ cảnh này (đang xem dữ liệu đã lưu, không phải vừa quét
        # xong 1 thẻ mới).
        for widget in (self.edit_last_name, self.edit_first_name, self.edit_gender, self.edit_dob):
            widget.setEnabled(False)
        self.lbl_scan_status.setText(
            tr(
                "🔒 Name, date of birth and gender cannot be changed after registration. "
                "Only address, phone and email can be updated."
            )
        )
        self.lbl_scan_status.setStyleSheet(_SCAN_STATUS_LOCKED_QSS)

    def _on_accept(self) -> None:
        if not self.edit_code.text().strip() or not self.edit_first_name.text().strip() or not self.edit_last_name.text().strip():
            QtWidgets.QMessageBox.warning(
                self, tr("Missing Information"), tr("Please fill in Employee Code, First Name and Last Name.")
            )
            return
        self.accept()

    def get_data(self) -> dict:
        return {
            "code": self.edit_code.text().strip(),
            "first_name": self.edit_first_name.text().strip(),
            "last_name": self.edit_last_name.text().strip(),
            "gender": self._gender_value(),
            "dob": _qdate_to_iso_or_none(self.edit_dob.date()),
            "address": self.edit_address.text().strip() or None,
            "phone": self.edit_phone.text().strip() or None,
            "email": self.edit_email.text().strip() or None,
        }
