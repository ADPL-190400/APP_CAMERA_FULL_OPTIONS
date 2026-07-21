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
"""
from __future__ import annotations

import json
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, QThread, pyqtSignal

from scr import Web_API

_SIMILARITY_THRESHOLD = 0.7  # port từ D:\APP_MIRAI_ver1\process\cameraTab\Face_detection.py


class KnownFacesRefreshWorker(QThread):
    # names, embeddings, employees (bản ghi đầy đủ từ API, cùng thứ tự với
    # names/embeddings - dùng cho match_employee()), error_message ("" nếu
    # thành công)
    result_ready = pyqtSignal(list, list, list, str)

    def run(self) -> None:
        names: list[str] = []
        embeddings: list[np.ndarray] = []
        employees: list[dict] = []
        try:
            res = Web_API.get_employee()
            for nv in res.get("data", []):
                code = nv.get("identifier_code")
                if not code:
                    continue
                embeddings.append(np.array(json.loads(code)))
                names.append(nv.get("first_name", "?"))
                employees.append(nv)
        except Exception as exc:  # noqa: BLE001 - lỗi mạng/API không được làm crash app
            self.result_ready.emit([], [], [], str(exc))
            return
        self.result_ready.emit(names, embeddings, employees, "")


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
        self._embeddings: list[np.ndarray] = []
        self._employees: list[dict] = []  # cùng thứ tự với _names/_embeddings
        self._last_error: str = ""
        self._worker: KnownFacesRefreshWorker | None = None

    def refresh_async(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return  # 1 lượt refresh đang chạy -> bỏ qua, tránh chồng request
        self._worker = KnownFacesRefreshWorker()
        self._worker.result_ready.connect(self._on_result)
        self._worker.start()

    def _on_result(self, names: list[str], embeddings: list, employees: list, error: str) -> None:
        if error:
            self._last_error = error
        else:
            self._names = names
            self._embeddings = embeddings
            self._employees = employees
            self._last_error = ""
        self.updated.emit()

    @property
    def count(self) -> int:
        return len(self._names)

    @property
    def last_error(self) -> str:
        return self._last_error

    def match(self, embedding: np.ndarray) -> tuple[str, float]:
        """So embedding 1 khuôn mặt vừa phát hiện với toàn bộ known faces.
        Trả về (tên, similarity) - tên là "Stranger" nếu không ai vượt
        ngưỡng _SIMILARITY_THRESHOLD (không phân biệt "Unknown" riêng - ai
        không khớp coi như người lạ, đúng yêu cầu cảnh báo người lạ)."""
        best_sim = _SIMILARITY_THRESHOLD
        best_name = "Stranger"
        for name, emb_ref in zip(self._names, self._embeddings):
            sim = float(np.dot(embedding, emb_ref))
            if sim > best_sim:
                best_sim = sim
                best_name = name
        return best_name, best_sim

    def match_employee(self, embedding: np.ndarray) -> tuple[Optional[dict], float]:
        """Giống match() nhưng trả về TOÀN BỘ bản ghi employee (id, code,
        first_name, last_name, phone, email, dob...) thay vì chỉ tên - dùng
        bởi Face App (pages/face_attendance_page.py) để biết employee_id cho
        điểm danh (send_mobile_employee) và để prefill form "Sửa thông tin".
        Trả về (None, 0.0) nếu không ai vượt ngưỡng (người lạ)."""
        best_sim = _SIMILARITY_THRESHOLD
        best_employee: Optional[dict] = None
        for employee, emb_ref in zip(self._employees, self._embeddings):
            sim = float(np.dot(embedding, emb_ref))
            if sim > best_sim:
                best_sim = sim
                best_employee = employee
        return best_employee, best_sim
