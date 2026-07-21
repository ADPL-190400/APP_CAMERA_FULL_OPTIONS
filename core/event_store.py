"""
EventStore: lưu trữ TOÀN app các sự kiện cảnh báo (PPE/Fire/Fall/Stranger)
kèm ảnh bằng chứng - singleton dùng chung, cùng kiểu với DeviceManager/
KnownFacesStore. Ảnh lưu ở {account_dir}/events/{device_id}/, metadata lưu
{account_dir}/events.json (atomic write, cùng pattern core/device_store.py) -
RIÊNG cho tài khoản đang đăng nhập (core/account_context.py), tránh lẫn
Event Log giữa các tài khoản dùng chung máy.
"""
from __future__ import annotations

import json
import os
import threading

import cv2
from PyQt6.QtCore import QObject, pyqtSignal

from core.account_context import account_dir
from core.models.event_record import EventRecord, EventKind


def _events_dir() -> str:
    return os.path.join(account_dir(), "events")


def _events_json_path() -> str:
    return os.path.join(account_dir(), "events.json")


class EventStore(QObject):
    _instance: "EventStore | None" = None

    event_added = pyqtSignal(object)  # EventRecord

    def __init__(self):
        super().__init__()
        self._lock = threading.Lock()
        self._events: list[EventRecord] = self._load_from_disk()

    @classmethod
    def instance(cls) -> "EventStore":
        if cls._instance is None:
            cls._instance = EventStore()
        return cls._instance

    def all_events(self) -> list[EventRecord]:
        with self._lock:
            return sorted(self._events, key=lambda e: e.timestamp, reverse=True)

    def add_event(self, device_id: str, camera_name: str, kind: EventKind, frame) -> EventRecord:
        """Lưu 1 frame (numpy BGR, full-res) thành ảnh JPEG + thêm 1
        EventRecord. Gọi từ thread của CameraPipeline (không phải main
        thread) - an toàn vì self._lock bảo vệ list + file JSON khỏi ghi đè
        lẫn nhau giữa nhiều camera báo động cùng lúc; event_added tự động
        queue sang main thread nhờ cơ chế Qt signal chuẩn (giống
        DeviceManager.ai_result_ready)."""
        record = EventRecord.new(device_id, camera_name, kind, image_path="")
        record.image_path = self._save_image(record, frame)

        with self._lock:
            self._events.append(record)
            self._save_to_disk()

        self.event_added.emit(record)
        return record

    @staticmethod
    def _save_image(record: EventRecord, frame) -> str:
        device_dir = os.path.join(_events_dir(), record.device_id)
        os.makedirs(device_dir, exist_ok=True)
        safe_ts = record.timestamp.replace(":", "-")
        filename = f"{safe_ts}_{record.kind.value}_{record.id}.jpg"
        path = os.path.join(device_dir, filename)
        cv2.imwrite(path, frame)
        return path

    def _save_to_disk(self) -> None:
        events_json = _events_json_path()
        os.makedirs(os.path.dirname(events_json), exist_ok=True)
        data = [e.to_dict() for e in self._events]
        tmp_path = events_json + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, events_json)

    @staticmethod
    def _load_from_disk() -> list[EventRecord]:
        events_json = _events_json_path()
        if not os.path.exists(events_json):
            return []
        try:
            with open(events_json, "r", encoding="utf-8") as f:
                raw = json.load(f)
            return [EventRecord.from_dict(item) for item in raw]
        except (json.JSONDecodeError, OSError, TypeError, KeyError, ValueError):
            return []
