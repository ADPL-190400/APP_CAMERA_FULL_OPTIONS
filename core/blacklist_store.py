"""
BlacklistStore: danh sách người trong "danh sách đen" (blacklist) - LƯU CỤC
BỘ hoàn toàn, KHÔNG đồng bộ backend (khác KnownFacesStore - xem module
docstring core/known_faces_store.py, lấy từ Web_API.get_employee() vì đó là
danh sách nhân viên dùng chung với MIRAI). Blacklist là dữ liệu do CHÍNH
người dùng app này tự quản lý (chọn ảnh từ Stranger đã phát hiện, hoặc import
ảnh trực tiếp - xem pages/blacklist_page.py), không liên quan gì tới hệ thống
nhân viên/chấm công.

Mỗi entry (BlacklistEntry) giữ NHIỀU embedding riêng biệt cho CÙNG 1 người
(KHÔNG trung bình cộng thành 1 vector - lý do giống hệt _load_local_embeddings
ở known_faces_store.py: trộn nhiều góc mặt/thời điểm khác nhau làm giảm độ
khớp so với giữ riêng từng vector). match() so 1 embedding với TẤT CẢ embedding
của TẤT CẢ entry ĐANG ACTIVE cùng lúc (1 phép nhân ma trận numpy/BLAS, xem
_rebuild_matrix) - lấy điểm cao nhất, giống hệt thiết kế KnownFacesStore.match().

Lưu trữ: 1 file JSON/entry tại {account_dir()}/blacklist/{entry_id}.json -
CRUD đơn giản (thêm/sửa/xoá 1 entry = ghi/xoá đúng 1 file, không cần đọc/ghi
lại toàn bộ danh sách như events.json bản cũ đã bỏ - xem core/event_store.py).

_MAX_EMBEDDINGS_PER_ENTRY giới hạn số ảnh/entry (rolling: thêm ảnh mới khi đã
đầy thì bỏ ảnh CŨ NHẤT) - tránh phình vô hạn nếu 1 người bị "gặp lại" rất
nhiều lần qua nhiều năm (đã bàn kỹ lúc thiết kế - xem lịch sử trao đổi, khác
hẳn ý tưởng "ghi đè liên tục mỗi lần detect" đã bị bác vì gây phình ma trận
không kiểm soát được)."""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal

from core.account_context import account_dir

# Trần số embedding/entry - đầy thì bỏ embedding CŨ NHẤT khi thêm ảnh mới
# (xem BlacklistStore.add_embeddings) - KHÁC hẳn KnownFacesStore (cố định
# ~1-4 embedding/nhân viên, không bao giờ tăng) vì Blacklist có luồng "bổ
# sung ảnh từ lịch sử nhận diện" theo thời gian (xem pages/blacklist_page.py).
_MAX_EMBEDDINGS_PER_ENTRY = 30


def _blacklist_dir() -> str:
    path = os.path.join(account_dir(), "blacklist")
    os.makedirs(path, exist_ok=True)
    return path


def _entry_path(entry_id: str) -> str:
    return os.path.join(_blacklist_dir(), f"{entry_id}.json")


@dataclass
class BlacklistEntry:
    id: str
    name: str                      # bắt buộc - nhãn/tên tự do, KHÔNG ép tên thật
    note: str = ""                 # tuỳ chọn - lý do đưa vào blacklist
    active: bool = True            # tuỳ chọn - tạm ngưng cảnh báo không cần xoá entry
    created_at: str = ""
    # Mỗi phần tử là 1 embedding 512-D (list[float] để json.dump được trực
    # tiếp, không cần numpy) - xem docstring module về lý do giữ nhiều thay
    # vì trung bình cộng.
    embeddings: list[list[float]] = field(default_factory=list)
    # photo_paths[i] = đường dẫn ảnh evidence GỐC (từ EventStore, KHÔNG copy
    # riêng ra chỗ khác) mà embeddings[i] được trích ra - CÙNG index, CÙNG độ
    # dài với embeddings - chỉ để hiển thị ảnh đại diện ở trang quản lý
    # (pages/blacklist_page.py), KHÔNG dùng để so khớp (đó là việc của
    # embeddings). Ảnh có thể bị EventStore tự xoá theo retention (90 ngày,
    # xem core/event_store.py) - path treo (file không còn) không ảnh hưởng
    # gì tới khả năng nhận diện, chỉ mất ảnh xem trước, UI tự xử lý (hiện
    # placeholder).
    photo_paths: list[str] = field(default_factory=list)

    @staticmethod
    def new(name: str, note: str = "") -> "BlacklistEntry":
        return BlacklistEntry(
            id=str(uuid.uuid4())[:8],
            name=name,
            note=note,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: dict) -> "BlacklistEntry":
        return BlacklistEntry(
            id=d["id"],
            name=d["name"],
            note=d.get("note", ""),
            active=d.get("active", True),
            created_at=d.get("created_at", ""),
            embeddings=d.get("embeddings", []),
            photo_paths=d.get("photo_paths", []),
        )


class BlacklistStore(QObject):
    """Singleton - CameraPipeline (nhiều thread) chỉ gọi match() (đọc
    _embeddings_matrix/_row_owner, an toàn không cần Lock vì mọi thao tác ghi
    (create/update/delete/add_embeddings) đều THAY NGUYÊN reference 2 mảng đó
    bằng _rebuild_matrix() - gán reference là thao tác atomic trong CPython,
    giống hệt lý do KnownFacesStore không cần Lock cho match())."""

    _instance: "BlacklistStore | None" = None

    updated = pyqtSignal()  # bắn sau MỌI thay đổi entries (thêm/sửa/xoá/bổ sung ảnh) - pages/blacklist_page.py lắng nghe để tự làm mới danh sách

    @classmethod
    def instance(cls) -> "BlacklistStore":
        if cls._instance is None:
            cls._instance = BlacklistStore()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._entries: list[BlacklistEntry] = []
        self._embeddings_matrix: np.ndarray = np.empty((0, 0), dtype=np.float32)
        # _row_owner[i] = index vào self._entries mà dòng i (1 embedding)
        # thuộc về - CHỈ entry active mới có dòng trong ma trận (entry tạm
        # ngưng vẫn hiện trong self._entries cho UI quản lý, nhưng không
        # tham gia match() nữa).
        self._row_owner: list[int] = []
        self._load_all()

    # ------------------------------------------------------------------ #
    # Đọc từ đĩa
    # ------------------------------------------------------------------ #
    def _load_all(self) -> None:
        self._entries = []
        folder = _blacklist_dir()
        for filename in sorted(os.listdir(folder)):
            if not filename.endswith(".json"):
                continue
            try:
                with open(os.path.join(folder, filename), "r", encoding="utf-8") as f:
                    self._entries.append(BlacklistEntry.from_dict(json.load(f)))
            except (OSError, ValueError, KeyError):
                continue  # 1 file hỏng không được làm crash cả danh sách
        self._rebuild_matrix()

    def _rebuild_matrix(self) -> None:
        rows: list[np.ndarray] = []
        owner: list[int] = []
        for idx, entry in enumerate(self._entries):
            if not entry.active:
                continue
            for emb in entry.embeddings:
                rows.append(np.array(emb, dtype=np.float32))
                owner.append(idx)
        self._embeddings_matrix = np.stack(rows).astype(np.float32) if rows else np.empty((0, 0), dtype=np.float32)
        self._row_owner = owner

    def _save_entry(self, entry: BlacklistEntry) -> None:
        with open(_entry_path(entry.id), "w", encoding="utf-8") as f:
            json.dump(entry.to_dict(), f, indent=2)

    # ------------------------------------------------------------------ #
    # Đọc - dùng bởi pages/blacklist_page.py
    # ------------------------------------------------------------------ #
    @property
    def entries(self) -> list[BlacklistEntry]:
        return list(self._entries)

    def get_entry(self, entry_id: str) -> BlacklistEntry | None:
        return next((e for e in self._entries if e.id == entry_id), None)

    # ------------------------------------------------------------------ #
    # So khớp - dùng bởi CameraPipeline._bind_face_identities (nhiều thread,
    # chỉ ĐỌC, xem docstring class ở trên)
    # ------------------------------------------------------------------ #
    def match(self, embedding: np.ndarray, threshold: float) -> tuple[BlacklistEntry | None, float]:
        """So 1 embedding khuôn mặt với TẤT CẢ embedding của TẤT CẢ entry
        đang active - trả về (entry khớp nhất, similarity) nếu vượt
        threshold, ngược lại (None, similarity cao nhất đo được - có thể 0.0
        nếu blacklist rỗng)."""
        if self._embeddings_matrix.shape[0] == 0:
            return None, 0.0
        sims = self._embeddings_matrix @ embedding
        idx = int(np.argmax(sims))
        best_sim = float(sims[idx])
        if best_sim > threshold:
            return self._entries[self._row_owner[idx]], best_sim
        return None, best_sim

    # ------------------------------------------------------------------ #
    # Ghi - dùng bởi pages/blacklist_page.py (main thread, UI thao tác)
    # ------------------------------------------------------------------ #
    def create_entry(
        self, name: str, note: str, embeddings: list[np.ndarray], photo_paths: list[str]
    ) -> BlacklistEntry:
        """photo_paths PHẢI cùng độ dài với embeddings (photo_paths[i] = ảnh
        gốc mà embeddings[i] được trích ra, xem BlacklistEntry.photo_paths) -
        gọi bởi ui/dialogs/blacklist_photo_picker_dialog.py, nơi duy nhất xây
        cả 2 danh sách này cùng lúc từ EventStore."""
        entry = BlacklistEntry.new(name=name, note=note)
        entry.embeddings = [emb.tolist() for emb in embeddings[:_MAX_EMBEDDINGS_PER_ENTRY]]
        entry.photo_paths = list(photo_paths[:_MAX_EMBEDDINGS_PER_ENTRY])
        self._entries.append(entry)
        self._save_entry(entry)
        self._rebuild_matrix()
        self.updated.emit()
        return entry

    def update_entry(
        self, entry_id: str, name: str | None = None, note: str | None = None, active: bool | None = None
    ) -> None:
        entry = self.get_entry(entry_id)
        if entry is None:
            return
        if name is not None:
            entry.name = name
        if note is not None:
            entry.note = note
        if active is not None:
            entry.active = active
        self._save_entry(entry)
        self._rebuild_matrix()
        self.updated.emit()

    def delete_entry(self, entry_id: str) -> None:
        entry = self.get_entry(entry_id)
        if entry is None:
            return
        self._entries.remove(entry)
        try:
            os.remove(_entry_path(entry_id))
        except OSError:
            pass
        self._rebuild_matrix()
        self.updated.emit()

    def add_embeddings(self, entry_id: str, embeddings: list[np.ndarray], photo_paths: list[str]) -> None:
        """Bổ sung thêm ảnh vào 1 entry ĐÃ CÓ (luồng "Thêm ảnh từ lịch sử
        nhận diện" - xem pages/blacklist_page.py) - rolling: vượt quá
        _MAX_EMBEDDINGS_PER_ENTRY thì bỏ bớt embedding/ảnh CŨ NHẤT (đầu danh
        sách) trước, không phải ghi đè/trung bình. photo_paths PHẢI cùng độ
        dài với embeddings (xem docstring create_entry)."""
        entry = self.get_entry(entry_id)
        if entry is None or not embeddings:
            return
        entry.embeddings.extend(emb.tolist() for emb in embeddings)
        entry.photo_paths.extend(photo_paths)
        if len(entry.embeddings) > _MAX_EMBEDDINGS_PER_ENTRY:
            entry.embeddings = entry.embeddings[-_MAX_EMBEDDINGS_PER_ENTRY:]
            entry.photo_paths = entry.photo_paths[-_MAX_EMBEDDINGS_PER_ENTRY:]
        self._save_entry(entry)
        self._rebuild_matrix()
        self.updated.emit()
