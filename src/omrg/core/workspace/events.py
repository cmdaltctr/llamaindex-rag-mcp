"""Commit run events, then notify subscribers; replay after a sequence.

The repository is the source of truth. A notification only wakes a
subscriber, which then reads the committed events after the last sequence
it delivered. A subscriber therefore never sees an uncommitted event, never
skips one, and never sees one twice.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from typing import Any

from omrg.core.workspace.records import TERMINAL_RUN_STATUSES, RunEventRecord, RunRecord
from omrg.core.workspace.repository import WorkspaceRepository

STATUS_EVENT = "run.status"


class RunEventLog:
    """Persist run updates and stream them to subscribers.

    Args:
        repository: Workspace repository; each update is one transaction.
    """

    def __init__(self, repository: WorkspaceRepository) -> None:
        """Create a log with no subscribers."""
        self._repository = repository
        self._waiters: dict[str, set[asyncio.Event]] = {}

    def record(
        self,
        run_id: str,
        *,
        kind: str,
        summary: Mapping[str, Any],
        status: str | None = None,
        node_id: str | None = None,
        unit_id: str | None = None,
        failure: Mapping[str, Any] | None = None,
        result_ref: str | None = None,
    ) -> tuple[RunRecord, RunEventRecord]:
        """Commit a run update with its event, then wake subscribers.

        Raises:
            KeyError: If the run does not exist.
            ValueError: If the run is terminal or the update is invalid.
        """
        committed = self._repository.record_update(
            run_id,
            kind=kind,
            summary=summary,
            status=status,
            node_id=node_id,
            unit_id=unit_id,
            failure=failure,
            result_ref=result_ref,
        )
        self.notify(run_id)
        return committed

    def notify(self, run_id: str) -> None:
        """Wake every subscriber of ``run_id``."""
        for waiter in self._waiters.get(run_id, ()):
            waiter.set()

    def replay(
        self, run_id: str, *, after_sequence: int = 0, limit: int | None = None
    ) -> list[RunEventRecord]:
        """Return committed events after ``after_sequence``, in order.

        Raises:
            KeyError: If the run does not exist.
        """
        return self._repository.list_events(run_id, after_sequence=after_sequence, limit=limit)

    async def subscribe(
        self, run_id: str, *, after_sequence: int = 0
    ) -> AsyncIterator[RunEventRecord]:
        """Yield committed events after ``after_sequence`` until the run ends.

        The stream replays retained events first, then follows new ones. It
        ends after the event that made the run terminal. Closing the stream
        detaches monitoring only; the run continues.

        Raises:
            KeyError: If the run does not exist.
        """
        wake = asyncio.Event()
        self._waiters.setdefault(run_id, set()).add(wake)
        last = after_sequence
        try:
            while True:
                wake.clear()
                events = self._repository.list_events(run_id, after_sequence=last)
                for event in events:
                    last = event["sequence"]
                    yield event
                run = self._repository.get_run(run_id)
                if run["status"] not in TERMINAL_RUN_STATUSES:
                    await wake.wait()
                elif run["last_sequence"] <= last or not events:
                    # A terminal run gets no new events; stop instead of spinning.
                    return
        finally:
            waiters = self._waiters.get(run_id, set())
            waiters.discard(wake)
            if not waiters:
                self._waiters.pop(run_id, None)
