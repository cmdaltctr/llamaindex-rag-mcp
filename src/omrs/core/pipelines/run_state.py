"""State shared by every scheduling pass of one run."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .cancellation import RunCancellation
from .catalogue import RegisteredOperation
from .events import EventEmitter
from .models import GraphDocument
from .results import EventKind, NodeOutcome
from .scheduler import Lease
from .snapshot import AdmissionSnapshot
from .wiring import Wiring


@dataclass
class RunState:
    """State shared by every pass of one run."""

    run_id: str
    snapshot: AdmissionSnapshot
    graph: GraphDocument
    wiring: Wiring
    entries: Mapping[str, RegisteredOperation]
    leases: Mapping[str, Lease]
    resources: Mapping[str, Any]
    emitter: EventEmitter
    token: RunCancellation
    max_concurrency: int
    clock: Callable[[], float]
    outcomes: list[NodeOutcome] = field(default_factory=list)
    effects: list[str] = field(default_factory=list)
    failed_node: str | None = None
    error: str | None = None
    fatal: bool = False
    outer_cancelled: bool = False
    cancelling_reported: bool = False

    @property
    def stopping(self) -> bool:
        """Return whether no further node may start."""
        return self.fatal or self.token.cancelled

    async def report_cancelling(self) -> None:
        """Emit ``run_cancelling`` once, when cancellation is first seen."""
        if self.token.cancelled and not self.cancelling_reported:
            self.cancelling_reported = True
            await self.emitter.emit(
                EventKind.RUN_CANCELLING, message=self.token.reason or "Cancellation requested."
            )
