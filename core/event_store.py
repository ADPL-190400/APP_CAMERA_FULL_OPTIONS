"""
EventStore: lưu trữ TOÀN app các sự kiện cảnh báo (PPE/Fire/Fall/Stranger)
kèm ảnh bằng chứng - singleton dùng chung, cùng kiểu với DeviceManager/
KnownFacesStore. Ảnh lưu ở {account_dir}/events/{device_id}/, metadata lưu
trong SQLite {account_dir}/events.db - RIÊNG cho tài khoản đang đăng nhập
(core/account_context.py), tránh lẫn Event Log giữa các tài khoản dùng
chung máy.

Vì sao SQLite thay vì JSON (bản cũ): bản JSON phải đọc/ghi lại TOÀN BỘ file
mỗi khi có 1 event mới (chi phí I/O tăng dần theo TỔNG số event đã có, không
phải hằng số - camera nào báo động cũng bị chặn thêm lúc ghi), và trang Event
Log phải load hết + sort lại toàn bộ list rồi mới lọc/phân trang bằng Python,
không đẩy được lọc/phân trang xuống tầng lưu trữ. SQLite (embedded, sẵn
trong Python stdlib, không cần cài server riêng) cho: ghi INSERT incremental
(O(1), không phụ thuộc tổng số event cũ), query có WHERE/LIMIT/OFFSET + index
(lọc + phân trang ngay ở DB, không cần load hết vào RAM), và ghi có
transaction nên không có rủi ro hỏng file do ghi dở dang giữa chừng.

Retention: tự xoá event (+ ảnh bằng chứng) cũ hơn _RETENTION_DAYS ngày, tránh
phình to vô hạn - chạy 1 lần lúc khởi tạo (đủ cho app chạy qua nhiều ngày),
và throttle chạy lại tối đa 1 lần/_PRUNE_INTERVAL_SEC nếu app mở liên tục rất
lâu trong 1 phiên (xem _maybe_prune).

Có migrate 1 LẦN DUY NHẤT dữ liệu từ events.json bản cũ (nếu còn) sang SQLite
lúc khởi tạo - không làm mất lịch sử Event Log đã có của người dùng khi nâng
cấp lên bản này.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta

import cv2
from PyQt6.QtCore import QObject, pyqtSignal

from core.account_context import account_dir
from core.models.event_record import EventRecord, EventKind

_RETENTION_DAYS = 90
_PRUNE_INTERVAL_SEC = 3600.0  # không check retention quá 1 lần/giờ trong 1 phiên chạy dài


def _events_dir() -> str:
    return os.path.join(account_dir(), "events")


def _events_db_path() -> str:
    return os.path.join(account_dir(), "events.db")


def _legacy_events_json_path() -> str:
    return os.path.join(account_dir(), "events.json")


class EventStore(QObject):
    _instance: "EventStore | None" = None

    event_added = pyqtSignal(object)  # EventRecord

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        os.makedirs(account_dir(), exist_ok=True)
        self._conn = sqlite3.connect(_events_db_path(), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                device_id TEXT NOT NULL,
                camera_name TEXT NOT NULL,
                kind TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                image_path TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                embedding BLOB DEFAULT NULL
            )
            """
        )
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_camera ON events(camera_name)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind)")
        self._conn.commit()
        self._migrate_detail_column()
        self._migrate_embedding_column()
        self._migrate_legacy_json()
        self._last_prune = time.monotonic()
        self._prune_old_events()

    @classmethod
    def instance(cls) -> "EventStore":
        if cls._instance is None:
            cls._instance = EventStore()
        return cls._instance

    # ------------------------------------------------------------------ #
    # Migration cột "detail" (thêm sau - DB cũ tạo TRƯỚC khi có cột này
    # trong CREATE TABLE ở trên sẽ KHÔNG tự có cột, "CREATE TABLE IF NOT
    # EXISTS" chỉ chạy khi bảng chưa tồn tại) - ALTER TABLE thêm cột, lờ đi
    # lỗi "duplicate column" nếu đã chạy migration này rồi (idempotent).
    # ------------------------------------------------------------------ #
    def _migrate_detail_column(self) -> None:
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN detail TEXT NOT NULL DEFAULT ''")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # cột đã tồn tại (DB tạo mới đã có sẵn, hoặc đã migrate từ trước)

    def _migrate_embedding_column(self) -> None:
        """embedding (BLOB, NULL mặc định) - CHỈ Stranger/Blacklist mới có
        giá trị (xem add_event/core/blacklist_store.py) - lưu ngay lúc event
        được tạo để tránh phải detect lại trên ảnh crop đã lưu (đo thật: ~55%
        thất bại vì crop quá nhỏ/đã nén JPEG, xem CameraPipeline._capture_face_events)."""
        try:
            self._conn.execute("ALTER TABLE events ADD COLUMN embedding BLOB DEFAULT NULL")
            self._conn.commit()
        except sqlite3.OperationalError:
            pass  # cột đã tồn tại

    # ------------------------------------------------------------------ #
    # Migration từ events.json bản cũ (chỉ chạy nếu file đó còn tồn tại -
    # đổi tên thành .migrated/.corrupt ngay sau khi xử lý nên chỉ chạy 1 lần)
    # ------------------------------------------------------------------ #
    def _migrate_legacy_json(self) -> None:
        legacy_path = _legacy_events_json_path()
        if not os.path.exists(legacy_path):
            return
        try:
            with open(legacy_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            records = [EventRecord.from_dict(item) for item in raw]
        except (json.JSONDecodeError, OSError, TypeError, KeyError, ValueError):
            os.rename(legacy_path, legacy_path + ".corrupt")
            return
        self._conn.executemany(
            "INSERT OR IGNORE INTO events (id, device_id, camera_name, kind, timestamp, image_path, detail) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            [(r.id, r.device_id, r.camera_name, r.kind.value, r.timestamp, r.image_path, r.detail) for r in records],
        )
        self._conn.commit()
        os.rename(legacy_path, legacy_path + ".migrated")

    # ------------------------------------------------------------------ #
    # Ghi
    # ------------------------------------------------------------------ #
    def add_event(
        self, device_id: str, camera_name: str, kind: EventKind, frame, detail: str = "",
        embedding: bytes | None = None,
    ) -> EventRecord:
        """Lưu 1 frame (numpy BGR, full-res) thành ảnh JPEG + thêm 1
        EventRecord (INSERT incremental, KHÔNG ghi lại toàn bộ bảng). Gọi từ
        thread của CameraPipeline (không phải main thread) - an toàn nhờ
        self._lock; event_added tự động queue sang main thread nhờ cơ chế Qt
        signal chuẩn (giống DeviceManager.ai_result_ready).

        detail: thông tin phụ hiện tại Event Log (vd tên người quen được
        nhận diện - xem EventRecord.detail) - rỗng nếu loại sự kiện không có
        danh tính cụ thể để hiện (PPE/Fire/Fall/Stranger/Overcrowding).

        embedding: face.normed_embedding.tobytes() (float32 512-D, ~2KB) -
        CHỈ Stranger/Blacklist truyền vào (xem CameraPipeline._capture_face_events)
        - None với mọi loại khác. KHÔNG trả lại qua query_events()/EventRecord
        (giữ việc load danh sách Event Log nhẹ, đa số lượt không cần tới) -
        đọc riêng qua get_embedding() khi thực sự cần (vd gallery picker
        Blacklist, xem core/blacklist_store.py)."""
        record = EventRecord.new(device_id, camera_name, kind, image_path="", detail=detail)
        record.image_path = self._save_image(record, frame)

        with self._lock:
            self._conn.execute(
                "INSERT INTO events (id, device_id, camera_name, kind, timestamp, image_path, detail, embedding) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record.id, record.device_id, record.camera_name, record.kind.value,
                    record.timestamp, record.image_path, record.detail, embedding,
                ),
            )
            self._conn.commit()
            self._maybe_prune()

        self.event_added.emit(record)
        return record

    def get_embedding(self, event_id: str) -> bytes | None:
        """Đọc riêng embedding của 1 event (không đi qua query_events() - xem
        docstring add_event) - None nếu event không tồn tại hoặc không có
        embedding (mọi loại trừ Stranger/Blacklist)."""
        with self._lock:
            cur = self._conn.execute("SELECT embedding FROM events WHERE id = ?", (event_id,))
            row = cur.fetchone()
        return row[0] if row else None

    @staticmethod
    def _save_image(record: EventRecord, frame) -> str:
        device_dir = os.path.join(_events_dir(), record.device_id)
        os.makedirs(device_dir, exist_ok=True)
        safe_ts = record.timestamp.replace(":", "-")
        filename = f"{safe_ts}_{record.kind.value}_{record.id}.jpg"
        path = os.path.join(device_dir, filename)
        cv2.imwrite(path, frame)
        return path

    # ------------------------------------------------------------------ #
    # Retention - PHẢI gọi trong lúc giữ self._lock (hoặc lúc __init__,
    # trước khi thread khác có reference tới self)
    # ------------------------------------------------------------------ #
    def _maybe_prune(self) -> None:
        now = time.monotonic()
        if now - self._last_prune < _PRUNE_INTERVAL_SEC:
            return
        self._last_prune = now
        self._prune_old_events()

    def _prune_old_events(self) -> None:
        cutoff = (datetime.now() - timedelta(days=_RETENTION_DAYS)).isoformat(timespec="seconds")
        cur = self._conn.execute("SELECT image_path FROM events WHERE timestamp < ?", (cutoff,))
        old_paths = [row[0] for row in cur.fetchall()]
        if not old_paths:
            return
        self._conn.execute("DELETE FROM events WHERE timestamp < ?", (cutoff,))
        self._conn.commit()
        for path in old_paths:
            try:
                os.remove(path)
            except OSError:
                pass

    # ------------------------------------------------------------------ #
    # Đọc - lọc + phân trang ngay ở tầng DB (không load hết vào RAM), dùng
    # bởi pages/event_log_page.py
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_where(
        camera_name: str | None, kind: EventKind | None, since: datetime | None
    ) -> tuple[str, list]:
        where = []
        params: list = []
        if camera_name is not None:
            where.append("camera_name = ?")
            params.append(camera_name)
        if kind is not None:
            where.append("kind = ?")
            params.append(kind.value)
        if since is not None:
            where.append("timestamp >= ?")
            params.append(since.isoformat(timespec="seconds"))
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        return clause, params

    def query_events(
        self,
        camera_name: str | None = None,
        kind: EventKind | None = None,
        since: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[EventRecord]:
        clause, params = self._build_where(camera_name, kind, since)
        sql = (
            f"SELECT id, device_id, camera_name, kind, timestamp, image_path, detail FROM events "
            f"{clause} ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        )
        with self._lock:
            cur = self._conn.execute(sql, [*params, limit, offset])
            rows = cur.fetchall()
        return [
            EventRecord(
                id=r[0], device_id=r[1], camera_name=r[2], kind=EventKind(r[3]),
                timestamp=r[4], image_path=r[5], detail=r[6],
            )
            for r in rows
        ]

    def count_events(
        self,
        camera_name: str | None = None,
        kind: EventKind | None = None,
        since: datetime | None = None,
    ) -> int:
        clause, params = self._build_where(camera_name, kind, since)
        with self._lock:
            cur = self._conn.execute(f"SELECT COUNT(*) FROM events {clause}", params)
            return cur.fetchone()[0]
