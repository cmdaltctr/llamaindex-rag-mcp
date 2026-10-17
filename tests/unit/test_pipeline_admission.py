"""Task 2.4: inherited/named profile resolution, overrides and snapshots."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest
from pydantic import ValidationError
from tests.unit.test_pipeline_support import (
    fixture_catalogue,
    fixture_host,
    ingest_graph,
    search_graph,
)

from omrg.core.pipelines import (
    ControlSource,
    IssueCode,
    PipelineValidationError,
    ResolverProfileSource,
    admit_pipeline,
    parse_definition,
    preflight,
)
from omrg.core.pipelines.admission import draft_node_controls
from omrg.core.profiles.resolver import ProfileResolver


class FakeStore:
    """Collection metadata store that records every mutation."""

    def __init__(self, tags: dict[str, str | None]) -> None:
        self.metadata: dict[str, dict[str, Any]] = {
            name: ({"profile": tag} if tag else {}) for name, tag in tags.items()
        }
        self.mutations: list[tuple[str, dict[str, Any]]] = []

    def get_collection_metadata(self, name: str) -> dict[str, Any] | None:
        meta = self.metadata.get(name)
        return dict(meta) if meta is not None else None

    def update_collection_metadata(self, name: str, metadata: dict[str, Any]) -> None:
        self.mutations.append((name, metadata))
        self.metadata.setdefault(name, {}).update(metadata)


def _profiles(
    store: FakeStore, effective_settings: Any, env: dict[str, str] | None = None
) -> ResolverProfileSource:
    resolver = ProfileResolver(
        store=store,  # type: ignore[arg-type]
        server_profile="documents",
        base=effective_settings(),
        env_overrides=env or {},
    )
    return ResolverProfileSource(resolver)


def _admit(data: dict[str, Any], profiles: Any, **kwargs: Any):
    return admit_pipeline(
        parse_definition(data),
        fixture_catalogue(),
        host=fixture_host(),
        profiles=profiles,
        **kwargs,
    )


def _control(snapshot: Any, node_id: str, lever: str):
    return next(c for c in snapshot.node(node_id).controls if c.lever == lever)


def test_omitted_profile_inherits_collection_profile(effective_settings: Any) -> None:
    """Collection-bound nodes inherit their collection's resolved profile."""
    data = search_graph()
    data["collection"] = "code"
    store = FakeStore({"code": "codebase"})
    snapshot = _admit(data, _profiles(store, effective_settings), inputs={"query": "q"})
    dense = snapshot.node("dense")
    assert dense.collection == "code"
    assert dense.settings.profile_name == "codebase"
    assert dense.settings.retrieval.top_k == 20
    collection = snapshot.collection("code")
    assert collection.profile_name == "codebase"
    assert collection.profile_origin == "collection"
    assert snapshot.profile_mode == "inherited"


def test_explicit_profile_uses_bundle_and_keeps_collection_metadata(
    effective_settings: Any,
) -> None:
    """An explicit graph profile supplies defaults without retagging."""
    data = search_graph()
    data["profile"] = "codebase"
    store = FakeStore({"documents": "documents"})
    before = store.get_collection_metadata("documents")
    snapshot = _admit(data, _profiles(store, effective_settings), inputs={"query": "q"})
    assert snapshot.node("dense").settings.retrieval.top_k == 20
    assert snapshot.node("rerank").settings.retrieval.rerank_enabled is False
    assert snapshot.collection("documents").profile_origin == "graph"
    assert snapshot.profile_mode == "explicit"
    assert store.mutations == []
    assert store.get_collection_metadata("documents") == before


def test_hybrid_graph_profile_rejected_before_resolution(effective_settings: Any) -> None:
    """``hybrid`` is rejected during validation with no resolver call."""

    class Exploding:
        def resolve(self, collection: str) -> Any:
            raise AssertionError("resolver must not run for an invalid graph")

        resolve_profile_name = load_profile = resolve

        def environment_keys(self) -> frozenset[str]:
            return frozenset()

    data = search_graph()
    data["profile"] = "hybrid"
    with pytest.raises(PipelineValidationError) as excinfo:
        _admit(data, Exploding(), inputs={"query": "q"})
    assert excinfo.value.codes == (IssueCode.UNSUPPORTED_PROFILE,)


def test_node_override_beats_graph_override_beats_profile(effective_settings: Any) -> None:
    """Precedence is node, then graph-wide, then resolved profile."""
    data = search_graph()
    data["overrides"] = {"retrieval.top_k": 15}
    data["nodes"][0]["params"] = {"top_k": 3}
    store = FakeStore({"documents": "documents"})
    snapshot = _admit(data, _profiles(store, effective_settings), inputs={"query": "q"})

    dense_top_k = _control(snapshot, "dense", "retrieval.top_k")
    assert (dense_top_k.value, dense_top_k.source) == (3, ControlSource.NODE)
    assert snapshot.node("dense").settings.retrieval.top_k == 3

    sparse_top_k = _control(snapshot, "sparse", "retrieval.top_k")
    assert (sparse_top_k.value, sparse_top_k.source) == (15, ControlSource.GRAPH)
    assert snapshot.node("sparse").settings.retrieval.top_k == 15


def test_node_disables_reranker_regardless_of_profile(effective_settings: Any) -> None:
    """A node override records the effective control and its source."""
    data = search_graph()
    data["nodes"][3]["params"] = {"enabled": False}
    store = FakeStore({"documents": "documents"})
    snapshot = _admit(data, _profiles(store, effective_settings), inputs={"query": "q"})
    control = _control(snapshot, "rerank", "retrieval.rerank_enabled")
    assert control.value is False
    assert control.source == ControlSource.NODE
    assert snapshot.node("rerank").settings.retrieval.rerank_enabled is False


def test_inherited_control_reports_profile_source(effective_settings: Any) -> None:
    """A node that inherits names the profile that supplied the value."""
    store = FakeStore({"documents": "documents"})
    snapshot = _admit(search_graph(), _profiles(store, effective_settings), inputs={"query": "q"})
    control = _control(snapshot, "rerank", "retrieval.rerank_enabled")
    assert control.value is True
    assert control.source == ControlSource.PROFILE
    assert "documents" in control.detail


def test_captured_environment_keeps_priority_over_profile(effective_settings: Any) -> None:
    """Environment values still beat profile bundles, and are labelled."""
    store = FakeStore({"documents": "documents"})
    env = {"RETRIEVAL__TOP_K": "7"}
    snapshot = _admit(
        search_graph(), _profiles(store, effective_settings, env), inputs={"query": "q"}
    )
    control = _control(snapshot, "dense", "retrieval.top_k")
    assert (control.value, control.source) == (7, ControlSource.ENVIRONMENT)

    data = search_graph()
    data["overrides"] = {"retrieval.top_k": 15}
    overridden = _admit(data, _profiles(store, effective_settings, env), inputs={"query": "q"})
    assert _control(overridden, "dense", "retrieval.top_k").value == 15


def test_ingestion_node_override_changes_chunk_settings(effective_settings: Any) -> None:
    """Index-shaping node levers reach the node's settings."""
    data = ingest_graph()
    data["nodes"][2]["params"] = {"chunk_size": 256}
    store = FakeStore({"documents": None})
    snapshot = _admit(data, _profiles(store, effective_settings), inputs={"path": "notes/"})
    assert snapshot.node("chunk").settings.chunking.chunk_size == 256
    assert snapshot.node("commit").settings.chunking.chunk_size == 512
    assert snapshot.node("commit").collection == "documents"


def test_snapshot_is_immutable_and_detached(effective_settings: Any) -> None:
    """Later edits to the draft, inputs or profile do not reach the snapshot."""
    data = search_graph()
    data["nodes"][0]["params"] = {"top_k": 4}
    inputs: dict[str, Any] = {"query": "first"}
    store = FakeStore({"documents": "documents"})
    snapshot = _admit(data, _profiles(store, effective_settings), inputs=inputs)

    with pytest.raises(ValidationError):
        snapshot.profile_mode = "explicit"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        snapshot.node("dense").collection = "x"  # type: ignore[misc]

    params = snapshot.node("dense").params
    params["top_k"] = 99
    inputs["query"] = "changed"
    data["nodes"][0]["params"]["top_k"] = 50
    store.metadata["documents"]["profile"] = "codebase"

    assert snapshot.node("dense").params == {"top_k": 4}
    assert snapshot.inputs == {"query": "first"}
    assert snapshot.node("rerank").settings.profile_name == "documents"

    later = _admit(search_graph(), _profiles(store, effective_settings), inputs={"query": "q"})
    assert later.node("rerank").settings.profile_name == "codebase"


def test_snapshot_records_graph_identity_and_versions(effective_settings: Any) -> None:
    """The snapshot holds the admitted graph and resolved versions."""
    definition = parse_definition(search_graph())
    store = FakeStore({"documents": "documents"})
    snapshot = admit_pipeline(
        definition,
        fixture_catalogue(),
        host=fixture_host(),
        profiles=_profiles(store, effective_settings),
        inputs={"query": "q"},
    )
    assert snapshot.graph == definition.graph
    assert snapshot.graph_identity == definition.graph.execution_identity()
    assert snapshot.node("dense").version == 1
    assert snapshot.order.index("fuse") > snapshot.order.index("dense")


def test_invalid_collection_tag_fails_admission(effective_settings: Any) -> None:
    """A collection tagged with a non-operational profile fails before execution."""
    store = FakeStore({"documents": "hybrid"})
    with pytest.raises(PipelineValidationError) as excinfo:
        _admit(search_graph(), _profiles(store, effective_settings), inputs={"query": "q"})
    issue = excinfo.value.issues[0]
    assert issue.code == IssueCode.PROFILE_RESOLUTION_FAILED
    assert "documents" in issue.message


def test_missing_run_input_fails_admission(effective_settings: Any) -> None:
    """Admission requires every declared graph input."""
    store = FakeStore({"documents": "documents"})
    with pytest.raises(PipelineValidationError) as excinfo:
        _admit(search_graph(), _profiles(store, effective_settings), inputs={})
    assert IssueCode.MISSING_GRAPH_INPUT in excinfo.value.codes


def test_profile_resolved_once_per_collection(effective_settings: Any) -> None:
    """Each referenced collection is resolved once at admission."""

    class Counting(ResolverProfileSource):
        calls: list[str] = []

        def resolve(self, collection: str) -> Any:
            self.calls.append(collection)
            return super().resolve(collection)

    store = FakeStore({"documents": "documents"})
    resolver = ProfileResolver(
        store=store,  # type: ignore[arg-type]
        server_profile="documents",
        base=effective_settings(),
        env_overrides={},
    )
    _admit(search_graph(), Counting(resolver), inputs={"query": "q"})
    assert Counting.calls == ["documents"]


# ── Draft controls (design D24) ───────────────────────────────────────


def _draft(
    data: dict[str, Any], profiles: Any, host: Any = None
) -> dict[str, list[dict[str, Any]]]:
    """Return the draft controls keyed by node id (no run inputs)."""
    definition = parse_definition(data)
    catalogue = fixture_catalogue()
    host = host or fixture_host()
    report = preflight(definition, catalogue, host=host)
    rows = draft_node_controls(definition.graph, report, catalogue, host=host, profiles=profiles)
    return {row["node_id"]: row["controls"] for row in rows}


def _draft_control(draft: dict[str, Any], node_id: str, lever: str) -> dict[str, Any]:
    return next(c for c in draft[node_id] if c["lever"] == lever)


def test_draft_returns_controls_of_every_valid_node(effective_settings: Any) -> None:
    """Without run inputs, each node of a valid graph carries its controls."""
    store = FakeStore({"documents": "documents"})
    draft = _draft(search_graph(), _profiles(store, effective_settings))
    assert set(draft) == {"dense", "sparse", "fuse", "rerank", "context", "answer"}
    top_k = _draft_control(draft, "dense", "retrieval.top_k")
    assert top_k["source"] == "profile"
    assert (
        top_k["value"] == _profiles(store, effective_settings).resolve("documents").retrieval.top_k
    )
    assert draft["fuse"] == []


def test_draft_graph_profile_beats_collection_profile(effective_settings: Any) -> None:
    """``graph.profile`` supplies the values although the collection is tagged otherwise."""
    data = search_graph()
    data["profile"] = "documents"
    data["collection"] = "code"
    store = FakeStore({"code": "codebase"})
    profiles = _profiles(store, effective_settings)
    control = _draft_control(_draft(data, profiles), "dense", "retrieval.top_k")
    assert control["value"] == profiles.load_profile("documents").retrieval.top_k
    assert control["value"] != profiles.load_profile("codebase").retrieval.top_k
    assert "(graph)" in control["detail"]


def test_draft_collection_profile_when_graph_names_none(effective_settings: Any) -> None:
    """Without ``graph.profile`` the collection's profile supplies the values."""
    data = search_graph()
    data["collection"] = "code"
    store = FakeStore({"code": "codebase"})
    control = _draft_control(
        _draft(data, _profiles(store, effective_settings)), "dense", "retrieval.top_k"
    )
    assert (control["value"], control["source"]) == (20, "profile")
    assert "(collection)" in control["detail"]


def test_draft_node_parameter_beats_graph_override(effective_settings: Any) -> None:
    """Precedence is node, then graph-wide, then profile."""
    data = search_graph()
    data["overrides"] = {"retrieval.top_k": 15}
    data["nodes"][0]["params"] = {"top_k": 3}
    store = FakeStore({"documents": "documents"})
    draft = _draft(data, _profiles(store, effective_settings))
    dense = _draft_control(draft, "dense", "retrieval.top_k")
    sparse = _draft_control(draft, "sparse", "retrieval.top_k")
    assert (dense["value"], dense["source"]) == (3, "node")
    assert (sparse["value"], sparse["source"]) == (15, "graph")


def test_draft_collection_chain(effective_settings: Any) -> None:
    """Node collection, then graph collection, then request collection, then host default."""
    store = FakeStore({"documents": "documents", "code": "codebase", "other": "codebase"})
    profiles = _profiles(store, effective_settings)

    # Host default only: every node reads the default collection (documents, top_k 10).
    base = _draft(search_graph(), profiles)
    assert _draft_control(base, "dense", "retrieval.top_k")["value"] != 20

    # Request collection stands in for the host default (the caller passes it as such).
    host = replace(fixture_host(), default_collection="other")
    requested = _draft(search_graph(), profiles, host)
    assert _draft_control(requested, "dense", "retrieval.top_k")["value"] == 20

    # graph.collection beats the request collection.
    data = search_graph()
    data["collection"] = "documents"
    graph_level = _draft(data, profiles, host)
    assert _draft_control(graph_level, "dense", "retrieval.top_k")["value"] != 20
    # A node without a collection parameter follows graph.collection as well.
    assert _draft_control(graph_level, "rerank", "retrieval.rerank_enabled")["value"] is True
    assert _draft_control(requested, "rerank", "retrieval.rerank_enabled")["value"] is False

    # The node's collection parameter beats both.
    data["nodes"][0]["params"] = {"collection": "code"}
    node_level = _draft(data, profiles, host)
    assert _draft_control(node_level, "dense", "retrieval.top_k")["value"] == 20
    assert "(collection)" in _draft_control(node_level, "dense", "retrieval.top_k")["detail"]


def test_draft_skips_node_with_invalid_parameters(effective_settings: Any) -> None:
    """Valid nodes keep their controls although another node has invalid parameters."""
    data = search_graph()
    data["nodes"][0]["params"] = {"top_k": 0}
    store = FakeStore({"documents": "documents"})
    draft = _draft(data, _profiles(store, effective_settings))
    assert "dense" not in draft
    assert {"sparse", "fuse", "rerank", "context", "answer"} <= set(draft)


def test_draft_skips_node_whose_profile_cannot_resolve(effective_settings: Any) -> None:
    """A node bound to a collection with an unusable profile gets no controls."""
    data = search_graph()
    data["nodes"][0]["params"] = {"collection": "broken"}
    store = FakeStore({"documents": "documents", "broken": "hybrid"})
    draft = _draft(data, _profiles(store, effective_settings))
    assert "dense" not in draft
    assert "sparse" in draft


def test_draft_unsupported_graph_profile_resolves_nothing() -> None:
    """``hybrid`` is already a validation issue; the resolver is not called."""

    class Exploding:
        def resolve(self, collection: str) -> Any:
            raise AssertionError("resolver must not run for an unsupported profile")

        load_profile = resolve

        def environment_keys(self) -> frozenset[str]:
            return frozenset()

    data = search_graph()
    data["profile"] = "hybrid"
    assert _draft(data, Exploding()) == {}


def test_draft_controls_equal_admission_controls(effective_settings: Any) -> None:
    """Draft and admitted controls cannot drift for the same graph."""
    data = search_graph()
    data["overrides"] = {"retrieval.top_k": 15}
    data["nodes"][0]["params"] = {"top_k": 3}
    data["nodes"][3]["params"] = {"enabled": False}
    store = FakeStore({"documents": "documents"})
    env = {"RETRIEVAL__TOP_K": "7"}
    profiles = _profiles(store, effective_settings, env)
    draft = _draft(data, profiles)
    snapshot = _admit(data, profiles, inputs={"query": "q"})
    assert set(draft) == {n.node_id for n in snapshot.nodes}
    for node in snapshot.nodes:
        assert draft[node.node_id] == [c.model_dump(mode="json") for c in node.controls]
