"""Standard graphs for a profile duplicate (unify-profiles-and-pipelines, D21, tasks 4.1-4.2)."""

from __future__ import annotations

import pytest
from tests.unit.test_engine_pipelines_support import build_engine

from omrg.compose_templates import profile_templates
from omrg.core.pipelines import AdmissionSnapshot, PreflightReport
from omrg.core.profiles.resolver import ProfileResolver

SLOTS = ("ingest", "search", "answer")
_INPUTS = {"ingest": {"path": "."}, "search": {"query": "q"}, "answer": {"query": "q"}}


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


def _engine(effective_settings, **overrides):
    base = effective_settings(**overrides)
    resolver = ProfileResolver(store=None, server_profile="documents", base=base, env_overrides={})
    return build_engine(base, profile_resolver=resolver)


def _nodes(graph: dict) -> set[str]:
    return {node["id"] for node in graph["nodes"]}


def test_returns_one_graph_document_per_slot(effective_settings) -> None:
    graphs = profile_templates(_engine(effective_settings), "documents")
    assert tuple(graphs) == SLOTS
    assert all(isinstance(g, dict) and "nodes" in g for g in graphs.values())


def test_codebase_duplicate_has_sparse_and_fusion_on_a_host_with_hybrid_off(
    effective_settings,
) -> None:
    engine = _engine(effective_settings, **{"retrieval.hybrid_enabled": False})
    codebase = profile_templates(engine, "codebase")
    documents = profile_templates(engine, "documents")
    for slot in ("search", "answer"):
        assert {"sparse", "fuse"} <= _nodes(codebase[slot]), slot
        assert not {"sparse", "fuse"} & _nodes(documents[slot]), slot


def test_documents_duplicate_stays_dense_on_a_host_with_hybrid_on(effective_settings) -> None:
    engine = _engine(effective_settings, **{"retrieval.hybrid_enabled": True})
    graphs = profile_templates(engine, "documents")
    assert not {"sparse", "fuse"} & _nodes(graphs["search"])


@pytest.mark.parametrize("base", ["documents", "codebase"])
def test_every_graph_names_its_base_profile_and_no_collection(effective_settings, base) -> None:
    graphs = profile_templates(_engine(effective_settings), base)
    for slot, graph in graphs.items():
        assert graph["profile"] == base, slot
        assert graph["collection"] is None, slot


@pytest.mark.parametrize("base", ["documents", "codebase"])
def test_no_graph_writes_explicit_step_settings(effective_settings, base) -> None:
    """A duplicate inherits the profile's settings, so it holds no node parameters."""
    graphs = profile_templates(_engine(effective_settings), base)
    for slot, graph in graphs.items():
        assert all(not node.get("params") for node in graph["nodes"]), slot
        assert graph["overrides"] == {}, slot


@pytest.mark.parametrize("base", ["documents", "codebase"])
def test_every_graph_passes_engine_validation(effective_settings, base) -> None:
    engine = _engine(effective_settings)
    for slot, graph in profile_templates(engine, base).items():
        report = engine.validate_pipeline(graph)
        assert isinstance(report, PreflightReport) and report.ok, slot
        snapshot = engine.validate_pipeline(graph, inputs=_INPUTS[slot])
        assert isinstance(snapshot, AdmissionSnapshot), slot


def test_an_engine_without_a_resolver_cannot_build_profile_graphs(effective_settings) -> None:
    with pytest.raises(ValueError, match="profile resolver"):
        profile_templates(build_engine(effective_settings()), "codebase")
