"""Execute an admitted pipeline graph: the public runner entry point.

:func:`run_pipeline` takes an :class:`AdmissionSnapshot` from
``admit_pipeline``, the injected :class:`OperationCatalogue` and the
Engine-owned resources. It never imports a domain package; adapters do the
domain work.

* Ready nodes run within :class:`RunLimits`: a concurrency bound (default
  two) and resource leases (model calls and source commits are exclusive
  on their capabilities by default).
* A node failure fails its execution unit and skips its dependants. A
  :class:`FatalNodeError` stops the run.
* An adapter fallback is a successful outcome with a reported reason.
* With a :class:`UnitSplit`, the nodes downstream of one output run once
  per unit (for example once per source file). Each unit's values are
  released before the next unit starts. Earlier unit commits remain in the
  result when a later unit fails.
* Cancellation is run-scoped and cooperative (see ``cancellation``).
* Node durations are recorded separately. ``wall_time_s`` is measured end
  to end and is never a sum of node durations.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .adapters import CancellationToken
from .cancellation import run_cancellation
from .catalogue import EffectClass, OperationCatalogue, RegisteredOperation
from .events import EventEmitter, EventSink
from .execution import GraphPass
from .results import EventKind, NodeStatus, PipelineResult, RunStatus, UnitOutcome
from .run_state import RunState
from .scheduler import lease_for
from .snapshot import AdmissionSnapshot
from .wiring import SourceKey, Wiring

_DEFAULT_EXCLUSIVE = frozenset({EffectClass.MODEL_CALL, EffectClass.SOURCE_COMMIT})


@dataclass(frozen=True)
class RunLimits:
    """Scheduling limits for one run.

    Attributes:
        max_concurrency: Most nodes that run at the same time.
        exclusive_effects: Effects whose operations hold exclusive leases
            on their capabilities. Other operations hold shared leases.
    """

    max_concurrency: int = 2
    exclusive_effects: frozenset[EffectClass] = _DEFAULT_EXCLUSIVE

    def __post_init__(self) -> None:
        """Reject a bound below one."""
        if self.max_concurrency < 1:
            raise ValueError(f"max_concurrency must be at least 1, not {self.max_concurrency}")


@dataclass(frozen=True)
class UnitSplit:
    """Run the downstream part of a graph once per unit.

    Attributes:
        node: Node whose output lists the units, for example ``discover``.
        port: Output port that holds the unit sequence.
        unit_id: Returns the identifier of one unit. Default ``str``.
    """

    node: str
    port: str
    unit_id: Callable[[Any], str] = str

    def label(self) -> str:
        """Return ``node.port``."""
        return f"{self.node}.{self.port}"


async def run_pipeline(
    snapshot: AdmissionSnapshot,
    catalogue: OperationCatalogue,
    resources: Mapping[str, Any],
    *,
    on_event: EventSink | None = None,
    cancellation: CancellationToken | None = None,
    limits: RunLimits | None = None,
    units: UnitSplit | None = None,
    run_id: str | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> PipelineResult:
    """Execute an admitted graph and return its actual outcome.

    Args:
        snapshot: Frozen admission state from ``admit_pipeline``.
        catalogue: Catalogue whose adapters execute the nodes.
        resources: Engine-owned resources by name. Adapters borrow them
            through a read-only mapping and never close them.
        on_event: Async sink for ordered :class:`PipelineEvent` values.
        cancellation: Run-scoped token. Pass a ``RunCancellation`` so the
            runner wakes on a request; other tokens are polled.
        limits: Scheduling limits. Default: two nodes, exclusive model
            calls and source commits.
        units: Optional per-unit split, for example per source file.
        run_id: Run identifier. Default: a new random identifier.
        clock: Monotonic clock in seconds, for durations.

    Returns:
        The result. Runtime failures and cancellation produce a result; they
        do not raise.

    Raises:
        ValueError: If ``units`` names a node or port that does not exist.
        asyncio.CancelledError: If the awaiting task was cancelled. Started
            nodes finish first and the terminal event is emitted.
    """
    limits = limits or RunLimits()
    token = run_cancellation(cancellation)
    run_id = run_id or uuid.uuid4().hex
    graph = snapshot.graph
    entries, missing = _resolve_entries(snapshot, catalogue)
    if units is not None:
        _check_split(snapshot, entries, units)
    emitter = EventEmitter(run_id, on_event)
    started = clock()
    if missing:
        error = "; ".join(missing)
        await emitter.emit(EventKind.RUN_FAILED, message=error)
        return PipelineResult(
            run_id=run_id,
            status=RunStatus.FAILED,
            graph_identity=snapshot.graph_identity,
            error=error,
            wall_time_s=max(clock() - started, 0.0),
        )
    state = RunState(
        run_id=run_id,
        snapshot=snapshot,
        graph=graph,
        wiring=Wiring.build(graph),
        entries=entries,
        leases={n: lease_for(e.descriptor, limits.exclusive_effects) for n, e in entries.items()},
        resources=resources,
        emitter=emitter,
        token=token,
        max_concurrency=limits.max_concurrency,
        clock=clock,
    )
    await emitter.emit(EventKind.RUN_STARTED, data={"nodes": len(snapshot.order)})
    seeds: dict[SourceKey, Any] = {("", name): value for name, value in snapshot.inputs.items()}
    if units is None:
        whole = GraphPass(state, snapshot.order, unit_id=None, seeds=seeds)
        await whole.run()
        state.outcomes.extend(whole.ordered_outcomes())
        outputs, unit_outcomes = whole.graph_outputs(), ()
    else:
        outputs, unit_outcomes = await _run_units(state, units, seeds)
    return await _conclude(state, outputs, unit_outcomes, started)


def _resolve_entries(
    snapshot: AdmissionSnapshot, catalogue: OperationCatalogue
) -> tuple[dict[str, RegisteredOperation], list[str]]:
    entries, missing = {}, []
    for node in snapshot.nodes:
        entry = catalogue.get(node.operation, node.version)
        if entry is None:
            missing.append(
                f"Operation {node.operation!r} version {node.version} (node {node.node_id!r}) "
                "is not registered in this catalogue. Register it, or admit the graph again."
            )
        else:
            entries[node.node_id] = entry
    return entries, missing


def _check_split(
    snapshot: AdmissionSnapshot, entries: Mapping[str, RegisteredOperation], units: UnitSplit
) -> None:
    entry = entries.get(units.node)
    if units.node not in snapshot.order or (
        entry is not None and entry.descriptor.output_port(units.port) is None
    ):
        raise ValueError(
            f"Unit split {units.label()} does not name an output port of an admitted node."
        )


async def _run_units(
    state: RunState, units: UnitSplit, seeds: dict[SourceKey, Any]
) -> tuple[dict[str, Any], tuple[UnitOutcome, ...]]:
    key = (units.node, units.port)
    downstream = state.wiring.descendants(units.node)
    order = state.snapshot.order
    prefix = GraphPass(
        state, tuple(n for n in order if n not in downstream), unit_id=None, seeds=seeds
    )
    await prefix.run()
    state.outcomes.extend(prefix.ordered_outcomes())
    outputs = prefix.graph_outputs()
    if state.failed_node is not None or state.stopping or key not in prefix.values:
        return outputs, ()
    sequence = prefix.values[key]
    if isinstance(sequence, str | bytes) or not hasattr(sequence, "__iter__"):
        state.fatal = True
        state.error = (
            f"Unit source {units.label()} returned {type(sequence).__name__}, "
            "not a sequence of units."
        )
        return outputs, ()
    shared = dict(prefix.values)
    del prefix
    per_unit = tuple(n for n in order if n in downstream)
    copy_keys = frozenset(shared) - {key}
    results: list[UnitOutcome] = []
    for unit in sequence:
        unit_id = units.unit_id(unit)
        if state.stopping:
            status = NodeStatus.CANCELLED if state.token.cancelled else NodeStatus.SKIPPED
            results.append(UnitOutcome(unit_id=unit_id, status=status))
            continue
        seeded = {**shared, key: (unit,)}
        results.append(await _run_unit(state, per_unit, unit_id, seeded, copy_keys))
    return outputs, tuple(results)


async def _run_unit(
    state: RunState,
    nodes: tuple[str, ...],
    unit_id: str,
    seeds: dict[SourceKey, Any],
    copy_keys: frozenset[SourceKey],
) -> UnitOutcome:
    await state.emitter.emit(EventKind.UNIT_STARTED, unit_id=unit_id)
    started = state.clock()
    unit = GraphPass(state, nodes, unit_id=unit_id, seeds=seeds, copy_keys=copy_keys)
    await unit.run()
    state.outcomes.extend(unit.ordered_outcomes())
    statuses = {o.status for o in unit.outcomes.values()}
    if unit.failed_node is not None:
        status, kind = NodeStatus.FAILED, EventKind.UNIT_FAILED
    elif NodeStatus.CANCELLED in statuses:
        status, kind = NodeStatus.CANCELLED, EventKind.UNIT_CANCELLED
    else:
        status, kind = NodeStatus.SUCCEEDED, EventKind.UNIT_COMPLETED
    outcome = UnitOutcome(
        unit_id=unit_id,
        status=status,
        failed_node=unit.failed_node,
        error=unit.error,
        effects=tuple(unit.effects),
        outputs=unit.graph_outputs(),
        duration_s=max(state.clock() - started, 0.0),
    )
    await state.emitter.emit(
        kind, unit_id=unit_id, message=unit.error or "", data={"effects": len(unit.effects)}
    )
    return outcome


async def _conclude(
    state: RunState,
    outputs: dict[str, Any],
    units: tuple[UnitOutcome, ...],
    started: float,
) -> PipelineResult:
    wall = max(state.clock() - started, 0.0)
    error = state.error
    failed_units = [u for u in units if u.status is NodeStatus.FAILED]
    if failed_units:
        error = f"{len(failed_units)} of {len(units)} units failed. First failure: {state.error}"
    if state.token.cancelled:
        await state.report_cancelling()
        status, kind = RunStatus.CANCELLED, EventKind.RUN_CANCELLED
    elif error is not None:
        status, kind = RunStatus.FAILED, EventKind.RUN_FAILED
    else:
        status, kind = RunStatus.SUCCEEDED, EventKind.RUN_COMPLETED
    await state.emitter.emit(
        kind, message=error or "", data={"completed_effects": len(state.effects)}
    )
    result = PipelineResult(
        run_id=state.run_id,
        status=status,
        graph_identity=state.snapshot.graph_identity,
        outputs=outputs,
        nodes=tuple(state.outcomes),
        failed_node=state.failed_node,
        completed_effects=tuple(state.effects),
        wall_time_s=wall,
        error=error,
        units=units,
    )
    if state.outer_cancelled:
        raise asyncio.CancelledError
    return result
