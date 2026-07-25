"""Form thông tin nhân viên cho Face App (đăng ký mới / sửa thông tin) -
cùng khuôn với ui/dialogs/add_device_dialog.py (QDialog dựng thủ công,
không cần file .ui riêng cho 1 form đơn giản).

Field khớp đúng payload employee_data mà backend AIoT chấp nhận (xem
scr/Web_API.py:post_employee) - "code" ("employee_code"), "first_name",
"last_name" là bắt buộc; "phone"/"email"/"dob"/"gender"/"address" tuỳ chọn
(gửi None nếu để trống, giống code gốc bên MIRAI).

Hỗ trợ quét mã CCCD (đầu đọc barcode/QR USB kiểu "HID keyboard wedge" - gõ
thẳng ký tự như bàn phím thật) - KHÔNG cần bấm/focus vào ô nào cả: cài 1
event filter ở cấp QApplication (installEventFilter) trong lúc dialog này
đang mở, bắt MỌI QKeyEvent bất kể widget con nào đang focus. Ký tự ĐẦU TIÊN
là chữ số (mọi mã CCCD hợp lệ đều bắt đầu bằng 12 số) sẽ mở 1 "lượt nghi là
quét" - từ đó CHẶN HẲN các ký tự tiếp theo (không cho lọt vào ô đang focus
nữa, xem _on_key_press) cho tới khi khớp đủ cấu trúc hoặc hết giờ; gõ tay
bắt đầu bằng chữ (vd "NV001") không rơi vào nhánh này nên không bị ảnh
hưởng. (Bản đầu chỉ "quan sát" không chặn - lộ bug: cả chuỗi quét bị gõ
thẳng như văn bản thường vào đúng ô "Mã nhân viên" đang mặc định focus sẵn
lúc mở dialog, xem lịch sử sửa.) Ký tự gõ được dồn vào 1 buffer nội bộ; hễ
nội dung buffer khớp đúng cấu trúc mã QR CCCD chuẩn Bộ Công an
("so_cccd|so_cmnd_cu|ho_ten|ngay_sinh|gioi_tinh|dia_chi|ngay_cap||||", xem
parse_cccd_scan()) là coi như "quét xong", tự fill - không cần đợi phím
Enter (một số đầu đọc không gửi) hay bất kỳ tín hiệu nào khác. Buffer tự
reset nếu khoảng cách giữa 2 ký tự liên tiếp quá xa so với tốc độ máy quét
(xem _SCAN_KEY_GAP_SEC) - máy quét gõ nhanh hơn người rất nhiều, nhưng ký tự
tiếng Việt có dấu có thể chậm hơn ASCII (Windows giải mã Unicode qua chuỗi
phím numpad nội bộ trước khi Qt nhận được 1 ký tự) nên ngưỡng để khá rộng,
tránh reset nhầm giữa chừng 1 lượt quét làm mất dữ liệu (bug đã gặp: "quét
không fill hết thông tin")."""
from __future__ import annotations

import os
import time
import unicodedata
from typing import Optional

from PyQt6 import QtWidgets
from PyQt6.QtCore import QEvent, Qt, QTimer

# ── Debug tạm thời cho lỗi quét CCCD (2 lần sửa trước KHÔNG ăn trên máy thật
# của người dùng dù test giả lập đều pass) - thay vì đoán tiếp cơ chế OS/Qt
# đang dùng, GHI LẠI đúng luồng event thật (KeyPress/InputMethod, nội dung,
# thời điểm) mỗi khi có phím tới trong lúc dialog này đang mở, để lần sau
# test trên máy thật có dữ liệu THẬT thay vì đoán mò. Cố tình bật SẴN
# (không cần bật cờ gì thêm) vì bug chỉ tái hiện được trên máy có máy quét
# thật - tắt lại bằng cách đặt _SCAN_DEBUG = False khi đã tìm ra nguyên nhân
# và không cần log nữa.
_SCAN_DEBUG = True
_scan_debug_log_path: Optional[str] = None


def _scan_debug(msg: str) -> None:
    if not _SCAN_DEBUG:
        return
    global _scan_debug_log_path
    try:
        if _scan_debug_log_path is None:
            from core.path_manager import BASE_DIR
            log_dir = os.path.join(BASE_DIR, "logs")
            os.makedirs(log_dir, exist_ok=True)
            _scan_debug_log_path = os.path.join(log_dir, "cccd_scan_debug.log")
        with open(_scan_debug_log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.time():.3f} {msg}\n")
    except Exception:
        pass

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

# Đ/đ KHÔNG decompose được qua unicodedata.normalize("NFD", ...) như các chữ
# có dấu khác (ả -> "a" + dấu, nhưng "Đ" là 1 chữ cái Latin Extended-A riêng
# trong Unicode) - map thủ công để coi "D" là chữ gốc của "Đ".
_VIET_LETTER_BASE = {"Đ": "D", "đ": "d"}


def _char_base(ch: str) -> str:
    if ch in _VIET_LETTER_BASE:
        return _VIET_LETTER_BASE[ch]
    decomposed = unicodedata.normalize("NFD", ch)
    return decomposed[:1] or ch


def _is_next_compose_step(prev: str, new: str) -> bool:
    """True nếu `new` là CÙNG 1 CHỮ CÁI GỐC với `prev` (vd a/ă/ặ đều gốc "a",
    D/Đ đều gốc "D") - dùng để gộp lại các bước trung gian mà driver bàn
    phím/HID Windows gửi thành từng phím RIÊNG BIỆT thay vì gửi thẳng ký tự
    có dấu cuối cùng (lỗi thật đã gặp khi quét CCCD qua máy quét: "Đặng
    Hồng" -> "DĐaăặng Hoôồng" - mỗi ký tự có dấu bị "gõ" ra thành cả chuỗi
    bước hợp dấu trung gian thay vì 1 ký tự cuối).

    CỐ Ý không đòi hỏi `new` phải "nhiều dấu hơn" `prev` (thử as vậy trước
    đây vẫn KHÔNG khớp được hết các trường hợp thực tế trên máy quét thật -
    driver/HID có thể gửi các bước hợp dấu theo thứ tự/số lượng khác dự
    đoán) - chỉ cần CÙNG chữ cái gốc là coi bước sau THAY THẾ bước trước,
    kể cả khi 2 ký tự giống hệt nhau (dedup luôn các phím lặp/dội của driver).

    Chỉ áp dụng cho CHỮ CÁI (`str.isalpha()`) - KHÔNG áp dụng cho chữ số hay
    ký tự khác, vì số CCCD có thể có 2 chữ số giống nhau đứng cạnh nhau (vd
    "...4009698" có "00") và không được phép gộp mất 1 chữ số."""
    if not prev.isalpha() or not new.isalpha():
        return False
    return _char_base(prev).lower() == _char_base(new).lower()

# Khoảng cách tối đa giữa 2 ký tự liên tiếp để còn tính là "cùng 1 lượt quét".
# Từng để 0.1s (100ms) nhưng THỰC TẾ máy quét bị reset buffer giữa chừng
# (bug "quét không fill hết thông tin") - có thể do ký tự tiếng Việt có dấu
# chậm hơn ASCII đáng kể (Windows giải mã qua chuỗi phím numpad nội bộ). Nới
# lên 0.5s - vẫn nhanh hơn hẳn tốc độ gõ tay của người (trung bình >150-200ms/
# ký tự), an toàn hơn cho việc mất dữ liệu giữa chừng.
_SCAN_KEY_GAP_SEC = 0.5
# Chặn buffer phình vô hạn nếu vì lý do gì đó không bao giờ khớp được.
_SCAN_BUFFER_MAX_LEN = 300
# Sau khi 1 lượt quét vừa THÀNH CÔNG, bỏ qua mọi ký tự số "mở đầu buffer mới"
# tới trong khoảng này - lỗi thật đã gặp: 1 đoạn đuôi chuỗi cũ tới trễ/dội lại
# ngay sau khi đã quét xong, bị hiểu nhầm thành lượt quét MỚI, dính thêm rác
# vào field đã đúng. Đủ ngắn để không cản trở quét thẻ KHÁC ngay sau đó (cần
# vài giây thao tác vật lý: rút thẻ cũ, đưa thẻ mới vào đầu đọc).
_SCAN_SUCCESS_COOLDOWN_SEC = 0.5


def parse_cccd_scan(raw: str) -> Optional[dict]:
    """Parse 1 chuỗi quét từ đầu đọc mã QR CCCD (chuẩn Bộ Công an, ví dụ
    "051084009698|212163684|Đặng Hồng Bảo|02081984|Nam|<địa chỉ>|23092024||||").
    Trả về None nếu raw CHƯA khớp cấu trúc này (còn đang gõ tay dở, hoặc
    không phải mã CCCD) - dùng làm tín hiệu "đã quét xong" luôn, không cần
    đợi thêm sự kiện nào khác.

    "Mã nhân viên" lấy từ field[0] (số CCCD, 12 số) - field[1] (số CMND cũ,
    9 số) không dùng tới.
    "Tên"/"Họ" tách từ field[2] theo quy ước tiếng Việt: từ CUỐI CÙNG của họ
    tên đầy đủ là "Tên" (first_name), phần còn lại là "Họ" (last_name)."""
    parts = raw.split("|")
    if len(parts) < _CCCD_MIN_FIELDS:
        return None

    employee_code = parts[0].strip()
    if not (employee_code.isdigit() and len(employee_code) == 12):
        return None
    if not parts[1].strip().isdigit():
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

        self._scan_buffer = ""
        self._scan_last_key_ts = 0.0
        self._scan_cooldown_until = 0.0  # xem _SCAN_SUCCESS_COOLDOWN_SEC
        # Widget đang focus TẠI THỜI ĐIỂM bắt đầu buffer 1 ký tự số đầu tiên
        # (không tra lại focusWidget() lúc flush - người dùng có thể đã bấm
        # chuột sang ô khác trong lúc buffer đang chờ, tra lại lúc đó sẽ trả
        # nhầm ký tự vào ô mới thay vì ô đang gõ dở).
        self._scan_target_widget: Optional[QtWidgets.QLineEdit] = None
        # Hết giờ mà không có ký tự tiếp theo (KHÔNG có phím nào tới để tự so
        # sánh mốc thời gian) -> coi như KHÔNG phải quét, trả lại nguyên văn
        # đã chặn vào đúng ô đang gõ dở (xem _flush_scan_buffer).
        self._scan_timer = QTimer(self)
        self._scan_timer.setSingleShot(True)
        self._scan_timer.timeout.connect(self._flush_scan_buffer)

        self._build_ui()
        if employee:
            self._fill(employee)

        # Cài lúc dựng dialog, gỡ lúc đóng (done()) - xem module docstring.
        QtWidgets.QApplication.instance().installEventFilter(self)

    def _build_ui(self) -> None:
        layout = QtWidgets.QFormLayout(self)
        layout.setContentsMargins(28, 28, 28, 24)
        layout.setVerticalSpacing(14)
        layout.setHorizontalSpacing(16)

        self.lbl_scan_status = QtWidgets.QLabel(
            "💳 Quét thẻ CCCD bất kỳ lúc nào (không cần bấm vào ô nào) để tự điền "
            "Mã NV/Tên/Họ/Ngày sinh/Giới tính/Địa chỉ, hoặc tự nhập tay bên dưới."
        )
        self.lbl_scan_status.setStyleSheet(_SCAN_HINT_QSS)
        self.lbl_scan_status.setWordWrap(True)
        layout.addRow(self.lbl_scan_status)

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

    # ── Quét mã CCCD (bắt phím toàn dialog, không cần focus ô nào) ──────────
    def eventFilter(self, obj, event) -> bool:
        if _SCAN_DEBUG and event.type() in (QEvent.Type.KeyPress, QEvent.Type.InputMethod):
            # Ghi lại NGUYÊN VĂN mọi event tới đây, kể cả InputMethod lúc
            # buffer đang RỖNG (để kiểm tra luôn giả thiết "số CCCD luôn tới
            # qua KeyPress" - nếu giả thiết đó cũng sai trên máy người dùng,
            # log này sẽ lộ ra ngay).
            if event.type() == QEvent.Type.KeyPress:
                _scan_debug(
                    f"KeyPress obj={obj.objectName() if hasattr(obj, 'objectName') else obj!r} "
                    f"text={event.text()!r} key={event.key()} buffer={self._scan_buffer!r}"
                )
            else:
                _scan_debug(
                    f"InputMethod obj={obj.objectName() if hasattr(obj, 'objectName') else obj!r} "
                    f"commit={event.commitString()!r} preedit={event.preeditString()!r} "
                    f"buffer={self._scan_buffer!r}"
                )
        if event.type() == QEvent.Type.KeyPress:
            if self._on_key_press(event):
                return True  # CHẶN - không cho ký tự này lọt vào ô đang focus (xem _on_key_press)
        elif event.type() == QEvent.Type.InputMethod and self._scan_buffer:
            # Thực tế đã xác nhận: quét thẻ vào Notepad (không qua Qt) ra
            # đúng chữ tuyệt đối ("Đặng Hồng Bảo"), nhưng quét vào chính
            # dialog này thì các ký tự có dấu vẫn bị lặp/gãy dấu ("Đặng Hồng"
            # -> "DĐaăặng Hoôồng") DÙ ĐÃ gộp theo _is_next_compose_step ở
            # _on_key_press - nghĩa là driver KHÔNG hề gửi ký tự trung gian,
            # dữ liệu vào hệ điều hành vốn đã sạch/đúng ngay từ đầu. Nguyên
            # nhân thực sự: Windows/Qt định tuyến các ký tự tiếng Việt có dấu
            # qua cơ chế IME/composition (QInputMethodEvent), KHÔNG qua
            # KeyPress bình thường như số/chữ không dấu/"|" - nên toàn bộ
            # logic ở _on_key_press không bao giờ thấy được các ký tự này,
            # chúng lọt thẳng (không bị chặn) vào ô đang focus qua đường
            # input-method mặc định của chính QLineEdit, cộng dồn lên trên
            # phần đã được _apply_scanned_data() điền đúng.
            #
            # commitString() của Qt là ký tự/đoạn ĐÃ ghép dấu xong hoàn
            # chỉnh (Qt tự quản lý preedit nội bộ trước khi commit, không
            # cần tự gộp bước trung gian như _is_next_compose_step) - chỉ
            # cần nối thẳng vào buffer. CHỈ xử lý khi đang có 1 buffer dở
            # dang (đã bắt đầu từ số CCCD qua KeyPress) - tránh chặn nhầm
            # gõ tay tiếng Việt bình thường lúc không quét gì cả.
            if self._on_input_method(event):
                return True
        elif (
            event.type() == QEvent.Type.FocusIn
            and self._scan_buffer
            and self._scan_target_widget is not None
            and obj is not self._scan_target_widget
        ):
            # Có 1 buffer đang chờ dở dang MÀ nó bắt đầu từ 1 Ô CỤ THỂ đang
            # gõ dở (self._scan_target_widget không None), và focus vừa
            # chuyển sang Ô KHÁC (bấm chuột/Tab) trước khi kịp hết giờ chờ -
            # chốt lại NGAY, không đợi timer nữa. Không làm vậy thì ký tự gõ
            # tiếp theo ở ô MỚI sẽ bị cộng nhầm vào buffer của ô CŨ (đã kiểm
            # chứng bằng test: gõ dở "NV002" ở Mã NV rồi bấm sang ô Tên gõ
            # tiếp "Test" -> "Test" bị dính vào Mã NV).
            #
            # CHỈ xét khi target KHÔNG None - lúc quét thẻ mà KHÔNG bấm/focus
            # ô nào cả (đúng luồng chính), Qt có thể tự gán focus mặc định
            # cho 1 ô nào đó ngay trong lúc đang quét dở (không phải do
            # người dùng bấm) - nếu cũng flush ở đây sẽ huỷ ngang lượt quét
            # thật giữa chừng (bug đã gặp: chế độ Sửa, ô Mã NV bị khoá nên
            # không có focus rõ ràng lúc mở dialog, quét bị huỷ ngang).
            self._flush_scan_buffer()
        return super().eventFilter(obj, event)

    def _on_key_press(self, event) -> bool:
        """Trả về True nếu ký tự này CẦN CHẶN (không cho ô đang focus nhận
        được) vì đang trong 1 chuỗi nghi là quét thẻ.

        Ô "Mã nhân viên" là ô đầu tiên trong form nên MẶC ĐỊNH được focus
        sẵn lúc dialog vừa mở - trước đây filter chỉ "quan sát" (không chặn)
        nên toàn bộ chuỗi quét (kể cả ký tự "|") bị gõ thẳng như văn bản
        thường vào đúng ô đó, hiện ra 1 đống chữ lộn xộn CHỈ ở "Mã nhân
        viên" trong khi các ô khác không có gì (bug đã gặp: "quét chỉ fill
        vào mã NV rồi thôi"). Phải CHẶN hẳn trong lúc đang tích luỹ 1 lượt
        quét, chỉ khi khớp đủ cấu trúc mới thật sự fill (_apply_scanned_data).

        Chỉ bắt đầu chặn khi ký tự ĐẦU buffer là 1 CHỮ SỐ (mọi mã CCCD hợp lệ
        đều bắt đầu bằng 12 số) - gõ tay bình thường bắt đầu bằng chữ (vd
        "NV001", 2 ký tự đầu "N"/"V") không rơi vào nhánh này. Nhưng nếu
        NGƯỜI DÙNG gõ tay 1 mã có số ở đâu đó (vd tiếp sau "N"/"V" là "001")
        thì các số đó SẼ bị tạm chặn/tích luỹ giống hệt đang nghi ngờ là quét
        - để không mất chữ đã gõ, buffer đó được TRẢ LẠI (chèn nguyên văn vào
        đúng ô đang gõ dở) qua _flush_scan_buffer() nếu hết giờ không khớp
        được cấu trúc CCCD nào (xem _scan_timer)."""
        now = time.monotonic()
        gap_exceeded = now - self._scan_last_key_ts > _SCAN_KEY_GAP_SEC
        self._scan_last_key_ts = now

        text = event.text()
        if not text:
            return False  # phím điều khiển (mũi tên, Ctrl...) không có ký tự - không liên quan

        if gap_exceeded and self._scan_buffer:
            # Lượt trước bị bỏ dở (không có ký tự nào tới kịp trong
            # _SCAN_KEY_GAP_SEC để chính nó kích hoạt _scan_timer xử lý) -
            # trả lại trước khi xét ký tự MỚI này như 1 khởi đầu hoàn toàn
            # riêng biệt.
            self._flush_scan_buffer()

        if not self._scan_buffer:
            if now < self._scan_cooldown_until:
                # Vừa quét THÀNH CÔNG cách đây rất gần (xem _apply_scanned_data)
                # - ký tự số mới tới ngay sau đó nhiều khả năng là dữ liệu
                # dội/lặp lại của CHÍNH lượt quét vừa xong (đã gặp thật: 1 đoạn
                # đuôi chuỗi cũ "23092024||||" tới trễ, dính thêm vào Mã nhân
                # viên đã đúng) chứ không phải quét thẻ mới hay gõ tay - bỏ hẳn
                # ký tự này, không mở buffer mới.
                return True
            if not text.isdigit():
                return False  # ký tự ĐẦU không phải số -> chắc chắn không phải mở đầu 1 mã CCCD, cho gõ tay bình thường, không đụng vào buffer
            self._scan_target_widget = QtWidgets.QApplication.focusWidget()

        if self._scan_buffer and _is_next_compose_step(self._scan_buffer[-1], text):
            # Ký tự MỚI là bước ghép dấu tiếp theo của CHÍNH ký tự cuối buffer
            # (vd vừa thêm "ă", giờ tới "ặ") - THAY THẾ, không nối thêm (xem
            # _is_next_compose_step - lỗi thật đã gặp: driver gửi từng bước
            # trung gian thành phím riêng, "Đặng" thành "DĐaăặng").
            self._scan_buffer = self._scan_buffer[:-1] + text
        else:
            self._scan_buffer += text

        return self._after_buffer_append(now)

    def _on_input_method(self, event) -> bool:
        """Xử lý phần ký tự có dấu tiếng Việt đi qua đường IME/composition
        (QInputMethodEvent) thay vì KeyPress - xem giải thích chi tiết ở
        eventFilter(). commitString() đã LÀ ký tự/đoạn ghép dấu cuối cùng,
        đúng hoàn toàn (Qt tự quản lý preedit nội bộ) - không cần gộp bước
        trung gian như _is_next_compose_step (đường KeyPress mới cần).

        Khi commitString() rỗng (đang trong lúc preedit, chưa chốt) - vẫn
        CHẶN (return True), không cho hiện tạm preedit vào ô đang focus
        (tránh nháy chữ tạm lên UI trong lúc quét), chờ tới lúc thật sự
        commit mới xử lý tiếp."""
        commit = event.commitString()
        if not commit:
            return True
        now = time.monotonic()
        self._scan_last_key_ts = now
        self._scan_buffer += commit
        return self._after_buffer_append(now)

    def _after_buffer_append(self, now: float) -> bool:
        """Phần xử lý DÙNG CHUNG sau khi có thêm ký tự/đoạn mới vào
        _scan_buffer, bất kể nguồn là KeyPress (_on_key_press) hay IME
        composition (_on_input_method) - kiểm tra độ dài bất thường, khớp
        cấu trúc CCCD, hoặc hẹn giờ chờ tiếp."""
        if len(self._scan_buffer) > _SCAN_BUFFER_MAX_LEN:
            # Dài bất thường mà vẫn chưa khớp -> chắc chắn không phải mã
            # CCCD (lượt quét thật khớp rất sớm ngay khi đủ field) - trả lại
            # toàn bộ, không giữ tiếp.
            self._flush_scan_buffer()
            return False

        parsed = parse_cccd_scan(self._scan_buffer)
        if parsed is not None:
            _scan_debug(f"MATCHED raw_buffer={self._scan_buffer!r} parsed={parsed!r}")
            self._apply_scanned_data(parsed)
            self._scan_buffer = ""
            self._scan_target_widget = None
            self._scan_timer.stop()
            self._scan_cooldown_until = now + _SCAN_SUCCESS_COOLDOWN_SEC
            return True

        # Chưa khớp - có thể còn đang quét dở (ký tự tiếp theo sắp tới) hoặc
        # là gõ tay tình cờ bắt đầu bằng số - hẹn giờ, hết giờ mà không có gì
        # thêm thì _flush_scan_buffer() tự trả lại (xem __init__).
        self._scan_timer.start(int(_SCAN_KEY_GAP_SEC * 1000))
        return True

    def _flush_scan_buffer(self) -> None:
        """Buffer đang tích luỹ dở KHÔNG khớp được cấu trúc CCCD nào trong
        thời gian chờ - kết luận đây KHÔNG phải 1 lượt quét, trả lại nguyên
        văn các ký tự đã tạm chặn vào ĐÚNG ô đang gõ dở lúc bắt đầu buffer
        (không tra lại focus hiện tại - có thể người dùng đã bấm sang ô khác
        trong lúc chờ)."""
        self._scan_timer.stop()
        text, self._scan_buffer = self._scan_buffer, ""
        widget, self._scan_target_widget = self._scan_target_widget, None
        if text:
            _scan_debug(f"FLUSH (khong khop CCCD) text={text!r} widget={widget!r}")
        if text and isinstance(widget, QtWidgets.QLineEdit):
            widget.insert(text)

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
        self.lbl_scan_status.setText("✓ Đã điền thông tin từ thẻ vừa quét.")
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
        # Bấm OK ngay khi 1 buffer đang chờ hết giờ (vd vừa gõ tay xong số
        # cuối rồi bấm OK liền, chưa đủ _SCAN_KEY_GAP_SEC để tự flush) -
        # flush ngay để không mất mấy ký tự cuối trước khi validate.
        self._flush_scan_buffer()
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

    def done(self, result: int) -> None:
        # Gỡ event filter TOÀN CỤC ngay khi dialog đóng (OK/Cancel/X đều đi
        # qua done()) - không gỡ thì filter vẫn "sống" trên QApplication sau
        # khi dialog đã bị huỷ, rò rỉ + có thể lỗi khi eventFilter cố truy
        # cập self của 1 dialog đã chết.
        QtWidgets.QApplication.instance().removeEventFilter(self)
        self._scan_timer.stop()
        super().done(result)
