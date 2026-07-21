"""
ui/theme_manager.py
===================
ThemeManager – tải và switch QSS theme toàn ứng dụng.

Cách dùng:
    from ui.theme_manager import ThemeManager

    # Khởi tạo một lần trong main (trước khi show window)
    ThemeManager.init(app, default="dark")

    # Switch runtime (gắn vào btn_dark_mode toggled signal)
    ThemeManager.set_theme("light")
    ThemeManager.toggle()

    # Query
    ThemeManager.current_theme   # "dark" | "light"
"""

from __future__ import annotations

import os
from typing import Literal

from PyQt6.QtWidgets import QApplication

Theme = Literal["dark", "light"]

# Thư mục chứa file .qss.  Mặc định: cùng cấp với file này.
_THEMES_DIR = os.path.join(os.path.dirname(__file__), "..", "themes")

# Nếu để file .qss trong thư mục gốc project thay vì sub-folder,
# đổi dòng trên thành:
# _THEMES_DIR = os.path.join(os.path.dirname(__file__), "..")


class ThemeManager:
    """
    Singleton-style static class.  Không cần instance.
    """

    _app: QApplication | None = None
    _current: Theme = "dark"

    # ── Public API ────────────────────────────────────────────────────────────

    @classmethod
    def init(cls, app: QApplication, default: Theme = "dark") -> None:
        """
        Gọi một lần sau khi tạo QApplication, trước khi show window.

        Args:
            app:     QApplication instance.
            default: "dark" hoặc "light".
        """
        cls._app = app
        cls.set_theme(default)

    @classmethod
    def set_theme(cls, theme: Theme) -> None:
        """
        Áp dụng theme và refresh toàn bộ widget.

        Args:
            theme: "dark" hoặc "light".
        """
        if cls._app is None:
            raise RuntimeError(
                "ThemeManager chưa được init. Gọi ThemeManager.init(app) trước."
            )

        qss = cls._load_qss(theme)
        cls._app.setStyleSheet(qss)
        cls._current = theme

        # Force style recalculation on all top-level windows
        for w in cls._app.topLevelWidgets():
            w.style().unpolish(w)
            w.style().polish(w)
            w.update()

    @classmethod
    def toggle(cls) -> Theme:
        """
        Đổi qua lại dark ↔ light.

        Returns:
            Theme mới sau khi toggle.
        """
        new = "light" if cls._current == "dark" else "dark"
        cls.set_theme(new)
        return new

    @classmethod
    @property
    def current_theme(cls) -> Theme:
        return cls._current

    # ── Internal ──────────────────────────────────────────────────────────────

    @classmethod
    def _load_qss(cls, theme: Theme) -> str:
        filename = f"theme_{theme}.qss"
        path = os.path.join(_THEMES_DIR, filename)

        if not os.path.isfile(path):
            raise FileNotFoundError(
                f"ThemeManager: không tìm thấy file QSS tại '{path}'.\n"
                f"Hãy kiểm tra _THEMES_DIR = '{_THEMES_DIR}'"
            )

        with open(path, encoding="utf-8") as f:
            return f.read()
