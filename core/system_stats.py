"""
SystemStatsWorker: lấy chỉ số tài nguyên hệ thống (CPU/RAM/Disk/Network qua
psutil, GPU/VRAM/nhiệt độ qua `nvidia-smi` nếu máy có) cho dashboard_page.

Chạy trên QThread riêng (giống StatusCheckWorker ở core/status_checker.py) vì
psutil.cpu_percent(interval=...) và gọi subprocess nvidia-smi đều có thể mất
vài trăm ms - không nên chặn UI thread.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass

import psutil
from PyQt6.QtCore import QObject, QThread, QTimer, pyqtSignal

from core.path_manager import BASE_DIR

# shutil.which() phụ thuộc PATH của process - trên 1 số máy Linux/ARM
# (vd NVIDIA GB10/Grace Blackwell aarch64) nvidia-smi vẫn cài nhưng PATH lúc
# app khởi động (systemd service, .desktop launcher, venv activate script...)
# có thể không đủ đầy đủ như PATH của 1 shell terminal thường - dò thêm vài
# vị trí cài đặt phổ biến trên Linux làm lưới an toàn.
_NVIDIA_SMI_FALLBACK_PATHS = (
    "/usr/bin/nvidia-smi",
    "/usr/local/bin/nvidia-smi",
    "/usr/lib/wsl/lib/nvidia-smi",  # WSL2
)


def _find_nvidia_smi() -> str | None:
    found = shutil.which("nvidia-smi")
    if found:
        return found
    for path in _NVIDIA_SMI_FALLBACK_PATHS:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


_NVIDIA_SMI = _find_nvidia_smi()
_DEFAULT_POLL_INTERVAL_MS = 3000
_logged_nvidia_smi_error = False  # chỉ log lỗi 1 lần, tránh spam console mỗi 3s

NetSample = tuple[int, int, float]  # bytes_sent, bytes_recv, time.monotonic() lúc lấy mẫu


@dataclass
class SystemStats:
    cpu_percent: float
    ram_percent: float
    ram_used_gb: float
    ram_total_gb: float
    disk_percent: float
    disk_used_gb: float
    disk_total_gb: float
    disk_free_gb: float
    net_sent_mbps: float
    net_recv_mbps: float
    gpu_percent: float | None   # None nếu không có GPU NVIDIA / không có nvidia-smi
    vram_percent: float | None
    gpu_temp_c: float | None


class SystemStatsWorker(QThread):
    # (SystemStats, NetSample) - NetSample để lượt sau tính lại delta Mbps
    result_ready = pyqtSignal(object, object)

    def __init__(self, prev_net: NetSample | None, parent=None):
        super().__init__(parent)
        self._prev_net = prev_net

    def run(self) -> None:
        cpu = psutil.cpu_percent(interval=0.3)
        vmem = psutil.virtual_memory()
        drive = os.path.splitdrive(BASE_DIR)[0] + os.sep
        disk = psutil.disk_usage(drive)
        net = psutil.net_io_counters()
        now = time.monotonic()

        sent_mbps = recv_mbps = 0.0
        if self._prev_net is not None:
            prev_sent, prev_recv, prev_ts = self._prev_net
            dt = max(now - prev_ts, 0.001)
            sent_mbps = max((net.bytes_sent - prev_sent) * 8 / dt / 1_000_000, 0.0)
            recv_mbps = max((net.bytes_recv - prev_recv) * 8 / dt / 1_000_000, 0.0)

        gpu_percent, vram_percent, gpu_temp = self._query_nvidia_smi()

        stats = SystemStats(
            cpu_percent=cpu,
            ram_percent=vmem.percent,
            ram_used_gb=vmem.used / 1e9,
            ram_total_gb=vmem.total / 1e9,
            disk_percent=disk.percent,
            disk_used_gb=disk.used / 1e9,
            disk_total_gb=disk.total / 1e9,
            disk_free_gb=disk.free / 1e9,
            net_sent_mbps=sent_mbps,
            net_recv_mbps=recv_mbps,
            gpu_percent=gpu_percent,
            vram_percent=vram_percent,
            gpu_temp_c=gpu_temp,
        )
        self.result_ready.emit(stats, (net.bytes_sent, net.bytes_recv, now))

    @staticmethod
    def _query_nvidia_smi() -> tuple[float | None, float | None, float | None]:
        global _logged_nvidia_smi_error
        if not _NVIDIA_SMI:
            if not _logged_nvidia_smi_error:
                _logged_nvidia_smi_error = True
                print(
                    "[SystemStats] Không tìm thấy nvidia-smi trong PATH (đã dò thêm "
                    f"{_NVIDIA_SMI_FALLBACK_PATHS}) - GPU sẽ hiện N/A. Nếu máy có GPU "
                    "NVIDIA, chạy `nvidia-smi` trong terminal để kiểm tra đường dẫn thật, "
                    "hoặc set biến môi trường PATH bao gồm thư mục chứa nó.",
                    file=sys.stderr,
                )
            return None, None, None
        try:
            out = subprocess.run(
                [
                    _NVIDIA_SMI,
                    "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
            if out.returncode != 0:
                raise RuntimeError(f"nvidia-smi exit code {out.returncode}: {out.stderr.strip()}")
            # Nhiều GPU (đa card) -> nvidia-smi trả nhiều dòng, mỗi dòng 1 GPU;
            # chỉ lấy GPU đầu tiên (giống hành vi cũ) - tránh crash split(",")
            # nếu output có nhiều dòng thay vì đúng 1 dòng như kỳ vọng.
            first_line = out.stdout.strip().splitlines()[0]
            raw_util, raw_mem_used, raw_mem_total, raw_temp = (
                x.strip() for x in first_line.split(",")
            )

            # Trên GPU unified-memory (vd NVIDIA GB10/Grace Blackwell) memory.used
            # và memory.total trả về "[N/A]" (không tách VRAM riêng CPU/GPU) -
            # parse từng field riêng để util/temp vẫn hiện được thay vì mất hết
            # cả 3 chỉ vì memory không đọc được.
            def _parse_float(raw: str) -> float | None:
                try:
                    return float(raw)
                except ValueError:
                    return None

            util = _parse_float(raw_util)
            mem_used = _parse_float(raw_mem_used)
            mem_total = _parse_float(raw_mem_total)
            temp = _parse_float(raw_temp)
            vram_pct = (mem_used / mem_total * 100.0) if mem_used is not None and mem_total else None
            return util, vram_pct, temp
        except Exception as exc:  # noqa: BLE001 - không có GPU/driver/timeout đều coi là "không có GPU"
            if not _logged_nvidia_smi_error:
                _logged_nvidia_smi_error = True
                print(f"[SystemStats] nvidia-smi chạy được nhưng lỗi khi đọc kết quả: {exc!r} "
                      f"- GPU sẽ hiện N/A.", file=sys.stderr)
            return None, None, None


class SystemStatsMonitor(QObject):
    """Singleton đo CPU/RAM/Disk/Network/GPU MỘT lần dùng chung cho toàn app
    (top bar menu_window luôn hiển thị + System Monitor/Storage panel của
    dashboard_page) - tránh chạy 2 SystemStatsWorker song song đo trùng cùng
    1 thứ (double subprocess nvidia-smi + double psutil call mỗi chu kỳ mà
    không cần thiết). Các trang chỉ cần subscribe stats_ready + gọi start()
    (idempotent, giống DeviceManager.start_auto_status_check())."""

    _instance: "SystemStatsMonitor | None" = None

    stats_ready = pyqtSignal(object)  # SystemStats

    def __init__(self):
        super().__init__()
        self._prev_net: NetSample | None = None
        self._worker: SystemStatsWorker | None = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.latest: SystemStats | None = None

    @classmethod
    def instance(cls) -> "SystemStatsMonitor":
        if cls._instance is None:
            cls._instance = SystemStatsMonitor()
        return cls._instance

    def start(self, interval_ms: int = _DEFAULT_POLL_INTERVAL_MS) -> None:
        if not self._timer.isActive():
            self._timer.start(interval_ms)
            self._tick()  # đo ngay lần đầu, không đợi hết interval

    def refresh_now(self) -> None:
        """Ép đo lại ngay (vd bấm nút Refresh), không đợi hết chu kỳ timer."""
        self._tick()

    def _tick(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # lượt trước chưa xong -> bỏ qua lượt này, tránh chồng thread
        self._worker = SystemStatsWorker(self._prev_net)
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    def _on_result(self, stats: SystemStats, prev_net) -> None:
        self._prev_net = prev_net
        self.latest = stats
        self.stats_ready.emit(stats)
