"""Ordered run events delivered to an injected async sink.

The emitter gives each event the next sequence number of its run when the
event is created, so the order is the order of the transitions. Events wait
in a queue and go to the sink one at a time, in sequence order.

Adapter progress may come from a worker thread. :meth:`EventEmitter.post`
is thread-safe; the runner sends posted progress at its next scheduling
point. A sink failure is logged and does not stop the run, because a
started commit must still finish.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

from .results import EventKind, PipelineEvent

logger = logging.getLogger(__name__)

EventSink = Callable[[PipelineEvent], Awaitable[None]]


def json_safe(data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return a JSON-safe copy of ``data``; unknown values become text."""
    if not data:
        return {}
    return json.loads(json.dumps(dict(data), default=str))


class EventEmitter:
    """Assigns run sequence numbers and delivers events in order.

    Args:
        run_id: Run identifier written on every event.
        sink: Async callback, or ``None`` to discard events.
    """

    def __init__(self, run_id: str, sink: EventSink | None) -> None:
        """Create an emitter with no events."""
        self.run_id = run_id
        self._sink = sink
        self._sequence = 0
        self._lock = threading.Lock()
        self._pending: deque[PipelineEvent] = deque()
        self._delivery = asyncio.Lock()

    def post(
        self,
        kind: EventKind,
        *,
        node_id: str | None = None,
        unit_id: str | None = None,
        message: str = "",
        data: Mapping[str, Any] | None = None,
    ) -> None:
        """Queue one event. Safe to call from any thread."""
        safe = json_safe(data)
        with self._lock:
            self._sequence += 1
            event = PipelineEvent(
                run_id=self.run_id,
                sequence=self._sequence,
                kind=kind,
                node_id=node_id,
                unit_id=unit_id,
                message=message,
                data=safe,
            )
            if self._sink is not None:
                self._pending.append(event)

    async def emit(
        self,
        kind: EventKind,
        *,
        node_id: str | None = None,
        unit_id: str | None = None,
        message: str = "",
        data: Mapping[str, Any] | None = None,
    ) -> None:
        """Queue one event and deliver every queued event."""
        self.post(kind, node_id=node_id, unit_id=unit_id, message=message, data=data)
        await self.flush()

    async def flush(self) -> None:
        """Deliver queued events to the sink in sequence order."""
        if self._sink is None:
            return
        async with self._delivery:
            while True:
                with self._lock:
                    if not self._pending:
                        return
                    event = self._pending.popleft()
                try:
                    await self._sink(event)
                except Exception:
                    logger.exception(
                        "Pipeline event sink failed for run %s event %d; the run continues.",
                        event.run_id,
                        event.sequence,
                    )
