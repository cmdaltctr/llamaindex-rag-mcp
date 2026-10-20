"""The profile-change preview reports what a user profile's Search graph runs.

A user profile inherits its settings from a built-in base profile, but its
saved Search graph decides what runs: a sparse branch turns hybrid retrieval
on, a missing or bypassed rerank node turns the reranker off, and graph or
prepare-node values change top_k. The preview used to compare base profiles
only, so a hybrid user profile based on ``documents`` showed
"hybrid_enabled False (unchanged)" (2026-10-20).
"""

from __future__ import annotations

from typing import Any

import pytest
from tests.test_profiles import _make_mock_store, _user_profile

from omrg.core.profiles import generate_safety_contract
from omrg.core.profiles.contract import _PREPARE_QUERY_LEVERS
from omrg.core.retrieval.graph_adapters_catalogue import _descriptors
from omrg.pipeline_templates import _search_graph


class _Catalogue:
    """An in-memory catalogue that serves one saved Search graph."""

    def __init__(self, search: dict[str, Any] | None) -> None:
        self._profile = _user_profile("my-docs", base="documents")
        self._search = search

    def get_profile(self, profile_id: str) -> dict | None:
        return self._profile if profile_id == "my-docs" else None

    def list_profiles(self) -> list[dict]:
        return [self._profile]

    def slot_revision(self, profile_id: str, slot: str) -> dict | None:
        return {"revision_id": f"{slot}-1", "revision_number": 1}

    def slot_document(self, profile_id: str, slot: str) -> dict | None:
        return self._search if slot == "search" else {"version": 1}


@pytest.fixture(autouse=True)
def _no_tier2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__TOP_K", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__HYBRID_ENABLED"):
        monkeypatch.delenv(name, raising=False)


def _levers(search: dict[str, Any] | None, old: str = "documents", new: str = "my-docs") -> dict:
    store = _make_mock_store(collection_meta={"papers": {"profile": old}})
    contract = generate_safety_contract("papers", new, store=store, catalogue=_Catalogue(search))
    return {impact["lever"]: impact["change"] for impact in contract["lever_impacts"]}


def _graph(*, hybrid: bool = False, rerank: bool = True) -> dict[str, Any]:
    graph = _search_graph(None, hybrid=hybrid, rerank=rerank)
    graph["profile"] = "documents"
    return graph


def test_a_sparse_branch_shows_hybrid_turning_on() -> None:
    assert _levers(_graph(hybrid=True))["hybrid_enabled"] == "False → True"


def test_moving_back_to_the_base_profile_shows_hybrid_turning_off() -> None:
    assert _levers(_graph(hybrid=True), old="my-docs", new="documents")["hybrid_enabled"] == (
        "True → False"
    )


def test_a_dense_only_graph_keeps_hybrid_off() -> None:
    assert _levers(_graph())["hybrid_enabled"] == "False (unchanged)"


def test_a_bypassed_rerank_node_turns_the_reranker_off() -> None:
    assert _levers(_graph(rerank=False))["reranker_enabled"] == "True → False"


def test_a_graph_without_a_rerank_node_turns_the_reranker_off() -> None:
    graph = _graph()
    graph["nodes"] = [n for n in graph["nodes"] if n["operation"] != "select.rerank"]
    assert _levers(graph)["reranker_enabled"] == "True → False"


def test_a_prepare_node_value_changes_top_k_and_the_reranker() -> None:
    graph = _graph()
    prepare = next(n for n in graph["nodes"] if n["operation"] == "retrieve.prepare_query")
    prepare["params"] = {"top_k": 4, "rerank": False}
    levers = _levers(graph)
    assert levers["top_k"] == "10 → 4"
    assert levers["reranker_enabled"] == "True → False"


def test_a_graph_wide_override_changes_top_k() -> None:
    graph = _graph()
    graph["overrides"] = {"retrieval.top_k": 7}
    assert _levers(graph)["top_k"] == "10 → 7"


def test_a_profile_without_a_saved_search_graph_follows_its_base() -> None:
    levers = _levers(None)
    assert levers["hybrid_enabled"] == "False (unchanged)"
    assert levers["reranker_enabled"] == "True (unchanged)"


def test_the_prepare_node_lever_map_matches_its_descriptor() -> None:
    descriptor = next(d for d in _descriptors() if d.operation_id == "retrieve.prepare_query")
    assert dict(_PREPARE_QUERY_LEVERS).items() <= dict(descriptor.lever_params).items()
