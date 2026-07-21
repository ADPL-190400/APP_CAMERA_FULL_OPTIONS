import sys
from PyQt6.QtWidgets import QApplication
from pages.login import LoginPage
from ui.ui_menu.theme_manager import ThemeManager



app = QApplication(sys.argv)
login = LoginPage()
login.show()
ThemeManager.init(app, default="dark")
sys.exit(app.exec())
