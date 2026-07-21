import sys
from datetime import datetime

from PyQt6 import uic
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QButtonGroup, QMainWindow, QMessageBox
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from core.path_manager import BASE_DIR
from core.device_manager import DeviceManager
from core.system_stats import SystemStats, SystemStatsMonitor

from pages.dashboard_page import DashboardPage
from pages.liveview_page import LiveViewPage
from pages.device_page import DeviceManagementPage
from pages.camera_config_page import CameraConfigPage
from pages.event_log_page import EventLogPage
from pages.face_attendance_page import FaceAttendanceWindow
from pages.gate_kiosk_page import GateWindow


from ui.ui_menu.models.camera_model import CameraModel
from ui.ui_menu.controllers.grid_controller import GridController, GridMode
from ui.ui_menu.theme_manager import ThemeManager

import os

_CLOCK_TICK_MS = 1000


class MenuWindow(QMainWindow):



    def __init__(self, username: str = ""):
        super().__init__()



        ui_path = os.path.join(BASE_DIR, "ui", "menu_window.ui")
        uic.loadUi(ui_path, self)

        self.lbl_user.setText(username or "Admin")

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._on_clock_tick)
        self._clock_timer.start(_CLOCK_TICK_MS)
        self._on_clock_tick()

        # Dùng chung SystemStatsMonitor với dashboard_page - top bar này luôn
        # hiển thị bất kể đang ở trang nào nên là nơi hợp lý để khởi động
        # monitor (start() idempotent, an toàn gọi lại ở dashboard_page).
        self._stats_monitor = SystemStatsMonitor.instance()
        self._stats_monitor.stats_ready.connect(self._on_stats_ready)
        self._stats_monitor.start()
        if self._stats_monitor.latest is not None:
            self._on_stats_ready(self._stats_monitor.latest)

        self.dashboard_page = DashboardPage()
        self.liveview_page = LiveViewPage()
        self.device_page = DeviceManagementPage()
        self.camera_config_page = CameraConfigPage()
        self.event_log_page = EventLogPage()


        self.stackedPages.addWidget(self.dashboard_page)
        self.stackedPages.addWidget(self.liveview_page)
        self.stackedPages.addWidget(self.device_page)
        self.stackedPages.addWidget(self.camera_config_page)
        self.stackedPages.addWidget(self.event_log_page)


        # Bấm ⚙ ở cột Operation (device_management_page) -> mở đúng camera đó
        # trong camera_config_page.
        self.device_page.open_camera_config.connect(self._on_open_camera_config)

        # Bấm "All →" ở Event Feed (dashboard_page) -> chuyển sang EventLogPage.
        self.dashboard_page.open_event_log.connect(self._on_open_event_log)

        # Toggle dark/light mode
        self.btn_dark_mode.clicked.connect(self._on_toggle_theme)

        # "Face App" (Attendance) không phải page trong stackedPages - bấm mở
        # 1 QMainWindow riêng (kiosk nhận diện/đăng ký khuôn mặt), không
        # tham gia nav_group (không có khái niệm "đang chọn" như các trang
        # khác - đóng cửa sổ đó thì nav vẫn giữ nguyên trang hiện tại).
        self._attendance_window: FaceAttendanceWindow | None = None
        self.btn_nav_attendance.clicked.connect(self._on_open_attendance)

        # "Check In"/"Check Out" (Attendance) - 2 cửa sổ kiosk chấm công theo
        # vạch ảo, cùng dạng cửa sổ độc lập như Face App ở trên (không phải
        # page trong stackedPages, mỗi cửa sổ tự mở 1 camera riêng).
        self._checkin_window: GateWindow | None = None
        self._checkout_window: GateWindow | None = None
        self.btn_nav_checkin.clicked.connect(self._on_open_checkin)
        self.btn_nav_checkout.clicked.connect(self._on_open_checkout)

        self.nav_pages = {
            self.btn_nav_dashboard: self.dashboard_page,
            self.btn_nav_liveview: self.liveview_page,
            self.btn_nav_device_management: self.device_page,
            self.btn_nav_camera_config: self.camera_config_page,
            self.btn_nav_event_log: self.event_log_page,
        }

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        for btn in list(self.nav_pages.keys()) :
            self.nav_group.addButton(btn)
            btn.clicked.connect(self._on_nav_clicked)

        # Trang mặc định khi mở app
        self.btn_nav_dashboard.setChecked(True)
        self.stackedPages.setCurrentWidget(self.dashboard_page)

        

     

        self.show()
        
    

    # ── Top bar: clock + CPU/RAM/GPU ────────────────────────────────────────

    def _on_clock_tick(self) -> None:
        self.lbl_datetime.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

    def _on_stats_ready(self, stats: SystemStats) -> None:
        self.lbl_cpu_usage.setText(f"CPU: {stats.cpu_percent:.0f}%")
        self.lbl_ram_usage.setText(f"RAM: {stats.ram_used_gb:.1f} GB")
        if stats.gpu_percent is not None:
            self.lbl_gpu_usage.setText(f"GPU: {stats.gpu_percent:.0f}%")
        else:
            self.lbl_gpu_usage.setText("GPU: N/A")

    # ── Theme ──────────────────────────────────────────────────────────────

    def _on_toggle_theme(self) -> None:
        new_theme = ThemeManager.toggle()
        # Update button icon to reflect current state
        self.btn_dark_mode.setText("🌙" if new_theme == "dark" else "☀")
        print(f"[Theme] Switched to {new_theme}")

    # ── Navigation ───────────────────────────────────────────────────────

    def _on_nav_clicked(self) -> None:
        btn = self.sender()
        if btn is None:
            return
        page = self.nav_pages.get(btn)
        if page is not None:
            self.stackedPages.setCurrentWidget(page)

    def _on_open_camera_config(self, device_id: str) -> None:
        """Nhận signal device_management_page.open_camera_config(device_id)
        (bấm ⚙ ở cột Operation) -> chuyển sang camera_config_page và load
        đúng camera đó lên form."""
        self.camera_config_page.load_device(device_id)
        self.stackedPages.setCurrentWidget(self.camera_config_page)
        self.btn_nav_camera_config.setChecked(True)

    def _on_open_event_log(self) -> None:
        """Nhận signal dashboard_page.open_event_log (bấm "All →" ở Event
        Feed) -> chuyển sang event_log_page."""
        self.event_log_page.reload_events()
        self.stackedPages.setCurrentWidget(self.event_log_page)
        self.btn_nav_event_log.setChecked(True)

    def _on_open_attendance(self) -> None:
        """Bấm "🪪 Face App" (sidebar, mục ATTENDANCE) -> mở cửa sổ kiosk
        nhận diện/đăng ký khuôn mặt. Giữ instance trên self để không bị GC
        (QMainWindow không có parent giữ ref) và để bấm lại chỉ đưa cửa sổ
        đã mở lên trước thay vì tạo thêm cửa sổ mới (mỗi cửa sổ tự mở 1
        webcam - mở nhiều lần cùng lúc sẽ tranh giành camera)."""
        if self._attendance_window is None:
            self._attendance_window = FaceAttendanceWindow(self)
        self._attendance_window.show()
        self._attendance_window.raise_()
        self._attendance_window.activateWindow()

    def _on_open_checkin(self) -> None:
        """Bấm "🟢 Check In" (sidebar, mục ATTENDANCE) -> mở cửa sổ kiosk
        chấm công vào bằng vạch ảo. Giữ instance trên self để không bị GC và
        để bấm lại chỉ đưa cửa sổ đã mở lên trước (mỗi cửa sổ tự giữ 1
        camera riêng - mở nhiều lần cùng lúc sẽ tranh giành camera)."""
        if self._checkin_window is None:
            self._checkin_window = GateWindow(direction="in", parent=self)
        self._checkin_window.show()
        self._checkin_window.raise_()
        self._checkin_window.activateWindow()

    def _on_open_checkout(self) -> None:
        """Bấm "🔴 Check Out" (sidebar, mục ATTENDANCE) -> mở cửa sổ kiosk
        chấm công ra bằng vạch ảo. Xem docstring _on_open_checkin."""
        if self._checkout_window is None:
            self._checkout_window = GateWindow(direction="out", parent=self)
        self._checkout_window.show()
        self._checkout_window.raise_()
        self._checkout_window.activateWindow()

    # ── Shutdown ─────────────────────────────────────────────────────────
    def closeEvent(self, event) -> None:
        # Dừng sạch mọi pipeline camera (capture + AI) đang chạy nền trước
        # khi thoát, tránh cảnh báo/crash do QThread bị huỷ khi đang chạy.
        DeviceManager.instance().shutdown()
        super().closeEvent(event)

