"""Pure ready-node scheduling with a concurrency bound and resource leases.

The scheduler holds dependency counts, the ready list, running nodes and
held leases. It does no I/O and never awaits; the runner asks it which
nodes may start and tells it which nodes finished.

Ready nodes start in admitted topological order. A node whose lease
conflicts with a running node waits, and later ready nodes that fit still
start, so one blocked node does not block the rest.

A :class:`Lease` names host resources (descriptor capabilities). Shared
leases on one resource run together. An exclusive lease runs alone on that
resource. :func:`lease_for` gives operations whose effect is in the
exclusive set (by default model calls and source commits) exclusive leases.
Domain limiters and write locks still apply inside the adapters.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from .catalogue import EffectClass, OperationDescriptor


@dataclass(frozen=True)
class Lease:
    """Resources a node holds while it runs.

    Attributes:
        exclusive: Resources no other running node may hold.
        shared: Resources other shared holders may also hold.
    """

    exclusive: frozenset[str] = frozenset()
    shared: frozenset[str] = frozenset()


def lease_for(descriptor: OperationDescriptor, exclusive_effects: frozenset[EffectClass]) -> Lease:
    """Return the lease an operation needs.

    Args:
        descriptor: Operation contract. Its capabilities name the resources.
        exclusive_effects: Effects that need exclusive access.

    Returns:
        An exclusive lease on every capability when the effect is in
        ``exclusive_effects``, else a shared lease.
    """
    resources = frozenset(descriptor.capabilities)
    if descriptor.effect in exclusive_effects:
        return Lease(exclusive=resources)
    return Lease(shared=resources)


class ReadyScheduler:
    """Dependency-count scheduler for one execution unit.

    Args:
        order: Nodes of this unit in topological order.
        upstream: Node to the nodes it waits for. Nodes outside ``order``
            are ignored; their values are already available.
        leases: Node to its lease. Missing nodes hold no resources.
        max_concurrency: Most nodes that run at the same time.

    Raises:
        ValueError: If ``max_concurrency`` is below one.
    """

    def __init__(
        self,
        order: Sequence[str],
        upstream: Mapping[str, Iterable[str]],
        leases: Mapping[str, Lease],
        *,
        max_concurrency: int,
    ) -> None:
        """Create the scheduler with every dependency outstanding."""
        if max_concurrency < 1:
            raise ValueError(f"max_concurrency must be at least 1, not {max_concurrency}")
        members = set(order)
        self._position = {node: index for index, node in enumerate(order)}
        self._leases = dict(leases)
        self._bound = max_concurrency
        self._waiting: dict[str, set[str]] = {
            node: {dep for dep in upstream.get(node, ()) if dep in members} for node in order
        }
        self._downstream: dict[str, list[str]] = {node: [] for node in order}
        for node, deps in self._waiting.items():
            for dep in deps:
                self._downstream[dep].append(node)
        self._ready: list[str] = []
        self._new: list[str] = []
        self._running: set[str] = set()
        self._exclusive: set[str] = set()
        self._shared: Counter[str] = Counter()
        self._release_ready([node for node, deps in self._waiting.items() if not deps])

    @property
    def running(self) -> frozenset[str]:
        """Return the nodes that are running."""
        return frozenset(self._running)

    @property
    def ready(self) -> tuple[str, ...]:
        """Return the ready nodes that have not started, in order."""
        return tuple(self._ready)

    @property
    def idle(self) -> bool:
        """Return whether no node is waiting, ready or running."""
        return not (self._waiting or self._ready or self._running)

    def pop_newly_ready(self) -> list[str]:
        """Return nodes that became ready since the last call, in order."""
        new, self._new = self._sorted(self._new), []
        return new

    def dispatchable(self) -> list[str]:
        """Mark and return the ready nodes that may start now.

        A returned node holds its lease until :meth:`complete` or
        :meth:`fail` is called for it.
        """
        started = []
        for node in list(self._ready):
            if len(self._running) >= self._bound:
                break
            lease = self._leases.get(node, Lease())
            if not self._fits(lease):
                continue
            self._ready.remove(node)
            self._running.add(node)
            self._exclusive.update(lease.exclusive)
            self._shared.update(lease.shared)
            started.append(node)
        return started

    def complete(self, node: str) -> None:
        """Record that ``node`` finished (or was bypassed) with outputs."""
        self._settle(node)
        released = []
        for child in self._downstream.get(node, ()):
            deps = self._waiting.get(child)
            if deps is None:
                continue
            deps.discard(node)
            if not deps:
                released.append(child)
        self._release_ready(released)

    def fail(self, node: str) -> list[str]:
        """Record that ``node`` ended without outputs.

        Returns:
            Every transitive dependant that had not started, in order. They
            are removed and will never become ready.
        """
        self._settle(node)
        removed: set[str] = set()
        stack = list(self._downstream.get(node, ()))
        while stack:
            child = stack.pop()
            if child in removed or child in self._running:
                continue
            if self._waiting.pop(child, None) is None and child not in self._ready:
                continue
            removed.add(child)
            if child in self._ready:
                self._ready.remove(child)
            stack.extend(self._downstream.get(child, ()))
        self._new = [n for n in self._new if n not in removed]
        return self._sorted(removed)

    def drain(self) -> list[str]:
        """Remove and return every node that has not started, in order."""
        pending = self._sorted([*self._ready, *self._waiting])
        self._ready.clear()
        self._waiting.clear()
        self._new.clear()
        return pending

    # ── Internal helpers ─────────────────────────────────────────

    def _sorted(self, nodes: Iterable[str]) -> list[str]:
        return sorted(nodes, key=self._position.__getitem__)

    def _release_ready(self, nodes: list[str]) -> None:
        for node in nodes:
            self._waiting.pop(node, None)
        self._ready = self._sorted([*self._ready, *nodes])
        self._new.extend(nodes)

    def _fits(self, lease: Lease) -> bool:
        if lease.exclusive & (self._exclusive | set(self._shared)):
            return False
        return not lease.shared & self._exclusive

    def _settle(self, node: str) -> None:
        if node in self._running:
            self._running.discard(node)
            lease = self._leases.get(node, Lease())
            self._exclusive.difference_update(lease.exclusive)
            self._shared.subtract(lease.shared)
            self._shared += Counter()
        elif node in self._ready:
            self._ready.remove(node)
        self._new = [n for n in self._new if n != node]
