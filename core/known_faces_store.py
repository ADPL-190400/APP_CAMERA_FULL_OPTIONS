"""
KnownFacesStore: danh sách người quen (tên + embedding gương mặt) dùng CHUNG
cho mọi camera - không đăng ký/lưu cục bộ trong app này, mà lấy trực tiếp từ
backend AIoT (scr/Web_API.py, giống D:\\APP_MIRAI_ver1) qua Web_API.get_employee().

Vì sao không enroll cục bộ: backend đó đã là nơi quản lý nhân viên/khuôn mặt
dùng chung cho các app khác (bao gồm MIRAI) - app này chỉ cần ĐỌC danh sách đó
để nhận diện, không cần xây dựng lại 1 quy trình đăng ký khuôn mặt riêng.

pages/login.py gọi Web_API.get_api(user, pw) khi đăng nhập thành công -> token/
headers module-level của Web_API đã sẵn sàng trước khi bất kỳ nơi nào ở đây gọi
get_employee(), nên không cần tự lo việc đăng nhập lại ở đây.

Vector đa góc (bổ sung, KHÔNG đụng gì tới backend/MIRAI): "identifier_code"
backend trả về là 1 vector TRUNG BÌNH của 3 góc mặt (thẳng/trái/phải) chụp lúc
đăng ký (pages/face_attendance_page.py) - trộn trung bình các góc khác nhau
làm giảm độ khớp so với người đang nhìn ở 1 góc CỤ THỂ (vd nhìn thẳng ở camera
khác). Nếu máy này CŨNG là máy đã đăng ký người đó (Face App lưu thêm cục bộ,
xem EnrollWorker._save_local_embeddings), _load_local_embeddings() đọc thêm 3
vector RIÊNG từng góc từ file cục bộ đó, dùng làm THÊM tham chiếu để so khớp -
xem _embeddings_matrix/_row_owner. Không có file cục bộ (máy khác, hoặc người
đó do MIRAI đăng ký) -> chỉ còn 1 vector từ backend như trước, vẫn hoạt động
bình thường."""
from __future__ import annotations

import json
import os
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from core.account_context import account_dir
from scr import Web_API

_SIMILARITY_THRESHOLD = 0.7  # port từ D:\APP_MIRAI_ver1\process\cameraTab\Face_detection.py

# Ngưỡng "vùng xám" chống báo Stranger nhầm (det_score đủ cao + similarity đủ
# thấp mới xác nhận là Stranger thật, tránh nhầm người quen bị che khuất/góc
# xấu) giờ CHỈNH ĐƯỢC qua UI - xem core/ai_settings.py
# (stranger_confirm_min_score/stranger_ambiguous_max_sim, AI Setting ở
# sidebar) - core/camera_pipeline.py và pages/gate_kiosk_page.py đọc trực
# tiếp từ AISettings.instance(), không còn hằng số cố định ở đây nữa.


def _load_local_embeddings(employee: dict) -> list[np.ndarray]:
    """Đọc thêm vector riêng từng góc (thẳng/trái/phải) đã lưu cục bộ lúc
    đăng ký qua Face App TRÊN CHÍNH MÁY NÀY (xem module docstring/
    pages/face_attendance_page.py::EnrollWorker._save_local_embeddings) -
    không đồng bộ qua backend nên chỉ có nếu người đó từng đăng ký ở đây.
    Thiếu file/lỗi đọc -> [] (bỏ qua, không crash refresh)."""
    code = employee.get("code") or employee.get("employee_code")
    if not code:
        return []
    path = os.path.join(account_dir(), "faces", str(code), "embeddings.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            pose_vectors = json.load(f)
        return [np.array(v) for v in pose_vectors.values() if v]
    except (OSError, ValueError, AttributeError):
        return []


class KnownFacesRefreshWorker(QThread):
    # names, rows (embeddings - CÓ THỂ nhiều dòng/nhân viên nếu có vector cục
    # bộ, xem _load_local_embeddings), row_owner (dòng thứ i thuộc nhân viên
    # index row_owner[i] trong names/employees), employees, error_message
    # ("" nếu thành công)
    result_ready = pyqtSignal(list, list, list, list, str)

    def run(self) -> None:
        names: list[str] = []
        rows: list[np.ndarray] = []
        row_owner: list[int] = []
        employees: list[dict] = []
        try:
            res = Web_API.get_employee()
            for nv in res.get("data", []):
                code = nv.get("identifier_code")
                if not code:
                    continue
                owner = len(names)
                rows.append(np.array(json.loads(code)))
                row_owner.append(owner)
                names.append(nv.get("first_name", "?"))
                employees.append(nv)
                for extra in _load_local_embeddings(nv):
                    rows.append(extra)
                    row_owner.append(owner)
        except Exception as exc:  # noqa: BLE001 - lỗi mạng/API không được làm crash app
            self.result_ready.emit([], [], [], [], str(exc))
            return
        self.result_ready.emit(names, rows, row_owner, employees, "")


class KnownFacesStore(QObject):
    """Singleton - CameraPipeline (nhiều thread) chỉ gọi match() (đọc list, an
    toàn không cần Lock vì refresh_async() thay nguyên list mới thay vì sửa
    tại chỗ - gán reference là thao tác atomic trong CPython)."""

    _instance: Optional["KnownFacesStore"] = None

    updated = pyqtSignal()  # bắn sau mỗi lần refresh (thành công hoặc lỗi)

    @classmethod
    def instance(cls) -> "KnownFacesStore":
        if cls._instance is None:
            cls._instance = KnownFacesStore()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._names: list[str] = []
        self._employees: list[dict] = []  # cùng thứ tự với _names
        # Ma trận (TỔNG số dòng, D) dựng sẵn mỗi lần refresh - 1 nhân viên có
        # thể chiếm NHIỀU dòng (1 từ backend + tối đa 3 từ vector cục bộ theo
        # góc, xem _load_local_embeddings) - _row_owner[i] = index nhân viên
        # (trong _names/_employees) mà dòng i thuộc về. match()/match_employee()
        # nhân ma trận numpy (BLAS) 1 lần trên TOÀN BỘ dòng rồi map ngược qua
        # _row_owner, thay vì vòng lặp Python "for name, emb_ref in zip(...)"
        # gọi np.dot từng cặp một (chi phí so khớp từng là O(số mặt trong
        # frame x số nhân viên) chạy scalar trong interpreter).
        self._embeddings_matrix: np.ndarray = np.empty((0, 0), dtype=np.float32)
        self._row_owner: list[int] = []
        self._last_error: str = ""
        self._worker: KnownFacesRefreshWorker | None = None

    def refresh_async(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # 1 lượt refresh đang chạy -> bỏ qua, tránh chồng request
        self._worker = KnownFacesRefreshWorker()
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    def _on_result(
        self, names: list[str], rows: list, row_owner: list[int], employees: list, error: str
    ) -> None:
        if error:
            self._last_error = error
        else:
            self._names = names
            self._employees = employees
            self._row_owner = row_owner
            self._embeddings_matrix = (
                np.stack(rows).astype(np.float32) if rows else np.empty((0, 0), dtype=np.float32)
            )
            self._last_error = ""
        self.updated.emit()

    @property
    def count(self) -> int:
        return len(self._names)

    @property
    def last_error(self) -> str:
        return self._last_error

    def match(self, embedding: np.ndarray, threshold: float = _SIMILARITY_THRESHOLD) -> tuple[str, float]:
        """So embedding 1 khuôn mặt vừa phát hiện với toàn bộ known faces.
        Trả về (tên, similarity) - tên là "Stranger" nếu không ai vượt
        `threshold` (mặc định _SIMILARITY_THRESHOLD - không phân biệt
        "Unknown" riêng - ai không khớp coi như người lạ, đúng yêu cầu cảnh
        báo người lạ).

        `threshold` cho phép nơi gọi tự chỉnh độ chặt/lỏng theo NGỮ CẢNH
        riêng (vd core/camera_pipeline.py truyền AISettings.instance().
        face_similarity_threshold - chỉnh qua UI "AI Setting", áp dụng mọi
        camera ngay lập tức - không đụng tới hành vi mặc định của các nơi
        gọi khác: gate_kiosk_page.py/face_attendance_page.py vẫn dùng
        match_employee() với ngưỡng mặc định _SIMILARITY_THRESHOLD như cũ).

        similarity trả về LUÔN LÀ SỐ THẬT đã đo được (kể cả khi < ngưỡng,
        tức "Stranger") - không phải hằng số ngưỡng - để nơi gọi (vd log chẩn
        đoán ở gate_kiosk_page.py) biết được mức khớp gần nhất, không chỉ
        biết có khớp hay không."""
        if self._embeddings_matrix.shape[0] == 0:
            return "Stranger", 0.0
        sims = self._embeddings_matrix @ embedding
        idx = int(np.argmax(sims))
        best_sim = float(sims[idx])
        if best_sim > threshold:
            return self._names[self._row_owner[idx]], best_sim
        return "Stranger", best_sim

    def match_employee(self, embedding: np.ndarray) -> tuple[Optional[dict], float]:
        """Giống match() nhưng trả về TOÀN BỘ bản ghi employee (id, code,
        first_name, last_name, phone, email, dob...) thay vì chỉ tên - dùng
        bởi Face App (pages/face_attendance_page.py) để biết employee_id cho
        điểm danh (send_mobile_employee) và để prefill form "Sửa thông tin".
        Trả về (None, similarity thật đã đo được) nếu không ai vượt ngưỡng
        (người lạ) - xem docstring match() về ý nghĩa similarity trả về."""
        if self._embeddings_matrix.shape[0] == 0:
            return None, 0.0
        sims = self._embeddings_matrix @ embedding
        idx = int(np.argmax(sims))
        best_sim = float(sims[idx])
        if best_sim > _SIMILARITY_THRESHOLD:
            return self._employees[self._row_owner[idx]], best_sim
        return None, best_sim
