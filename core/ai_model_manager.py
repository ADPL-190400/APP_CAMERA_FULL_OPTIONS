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

import cv2
import numpy as np
import onnx
import torch
from insightface.app import FaceAnalysis
from insightface.app.common import Face
from onnx2torch import convert as onnx2torch_convert
from ultralytics import YOLO
from ultralytics.engine.results import Results

from core.ai_settings import AISettings
from core.path_manager import get_model_path

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _session_has_cuda(session) -> bool:
    """True nếu 1 onnxruntime.InferenceSession THỰC SỰ có CUDAExecutionProvider
    khả dụng (không chỉ được yêu cầu). Có máy (vd aarch64 - không có wheel
    onnxruntime-gpu cho kiến trúc đó) khiến onnxruntime ÂM THẦM fallback về
    CPUExecutionProvider dù code tưởng đang chạy GPU (chỉ in 1 UserWarning,
    không lỗi) - session.get_providers() phản ánh đúng provider ĐANG active,
    khác ctx_id/providers lúc request. Dùng để quyết định có cần lách qua
    _TorchOnnxSession (onnx2torch) hay dùng thẳng onnxruntime-gpu (máy này -
    xem _get_face_model)."""
    return "CUDAExecutionProvider" in session.get_providers()


class _TorchOnnxSession:
    """Thay thế onnxruntime.InferenceSession bên trong các model con của
    insightface (SCRFD detection, ArcFaceONNX recognition) bằng 1 bản chạy
    qua onnx2torch (convert ONNX -> torch.nn.Module) trên torch/CUDA.

    CHỈ dùng khi onnxruntime KHÔNG tự chạy được CUDAExecutionProvider (xem
    _session_has_cuda) - ví dụ PyPI không có wheel onnxruntime-gpu cho
    aarch64. torch/CUDA vẫn hoạt động bình thường trên những máy đó (YOLO
    dùng torch trực tiếp) nên dùng onnx2torch để chạy 2 model ONNX của
    insightface qua torch/CUDA thay vì onnxruntime - đã verify số học khớp
    onnxruntime-CPU (cosine similarity ~0.9999997, sai số float không đáng
    kể) và nhanh hơn ~9-22 lần so với onnxruntime-CPU khi đo thực tế. Máy có
    onnxruntime-gpu hoạt động đúng (CUDAExecutionProvider thật) thì dùng
    thẳng onnxruntime, không qua class này nữa - vừa đỡ 1 tầng convert, vừa
    tận dụng tối ưu riêng của onnxruntime (vd TensorRT nếu có).

    Chỉ implement đúng phần bề mặt API mà SCRFD/ArcFaceONNX thực sự gọi tới
    (get_inputs/get_outputs cho _init_vars() lúc khởi tạo, set_providers()
    cho prepare(), run() cho forward()/get_feat()) - KHÔNG phải triển khai
    lại toàn bộ onnxruntime.InferenceSession."""

    def __init__(self, model_path: str, meta_session, device: str):
        self._meta_session = meta_session  # onnxruntime session gốc - chỉ dùng đọc metadata, không chạy inference qua nó nữa
        self._output_names = [o.name for o in meta_session.get_outputs()]
        self._device = device
        self._torch_model = onnx2torch_convert(onnx.load(model_path)).eval().to(device)

    def get_inputs(self):
        return self._meta_session.get_inputs()

    def get_outputs(self):
        return self._meta_session.get_outputs()

    def set_providers(self, *_args, **_kwargs) -> None:
        pass  # device cố định lúc khởi tạo (theo DEVICE toàn cục) - không cần đổi provider theo runtime

    def run(self, output_names, input_feed: dict) -> list:
        (blob,) = input_feed.values()
        t_in = torch.from_numpy(blob).to(self._device)
        with torch.no_grad():
            t_out = self._torch_model(t_in)
        outs = [t_out] if isinstance(t_out, torch.Tensor) else list(t_out)
        outs = [o.detach().cpu().numpy() for o in outs]
        if output_names is None or list(output_names) == self._output_names:
            return outs
        by_name = dict(zip(self._output_names, outs))
        return [by_name[n] for n in output_names]


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
        # TOÀN KHUNG HÌNH (không phụ thuộc Body/Pose), 2 lớp {0: Fire, 1: Smoke}.
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
            results = model(frame, device=DEVICE, conf=AISettings.instance().pose_conf, verbose=False, imgsz=imgsz)
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
                    self._human_model = YOLO(get_model_path("best_5.pt")).to(DEVICE)
        return self._human_model

    def detect_humans(self, frame, imgsz: int = 480) -> Results:
        """Chạy best_re_final.pt (model dùng chung) trên 1 frame BGR. Trả về
        Ultralytics Results (chỉ có bbox VÙNG ĐẦU, KHÔNG có keypoints, KHÔNG
        phải bbox cả người) - CameraPipeline dùng làm input cho DeepSort
        tracking (đếm vào/ra, occupancy) và PPE zone-check."""
        model = self._get_human_model()
        with self._human_call_lock, self._measure("human"):
            results = model(
                frame, device=DEVICE, conf=AISettings.instance().human_conf, classes=[0], verbose=False, imgsz=imgsz
            )
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
        ppe_conf = AISettings.instance().ppe_conf
        with self._ppe_call_lock, self._measure("ppe"):
            result_a = model_a(frame, classes=[1, 2], device=DEVICE, verbose=False, conf=ppe_conf, imgsz=imgsz)[0]
            result_b = model_b(frame, classes=[1, 12], device=DEVICE, verbose=False, conf=ppe_conf, imgsz=imgsz)[0]

        classes_a = result_a.boxes.cls.cpu().numpy().astype(int) if len(result_a.boxes) else np.array([], dtype=int)
        classes_b = result_b.boxes.cls.cpu().numpy().astype(int) if len(result_b.boxes) else np.array([], dtype=int)

        vest_count = max(int(np.sum(classes_a == 1)), int(np.sum(classes_b == 12)))
        helmet_count = max(int(np.sum(classes_a == 2)), int(np.sum(classes_b == 1)))
        return vest_count, helmet_count

    # ------------------------------------------------------------------ #
    # Fire detection - dùng chung cho mọi camera, chạy trên TOÀN khung hình.
    # fire_detection_new.pt (bản model.names hiện tại - đã verify trực tiếp,
    # KHÔNG suy đoán từ bản cũ) có 2 lớp {0: Fire, 1: Smoke}, dùng CHUNG 1
    # ngưỡng fire_conf cho cả 2 (đơn giản hơn - không cần 2 ngưỡng riêng).
    # ------------------------------------------------------------------ #
    def _get_fire_model(self) -> YOLO:
        if self._fire_model is None:
            with self._fire_load_lock:
                if self._fire_model is None:
                    self._fire_model = YOLO(get_model_path("fire_detection_new.pt")).to(DEVICE)
        return self._fire_model

    def detect_fire(self, frame, imgsz: int = 480) -> Results:
        """Chạy fire_detection_new.pt (model dùng chung) trên toàn bộ frame BGR.
        Trả về Ultralytics Results - CameraPipeline chỉ cần kiểm tra
        len(result.boxes) > 0 để biết có cháy/khói hay không."""
        model = self._get_fire_model()
        with self._fire_call_lock, self._measure("fire"):
            results = model(
                frame, classes=[0, 1], device=DEVICE, verbose=False, conf=AISettings.instance().fire_conf, imgsz=imgsz
            )
        return results[0]

    # ------------------------------------------------------------------ #
    # Fall detection - dùng chung cho mọi camera, chạy trên 1 crop quanh
    # người (CameraPipeline tự crop dựa theo bbox + padding, port từ
    # Fall_detection.py). fall_detection_new.pt có 3 class {0: fallen,
    # 1: sitting, 2: standing} (bản cũ chỉ có 1 class "Fall-Detected") -
    # PHẢI lọc classes=[0] ("fallen"), nếu không người đang ngồi/đứng bình
    # thường (luôn xuất hiện, confidence cao) sẽ bị tính nhầm thành ngã.
    # ------------------------------------------------------------------ #
    def _get_fall_model(self) -> YOLO:
        if self._fall_model is None:
            with self._fall_load_lock:
                if self._fall_model is None:
                    self._fall_model = YOLO(get_model_path("fall_detection_new.pt")).to(DEVICE)
        return self._fall_model

    def check_fall(self, crop, imgsz: int = 480) -> float:
        """Chạy fall_detection_new.pt trên 1 crop quanh người (numpy BGR),
        chỉ lấy class "fallen" (index 0), lọc theo AISettings.instance().fall_conf
        (chỉnh được qua UI - ui/dialogs/ai_settings_dialog.py). Trả về
        confidence cao nhất tìm được (0.0 nếu không có box "fallen" nào,
        nghĩa là không có box nào vượt fall_conf) - CameraPipeline làm mượt
        thêm qua buffer nhiều frame (xem AISettings.fall_confirm_window/
        fall_confirm_min_count)."""
        model = self._get_fall_model()
        with self._fall_call_lock, self._measure("fall"):
            result = model(
                crop, classes=[0], conf=AISettings.instance().fall_conf, device=DEVICE, verbose=False, imgsz=imgsz
            )[0]
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
                    # model_zoo.get_model() mặc định request providers=
                    # ['CUDAExecutionProvider', 'CPUExecutionProvider'] nên
                    # nếu máy có onnxruntime-gpu hoạt động đúng thì mỗi
                    # session ở đây ĐÃ chạy CUDA thật rồi (session_has_cuda
                    # sẽ True) - chỉ cần lách qua _TorchOnnxSession
                    # (onnx2torch) khi onnxruntime ÂM THẦM fallback CPU (máy
                    # không có wheel onnxruntime-gpu phù hợp, vd aarch64) -
                    # xem docstring _session_has_cuda/_TorchOnnxSession.
                    # PHẢI làm TRƯỚC khi gọi model.prepare() vì prepare() có
                    # thể gọi session.set_providers() (khi ctx_id<0).
                    if DEVICE == "cuda" and not _session_has_cuda(model.det_model.session):
                        for sub_model in model.models.values():
                            sub_model.session = _TorchOnnxSession(sub_model.model_file, sub_model.session, DEVICE)
                    # det_size=(640, 640) tường minh - nếu để None, insightface
                    # tự chọn chế độ "auto" (list [(128,128),(640,640)]) và
                    # CHẠY DETECTION 2 LẦN mỗi frame (128px rồi 640px, gộp kết
                    # quả bằng NMS) - lãng phí cố định trên MỌI frame, không
                    # liên quan số khuôn mặt. Chỉ dùng 640px (kích thước lớn
                    # hơn, cũng chính xác hơn trong 2 lựa chọn cũ) -> giảm ~1
                    # nửa chi phí detection mà không đổi độ chính xác.
                    model.prepare(ctx_id=0 if DEVICE == "cuda" else -1, det_size=(640, 640))
                    self._face_model = model
        return self._face_model

    def detect_faces(self, frame, max_num: int = 0, roi_polygons=None) -> list:
        """Chạy insightface (model dùng chung) trên 1 frame BGR. Trả về list
        các Face object (bbox, det_score, normed_embedding) - CameraPipeline
        so từng face với KnownFacesStore để nhận diện người quen/người lạ.

        max_num: giới hạn số mặt XỬ LÝ (0 = không giới hạn). Cả detection lẫn
        recognition per-face đều tốn thêm khi số mặt tăng (xem module
        docstring), nên khi 1 frame có quá nhiều mặt (đám đông), giới hạn
        này tránh việc cả frame bị kéo chậm vì phải nhận diện HẾT từng mặt.

        roi_polygons: rỗng/None -> hành vi GỐC không đổi (insightface tự
        chọn max_num mặt LỚN NHẤT/gần tâm khung hình nhất để giữ lại - xem
        SCRFD.detect(), tham số metric='default') - xét TOÀN khung hình,
        KHÔNG có khái niệm ROI.

        Có roi_polygons -> CHỈ xét mặt có TÂM bbox nằm TRONG vùng ROI (mặt
        ngoài ROI bị loại NGAY TỪ ĐẦU, không cạnh tranh "suất" max_num với
        mặt trong ROI, kể cả khi ROI chỉ có vài người nhưng camera còn thấy
        cả đám đông ngoài vùng đó) - trong số các mặt ĐÃ Ở TRONG ROI, ưu
        tiên det_score cao hơn nếu vẫn nhiều hơn max_num. Vẫn CHỈ chạy bước
        nhận diện (ArcFace, bước tốn nhất) cho ĐÚNG max_num mặt đã chọn -
        bước phát hiện (SCRFD) không giới hạn số mặt trả về TỪ ĐẦU (chi phí
        gần như không đổi theo số mặt - 1 lượt suy luận NN cố định trên
        toàn ảnh, phần lọc/sắp xếp sau đó là numpy thuần, rẻ) nên không tốn
        thêm chi phí đáng kể để "nhìn thấy" cả các mặt ngoài ROI trước khi
        loại bỏ chúng."""
        model = self._get_face_model()
        with self._face_call_lock, self._measure("face"):
            if not roi_polygons:
                return model.get(frame, max_num=max_num)
            return self._detect_faces_in_roi(model, frame, max_num, roi_polygons)

    @staticmethod
    def _detect_faces_in_roi(model: FaceAnalysis, frame, max_num: int, roi_polygons) -> list:
        """PORT lại phần lõi của FaceAnalysis.get() (insightface) - CHỦ Ý
        KHÔNG dùng SCRFD.detect(..., max_num=...) như bản gốc (chọn theo
        kích thước/độ gần tâm khung hình, không biết gì về ROI) - tự LOẠI
        BỎ mặt ngoài ROI trước, rồi mới sắp theo det_score + cắt còn đúng
        max_num trong số mặt CÒN LẠI (đã chắc chắn trong ROI), sau đó mới
        chạy nhận diện (ArcFace) cho từng mặt đã chọn - giống hệt cách
        model.get() làm, chỉ khác bước chọn lọc ở giữa."""
        bboxes, kpss = model.det_model.detect(frame, max_num=0, metric="default")
        if bboxes.shape[0] == 0:
            return []

        def in_roi(index: int) -> bool:
            x1, y1, x2, y2 = bboxes[index, 0:4]
            center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
            return any(cv2.pointPolygonTest(polygon, center, False) >= 0 for polygon in roi_polygons)

        candidates = [i for i in range(bboxes.shape[0]) if in_roi(i)]
        candidates.sort(key=lambda i: -bboxes[i, 4])
        if max_num > 0:
            candidates = candidates[:max_num]

        faces = []
        for i in candidates:
            face = Face(bbox=bboxes[i, 0:4], kps=(kpss[i] if kpss is not None else None), det_score=bboxes[i, 4])
            for taskname, sub_model in model.models.items():
                if taskname == "detection":
                    continue
                sub_model.get(frame, face)
            faces.append(face)
        return faces
