"""
Controller cho dashboard_page.ui - trang tổng quan hệ thống: KPI camera/AI/
tài nguyên máy, tình trạng từng camera (Camera Health), tình trạng từng model
AI (AI Status), Event Feed hợp nhất (Alarms/AI Events/System/Camera), và
toolbar hành động nhanh (Refresh / Restart Cameras / Emergency Stop AI).

Trang này KHÔNG tự giữ dữ liệu camera - mọi thứ đọc qua DeviceManager.instance()
và AIModelManager.instance(), giống mọi trang khác trong app. Tài nguyên máy
(CPU/RAM/Disk/Network/GPU) lấy qua core/system_stats.py, chạy nền QThread vì
psutil + nvidia-smi có thể mất vài trăm ms.
"""
from __future__ import annotations

import dataclasses
import os
import time
from datetime import datetime

from PyQt6 import uic, QtWidgets
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMessageBox, QTableWidgetItem, QListWidgetItem, QHeaderView

from core.ai_model_manager import AIModelManager
from core.device_manager import DeviceManager
from core.event_dedup import PresenceDedup
from core.models.camera_device import CameraDevice, DeviceStatus
from core.path_manager import BASE_DIR
from core.system_stats import SystemStats, SystemStatsMonitor

# Cột bảng Camera Health (đúng thứ tự cột trong .ui)
COL_HEALTH_CAMERA = 0
COL_HEALTH_STATUS = 1
COL_HEALTH_STREAM = 2
COL_HEALTH_AI = 3
COL_HEALTH_REC = 4
COL_HEALTH_FPS = 5
COL_HEALTH_HEARTBEAT = 6

# Cột bảng AI Status (Model/Status/Active Cameras/GPU %/Last ms)
COL_AI_MODEL = 0
COL_AI_STATUS = 1
COL_AI_ACTIVE_CAMS = 2
COL_AI_GPU = 3
COL_AI_LAST_MS = 4

_STATUS_COLOR = {
    DeviceStatus.ONLINE: "#2e7d32",
    DeviceStatus.OFFLINE: "#9e9e9e",
    DeviceStatus.ERROR: "#c62828",
    DeviceStatus.UNKNOWN: "#9e9e9e",
}

# key (khớp AIModelManager.loaded_status()/latency_ms()) -> tên hiển thị
_AI_MODEL_ROWS = [
    ("human", "Human Detection"),
    ("pose", "Body / Pose (Fall)"),
    ("ppe", "PPE Detection"),
    ("fire", "Fire Detection"),
    ("fall", "Fall Detection"),
    ("face", "Face Recognition"),
]

# Nhãn cảnh báo - khớp field trong dict do CameraPipeline.ai_result_ready phát ra.
_ALARM_KINDS = [
    ("ppe_violation", "⚠ PPE vi phạm"),
    ("fire_alert", "🔥 Cháy"),
    ("fall_alert", "🚨 Té ngã"),
    ("stranger_alert", "🧑‍❓ Người lạ"),
]

_PRESENCE_GRACE_SEC = 5.0   # giống liveview_page.py - tránh Event Feed nhảy text liên tục
_MAX_EVENTS = 200
_STATS_POLL_INTERVAL_MS = 3000


class DashboardPage(QtWidgets.QWidget):
    open_event_log = pyqtSignal()  # bấm "All →" ở Event Feed -> MenuWindow chuyển sang EventLogPage

    def __init__(self):
        super().__init__()
        ui_path = os.path.join(BASE_DIR, "ui", "dashboard_page.ui")
        uic.loadUi(ui_path, self)

        self.device_manager = DeviceManager.instance()
        self.ai_manager = AIModelManager.instance()

        # device_id -> monotonic() lần cuối thấy device.status == ONLINE (Heartbeat).
        self._last_online_seen: dict[str, float] = {}
        # (device_id, alarm_kind) -> đang active hay không NGAY LÚC NÀY (cho KPI
        # "Active Alarms" - khác Event Feed vốn chỉ log 1 lần/đợt).
        self._current_alarm_state: dict[tuple[str, str], bool] = {}
        self._alarm_dedup = PresenceDedup(_PRESENCE_GRACE_SEC)
        self._detection_dedup = PresenceDedup(_PRESENCE_GRACE_SEC)

        # Event Feed: lưu toàn bộ (bất kể filter đang chọn), render lại theo
        # combo_event_filter mỗi khi có sự kiện mới hoặc đổi filter.
        self._events: list[tuple[datetime, str, str]] = []  # (thời điểm, category, text)

        self._latest_stats: SystemStats | None = None

        self._setup_tables()
        self._connect_signals()

        # Định kỳ Online/Offline chưa từng được bật ở đâu trong app trước đây -
        # Dashboard là trang mặc định khi mở app nên là nơi hợp lý để bật (an
        # toàn khi gọi nhiều lần từ nhiều trang - DeviceManager tự chặn trùng).
        self.device_manager.start_auto_status_check()

        # Dùng chung SystemStatsMonitor với menu_window (top bar) - tránh 2
        # nơi cùng tự chạy SystemStatsWorker đo trùng CPU/RAM/GPU (start()
        # idempotent, an toàn gọi từ nhiều trang).
        self._stats_monitor = SystemStatsMonitor.instance()
        self._stats_monitor.stats_ready.connect(self._on_stats_ready)
        self._stats_monitor.start(_STATS_POLL_INTERVAL_MS)
        if self._stats_monitor.latest is not None:
            self._on_stats_ready(self._stats_monitor.latest)

        self._refresh_camera_dependent_ui()

    # ------------------------------------------------------------------ #
    # Khởi tạo
    # ------------------------------------------------------------------ #
    def _setup_tables(self) -> None:
        self.table_camera_health.horizontalHeader().setSectionResizeMode(
            COL_HEALTH_CAMERA, QHeaderView.ResizeMode.Stretch
        )
        self.table_ai_status.horizontalHeader().setSectionResizeMode(
            COL_AI_MODEL, QHeaderView.ResizeMode.Stretch
        )

    def _connect_signals(self) -> None:
        dm = self.device_manager
        dm.devices_changed.connect(self._refresh_camera_dependent_ui)
        dm.device_status_changed.connect(self._on_device_status_changed)
        dm.device_running_changed.connect(self._on_device_running_changed)
        dm.device_added.connect(self._on_device_added)
        dm.device_removed.connect(self._on_device_removed)
        dm.ai_result_ready.connect(self._on_ai_result)

        self.combo_event_filter.currentIndexChanged.connect(lambda _i: self._render_event_feed())
        self.btn_clear_event_feed.clicked.connect(self._on_clear_events)
        self.btn_open_event_log.clicked.connect(self._on_open_event_log)

        self.btn_refresh_dashboard.clicked.connect(self._on_refresh_clicked)
        self.btn_restart_all_camera.clicked.connect(self._on_restart_all_clicked)
        self.btn_emergency_stop_ai.clicked.connect(self._on_emergency_stop_clicked)

    # ------------------------------------------------------------------ #
    # Signal từ DeviceManager - Event Feed (System / Camera) + refresh
    # ------------------------------------------------------------------ #
    def _on_device_status_changed(self, device_id: str, status: str) -> None:
        device = self.device_manager.get_device(device_id)
        name = device.name if device else device_id
        self._append_event("System", f"{name}: → {status}")
        self._refresh_camera_dependent_ui()

    def _on_device_running_changed(self, device_id: str, is_running: bool) -> None:
        device = self.device_manager.get_device(device_id)
        name = device.name if device else device_id
        self._append_event("Camera", f"{name}: {'Started' if is_running else 'Stopped'}")
        self._refresh_camera_dependent_ui()

    def _on_device_added(self, device_id: str) -> None:
        device = self.device_manager.get_device(device_id)
        name = device.name if device else device_id
        self._append_event("System", f"{name}: Đã thêm camera mới")

    def _on_device_removed(self, device_id: str) -> None:
        self._last_online_seen.pop(device_id, None)
        self._append_event("System", f"{device_id}: Đã xoá camera")

    # ------------------------------------------------------------------ #
    # ai_result_ready - KPI "Active Alarms" (trạng thái NGAY LÚC NÀY) + Event
    # Feed Alarms/AI Events (dedup, chỉ log 1 lần/đợt).
    # ------------------------------------------------------------------ #
    def _on_ai_result(self, device_id: str, result: dict) -> None:
        for key, _label in _ALARM_KINDS:
            self._current_alarm_state[(device_id, key)] = bool(result.get(key))

        device = self.device_manager.get_device(device_id)
        name = device.name if device else device_id

        for key, label in _ALARM_KINDS:
            if result.get(key) and self._alarm_dedup.is_new_occurrence((device_id, key)):
                self._append_event("Alarms", f"{name}: {label}")

        for known_name in result.get("known_faces", []):
            if self._detection_dedup.is_new_occurrence((device_id, known_name)):
                self._append_event("AI Events", f"{name}: Nhận diện {known_name}")

        self._refresh_alarm_kpi()

    def _refresh_alarm_kpi(self) -> None:
        count = sum(1 for active in self._current_alarm_state.values() if active)
        self.lbl_alarm_value.setText(str(count))
        self.lbl_alarm_status.setText("🔴 Đang có cảnh báo" if count else "No alarms")

    # ------------------------------------------------------------------ #
    # Event Feed
    # ------------------------------------------------------------------ #
    def _append_event(self, category: str, text: str) -> None:
        self._events.append((datetime.now(), category, text))
        if len(self._events) > _MAX_EVENTS:
            self._events.pop(0)
        self._render_event_feed()
        self.lbl_total_events_today.setText(f"Events Today: {len(self._events)}")

    def _render_event_feed(self) -> None:
        selected = self.combo_event_filter.currentText()
        self.list_event_feed.clear()
        for ts, category, text in reversed(self._events):
            if selected != "All Events" and category != selected:
                continue
            item = QListWidgetItem(f"[{ts.strftime('%H:%M:%S')}] {text}")
            if category == "Alarms":
                item.setForeground(QColor("#ff5555"))
            self.list_event_feed.addItem(item)

    def _on_clear_events(self) -> None:
        self._events.clear()
        self._alarm_dedup.clear()
        self._detection_dedup.clear()
        self._render_event_feed()
        self.lbl_total_events_today.setText("Events Today: 0")

    def _on_open_event_log(self) -> None:
        self.open_event_log.emit()

    # ------------------------------------------------------------------ #
    # KPI camera / Camera Health / AI Status / toolbar - đọc trực tiếp từ
    # DeviceManager, không cần thread (rẻ, chỉ là duyệt list in-memory).
    # ------------------------------------------------------------------ #
    def _refresh_camera_dependent_ui(self, *_args) -> None:
        devices = self.device_manager.all_devices()
        now = time.monotonic()
        for device in devices:
            if device.status == DeviceStatus.ONLINE:
                self._last_online_seen[device.id] = now

        total = len(devices)
        online = sum(1 for d in devices if d.status == DeviceStatus.ONLINE)
        running = [d for d in devices if d.is_running]
        ai_active = [d for d in running if d.ai.enabled]
        recording = [d for d in running if d.recording.enabled]
        ip_count = sum(1 for d in devices if d.device_type.value == "IP")

        self.lbl_total_camera_value.setText(str(total))
        self.lbl_total_camera_status.setText(f"{ip_count} IP · {total - ip_count} USB" if total else "—")

        self.lbl_online_camera_value.setText(str(online))
        self.lbl_online_camera_status.setText(f"{total - online} offline" if total else "—")

        self.lbl_ai_active_value.setText(str(len(ai_active)))
        self.lbl_ai_active_status.setText(f"của {len(running)} đang chạy" if running else "—")

        self.lbl_active_streams_value.setText(str(len(running)))
        self.lbl_active_streams_status.setText("camera đang stream" if running else "—")

        self.lbl_recording_value.setText(str(len(recording)))
        self.lbl_recording_status.setText(
            f"{len(recording)} camera đã cấu hình ghi hình" if recording else "Không có"
        )

        is_engine_running = bool(ai_active)
        self.lbl_ai_engine_status_bar.setText(f"AI Engine: {'Running' if is_engine_running else 'Idle'}")
        self.lbl_ai_engine_status.setText("● Running" if is_engine_running else "● Idle")
        self.lbl_camera_thread_count.setText(f"Threads: {len(running)}")
        self.lbl_status_active_streams.setText(f"Streams: {len(running)}")

        self._reload_camera_health_table(devices)
        self._reload_ai_status_table(devices)
        self._refresh_alarm_kpi()

    def _reload_camera_health_table(self, devices: list[CameraDevice]) -> None:
        table = self.table_camera_health
        table.setSortingEnabled(False)  # tránh bảng tự sắp xếp lại giữa lúc đang chèn từng dòng
        table.setRowCount(0)
        online_count = 0
        for device in devices:
            if device.status == DeviceStatus.ONLINE:
                online_count += 1
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, COL_HEALTH_CAMERA, QTableWidgetItem(device.name))

            status_item = QTableWidgetItem(device.status.value)
            status_item.setForeground(Qt.GlobalColor.white)
            status_item.setBackground(QColor(_STATUS_COLOR.get(device.status, "#9e9e9e")))
            table.setItem(row, COL_HEALTH_STATUS, status_item)

            table.setItem(row, COL_HEALTH_STREAM, QTableWidgetItem("Running" if device.is_running else "Stopped"))
            table.setItem(
                row, COL_HEALTH_AI,
                QTableWidgetItem("ON" if device.is_running and device.ai.enabled else "OFF"),
            )
            table.setItem(
                row, COL_HEALTH_REC,
                QTableWidgetItem("ON" if device.is_running and device.recording.enabled else "OFF"),
            )
            table.setItem(row, COL_HEALTH_FPS, QTableWidgetItem(str(device.fps) if device.is_running else "—"))
            table.setItem(row, COL_HEALTH_HEARTBEAT, QTableWidgetItem(self._heartbeat_text(device)))
        table.setSortingEnabled(True)

        self.lbl_online_camera_count.setText(f"Online: {online_count} / {len(devices)}")

    def _heartbeat_text(self, device: CameraDevice) -> str:
        if device.status == DeviceStatus.ONLINE:
            return "just now"
        last_seen = self._last_online_seen.get(device.id)
        if last_seen is None:
            return "—"
        elapsed = int(time.monotonic() - last_seen)
        return f"{elapsed}s ago" if elapsed < 60 else f"{elapsed // 60}m ago"

    def _reload_ai_status_table(self, devices: list[CameraDevice]) -> None:
        loaded = self.ai_manager.loaded_status()
        running_ai_devices = [d for d in devices if d.is_running and d.ai.enabled]
        gpu_pct = self._latest_stats.gpu_percent if self._latest_stats else None
        gpu_text = f"{gpu_pct:.0f}%" if gpu_pct is not None else "—"

        table = self.table_ai_status
        table.setRowCount(0)
        for key, label in _AI_MODEL_ROWS:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, COL_AI_MODEL, QTableWidgetItem(label))

            is_loaded = loaded.get(key, False)
            status_item = QTableWidgetItem("Loaded" if is_loaded else "Not loaded")
            status_item.setForeground(QColor("#2e7d32" if is_loaded else "#9e9e9e"))
            table.setItem(row, COL_AI_STATUS, status_item)

            active_count = sum(1 for d in running_ai_devices if self._uses_model(d, key))
            table.setItem(row, COL_AI_ACTIVE_CAMS, QTableWidgetItem(str(active_count)))
            table.setItem(row, COL_AI_GPU, QTableWidgetItem(gpu_text if is_loaded else "—"))

            latency = self.ai_manager.latency_ms(key)
            table.setItem(row, COL_AI_LAST_MS, QTableWidgetItem(f"{latency:.0f}" if latency is not None else "—"))

    @staticmethod
    def _uses_model(device: CameraDevice, key: str) -> bool:
        # Đếm vào/ra, Occupancy, PPE dùng human.pt (bbox-only); Fall là
        # tính năng DUY NHẤT còn dùng pose model (keypoints) - khớp
        # CameraPipeline._run_ai (need_person vs need_pose).
        ai = device.ai
        if key == "human":
            return ai.enable_counting or ai.enable_occupancy or ai.enable_ppe
        if key == "pose":
            return ai.enable_fall
        if key == "face":
            return ai.enable_face_recognition
        return getattr(ai, f"enable_{key}")

    # ------------------------------------------------------------------ #
    # System stats (CPU/RAM/Disk/Network/GPU) - đo dùng chung qua
    # SystemStatsMonitor (singleton), không tự chạy SystemStatsWorker riêng.
    # ------------------------------------------------------------------ #
    def _on_stats_ready(self, stats: SystemStats) -> None:
        self._latest_stats = stats
        self._apply_system_stats(stats)
        # "GPU %" ở bảng AI Status phụ thuộc _latest_stats -> vẽ lại bảng đó.
        self._reload_ai_status_table(self.device_manager.all_devices())

    def _apply_system_stats(self, stats: SystemStats) -> None:
        # --- KPI: CPU / RAM / GPU / Network ---
        self.progress_cpu_card.setValue(int(stats.cpu_percent))
        self.lbl_cpu_value.setText(f"{stats.cpu_percent:.0f}%")
        self.lbl_cpu_status.setText("Cao" if stats.cpu_percent >= 80 else "Bình thường")

        self.progress_ram_card.setValue(int(stats.ram_percent))
        self.lbl_ram_value.setText(f"{stats.ram_percent:.0f}%")
        self.lbl_ram_status.setText(f"{stats.ram_used_gb:.1f} / {stats.ram_total_gb:.1f} GB")

        if stats.gpu_percent is not None:
            self.progress_gpu_usage.setValue(int(stats.gpu_percent))
            self.lbl_gpu_value.setText(f"{stats.gpu_percent:.0f}%")
            self.lbl_gpu_status.setText(
                f"{stats.vram_percent:.0f}% VRAM" if stats.vram_percent is not None else "—"
            )
        else:
            self.progress_gpu_usage.setValue(0)
            self.lbl_gpu_value.setText("N/A")
            self.lbl_gpu_status.setText("No GPU")

        total_mbps = stats.net_sent_mbps + stats.net_recv_mbps
        self.lbl_network_value.setText(f"{total_mbps:.1f} Mbps")
        self.lbl_network_status.setText(f"↑ {stats.net_sent_mbps:.1f}  ↓ {stats.net_recv_mbps:.1f}")

        # --- System Monitor frame ---
        self.progress_cpu_usage.setValue(int(stats.cpu_percent))
        self.lbl_cpu_pct.setText(f"{stats.cpu_percent:.0f}%")

        if stats.gpu_percent is not None:
            self.progress_gpu_sysmon.setValue(int(stats.gpu_percent))
            self.lbl_gpu_pct.setText(f"{stats.gpu_percent:.0f}%")
        else:
            self.progress_gpu_sysmon.setValue(0)
            self.lbl_gpu_pct.setText("—")

        self.progress_ram_usage.setValue(int(stats.ram_percent))
        self.lbl_ram_pct.setText(f"{stats.ram_percent:.0f}%")

        if stats.vram_percent is not None:
            self.progress_vram_usage.setValue(int(stats.vram_percent))
            self.lbl_vram_pct.setText(f"{stats.vram_percent:.0f}%")
        else:
            self.progress_vram_usage.setValue(0)
            self.lbl_vram_pct.setText("—")

        self.progress_disk_usage.setValue(int(stats.disk_percent))
        self.lbl_disk_pct.setText(f"{stats.disk_percent:.0f}%")
        self.lbl_temperature.setText(f"{stats.gpu_temp_c:.0f} °C" if stats.gpu_temp_c is not None else "— °C")
        self.lbl_network_speed.setText(f"↑{stats.net_sent_mbps:.1f} ↓{stats.net_recv_mbps:.1f} Mbps")

        # --- Storage panel ---
        self.progress_disk_usage_detail.setValue(int(stats.disk_percent))
        self.lbl_disk_used_value.setText(f"{stats.disk_used_gb:.0f} GB / {stats.disk_total_gb:.0f} GB")
        self.lbl_total_storage_value.setText(f"{stats.disk_total_gb:.0f} GB")
        self.lbl_used_storage_value.setText(f"{stats.disk_used_gb:.0f} GB")
        self.lbl_free_space_value.setText(f"{stats.disk_free_gb:.0f} GB")

        recording_count = sum(1 for d in self.device_manager.all_devices() if d.is_running and d.recording.enabled)
        self.lbl_recording_status_value.setText(
            f"{recording_count} camera đang ghi" if recording_count else "Không có camera nào ghi"
        )
        # lbl_remaining_days: chưa có VideoWriter thật (recording.enabled chỉ
        # là cấu hình) -> không có tốc độ ghi thật để ước tính, để "—" thay vì đoán.

    # ------------------------------------------------------------------ #
    # Toolbar: Refresh / Restart Cameras / Emergency Stop AI
    # ------------------------------------------------------------------ #
    def _on_refresh_clicked(self) -> None:
        self._stats_monitor.refresh_now()
        self._refresh_camera_dependent_ui()

    def _on_restart_all_clicked(self) -> None:
        running_ids = [d.id for d in self.device_manager.all_devices() if d.is_running]
        if not running_ids:
            QMessageBox.information(self, "Restart Cameras", "Không có camera nào đang chạy.")
            return
        confirm = QMessageBox.question(
            self, "Restart Cameras", f"Khởi động lại {len(running_ids)} camera đang chạy?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        self.device_manager.stop_devices(running_ids)
        self.device_manager.start_devices(running_ids)

    def _on_emergency_stop_clicked(self) -> None:
        targets = [d for d in self.device_manager.all_devices() if d.is_running and d.ai.enabled]
        if not targets:
            QMessageBox.information(self, "Emergency Stop", "Không có camera nào đang bật AI.")
            return
        confirm = QMessageBox.question(
            self, "Emergency Stop AI",
            f"Tắt AI trên {len(targets)} camera đang chạy?\n"
            "(Camera vẫn tiếp tục stream, chỉ tắt xử lý AI - không dừng hẳn camera.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        for device in targets:
            self.device_manager.update_device(device.id, ai=dataclasses.replace(device.ai, enabled=False))
