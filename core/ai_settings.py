"""AISettings: ngưỡng confidence + tham số xác nhận cho các model AI dùng
CHUNG (core/ai_model_manager.py) - chỉnh được qua UI (ui/dialogs/ai_settings_dialog.py,
mở từ nút "⚙ Settings" ở sidebar - pages/menu_window.py), lưu cục bộ
config/ai_settings.json, áp dụng NGAY cho mọi camera đang chạy (model dùng
chung 1 instance qua AIModelManager, đọc giá trị mới nhất ở mỗi lượt gọi -
không cần restart pipeline/app).

Tách riêng khỏi AIModelManager: AIModelManager là nơi LOAD + CHẠY model
(torch/insightface, nặng) - dialog cấu hình chỉ cần biết tới AISettings, một
module nhẹ không kéo theo các dependency AI nặng đó."""
from __future__ import annotations

import json
import os
import threading
from dataclasses import asdict, dataclass, fields
from typing import ClassVar, Optional

from core.path_manager import BASE_DIR

_SETTINGS_PATH = os.path.join(BASE_DIR, "config", "ai_settings.json")


@dataclass
class AISettings:
    # Ngưỡng confidence khi gọi từng model YOLO (tham số "conf") - core/ai_model_manager.py.
    pose_conf: float = 0.4
    human_conf: float = 0.5
    ppe_conf: float = 0.5
    fire_conf: float = 0.5
    fall_conf: float = 0.75

    # Độ tương đồng tối thiểu để coi 1 khuôn mặt phát hiện được là khớp với 1
    # người quen (KnownFacesStore.match, dùng bởi core/camera_pipeline.py -
    # Live View/Dashboard) - cao hơn = chặt hơn (ít nhận nhầm 2 người giống
    # nhau, nhưng dễ bỏ sót người quen ở góc/ánh sáng xấu); thấp hơn = lỏng
    # hơn. Áp dụng CHUNG mọi camera (không còn per-camera - đổi ở đây có tác
    # dụng ngay toàn hệ thống). Gate Kiosk/Face App enrollment vẫn dùng
    # _SIMILARITY_THRESHOLD mặc định riêng ở core/known_faces_store.py, không
    # đụng tới.
    face_similarity_threshold: float = 0.7

    # Ngưỡng "vẫn là ĐÚNG 1 người này" khi bắc cầu qua lúc track DeepSort
    # chết (quay đầu/cúi xuống đủ lâu để mất dấu, xem
    # core/camera_pipeline.py::_recall_face_memory/_remember_face) - KHÁC
    # face_similarity_threshold (đó là so với ảnh ĐĂNG KÝ của người quen,
    # thường chụp khác ngày/khác góc nên cần nới hơn; đây là so 2 lần thấy
    # CÙNG 1 buổi, thường giống nhau hơn hẳn nên đặt CHẶT hơn để tránh nhận
    # nhầm 2 người lạ trông giống nhau thành 1 - lỡ nhận nhầm sẽ "miễn thông
    # báo" oan cho 1 người lạ hoàn toàn khác). Cao hơn = chặt hơn (ít nhận
    # nhầm 2 người khác nhau, nhưng dễ không bắc cầu được nếu góc/ánh sáng
    # đổi nhiều giữa 2 lần thấy); thấp hơn = lỏng hơn.
    face_memory_match_threshold: float = 0.6

    # "Xác nhận té ngã" (core/camera_pipeline.py::_check_fall): trong
    # fall_confirm_window lượt AI GẦN NHẤT, phải có ÍT NHẤT
    # fall_confirm_min_count lượt phát hiện "đang ngã" (fall_conf ở trên đã
    # lọc từng lượt) mới thực sự chốt cảnh báo/vẽ khung - tránh báo động chỉ
    # vì 1 lượt nhận diện sai (tư thế bất thường thoáng qua, nhiễu ánh
    # sáng...). fall_confirm_min_count PHẢI <= fall_confirm_window.
    fall_confirm_window: int = 10
    fall_confirm_min_count: int = 5

    # Chống báo "Stranger" NHẦM khi thực ra là 1 người QUEN bị che khuất/góc
    # mặt xấu/ánh sáng kém (nguyên nhân phổ biến nhất gây spam cảnh báo sai -
    # xem core/camera_pipeline.py::_check_faces + pages/gate_kiosk_page.py).
    # 1 khuôn mặt "Stranger" chỉ được TÍNH VÀO streak/cảnh báo khi CẢ 2 đúng:
    #   stranger_confirm_min_score - det_score đủ cao (mặt nhìn đủ rõ, không
    #     mờ/nghiêng/xa) - det_score thấp không có nghĩa "chắc chắn không
    #     phải ai", có thể chỉ là embedding kém do góc xấu.
    #   stranger_ambiguous_max_sim - similarity đủ THẤP, rõ ràng không giống
    #     ai đã đăng ký - similarity nằm giữa mức này và ngưỡng khớp nghĩa là
    #     "có nét giống 1 người quen nhưng chưa đủ" (thường do khẩu trang/
    #     tóc/góc nghiêng che 1 phần), KHÔNG nên tính là Stranger.
    # Dùng CHUNG 1 cặp giá trị cho cả Live View/Dashboard (camera_pipeline.py)
    # VÀ Gate Kiosk (gate_kiosk_page.py) - chỉnh ở đây áp dụng đồng thời cho
    # toàn hệ thống, không cần sửa nhiều nơi.
    stranger_confirm_min_score: float = 0.7
    stranger_ambiguous_max_sim: float = 0.45
    # Mặt quay nghiêng vẫn có thể có det_score CAO (detector vẫn thấy rõ đó
    # là mặt người) nhưng embedding tính từ góc nghiêng kém tin cậy, dễ làm
    # similarity tụt thấp dù là người quen thật (xem core/face_pose.py) - chỉ
    # tính vào streak/cảnh báo Stranger khi mặt đủ "thẳng" (không phải chỉ
    # đủ rõ) theo tỉ lệ này (0..1, 1.0 = chỉ chấp nhận mặt gần như thẳng
    # tuyệt đối, thấp hơn = chấp nhận góc nghiêng nhiều hơn).
    stranger_min_frontal_ratio: float = 0.5

    _instance: ClassVar[Optional["AISettings"]] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def instance(cls) -> "AISettings":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    settings = cls()
                    settings._load()
                    cls._instance = settings
        return cls._instance

    def _load(self) -> None:
        """Đọc config/ai_settings.json (nếu có) đè lên default - thiếu
        file/lỗi đọc/field lạ -> bỏ qua, giữ nguyên default cho field đó
        (không crash app vì 1 file cấu hình hỏng)."""
        try:
            with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except (OSError, ValueError):
            return
        valid_names = {f.name for f in fields(self)}
        for key, value in saved.items():
            if key in valid_names:
                setattr(self, key, value)

    def save(self) -> None:
        """Ghi TOÀN BỘ giá trị hiện tại xuống config/ai_settings.json - gọi
        sau khi UI (ai_settings_dialog.py) set xong các field mới."""
        os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
        with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
