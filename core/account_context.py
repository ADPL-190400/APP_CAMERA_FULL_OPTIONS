"""Ngữ cảnh tài khoản đang đăng nhập - đặt bởi pages/login.py NGAY SAU
Web_API.get_api() thành công, trước khi bất kỳ store nào ở dưới được chạm
tới lần đầu (DeviceManager/EventStore là singleton lazy-init, chỉ thực sự
load từ đĩa khi .instance() được gọi lần đầu - luôn xảy ra sau khi đăng
nhập xong, không có nơi nào gọi sớm hơn).

MỌI dữ liệu lưu cục bộ gắn với 1 tài khoản cụ thể (camera đã đăng ký,
MAC/camera_id server, sự kiện đã ghi nhận, avatar nhân viên cache local...)
phải qua account_dir() ở đây thay vì dùng thẳng BASE_DIR, để tài khoản A
đăng nhập không thấy/ghi đè dữ liệu của tài khoản B trên CÙNG 1 máy - 2 tài
khoản có thể thuộc 2 công ty/zone khác nhau bên web, camera_id/MAC hoàn toàn
không tương thích chéo.

Không có luồng "đăng xuất/đổi tài khoản giữa phiên" trong app (LoginPage chỉ
tạo 1 lần lúc app.py khởi động) nên chỉ cần set 1 LẦN, không cần reset/clear
state của các singleton đã lazy-init trước đó."""
from __future__ import annotations

import os
import re

from core.path_manager import BASE_DIR

_current_email: str | None = None


def set_current_account(email: str) -> None:
    global _current_email
    _current_email = email


def current_account_email() -> str | None:
    return _current_email


def _sanitize(email: str) -> str:
    # Chỉ giữ chữ/số/./-/_ , thay mọi ký tự khác (chủ yếu @) bằng "_" - đủ an
    # toàn làm tên thư mục trên cả Windows/Linux, không cần hash phức tạp vì
    # email hiếm khi chứa ký tự đặc biệt ngoài @ và .
    return re.sub(r"[^a-zA-Z0-9._-]", "_", email.strip().lower()) or "unknown"


def account_dir() -> str:
    """Thư mục gốc dữ liệu RIÊNG cho tài khoản đang đăng nhập
    (data/accounts/{email_đã_sanitize}/) - tự tạo nếu chưa có.

    Raise RuntimeError nếu gọi trước khi có account context - lỗi lập trình
    (1 store account-scoped bị chạm tới trước khi đăng nhập xong), cố tình
    KHÔNG âm thầm fallback về thư mục dùng chung để tránh lặp lại đúng vấn
    đề đang sửa (dữ liệu lẫn giữa các tài khoản)."""
    if _current_email is None:
        raise RuntimeError(
            "Chưa có account context (account_context.set_current_account chưa được gọi) - "
            "store account-scoped bị dùng trước khi đăng nhập xong?"
        )
    path = os.path.join(BASE_DIR, "data", "accounts", _sanitize(_current_email))
    os.makedirs(path, exist_ok=True)
    return path
