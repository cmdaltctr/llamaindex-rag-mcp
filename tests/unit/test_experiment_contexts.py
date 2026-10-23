"""Experiment context registry and admission guard (task 8.5, design D10).

These tests cover the pure core rules: workspace path checks below an
approved experiment root, approval records, revocation, leases and the
admission guard. They use no Engine, store or model.
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from omrs.core.experiments import (
    BackendIdentity,
    ExperimentAdmissionError,
    ExperimentPathError,
    ExperimentRegistry,
    check_credential_target,
    check_experiment_snapshot,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    """Return an approved experiment root with one workspace in it."""
    approved = tmp_path / "experiments"
    (approved / "exp-a").mkdir(parents=True)
    (approved / "exp-b").mkdir()
    return approved


@pytest.fixture
def registry(root: Path) -> ExperimentRegistry:
    """Return a registry that approves *root* only."""
    return ExperimentRegistry([root], store_backends=("lancedb", "chroma"))


# ── Registration and path checks ──────────────────────────────────────────


def test_registration_returns_an_opaque_context_id(registry: ExperimentRegistry, root: Path):
    """The id names no path, and the record keeps the canonical workspace."""
    context = registry.register(root / "exp-a", name="Chunk size sweep")

    assert context.context_id.startswith("exp_")
    assert "exp-a" not in context.context_id
    assert context.workspace == (root / "exp-a").resolve()
    assert context.output_dir == context.workspace / "output"
    assert context.store_backend == "lancedb"
    assert context.active
    assert registry.get(context.context_id) == context
    record = context.record()
    assert record["context_id"] == context.context_id
    assert record["workspace"] == str(context.workspace)
    assert record["status"] == "active" and record["revoked_at"] is None
    assert record["actions"] == ["ingest", "read"]


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda r, t: r / "exp-a" / ".." / "exp-b", "traversal"),
        (lambda r, t: r / ".." / "outside", "traversal"),
        (lambda r, t: t / "outside", "outside_root"),
        (lambda r, t: r, "is_root"),
        (lambda r, t: r / "missing", "not_found"),
        (lambda r, t: Path("experiments/exp-a"), "not_absolute"),
    ],
)
def test_bad_workspace_paths_are_rejected(
    registry: ExperimentRegistry, root: Path, tmp_path: Path, make: Any, code: str
):
    """Traversal, paths outside the root and the root itself fail."""
    (tmp_path / "outside").mkdir(exist_ok=True)
    with pytest.raises(ExperimentPathError) as info:
        registry.register(make(root, tmp_path))
    assert info.value.code == code
    assert registry.contexts() == []


def test_a_file_is_not_a_workspace(registry: ExperimentRegistry, root: Path):
    """A workspace must be a directory."""
    (root / "notes.txt").write_text("x", encoding="utf-8")
    with pytest.raises(ExperimentPathError) as info:
        registry.register(root / "notes.txt")
    assert info.value.code == "not_a_directory"


def test_symlink_that_escapes_the_root_is_rejected(
    registry: ExperimentRegistry, root: Path, tmp_path: Path
):
    """A link below the root that resolves outside it fails."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExperimentPathError) as info:
        registry.register(root / "link")
    assert info.value.code == "symlink_escape"


def test_symlinked_output_directory_is_rejected(
    registry: ExperimentRegistry, root: Path, tmp_path: Path
):
    """An existing ``output`` link could send the store outside the workspace."""
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (root / "exp-a" / "output").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExperimentPathError) as info:
        registry.register(root / "exp-a")
    assert info.value.code == "symlink_escape"


def test_symlink_inside_the_root_resolves_to_its_target(registry: ExperimentRegistry, root: Path):
    """A link that stays below the root registers its real directory."""
    (root / "alias").symlink_to(root / "exp-a", target_is_directory=True)
    context = registry.register(root / "alias")
    assert context.workspace == (root / "exp-a").resolve()


def test_unapproved_root_is_rejected(tmp_path: Path):
    """An approved root must be an existing directory."""
    with pytest.raises(ExperimentPathError) as info:
        ExperimentRegistry([tmp_path / "missing"])
    assert info.value.code == "root_not_approved"


def test_overlapping_workspaces_are_rejected(registry: ExperimentRegistry, root: Path):
    """Two active contexts never share or nest a workspace."""
    (root / "exp-a" / "inner").mkdir()
    registry.register(root / "exp-a")
    for path in (root / "exp-a", root / "exp-a" / "inner"):
        with pytest.raises(ExperimentPathError) as info:
            registry.register(path)
        assert info.value.code == "overlaps_context"


def test_non_default_store_needs_a_declared_factor(registry: ExperimentRegistry, root: Path):
    """LanceDB is the default; another backend must be the declared factor."""
    with pytest.raises(ExperimentPathError) as info:
        registry.register(root / "exp-a", store_backend="chroma")
    assert info.value.code == "store_not_declared"
    with pytest.raises(ExperimentPathError) as info:
        registry.register(root / "exp-a", store_backend="faiss", declared_factors=["store"])
    assert info.value.code == "store_unknown"
    context = registry.register(root / "exp-a", store_backend="chroma", declared_factors=["store"])
    assert context.store_backend == "chroma"


def test_unknown_actions_are_rejected(registry: ExperimentRegistry, root: Path):
    """Only the read and ingest actions exist."""
    with pytest.raises(ExperimentPathError) as info:
        registry.register(root / "exp-a", actions=["read", "delete"])
    assert info.value.code == "action_unknown"


# ── Revocation and leases ─────────────────────────────────────────────────


def test_revocation_blocks_later_leases(registry: ExperimentRegistry, root: Path):
    """A revoked context gives a structured error and keeps its record."""
    context = registry.register(root / "exp-a")
    revoked = registry.revoke(context.context_id)

    assert not revoked.active and revoked.record()["status"] == "revoked"
    with pytest.raises(ExperimentAdmissionError) as info:
        registry.acquire(context.context_id)
    assert info.value.code == "experiment_context_revoked"
    assert info.value.to_dict()["context_id"] == context.context_id


def test_unknown_context_gives_a_structured_error(registry: ExperimentRegistry):
    """An unknown id fails without naming any path."""
    with pytest.raises(ExperimentAdmissionError) as info:
        registry.acquire("exp_missing")
    payload = info.value.to_dict()
    assert payload == {
        "status": "error",
        "code": "experiment_context_unknown",
        "message": payload["message"],
        "context_id": "exp_missing",
    }


def test_a_revoked_workspace_can_be_registered_again(registry: ExperimentRegistry, root: Path):
    """Revocation frees the workspace; the new context gets a new id."""
    first = registry.register(root / "exp-a")
    registry.revoke(first.context_id)
    second = registry.register(root / "exp-a")
    assert second.context_id != first.context_id


def test_leases_are_counted_and_released_once(registry: ExperimentRegistry, root: Path):
    """Release is idempotent and the context manager always releases."""
    context = registry.register(root / "exp-a")
    lease = registry.acquire(context.context_id)
    with registry.acquire(context.context_id):
        assert registry.active_leases(context.context_id) == 2
    lease.release()
    lease.release()
    assert registry.active_leases(context.context_id) == 0

    with pytest.raises(RuntimeError), registry.acquire(context.context_id):
        raise RuntimeError("job failed")
    assert registry.active_leases(context.context_id) == 0


def test_idle_listener_fires_when_a_revoked_context_has_no_leases(
    registry: ExperimentRegistry, root: Path
):
    """Revocation waits for in-flight leases before it reports idle."""
    idle: list[str] = []
    registry.add_idle_listener(idle.append)
    busy = registry.register(root / "exp-a")
    quiet = registry.register(root / "exp-b")

    lease = registry.acquire(busy.context_id)
    registry.revoke(busy.context_id)
    registry.revoke(quiet.context_id)
    assert idle == [quiet.context_id]
    lease.release()
    assert idle == [quiet.context_id, busy.context_id]


# ── Admission guard ───────────────────────────────────────────────────────


def _node(node_id: str, effect: str, collection: str | None = "graph") -> Any:
    return SimpleNamespace(node_id=node_id, effect=effect, enabled=True, collection=collection)


def _snapshot(*nodes: Any) -> Any:
    return SimpleNamespace(nodes=nodes, graph_identity="g" * 64)


def _identity(context: Any, store_path: Path | None = None) -> BackendIdentity:
    return BackendIdentity(
        context_id=context.context_id,
        store_kind="lancedb",
        store_path=str(store_path or context.output_dir / "lancedb"),
        embedding_provider="llamacpp",
        embedding_model="fake",
    )


@pytest.mark.parametrize(
    ("bound", "target", "session", "code"),
    [
        ("exp_a", None, False, "live_library_target"),
        ("exp_a", "exp_b", False, "experiment_scope_mismatch"),
        (None, "exp_a", False, "experiment_credential_required"),
    ],
)
def test_credential_target_rejections(bound: Any, target: Any, session: bool, code: str):
    """An experiment credential reaches only its own context."""
    with pytest.raises(ExperimentAdmissionError) as info:
        check_credential_target(bound_context=bound, target_context=target, session=session)
    assert info.value.code == code


@pytest.mark.parametrize(
    ("bound", "target", "session"),
    [("exp_a", "exp_a", False), (None, None, False), (None, "exp_a", True), (None, None, True)],
)
def test_credential_target_acceptances(bound: Any, target: Any, session: bool):
    """Bound credentials reach their context; sessions reach any context."""
    check_credential_target(bound_context=bound, target_context=target, session=session)


def test_read_only_graph_in_the_context_is_admitted(registry: ExperimentRegistry, root: Path):
    """A graph without commits needs only the read action."""
    context = registry.register(root / "exp-a", actions=["read"])
    snapshot = _snapshot(_node("dense", "model_call"), _node("context", "pure", None))
    check_experiment_snapshot(context, snapshot, _identity(context))


def test_commit_needs_the_ingest_action(registry: ExperimentRegistry, root: Path):
    """A read-only context rejects a source commit."""
    context = registry.register(root / "exp-a", actions=["read"])
    with pytest.raises(ExperimentAdmissionError) as info:
        check_experiment_snapshot(
            context, _snapshot(_node("commit", "source_commit")), _identity(context)
        )
    assert info.value.code == "action_not_permitted"


def test_commit_into_a_store_outside_the_context_is_rejected(
    registry: ExperimentRegistry, root: Path, tmp_path: Path
):
    """The engine store must sit below the context's output directory."""
    context = registry.register(root / "exp-a")
    live = _identity(context, tmp_path / "lancedb")
    other = registry.register(root / "exp-b")
    foreign = BackendIdentity(**{**_identity(context).as_record(), "context_id": other.context_id})
    snapshot = _snapshot(_node("commit", "source_commit"))
    for identity in (live, foreign):
        with pytest.raises(ExperimentAdmissionError) as info:
            check_experiment_snapshot(context, snapshot, identity)
        assert info.value.code == "commit_outside_context"


def test_disabled_commit_node_is_not_a_write(registry: ExperimentRegistry, root: Path):
    """Only enabled commit nodes count as writes."""
    context = registry.register(root / "exp-a", actions=["read"])
    node = _node("commit", "source_commit")
    node.enabled = False
    check_experiment_snapshot(context, _snapshot(node), _identity(context))


def test_commit_without_a_destination_is_rejected(registry: ExperimentRegistry, root: Path):
    """A commit node must name its experiment collection."""
    context = registry.register(root / "exp-a")
    with pytest.raises(ExperimentAdmissionError) as info:
        check_experiment_snapshot(
            context, _snapshot(_node("commit", "source_commit", None)), _identity(context)
        )
    assert info.value.code == "commit_outside_context"


def test_index_identity_is_stable_and_path_bound(registry: ExperimentRegistry, root: Path):
    """The index identity changes with the store path or embedding model."""
    context = registry.register(root / "exp-a")
    first = _identity(context)
    assert first.index_identity == _identity(context).index_identity
    moved = _identity(context, context.output_dir / "other")
    assert moved.index_identity != first.index_identity
    record = first.as_record()
    assert set(record) >= {"store_kind", "store_path", "embedding_provider", "embedding_model"}
    assert first.provenance()["index_identity"] == first.index_identity
    assert os.path.isabs(record["store_path"])
