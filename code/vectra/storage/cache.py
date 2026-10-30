"""In-memory answer cache for repeat questions."""
from __future__ import annotations

import threading
import time
from collections import OrderedDict
from typing import Any, Callable


class TTLCache:
    """Thread-safe TTL + LRU cache."""

    def __init__(self, maxsize: int, ttl_seconds: float, clock: Callable[[], float] = time.time):
        self.maxsize = maxsize
        self.ttl = ttl_seconds
        self._clock = clock
        self._data: OrderedDict[str, tuple[float, Any]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        with self._lock:
            item = self._data.get(key)
            if item is None:
                return None
            expires_at, value = item
            if self._clock() > expires_at:
                del self._data[key]
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = (self._clock() + self.ttl, value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._data)
