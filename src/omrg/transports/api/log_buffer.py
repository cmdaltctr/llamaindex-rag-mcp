"""In-memory ring buffer of server log records (design D13).

``omrg web`` attaches one :class:`LogBuffer` to the root logger. The
buffer keeps the last 1,000 records in memory and writes no file. The
:class:`~omrg.transports.api.security.RedactingFilter` sits on the handler
itself, so provider keys and bearer tokens are removed before a record is
stored, whatever logger or handler order produced it.

Each record gets a sequence number that rises by one and never repeats in
one launch. Readers ask for the records after a sequence, which is how the
HTTP routes replay and follow the log.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Any

from .security import RedactingFilter, SecretSet

#: Records kept in memory.
LOG_CAPACITY = 1000
#: Longest stored message. A longer one is cut, with an ellipsis.
MAX_MESSAGE_CHARS = 10_000


class LogBuffer(logging.Handler):
    """A logging handler that keeps the newest records for the web log panel."""

    def __init__(self, secrets: Iterable[str] = (), capacity: int = LOG_CAPACITY) -> None:
        """Create the buffer.

        Args:
            secrets: Provider keys to remove from every record. A
                :class:`~omrg.transports.api.security.SecretSet` is read at
                filter time, so keys added later are removed too.
            capacity: Most records to keep.
        """
        super().__init__()
        self.capacity = capacity
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()
        self.secrets = secrets if isinstance(secrets, SecretSet) else SecretSet(secrets)
        self.addFilter(RedactingFilter(self.secrets))

    @property
    def last_seq(self) -> int:
        """Sequence of the newest record, or 0 when none was logged."""
        return self._seq

    def emit(self, record: logging.LogRecord) -> None:
        """Store *record* (already redacted by the handler's filter)."""
        try:
            message = record.getMessage()
            if len(message) > MAX_MESSAGE_CHARS:
                message = message[:MAX_MESSAGE_CHARS] + "…"
            entry = {
                "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname.lower(),
                "logger": record.name,
                "message": message,
            }
        except Exception:
            self.handleError(record)
            return
        with self._lock:
            self._seq += 1
            self._records.append({"seq": self._seq, **entry})

    def records(self, after: int = 0) -> list[dict[str, Any]]:
        """Return the buffered records with a sequence above *after*, oldest first."""
        with self._lock:
            return [item for item in self._records if item["seq"] > after]
