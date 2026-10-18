"""One scheduling pass over the nodes of one execution unit.

A pass routes port values, assembles joins, isolates fan-out values,
dispatches adapters through the catalogue and records actual outcomes. The
public entry point is :func:`omrg.core.pipelines.runner.run_pipeline`.

Value routing rules:

* A ``MANY`` input receives a tuple in declared order: connections in
  edge order, then graph inputs in input order. Completion order never
  changes it.
* When one value has more than one consumer (nodes or graph outputs),
  each consumer receives its own deep copy. Values a pass receives from
  an earlier pass are always copied, so units cannot change each other.
* An empty value (for example ``[]``) is a valid input, not a missing one.
"""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .adapters import NodeContext, NodeOutput
from .cancellation import PipelineCancelledError
from .catalogue import EffectClass, RegisteredOperation
from .ports import Cardinality
from .results import EventKind, NodeOutcome, NodeStatus
from .run_state import RunState
from .scheduler import ReadyScheduler
from .snapshot import NodeSnapshot
from .wiring import SourceKey


class FatalNodeError(Exception):
    """Raised by an adapter for an error that must stop the whole run.

    Ordinary exceptions fail only the current execution unit. Use this for
    graph or configuration errors that would fail every later unit too.
    """


@dataclass(frozen=True)
class _Finished:
    output: NodeOutput | None
    error: BaseException | None
    started: float
    ended: float


class GraphPass:
    """Runs a set of nodes once, for one unit (or for the whole run).

    Args:
        state: Shared run state.
        nodes: Nodes of this pass, in topological order.
        unit_id: Execution unit, or ``None`` for a run without units.
        seeds: Values available before the pass starts.
        copy_keys: Seed keys that are always copied on delivery.
    """

    def __init__(
        self,
        state: RunState,
        nodes: tuple[str, ...],
        *,
        unit_id: str | None,
        seeds: Mapping[SourceKey, Any],
        copy_keys: frozenset[SourceKey] = frozenset(),
    ) -> None:
        """Prepare the pass; nothing runs until :meth:`run`."""
        self.state = state
        self.nodes = nodes
        self.unit_id = unit_id
        self.values: dict[SourceKey, Any] = dict(seeds)
        self._copy_keys = copy_keys
        self.outcomes: dict[str, NodeOutcome] = {}
        self.effects: list[str] = []
        self.failed_node: str | None = None
        self.error: str | None = None

    # ── Values ────────────────────────────────────────────────────

    def deliver(self, key: SourceKey) -> Any:
        """Return the value at ``key`` for one consumer."""
        value = self.values[key]
        if key in self._copy_keys or self.state.wiring.consumers.get(key, 0) > 1:
            return copy.deepcopy(value)
        return value

    def _inputs(self, node_id: str, entry: RegisteredOperation) -> dict[str, Any]:
        inputs: dict[str, Any] = {}
        for port in entry.descriptor.inputs:
            keys = self.state.wiring.feeds.get((node_id, port.name), ())
            missing = [k for k in keys if k not in self.values]
            if missing:
                labels = ", ".join(f"{n or 'input'}.{p}" for n, p in missing)
                raise LookupError(f"Input port {port.name!r} has no value from {labels}.")
            if not keys:
                continue
            values = tuple(self.deliver(k) for k in keys)
            inputs[port.name] = values if port.cardinality is Cardinality.MANY else values[0]
        return inputs

    # ── Scheduling loop ───────────────────────────────────────────

    async def run(self) -> None:
        """Run every node of the pass and record outcomes."""
        state = self.state
        scheduler = ReadyScheduler(
            self.nodes,
            state.wiring.upstream,
            state.leases,
            max_concurrency=state.max_concurrency,
        )
        tasks: dict[asyncio.Task[_Finished], str] = {}
        waiter = asyncio.ensure_future(state.token.wait())
        try:
            while True:
                try:
                    if not await self._step(scheduler, tasks, waiter):
                        return
                except asyncio.CancelledError:
                    # The awaiting task was cancelled. Started nodes (an entered
                    # commit above all) still finish: request cooperative cancel.
                    if not tasks:
                        raise
                    state.outer_cancelled = True
                    state.token.cancel("The task awaiting the run was cancelled.")
        finally:
            waiter.cancel()

    async def _step(
        self,
        scheduler: ReadyScheduler,
        tasks: dict[asyncio.Task[_Finished], str],
        waiter: asyncio.Future[None],
    ) -> bool:
        """Start what may start and handle what finished; ``False`` when all is done."""
        state = self.state
        await state.report_cancelling()
        await self._announce_ready(scheduler)
        if state.stopping:
            self._stop_pending(scheduler)
        else:
            self._skip_commits_after_failure(scheduler)
            for node_id in scheduler.dispatchable():
                tasks[asyncio.create_task(self._invoke(node_id))] = node_id
                state.emitter.post(EventKind.NODE_STARTED, node_id=node_id, unit_id=self.unit_id)
        await state.emitter.flush()
        if not tasks:
            return False
        watch: set[asyncio.Future[Any]] = set(tasks)
        if not waiter.done():
            watch.add(waiter)
        done, _ = await asyncio.wait(watch, return_when=asyncio.FIRST_COMPLETED)
        finished = sorted((t for t in tasks if t in done), key=lambda t: self.nodes.index(tasks[t]))
        for task in finished:
            await self._finish(scheduler, tasks.pop(task), task.result())
        return True

    async def _announce_ready(self, scheduler: ReadyScheduler) -> None:
        while not self.state.stopping:
            ready = scheduler.pop_newly_ready()
            if not ready:
                return
            for node_id in ready:
                if self.state.snapshot.node(node_id).enabled:
                    self.state.emitter.post(
                        EventKind.NODE_QUEUED, node_id=node_id, unit_id=self.unit_id
                    )
                else:
                    self._bypass(scheduler, node_id)

    def _bypass(self, scheduler: ReadyScheduler, node_id: str) -> None:
        bypass = self.state.entries[node_id].descriptor.bypass
        if bypass is None:  # pragma: no cover - preflight rejects this
            raise RuntimeError(f"Node {node_id!r} is disabled without a bypass.")
        keys = self.state.wiring.feeds.get((node_id, bypass.input_port), ())
        forwarded = bool(keys) and all(k in self.values for k in keys)
        if forwarded:
            self.values[(node_id, bypass.output_port)] = self.deliver(keys[0])
        self._record(node_id, NodeStatus.BYPASSED)
        port = bypass.input_port
        effect = "passes its" if forwarded else "has no"
        tail = "through unchanged" if forwarded else "to pass through"
        self.state.emitter.post(
            EventKind.NODE_BYPASSED,
            node_id=node_id,
            unit_id=self.unit_id,
            message=f"Disabled in the graph; {effect} {port!r} input {tail}.",
            data={
                "reason": "disabled in the graph",
                "input_port": port,
                "output_port": bypass.output_port,
                "forwarded": forwarded,
            },
        )
        scheduler.complete(node_id)

    def _skip_commits_after_failure(self, scheduler: ReadyScheduler) -> None:
        # D3: a failed unit fails as a whole, so it starts no further source
        # commit, even on an independent branch. Entered commits finish.
        if self.failed_node is None:
            return
        for node_id in scheduler.ready:
            if self.state.entries[node_id].descriptor.effect is EffectClass.SOURCE_COMMIT:
                reason = f"Node {self.failed_node!r} failed in this unit; no commit starts."
                self._mark_dependants([node_id], NodeStatus.SKIPPED, self.failed_node, reason)
                self._mark_dependants(scheduler.fail(node_id), NodeStatus.SKIPPED, node_id)

    def _stop_pending(self, scheduler: ReadyScheduler) -> None:
        cancelled = self.state.token.cancelled
        status = NodeStatus.CANCELLED if cancelled else NodeStatus.SKIPPED
        kind = EventKind.NODE_CANCELLED if cancelled else EventKind.NODE_SKIPPED
        message = "Cancelled before it started." if cancelled else "The run stopped."
        for node_id in scheduler.drain():
            self._record(node_id, status)
            self.state.emitter.post(kind, node_id=node_id, unit_id=self.unit_id, message=message)

    async def _invoke(self, node_id: str) -> _Finished:
        state = self.state
        entry = state.entries[node_id]
        node: NodeSnapshot = state.snapshot.node(node_id)
        started = state.clock()
        try:
            inputs = self._inputs(node_id, entry)
            params = entry.descriptor.parameters.model_validate(node.params)
            context = NodeContext(
                run_id=state.run_id,
                node_id=node_id,
                settings=node.settings,
                resources=state.resources,
                cancellation=state.token,
                collection=node.collection,
                unit_id=self.unit_id,
                controls={c.lever: c.value for c in node.controls},
                progress=self._progress(node_id),
            )
            output = await entry.adapter(context, inputs, params)
            return _Finished(output, None, started, state.clock())
        except (Exception, asyncio.CancelledError) as exc:
            return _Finished(None, exc, started, state.clock())

    def _progress(self, node_id: str) -> Callable[[str, Mapping[str, Any]], None]:
        # Bind only the emitter and identifiers: an adapter that keeps its
        # context must not keep this pass's values alive.
        emitter, unit_id = self.state.emitter, self.unit_id

        def report(message: str, data: Mapping[str, Any]) -> None:
            emitter.post(
                EventKind.NODE_PROGRESS,
                node_id=node_id,
                unit_id=unit_id,
                message=message,
                data=data,
            )

        return report

    # ── Outcomes ──────────────────────────────────────────────────

    def _check_output(self, node_id: str, output: Any) -> str | None:
        if not isinstance(output, NodeOutput):
            return f"Adapter returned {type(output).__name__}, not NodeOutput."
        declared = {p.name for p in self.state.entries[node_id].descriptor.outputs}
        unknown = sorted(set(output.values) - declared)
        if unknown:
            return f"Adapter returned undeclared output ports: {', '.join(unknown)}."
        missing = sorted(
            port
            for port in declared - set(output.values)
            if self.state.wiring.consumers.get((node_id, port), 0) > 0
        )
        if missing:
            return f"Adapter produced no value for connected output port(s): {', '.join(missing)}."
        return None

    async def _finish(self, scheduler: ReadyScheduler, node_id: str, done: _Finished) -> None:
        duration = max(done.ended - done.started, 0.0)
        error = done.error
        problem = self._check_output(node_id, done.output) if error is None else None
        if error is None and problem is None and done.output is not None:
            self._succeed(scheduler, node_id, done.output, duration)
        elif isinstance(error, PipelineCancelledError | asyncio.CancelledError) and (
            self.state.token.cancelled or isinstance(error, asyncio.CancelledError)
        ):
            self._record(node_id, NodeStatus.CANCELLED, duration_s=duration)
            self.state.emitter.post(
                EventKind.NODE_CANCELLED,
                node_id=node_id,
                unit_id=self.unit_id,
                message="Stopped at a safe boundary.",
            )
            self._mark_dependants(scheduler.fail(node_id), NodeStatus.CANCELLED, node_id)
        else:
            message = problem or f"{type(error).__name__}: {error}"
            self._fail(
                scheduler, node_id, message, duration, fatal=isinstance(error, FatalNodeError)
            )
        await self.state.emitter.flush()

    def _succeed(
        self, scheduler: ReadyScheduler, node_id: str, output: NodeOutput, duration: float
    ) -> None:
        for port, value in output.values.items():
            self.values[(node_id, port)] = value
        self.effects.extend(output.effects)
        self.state.effects.extend(output.effects)
        emitter = self.state.emitter
        for effect in output.effects:
            # ``data.effect`` is the stable field the run service reads on restart.
            emitter.post(
                EventKind.EFFECT_COMMITTED,
                node_id=node_id,
                unit_id=self.unit_id,
                message=effect,
                data={"effect": effect},
            )
        if output.fallback is not None:
            emitter.post(
                EventKind.NODE_FALLBACK,
                node_id=node_id,
                unit_id=self.unit_id,
                message=output.fallback,
            )
        self._record(
            node_id,
            NodeStatus.SUCCEEDED,
            duration_s=duration,
            fallback=output.fallback,
            effects=tuple(output.effects),
        )
        emitter.post(
            EventKind.NODE_COMPLETED, node_id=node_id, unit_id=self.unit_id, data=output.summary
        )
        scheduler.complete(node_id)

    def _fail(
        self,
        scheduler: ReadyScheduler,
        node_id: str,
        message: str,
        duration: float,
        *,
        fatal: bool,
    ) -> None:
        self._record(node_id, NodeStatus.FAILED, duration_s=duration, error=message)
        self.state.emitter.post(
            EventKind.NODE_FAILED, node_id=node_id, unit_id=self.unit_id, message=message
        )
        if self.failed_node is None:
            self.failed_node, self.error = node_id, message
        if self.state.failed_node is None:
            self.state.failed_node = node_id
            self.state.error = f"Node {node_id!r} failed: {message}"
        self.state.fatal = self.state.fatal or fatal
        self._mark_dependants(scheduler.fail(node_id), NodeStatus.SKIPPED, node_id)

    def _mark_dependants(
        self, nodes: list[str], status: NodeStatus, cause: str, message: str | None = None
    ) -> None:
        kind = EventKind.NODE_SKIPPED if status is NodeStatus.SKIPPED else EventKind.NODE_CANCELLED
        for dependant in nodes:
            self._record(dependant, status)
            self.state.emitter.post(
                kind,
                node_id=dependant,
                unit_id=self.unit_id,
                message=message or f"Upstream node {cause!r} did not complete.",
            )

    def _record(self, node_id: str, status: NodeStatus, **fields: Any) -> None:
        self.outcomes[node_id] = NodeOutcome(
            node_id=node_id, status=status, unit_id=self.unit_id, **fields
        )

    def ordered_outcomes(self) -> list[NodeOutcome]:
        """Return this pass's outcomes in topological order."""
        return [self.outcomes[n] for n in self.nodes if n in self.outcomes]

    def graph_outputs(self) -> dict[str, Any]:
        """Return the graph outputs this pass produced."""
        members = set(self.nodes)
        outputs = {}
        for graph_output in self.state.graph.outputs:
            key = (graph_output.source.node, graph_output.source.port)
            if key[0] in members and key in self.values:
                outputs[graph_output.name] = self.deliver(key)
        return outputs
