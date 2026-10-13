"""Run events and results returned by graph execution.

Events report actual states only. The runner (``runner.py``) emits them
in sequence order; this module defines their shape. Results name the failing
node, skipped dependants and every completed effect, so a failed or
cancelled run still discloses committed sources.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from .snapshot import EffectiveControl

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class EventKind(StrEnum):
    """Kinds of run and node events."""

    RUN_ADMITTED = "run_admitted"
    RUN_STARTED = "run_started"
    UNIT_STARTED = "unit_started"
    UNIT_COMPLETED = "unit_completed"
    UNIT_FAILED = "unit_failed"
    UNIT_CANCELLED = "unit_cancelled"
    NODE_QUEUED = "node_queued"
    NODE_STARTED = "node_started"
    NODE_PROGRESS = "node_progress"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    NODE_SKIPPED = "node_skipped"
    NODE_BYPASSED = "node_bypassed"
    NODE_FALLBACK = "node_fallback"
    NODE_CANCELLED = "node_cancelled"
    EFFECT_COMMITTED = "effect_committed"
    RUN_CANCELLING = "run_cancelling"
    RUN_CANCELLED = "run_cancelled"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"


class RunStatus(StrEnum):
    """Terminal or current run status."""

    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"


class NodeStatus(StrEnum):
    """Per-node outcome."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    BYPASSED = "bypassed"
    CANCELLED = "cancelled"


def _now() -> datetime:
    return datetime.now(UTC)


class PipelineEvent(BaseModel):
    """One ordered run event with a safe summary.

    Attributes:
        run_id: Run identifier.
        sequence: Strictly increasing per run, starting at 1.
        kind: Event kind.
        node_id: Node the event concerns, if any.
        unit_id: Execution unit (for example a source) the event concerns.
        message: Short human-readable summary. Never holds secrets.
        data: Small JSON summary. Never holds vectors or full documents.
        timestamp: UTC time the event was produced.
    """

    model_config = _FROZEN

    run_id: str
    sequence: int = Field(ge=1)
    kind: EventKind
    node_id: str | None = None
    unit_id: str | None = None
    message: str = ""
    data: dict[str, JsonValue] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=_now)


class NodeOutcome(BaseModel):
    """What happened to one node.

    Attributes:
        node_id: Node identifier.
        status: Final node status.
        error: Failure message, when failed.
        fallback: Domain fallback reason, when one applied.
        effects: Completed effects, for example committed source identities.
        duration_s: Node wall time. Overlapping node times are not summed.
        unit_id: Execution unit the outcome belongs to, if any.
        summary: Small JSON summary of the node, the same data as its
            completed or bypassed event (for example ``reranked: false``
            and the reason). Empty when the node reported none.
    """

    model_config = _FROZEN

    node_id: str
    status: NodeStatus
    error: str | None = None
    fallback: str | None = None
    effects: tuple[str, ...] = ()
    duration_s: float | None = Field(default=None, ge=0)
    unit_id: str | None = None
    summary: dict[str, JsonValue] = Field(default_factory=dict)


class UnitOutcome(BaseModel):
    """What happened to one execution unit, for example one source file.

    Attributes:
        unit_id: Unit identifier.
        status: ``succeeded``, ``failed``, ``skipped`` (after a fatal error)
            or ``cancelled``.
        failed_node: First node that failed in this unit, if any.
        error: Failure message, if any.
        effects: Effects this unit completed.
        outputs: Graph outputs this unit produced. Intermediate values are
            released when the unit ends.
        duration_s: Unit wall time, when the unit ran.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    unit_id: str
    status: NodeStatus
    failed_node: str | None = None
    error: str | None = None
    effects: tuple[str, ...] = ()
    outputs: dict[str, Any] = Field(default_factory=dict)
    duration_s: float | None = Field(default=None, ge=0)


class PipelineResult(BaseModel):
    """The public result of a graph run.

    Attributes:
        run_id: Run identifier.
        status: Terminal run status.
        graph_identity: Execution identity of the admitted graph.
        outputs: Graph output name to value.
        nodes: Outcome of every node, in execution order.
        failed_node: First failing node, if any.
        completed_effects: Effects that completed, even on failure or
            cancellation.
        wall_time_s: End-to-end wall time (not a sum of node times).
        error: Run-level failure message, if any.
        units: Per-unit outcomes, when the run split its work into units.
        controls: Node id to the effective controls admitted for that node.
            ``source`` is ``node``, ``graph``, ``environment`` or ``profile``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    run_id: str
    status: RunStatus
    graph_identity: str
    outputs: dict[str, Any] = Field(default_factory=dict)
    nodes: tuple[NodeOutcome, ...] = ()
    failed_node: str | None = None
    completed_effects: tuple[str, ...] = ()
    wall_time_s: float | None = Field(default=None, ge=0)
    error: str | None = None
    units: tuple[UnitOutcome, ...] = ()
    controls: dict[str, tuple[EffectiveControl, ...]] = Field(default_factory=dict)

    @property
    def skipped_nodes(self) -> tuple[str, ...]:
        """Return the identifiers of skipped nodes."""
        return tuple(n.node_id for n in self.nodes if n.status is NodeStatus.SKIPPED)
