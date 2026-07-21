"""
Model dữ liệu cho 1 camera (IP hoặc USB).
Dùng chung cho device_management_page, camera_config_page và mọi trang khác
=> tất cả các trang đọc/ghi cùng 1 kiểu dữ liệu, tránh lệch field.

File này cũng chứa các sub-config tương ứng với từng TAB trong
camera_config_page.ui (AI, Recording, Overlay, Advanced) và 2 danh sách
ROI / Trigger Rule.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields
from enum import Enum
import re
import uuid


class DeviceType(str, Enum):
    IP = "IP"
    USB = "USB"


class DeviceStatus(str, Enum):
    ONLINE = "Online"
    OFFLINE = "Offline"
    ERROR = "Error"
    UNKNOWN = "Unknown"


# --------------------------------------------------------------------- #
# Tab: AI
# --------------------------------------------------------------------- #
@dataclass
class AIConfig:
    enabled: bool = False
    ai_fps_limit: int = 10
    # Camera có thể chọn NHIỀU tính năng AI cùng lúc (không phải 1 model duy
    # nhất) - mỗi cờ bật/tắt 1 tính năng độc lập ở CameraPipeline. Đếm vào/ra
    # cần vẽ Counting Line, Occupancy/PPE cần vẽ ít nhất 1 ROI (tab ROI) -
    # thiếu thì tính năng đó chỉ đơn giản không chạy (không lỗi).
    enable_counting: bool = False
    enable_occupancy: bool = False
    enable_ppe: bool = False
    enable_fire: bool = False
    enable_fall: bool = False
    enable_face_recognition: bool = False
    # Kích thước ảnh đưa vào model YOLO (pose/ppe/fire/fall) - độc lập với
    # resolution gốc/hiển thị. Giảm xuống Fast/Balanced để tăng tốc khi chạy
    # nhiều camera AI cùng lúc (đổi lại độ chính xác giảm nhẹ với người/vật
    # nhỏ/xa) - xem parse_inference_imgsz().
    inference_quality: str = "Balanced (480px - khuyến nghị)"


# --------------------------------------------------------------------- #
# Tab: ROI (mỗi vùng lưu dạng text toạ độ đơn giản, ROI Editor trực quan
# sẽ được làm riêng sau, ở đây chỉ lưu/đọc dữ liệu)
# --------------------------------------------------------------------- #
@dataclass
class ROIRegion:
    name: str = "ROI 1"
    points: str = ""  # ví dụ: "10,10;100,10;100,100;10,100"


def parse_preview_max_width(resolution: str) -> int:
    """Đọc số đầu tiên trước dấu '×' trong CameraDevice.resolution (vd
    "1920×1080  (1080p)" -> 1920) - dùng làm giới hạn chiều rộng khi
    CameraPipeline downscale frame TRƯỚC KHI hiển thị (không ảnh hưởng frame
    AI dùng để detect, vẫn chạy trên frame gốc full-res).

    Trước đây field "resolution" chỉ là UI chết (không set gì vào
    cv2.VideoCapture - với RTSP/IP camera, việc đó cũng không có tác dụng vì
    resolution do camera phía server quyết định). Ở đây đổi ý nghĩa thực tế
    của nó thành "giới hạn độ phân giải HIỂN THỊ tối đa" - cách duy nhất thực
    sự giảm được lag khi xem camera có resolution gốc rất cao (4K...) mà
    không cần đổi gì phía camera.

    Không parse được (chuỗi lạ) -> trả về 0 (không giới hạn)."""
    try:
        return int(resolution.split("×", 1)[0].strip())
    except (ValueError, IndexError, AttributeError):
        return 0


def parse_resolution_wh(resolution: str) -> tuple[int, int] | None:
    """Đọc "WxH" từ CameraDevice.resolution (vd "1280×720   (720p)" ->
    (1280, 720)) - dùng để yêu cầu camera USB capture ĐÚNG độ phân giải này
    qua cv2.CAP_PROP_FRAME_WIDTH/HEIGHT (xem CameraPipeline._open_capture).
    Chỉ có tác dụng cho USB - camera IP/RTSP do phía server quyết định
    resolution, set property này trên client không có tác dụng gì.

    Không parse được (chuỗi lạ) -> trả về None."""
    match = re.match(r"\s*(\d+)\D+(\d+)", resolution or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


# Preset tốc độ/độ chính xác AI - key khớp (không phân biệt hoa/thường) với
# 1 phần trong chuỗi AIConfig.inference_quality hiển thị ở combobox tab AI.
_INFERENCE_IMGSZ_PRESETS = {"fast": 320, "balanced": 480, "accurate": 640}


def parse_inference_imgsz(inference_quality: str) -> int:
    """Đọc mức Fast/Balanced/Accurate từ AIConfig.inference_quality (vd
    "Balanced (480px - khuyến nghị)" -> 480) - dùng làm tham số imgsz khi gọi
    model YOLO (pose/ppe/fire/fall) trong AIModelManager, độc lập hoàn toàn
    với resolution gốc/preview - chỉ ảnh hưởng bước resize nội bộ trước khi
    đưa vào model. Giảm xuống Fast/Balanced tăng tốc đáng kể (đo thực tế:
    yolov8x-pose ~41ms ở 640px -> ~28ms ở 480px -> ~17ms ở 320px trên GTX
    1660 Ti), đổi lại độ chính xác giảm nhẹ với người/vật nhỏ hoặc ở xa.

    Không parse được (chuỗi lạ) -> mặc định 480 (Balanced), an toàn hợp lý."""
    text = (inference_quality or "").lower()
    for name, size in _INFERENCE_IMGSZ_PRESETS.items():
        if name in text:
            return size
    return 480


def parse_points(text: str) -> list[tuple[int, int]]:
    """Parse chuỗi toạ độ 'x1,y1;x2,y2;...' (định dạng dùng chung bởi
    ROIRegion.points và CameraDevice.counting_line) -> list[(x, y)]. Bỏ qua
    phần tử không hợp lệ thay vì raise lỗi, vì đây là text người dùng tự gõ."""
    points: list[tuple[int, int]] = []
    for part in text.split(";"):
        part = part.strip()
        if not part:
            continue
        try:
            x_str, y_str = part.split(",")
            points.append((int(float(x_str)), int(float(y_str))))
        except ValueError:
            continue
    return points


# --------------------------------------------------------------------- #
# Tab: Trigger
# --------------------------------------------------------------------- #
@dataclass
class TriggerRule:
    name: str = "Rule 1"
    condition: str = ""   # ví dụ: "person count > 0 in ROI-1"
    action: str = ""      # ví dụ: "send notification + record 10s"


# --------------------------------------------------------------------- #
# Tab: Recording
# --------------------------------------------------------------------- #
@dataclass
class RecordingConfig:
    enabled: bool = False
    mode: str = "Continuous"
    save_path: str = ""
    retention_days: int = 30


# --------------------------------------------------------------------- #
# Tab: Overlay
# --------------------------------------------------------------------- #
@dataclass
class OverlayConfig:
    show_bbox: bool = True
    show_label: bool = True
    show_confidence: bool = False
    show_roi: bool = False
    show_tracking_id: bool = False


# --------------------------------------------------------------------- #
# Tab: Advanced
# --------------------------------------------------------------------- #
@dataclass
class AdvancedConfig:
    frame_queue_size: int = 32
    reconnect_timeout: int = 10
    decoder_backend: str = "CPU (FFmpeg)"
    hw_accel: bool = False
    gpu_device: str = "GPU 0 (default)"


@dataclass
class CameraDevice:
    # --- Định danh ---
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = "New Camera"
    device_type: DeviceType = DeviceType.IP
    vendor: str = "Unknown"

    # --- Kết nối ---
    ip_address: str = ""          # rỗng nếu là USB
    port: int = 554
    usb_index: int = 0            # chỉ dùng khi device_type == USB
    stream_url: str = ""          # rtsp://... hoặc để trống nếu USB
    substream_url: str = ""       # luồng phụ độ phân giải thấp (tuỳ chọn) - xem pipeline_source()
    use_substream: bool = True    # tick/bỏ tick để chuyển mainstream<->substream mà không mất URL đã lưu
    serial_no: str = ""
    mac_address: str = ""          # chỉ có với camera IP - tự lấy khi "Online Device" quét thấy (ARP)

    # --- Cấu hình stream (tab Basic) ---
    resolution: str = "1920×1080  (1080p)"
    fps: int = 25

    # --- Trạng thái runtime ---
    status: DeviceStatus = DeviceStatus.UNKNOWN   # kết nối được hay không (auto check)
    is_running: bool = False                       # đang start hay stop (không lưu qua phiên)

    # --- Cấu hình từng tab ---
    ai: AIConfig = field(default_factory=AIConfig)
    recording: RecordingConfig = field(default_factory=RecordingConfig)
    overlay: OverlayConfig = field(default_factory=OverlayConfig)
    advanced: AdvancedConfig = field(default_factory=AdvancedConfig)
    roi_regions: list[ROIRegion] = field(default_factory=list)
    trigger_rules: list[TriggerRule] = field(default_factory=list)
    counting_line: str = ""  # đúng 2 điểm "x1,y1;x2,y2" - dùng đếm người vào/ra

    def display_source(self) -> str:
        """Chuỗi hiển thị nguồn video, dùng khi start camera thực tế (cv2, ...)."""
        if self.device_type == DeviceType.USB:
            return str(self.usb_index)
        return self.stream_url or self.ip_address

    def pipeline_source(self) -> str:
        """Nguồn video CameraPipeline THỰC SỰ dùng để capture (khác
        display_source() vốn dùng để hiển thị/validate cấu hình) - ưu tiên
        substream_url nếu có cấu hình VÀ use_substream đang bật (chỉ áp dụng
        camera IP) để giảm băng thông + CPU decode, vì AI đã tự resize frame
        xuống <=640px trước khi đưa vào model nên không cần decode mainstream
        độ phân giải cao. use_substream cho phép tạm chuyển về mainstream mà
        KHÔNG cần xoá substream_url đã lưu - bỏ tick là dùng lại
        display_source() ngay. Không có substream_url -> dùng display_source()
        (mainstream/USB) như cũ, không đổi hành vi mặc định."""
        if self.device_type != DeviceType.USB and self.use_substream and self.substream_url.strip():
            return self.substream_url.strip()
        return self.display_source()

    def field_names(self) -> list[str]:
        return [f.name for f in fields(self)]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["device_type"] = self.device_type.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "CameraDevice":
        d = dict(d)
        d["device_type"] = DeviceType(d.get("device_type", "IP"))
        d["status"] = DeviceStatus(d.get("status", "Unknown"))

        if isinstance(d.get("ai"), dict):
            # Bỏ field lạ (ví dụ detection_model/ocr_model/tracking_model của
            # bản cũ trước khi có checkbox chọn tính năng) để tránh crash khi
            # đọc lại file JSON/device_store cũ.
            valid_ai_keys = {f.name for f in fields(AIConfig)}
            d["ai"] = AIConfig(**{k: v for k, v in d["ai"].items() if k in valid_ai_keys})
        if isinstance(d.get("recording"), dict):
            d["recording"] = RecordingConfig(**d["recording"])
        if isinstance(d.get("overlay"), dict):
            d["overlay"] = OverlayConfig(**d["overlay"])
        if isinstance(d.get("advanced"), dict):
            d["advanced"] = AdvancedConfig(**d["advanced"])
        if isinstance(d.get("roi_regions"), list):
            d["roi_regions"] = [
                ROIRegion(**r) if isinstance(r, dict) else r for r in d["roi_regions"]
            ]
        if isinstance(d.get("trigger_rules"), list):
            d["trigger_rules"] = [
                TriggerRule(**r) if isinstance(r, dict) else r for r in d["trigger_rules"]
            ]

        # Bỏ field lạ (phòng trường hợp file JSON cũ có field đã xoá) để tránh crash.
        valid_keys = {f.name for f in fields(cls)}
        d = {k: v for k, v in d.items() if k in valid_keys}
        return cls(**d)