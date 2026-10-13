"""Task 4.1: the pure ready-node scheduler and resource leases."""

from __future__ import annotations

import pytest
from tests.unit.test_pipeline_support import fixture_descriptors

from omrg.core.pipelines import EffectClass
from omrg.core.pipelines.scheduler import Lease, ReadyScheduler, lease_for

DIAMOND = {"a": set(), "b": set(), "c": {"a", "b"}, "d": {"c"}}
ORDER = ("a", "b", "c", "d")


def _scheduler(leases: dict[str, Lease] | None = None, bound: int = 2) -> ReadyScheduler:
    return ReadyScheduler(ORDER, DIAMOND, leases or {}, max_concurrency=bound)


def test_ready_nodes_follow_dependency_counts() -> None:
    """A join becomes ready only after every upstream node completes."""
    scheduler = _scheduler()
    assert scheduler.pop_newly_ready() == ["a", "b"]
    assert scheduler.dispatchable() == ["a", "b"]
    scheduler.complete("b")
    assert scheduler.pop_newly_ready() == []
    scheduler.complete("a")
    assert scheduler.pop_newly_ready() == ["c"]
    assert scheduler.dispatchable() == ["c"]
    scheduler.complete("c")
    assert scheduler.pop_newly_ready() == ["d"]
    scheduler.complete("d")
    assert scheduler.idle


def test_bound_limits_dispatch() -> None:
    """Only ``max_concurrency`` nodes run at once."""
    scheduler = _scheduler(bound=1)
    scheduler.pop_newly_ready()
    assert scheduler.dispatchable() == ["a"]
    assert scheduler.dispatchable() == []
    scheduler.complete("a")
    assert scheduler.dispatchable() == ["b"]


def test_exclusive_lease_excludes_other_holders() -> None:
    """An exclusive lease waits for shared holders and blocks new ones."""
    leases = {"a": Lease(shared=frozenset({"store"})), "b": Lease(exclusive=frozenset({"store"}))}
    scheduler = _scheduler(leases)
    scheduler.pop_newly_ready()
    assert scheduler.dispatchable() == ["a"]
    scheduler.complete("a")
    assert scheduler.dispatchable() == ["b"]


def test_shared_leases_coexist() -> None:
    """Two shared holders of one resource run together."""
    lease = Lease(shared=frozenset({"store"}))
    scheduler = _scheduler({"a": lease, "b": lease})
    scheduler.pop_newly_ready()
    assert scheduler.dispatchable() == ["a", "b"]


def test_blocked_node_does_not_block_later_ready_nodes() -> None:
    """A lease conflict skips one node, not the rest of the ready list."""
    order = ("a", "b", "c")
    upstream = {"a": set(), "b": set(), "c": set()}
    leases = {
        "a": Lease(exclusive=frozenset({"reranker"})),
        "b": Lease(exclusive=frozenset({"reranker"})),
    }
    scheduler = ReadyScheduler(order, upstream, leases, max_concurrency=3)
    scheduler.pop_newly_ready()
    assert scheduler.dispatchable() == ["a", "c"]


def test_fail_returns_transitive_dependants() -> None:
    """A failure removes every not-started dependant in topological order."""
    scheduler = _scheduler()
    scheduler.pop_newly_ready()
    scheduler.dispatchable()
    assert scheduler.fail("a") == ["c", "d"]
    scheduler.complete("b")
    assert scheduler.pop_newly_ready() == []
    assert scheduler.idle


def test_drain_returns_every_not_started_node() -> None:
    """Draining clears ready and waiting nodes; running nodes stay."""
    scheduler = _scheduler(bound=1)
    scheduler.pop_newly_ready()
    scheduler.dispatchable()
    assert scheduler.drain() == ["b", "c", "d"]
    assert scheduler.running == frozenset({"a"})
    scheduler.complete("a")
    assert scheduler.idle


def test_bypass_resolves_a_ready_node_without_a_slot() -> None:
    """A ready node can be resolved without dispatch."""
    scheduler = _scheduler(bound=1)
    scheduler.pop_newly_ready()
    scheduler.complete("a")
    scheduler.complete("b")
    assert scheduler.pop_newly_ready() == ["c"]
    scheduler.complete("c")
    assert scheduler.pop_newly_ready() == ["d"]


def test_zero_bound_is_rejected() -> None:
    """The bound must be at least one."""
    with pytest.raises(ValueError, match="max_concurrency"):
        _scheduler(bound=0)


def test_lease_follows_effect_and_capabilities() -> None:
    """Model calls and commits lease their capabilities exclusively by default."""
    by_id = {d.operation_id: d for d in fixture_descriptors()}
    exclusive = frozenset({EffectClass.MODEL_CALL, EffectClass.SOURCE_COMMIT})
    assert lease_for(by_id["select.rerank"], exclusive) == Lease(exclusive=frozenset({"reranker"}))
    assert lease_for(by_id["commit.source"], exclusive) == Lease(exclusive=frozenset({"store"}))
    assert lease_for(by_id["retrieve.dense"], exclusive) == Lease(
        shared=frozenset({"embedder", "store"})
    )
    assert lease_for(by_id["select.rerank"], frozenset()) == Lease(shared=frozenset({"reranker"}))
