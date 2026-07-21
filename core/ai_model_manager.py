"""
AIModelManager: quản lý các model AI dùng CHUNG cho mọi camera - load 1 lần
duy nhất (lazy, khi camera đầu tiên cần tới), KHÔNG load lại theo từng
CameraPipeline. Port từ D:\\APP_MIRAI_ver1\\process\\cameraTab\\YOLO_Body.py.

Vì sao dùng chung: mỗi model YOLO tốn vài trăm MB VRAM + vài giây để load;
nếu mỗi camera tự load 1 bản riêng thì N camera sẽ tốn N lần dung lượng/thời
gian đó. Ở đây dùng 1 instance model duy nhất, nhiều CameraPipeline (nhiều
QThread khác nhau) cùng gọi tới - có 1 threading.Lock riêng cho model này để
đảm bảo không có 2 thread gọi inference đồng thời (Cách A: đơn giản, tuần tự
hoá các lệnh gọi model thay vì dispatcher+batch phức tạp như bản gốc MIRAI;
có thể nâng cấp sau nếu nhiều camera cùng lúc bị nghẽn).

Giai đoạn 1: Body/Pose detection (nền tảng cho tracking, đếm vào/ra,
occupancy). Giai đoạn 3: thêm PPE detection (2 model ensemble, port từ
Safety_Area.py). Giai đoạn 4: thêm Fire detection (YOLO_FIRE.py) và Fall
detection (Fall_detection.py) - 2 cảnh báo độc lập, không cần ROI.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager

import numpy as np
import torch
from insightface.app import FaceAnalysis
from ultralytics import YOLO
from ultralytics.engine.results import Results

from core.path_manager import get_model_path

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


class AIModelManager:
    _instance: "AIModelManager | None" = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> "AIModelManager":
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = AIModelManager()
        return cls._instance

    def __init__(self):
        self._pose_model: YOLO | None = None
        self._pose_load_lock = threading.Lock()
        self._pose_call_lock = threading.Lock()

        # PPE: 2 model ENSEMBLE (không phải 2 loại đồ bảo hộ khác nhau) -
        # ppe.pt và ppe_1.pt là 2 model PPE huấn luyện riêng, có mapping
        # class-index khác nhau; kết quả 2 model được OR lại để giảm bỏ sót
        # (person được coi là "có vest/helmet" nếu MỘT TRONG HAI model thấy).
        # Port nguyên logic từ Safety_Area.py - không tự đổi vì đã verify kỹ
        # trước khi lên plan.
        self._ppe_model_a: YOLO | None = None  # ppe.pt   - check classes [1, 2]
        self._ppe_model_b: YOLO | None = None  # ppe_1.pt - check classes [1, 12]
        self._ppe_load_lock = threading.Lock()
        self._ppe_call_lock = threading.Lock()

        # Fire detection - port từ YOLO_FIRE.py, model riêng chạy trên
        # TOÀN KHUNG HÌNH (không phụ thuộc Body/Pose), classes=[0, 2].
        self._fire_model: YOLO | None = None
        self._fire_load_lock = threading.Lock()
        self._fire_call_lock = threading.Lock()

        # Fall detection - port từ Fall_detection.py, chạy trên crop quanh
        # từng người (do CameraPipeline chọn, dựa vào Body/Pose keypoints).
        self._fall_model: YOLO | None = None
        self._fall_load_lock = threading.Lock()
        self._fall_call_lock = threading.Lock()

        # Human detection (human.pt, 1 class "Human", KHÔNG có nhánh
        # keypoint) - nhẹ hơn nhiều so với yolov8x-pose vì chỉ là detector
        # thuần (đo thực tế: ~7ms/frame mọi imgsz, so với 17-41ms của
        # yolov8x-pose). Dùng thay pose model cho những tính năng CHỈ cần
        # bbox (đếm vào/ra, occupancy, PPE zone-check) - xem
        # CameraPipeline._run_ai. Pose model vẫn giữ riêng cho Fall (tính
        # năng DUY NHẤT thực sự cần keypoints).
        self._human_model: YOLO | None = None
        self._human_load_lock = threading.Lock()
        self._human_call_lock = threading.Lock()

        # Face recognition - port từ D:\APP_MIRAI_ver1\process\cameraTab\Face_detection.py,
        # dùng insightface (buffalo_l: detection + recognition, KHÔNG cần
        # landmark_2d_106 vì app này gate chất lượng detection bằng det_score
        # giống mọi model YOLO khác ở trên, không dùng heuristic góc mặt của
        # MIRAI). Known faces (tên + embedding) tới từ KnownFacesStore, không
        # load ở đây.
        self._face_model: FaceAnalysis | None = None
        self._face_load_lock = threading.Lock()
        self._face_call_lock = threading.Lock()

        # Thời gian chạy lần gần nhất của mỗi model (ms) - dùng cho dashboard
        # (bảng AI Status), không ảnh hưởng logic detect/check ở trên.
        self._last_latency_ms: dict[str, float] = {}

    @contextmanager
    def _measure(self, key: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self._last_latency_ms[key] = (time.perf_counter() - start) * 1000.0

    def latency_ms(self, key: str) -> float | None:
        return self._last_latency_ms.get(key)

    def loaded_status(self) -> dict[str, bool]:
        """Model nào đã thực sự load (lazy-load khi camera đầu tiên cần tới)
        - KHÔNG trigger load, chỉ đọc trạng thái hiện có. Dùng cho dashboard
        (bảng AI Status)."""
        return {
            "pose": self._pose_model is not None,
            "human": self._human_model is not None,
            "ppe": self._ppe_model_a is not None and self._ppe_model_b is not None,
            "fire": self._fire_model is not None,
            "fall": self._fall_model is not None,
            "face": self._face_model is not None,
        }

    # ------------------------------------------------------------------ #
    # Body / Pose (YOLOv8-pose) - dùng chung cho mọi camera
    # ------------------------------------------------------------------ #
    def _get_pose_model(self) -> YOLO:
        if self._pose_model is None:
            with self._pose_load_lock:
                if self._pose_model is None:
                    self._pose_model = YOLO(get_model_path("yolov8x-pose.pt")).to(DEVICE)
        return self._pose_model

    def detect_bodies(self, frame, imgsz: int = 480) -> Results:
        """Chạy YOLOv8-pose (model dùng chung) trên 1 frame BGR (numpy array).
        Trả về Ultralytics Results (bbox + keypoints từng người trong frame)
        - CameraPipeline dùng làm input cho DeepSort tracking.

        imgsz: kích thước resize nội bộ trước khi đưa vào model - lấy từ
        AIConfig.inference_quality của TỪNG camera (parse_inference_imgsz),
        khác camera có thể truyền imgsz khác nhau dù dùng chung 1 model
        instance (đây chỉ là tham số tiền xử lý mỗi lần gọi, không phải cấu
        hình cố định của model). Giảm imgsz tăng tốc đáng kể, đổi lại độ
        chính xác giảm nhẹ - xem parse_inference_imgsz() để biết số đo thực tế."""
        model = self._get_pose_model()
        with self._pose_call_lock, self._measure("pose"):
            results = model(frame, device=DEVICE, conf=0.4, verbose=False, imgsz=imgsz)
        return results[0]

    # ------------------------------------------------------------------ #
    # Human detection (best_re_final.pt) - detector thuần 1 class "head",
    # CHỈ detect vùng ĐẦU (không phải cả người) - dùng chung cho mọi camera.
    # Thay cho yolov8x-pose ở những tính năng chỉ cần bbox (đầu dễ detect
    # hơn, ít bị che khuất hơn body khi đông người). Vì bbox chỉ là vùng
    # đầu, CameraPipeline phải: (1) test tâm bbox đầu cho zone-check thay vì
    # foot-point, (2) ước lượng vùng thân qua _estimate_body_bbox() trước khi
    # đưa vào PPE ensemble (PPE cần thấy vai/ngực mới nhận ra áo vest) - xem
    # CameraPipeline._check_ppe/_count_occupancy.
    # ------------------------------------------------------------------ #
    def _get_human_model(self) -> YOLO:
        if self._human_model is None:
            with self._human_load_lock:
                if self._human_model is None:
                    self._human_model = YOLO(get_model_path("best_4.pt")).to(DEVICE)
        return self._human_model

    def detect_humans(self, frame, imgsz: int = 480) -> Results:
        """Chạy best_re_final.pt (model dùng chung) trên 1 frame BGR. Trả về
        Ultralytics Results (chỉ có bbox VÙNG ĐẦU, KHÔNG có keypoints, KHÔNG
        phải bbox cả người) - CameraPipeline dùng làm input cho DeepSort
        tracking (đếm vào/ra, occupancy) và PPE zone-check."""
        model = self._get_human_model()
        with self._human_call_lock, self._measure("human"):
            results = model(frame, device=DEVICE, conf=0.5, classes=[0], verbose=False, imgsz=imgsz)
        return results[0]

    # ------------------------------------------------------------------ #
    # PPE detection - dùng chung cho mọi camera (khác MIRAI: MIRAI load
    # riêng theo từng camera, ở đây gộp chung qua AIModelManager để giảm
    # VRAM, gọi tuần tự qua Lock giống Body/Pose).
    # ------------------------------------------------------------------ #
    def _get_ppe_models(self) -> tuple[YOLO, YOLO]:
        if self._ppe_model_a is None or self._ppe_model_b is None:
            with self._ppe_load_lock:
                if self._ppe_model_a is None:
                    self._ppe_model_a = YOLO(get_model_path("ppe.pt")).to(DEVICE)
                if self._ppe_model_b is None:
                    self._ppe_model_b = YOLO(get_model_path("ppe_1.pt")).to(DEVICE)
        return self._ppe_model_a, self._ppe_model_b

    def check_ppe(self, frame, imgsz: int = 480) -> tuple[int, int]:
        """Chạy 2 model PPE (ensemble) trên 1 frame/crop (numpy BGR). Trả về
        SỐ LƯỢNG (số vest, số helmet) phát hiện được - CameraPipeline so số
        này với số người trong ROI để phát hiện thiếu đồ bảo hộ (khác thiết
        kế cũ chỉ trả bool "có/không" - không phát hiện được trường hợp N
        người trong vùng nhưng chỉ 1 người có đủ đồ).

        Mỗi loại đồ (vest/helmet) được 2 model riêng biệt detect ra ở 2 class
        index khác nhau (xem _get_ppe_models) - lấy MAX số lượng giữa 2 model
        cho từng loại thay vì cộng dồn, vì cộng dồn sẽ đếm trùng 1 vest thật
        nếu cả 2 model cùng detect ra được nó."""
        model_a, model_b = self._get_ppe_models()
        with self._ppe_call_lock, self._measure("ppe"):
            result_a = model_a(frame, classes=[1, 2], device=DEVICE, verbose=False, conf=0.5, imgsz=imgsz)[0]
            result_b = model_b(frame, classes=[1, 12], device=DEVICE, verbose=False, conf=0.5, imgsz=imgsz)[0]

        classes_a = result_a.boxes.cls.cpu().numpy().astype(int) if len(result_a.boxes) else np.array([], dtype=int)
        classes_b = result_b.boxes.cls.cpu().numpy().astype(int) if len(result_b.boxes) else np.array([], dtype=int)

        vest_count = max(int(np.sum(classes_a == 1)), int(np.sum(classes_b == 12)))
        helmet_count = max(int(np.sum(classes_a == 2)), int(np.sum(classes_b == 1)))
        return vest_count, helmet_count

    # ------------------------------------------------------------------ #
    # Fire detection - dùng chung cho mọi camera, chạy trên TOÀN khung
    # hình (port từ YOLO_FIRE.py, classes=[0, 2] tương ứng "fire"/"smoke"
    # trong fire_detection.pt).
    # ------------------------------------------------------------------ #
    def _get_fire_model(self) -> YOLO:
        if self._fire_model is None:
            with self._fire_load_lock:
                if self._fire_model is None:
                    self._fire_model = YOLO(get_model_path("fire_detection.pt")).to(DEVICE)
        return self._fire_model

    def detect_fire(self, frame, imgsz: int = 480) -> Results:
        """Chạy fire_detection.pt (model dùng chung) trên toàn bộ frame BGR.
        Trả về Ultralytics Results - CameraPipeline chỉ cần kiểm tra
        len(result.boxes) > 0 để biết có cháy/khói hay không."""
        model = self._get_fire_model()
        with self._fire_call_lock, self._measure("fire"):
            results = model(frame, classes=[0, 2], device=DEVICE, verbose=False, conf=0.5, imgsz=imgsz)
        return results[0]

    # ------------------------------------------------------------------ #
    # Fall detection - dùng chung cho mọi camera, chạy trên 1 crop quanh
    # người (CameraPipeline tự crop dựa theo bbox + padding, port từ
    # Fall_detection.py).
    # ------------------------------------------------------------------ #
    def _get_fall_model(self) -> YOLO:
        if self._fall_model is None:
            with self._fall_load_lock:
                if self._fall_model is None:
                    self._fall_model = YOLO(get_model_path("fall_detection.pt")).to(DEVICE)
        return self._fall_model

    def check_fall(self, crop, imgsz: int = 480) -> float:
        """Chạy fall_detection.pt trên 1 crop quanh người (numpy BGR). Trả về
        confidence cao nhất tìm được (0.0 nếu không có box nào) - CameraPipeline
        so với FALL_CONF_THRESHOLD rồi làm mượt qua buffer nhiều frame."""
        model = self._get_fall_model()
        with self._fall_call_lock, self._measure("fall"):
            result = model(crop, conf=0.5, device=DEVICE, verbose=False, imgsz=imgsz)[0]
        if result.boxes is None or len(result.boxes) == 0:
            return 0.0
        return float(result.boxes.conf.max().item())

    # ------------------------------------------------------------------ #
    # Face recognition - dùng chung cho mọi camera, chạy trên TOÀN khung
    # hình (giống Fire detection, không phụ thuộc Body/Pose).
    # ------------------------------------------------------------------ #
    def _get_face_model(self) -> FaceAnalysis:
        if self._face_model is None:
            with self._face_load_lock:
                if self._face_model is None:
                    model = FaceAnalysis(
                        allowed_modules=["detection", "recognition"],
                        root=get_model_path("face"),
                    )
                    model.prepare(ctx_id=0 if DEVICE == "cuda" else -1)
                    self._face_model = model
        return self._face_model

    def detect_faces(self, frame) -> list:
        """Chạy insightface (model dùng chung) trên 1 frame BGR. Trả về list
        các Face object (bbox, det_score, normed_embedding) - CameraPipeline
        so từng face với KnownFacesStore để nhận diện người quen/người lạ."""
        model = self._get_face_model()
        with self._face_call_lock, self._measure("face"):
            return model.get(frame)
