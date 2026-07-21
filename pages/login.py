from PyQt6 import uic
from PyQt6.QtWidgets import QMainWindow, QMessageBox, QLineEdit
from pages.menu_window import MenuWindow
from scr import Web_API
from core.account_context import set_current_account
from core.known_faces_store import KnownFacesStore
from core.path_manager import BASE_DIR
import os


class LoginPage(QMainWindow):
    def __init__(self):
        super().__init__()
        ui_path = os.path.join(BASE_DIR, "ui", "login.ui")
        uic.loadUi(ui_path, self)

        self.btn_login.clicked.connect(self.login)
        self.btn_pw_state.clicked.connect(self.toggle_password_visibility)

        

    def login(self):
        entered_user = self.user_input.text()
        user = entered_user
        pw = self.pw_input.text()
        user = 'ai@gmail.com'
        pw = '123456'
        if not all([user, pw]):
            print("Có trường bị bỏ trống")
        #     QMessageBox.warning(
        #     self,
        #     "Thiếu thông tin",
        #     "Vui lòng nhập đầy đủ tài khoản và mật khẩu."
        # )
            self.show_custom_msg("Thiếu thông tin", "Vui lòng nhập đầy đủ tài khoản và mật khẩu.")
            return

        is_login = Web_API.get_api(user,pw)
        if is_login:
            # Đặt account context TRƯỚC khi MenuWindow (và các page con) được
            # tạo - DeviceManager/EventStore/gate_config chỉ thực sự load từ
            # đĩa lúc singleton .instance() được gọi lần đầu, xảy ra bên
            # trong accept_login() bên dưới. Dùng đúng "user" (email THẬT đã
            # đăng nhập), không phải "entered_user" (chỉ để hiển thị tên).
            set_current_account(user)
            self.accept_login(entered_user)
        else:
            print('Dang nhap khong thanh cong')
        #     QMessageBox.warning(
        # self,
        # "Đăng nhập thất bại",
        # "Sai tài khoản hoặc mật khẩu!\nVui lòng kiểm tra lại.)"
            self.show_custom_msg("Đăng nhập thất bại", "Sai tài khoản hoặc mật khẩu!\nKiểm tra lại kết nối hoặc thông tin.")
    

    def accept_login(self, username: str = ""):
        KnownFacesStore.instance().refresh_async()
        self.close()
        self.main = MenuWindow(username=username)
        self.main.show()

    def toggle_password_visibility(self):

        if self.btn_pw_state.isChecked():
            self.pw_input.setEchoMode(QLineEdit.EchoMode.Password)
            
        
        else:
            self.pw_input.setEchoMode(QLineEdit.EchoMode.Normal)
           

    def show_custom_msg(self, title, message, is_error=True):
        msg = QMessageBox(self)
        msg.setWindowTitle(title)
        msg.setText(message)
        
        # Modern CSS Styling
        bg_color = "#FFFFFF"
        text_color = "#333333"
        border_radius = "10px"
        button_style = """
            QPushButton {
                background-color: #4A90E2;
                color: white;
                border-radius: 5px;
                padding: 8px 20px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #357ABD;
            }
        """
        
        msg.setStyleSheet(f"""
            QMessageBox {{
                background-color: {bg_color};
                border-radius: {border_radius};
            }}
            QLabel {{
                color: {text_color};
                font-size: 14px;
                padding: 10px;
            }}
            {button_style}
        """)
        
        # Set icon based on type
        if is_error:
            msg.setIcon(QMessageBox.Icon.Critical)
        else:
            msg.setIcon(QMessageBox.Icon.Information)
            
        msg.exec()