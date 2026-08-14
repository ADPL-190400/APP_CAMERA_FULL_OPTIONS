"""LanguageManager: singleton static-style class quản lý ngôn ngữ hiện tại
của toàn app - cùng tinh thần với ui/ui_menu/theme_manager.py (ThemeManager)
nhưng phát signal thay vì tự setStyleSheet(), vì đổi NGÔN NGỮ cần từng
trang/dialog tự set lại text (không cascade tự động qua QSS như đổi màu).

Cách dùng:
    from ui.ui_menu.i18n import LanguageManager, tr

    # Đăng ký nhận thông báo đổi ngôn ngữ (mỗi trang sống lâu - MenuWindow và
    # các page con giữ trong stackedPages - gọi 1 lần lúc __init__):
    LanguageManager.instance().language_changed.connect(self.retranslate_ui)

    # Đổi ngôn ngữ (gọi bởi menu chọn ngôn ngữ ở top-bar):
    LanguageManager.instance().set_language("ja")

    # Lấy text đã dịch theo ngôn ngữ hiện tại (key = chuỗi tiếng Anh gốc,
    # xem ui/ui_menu/i18n/strings.py):
    label.setText(tr("Dashboard"))
"""
from __future__ import annotations

from PyQt6.QtCore import QObject, pyqtSignal

from ui.ui_menu.i18n.strings import STRINGS

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("vi", "en", "ja")


class LanguageManager(QObject):
    language_changed = pyqtSignal(str)  # language code mới ("vi"/"en"/"ja")

    _instance: "LanguageManager | None" = None

    def __init__(self) -> None:
        super().__init__()
        self._current = DEFAULT_LANGUAGE

    @classmethod
    def instance(cls) -> "LanguageManager":
        if cls._instance is None:
            cls._instance = LanguageManager()
        return cls._instance

    @property
    def current(self) -> str:
        return self._current

    def set_language(self, code: str) -> None:
        if code not in SUPPORTED_LANGUAGES or code == self._current:
            return
        self._current = code
        self.language_changed.emit(code)


def tr(key: str) -> str:
    """Dịch `key` (chuỗi tiếng Anh gốc, dùng thẳng làm key trong STRINGS)
    sang ngôn ngữ hiện tại. Không có bản dịch (thiếu key/thiếu ngôn ngữ đó) ->
    trả về nguyên `key` (chính là bản tiếng Anh) - an toàn, không bao giờ hiện
    ô trống hay lỗi, chỉ đơn giản chưa dịch được chuỗi này."""
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(LanguageManager.instance().current, key)
