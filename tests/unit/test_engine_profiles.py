"""Engine search on a collection that follows a user profile (design D2, D14, D15, tasks 5.2-5.6).

``Engine.search`` runs the profile's current Search pipeline in the request.
Built-in profiles keep the direct path.
"""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.retrieval import harness
from tests.unit.test_engine_pipelines_support import FakeStore, chunks
from tests.unit.test_engine_profiles_support import (
    COLLECTION,
    PROFILE,
    count_graph_runs,
    make_env,
    save_slot,
    slot_graph,
    tagged_engine,
)

from omrg.core.retrieval import registry
from omrg.engine_profiles import ProfileRunError

_CASES = harness.load_cases()
_REQUEST_KEYS = ("top_k", "similarity_threshold", "rerank", "fetch_k", "metadata_filter")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


def _reranker(case: dict[str, Any], chunks: list[dict[str, Any]]) -> Any:
    mode = case.get("reranker", "success")
    if mode == "none":
        return None
    return harness.ParityReranker({c["id"]: c["rerank_score"] for c in chunks}, fail=mode == "fail")


# ── 5.2 Rows, request values, diagnostics ─────────────────────────────


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_search_on_a_user_profile_returns_the_rows_of_the_built_in_profile(
    case, tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = [] if case.get("empty_collection") else harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    settings = effective_settings(**case.get("settings", {}))
    env = make_env(tmp_path, effective_settings, reranker=_reranker(case, chunks))
    request = {k: case["search"][k] for k in _REQUEST_KEYS if k in case["search"]}
    query = case["search"].get("query", harness.load_corpus()["query"])

    def run(tag: str) -> tuple[list[dict], list[str]]:
        engine = tagged_engine(env, settings, chunks, tag, reranker=_reranker(case, chunks))
        runs = count_graph_runs(engine)
        return engine.search(query, collection_name=COLLECTION, **request), runs

    (user_rows, user_runs), (builtin_rows, builtin_runs) = run(PROFILE), run("documents")
    assert user_rows == builtin_rows
    assert (builtin_runs, user_runs) == ([], ["run_pipeline"]), "the graph path must run once"


def test_a_request_top_k_replaces_the_step_setting(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path, effective_settings)
    graph = slot_graph(env, "search")
    graph["nodes"][0]["params"] = {"top_k": 3, "similarity_threshold": 0.0, "rerank": False}
    save_slot(env, "search", graph)
    engine = tagged_engine(env, effective_settings(), chunks, PROFILE)
    query = harness.load_corpus()["query"]
    assert len(engine.search(query, collection_name=COLLECTION)) == 3
    assert len(engine.search(query, collection_name=COLLECTION, top_k=1)) == 1


def test_a_node_setting_without_a_request_value_stays(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path, effective_settings)
    graph = slot_graph(env, "search")
    graph["nodes"][0]["params"] = {"top_k": 2, "similarity_threshold": 0.0, "rerank": False}
    save_slot(env, "search", graph)
    engine = tagged_engine(env, effective_settings(), chunks, PROFILE)
    rows = engine.search(harness.load_corpus()["query"], collection_name=COLLECTION)
    assert len(rows) == 2


def test_hybrid_has_no_effect_on_a_user_profile(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path, effective_settings)
    engine = tagged_engine(env, effective_settings(), chunks, PROFILE)
    query = harness.load_corpus()["query"]
    plain = engine.search(query, collection_name=COLLECTION, rerank=False)
    hybrid = engine.search(query, collection_name=COLLECTION, rerank=False, hybrid=True)
    assert hybrid == plain


def test_diagnostics_list_the_request_values_that_had_no_effect(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path, effective_settings)
    engine = tagged_engine(env, effective_settings(), chunks, PROFILE)
    query = harness.load_corpus()["query"]
    rows = engine.search(
        query,
        collection_name=COLLECTION,
        rerank=False,
        hybrid=True,
        technical_fraction=0.4,
        include_diagnostics=True,
    )
    assert rows and all(
        row["unused_request_values"] == ["hybrid", "technical_fraction"] for row in rows
    )
    quiet = engine.search(query, collection_name=COLLECTION, rerank=False, include_diagnostics=True)
    assert quiet and all("unused_request_values" not in row for row in quiet)
    public = engine.search(query, collection_name=COLLECTION, rerank=False, hybrid=True)
    assert all("unused_request_values" not in row for row in public)


# ── 5.3 Threads, run failure, validation failure ──────────────────────


def _threaded_setup(tmp_path, effective_settings, monkeypatch):
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path, effective_settings)
    engine = tagged_engine(env, effective_settings(), chunks, PROFILE)
    return env, engine, harness.load_corpus()["query"]


def test_search_works_from_a_worker_thread(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, engine, query = _threaded_setup(tmp_path, effective_settings, monkeypatch)
    expected = engine.search(query, collection_name=COLLECTION, rerank=False)

    async def scenario() -> list:
        return await asyncio.to_thread(
            engine.search, query, collection_name=COLLECTION, rerank=False
        )

    assert asyncio.run(scenario()) == expected


def test_search_works_from_a_thread_that_runs_an_event_loop(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, engine, query = _threaded_setup(tmp_path, effective_settings, monkeypatch)
    expected = engine.search(query, collection_name=COLLECTION, rerank=False)

    async def scenario() -> list:
        # A synchronous call made while this thread's loop is running.
        return engine.search(query, collection_name=COLLECTION, rerank=False)

    assert asyncio.run(scenario()) == expected


def test_parallel_searches_from_worker_threads_agree(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, engine, query = _threaded_setup(tmp_path, effective_settings, monkeypatch)
    expected = engine.search(query, collection_name=COLLECTION, rerank=False)
    results: list[list] = []
    errors: list[BaseException] = []

    def work() -> None:
        try:
            results.append(engine.search(query, collection_name=COLLECTION, rerank=False))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not errors and results == [expected] * 4
    assert engine._pipelines.active_runs == 0


def test_a_run_failure_names_the_failing_step(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    env = make_env(tmp_path, effective_settings)
    engine = tagged_engine(env, effective_settings(), chunks(), PROFILE)

    def broken(*args: Any, **kwargs: Any) -> list:
        raise OSError("disk gone")

    monkeypatch.setattr(FakeStore, "query_dense", broken)
    with pytest.raises(ProfileRunError) as caught:
        engine.search("q", collection_name=COLLECTION, rerank=False)
    message = str(caught.value)
    assert "Search pipeline" in message and "'dense'" in message and PROFILE in message
    assert engine._pipelines.active_runs == 0


def test_a_validation_failure_raises_value_error(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    env, engine, query = _threaded_setup(tmp_path, effective_settings, monkeypatch)
    graph = slot_graph(env, "search")
    graph["nodes"][1]["operation"] = "retrieve.nothing"
    save_slot(env, "search", graph)
    with pytest.raises(ValueError, match="retrieve.nothing|unknown"):
        engine.search(query, collection_name=COLLECTION, rerank=False)


def test_a_profile_without_a_saved_search_graph_raises_value_error(
    tmp_path: Path, effective_settings
) -> None:
    env = make_env(tmp_path, effective_settings)
    env.service.create_profile("Blank", source=None)
    engine = tagged_engine(env, effective_settings(), [], "blank")
    with pytest.raises(
        ValueError, match="Search pipeline of the profile 'blank' has no saved graph"
    ):
        engine.search("q", collection_name=COLLECTION)


# ── 5.6 Built-in collections never run a graph ────────────────────────


def _guarded(engine: Any) -> list[str]:
    calls: list[str] = []

    async def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append("run_pipeline")
        raise AssertionError("a graph ran")

    engine.run_pipeline = spy
    return calls


@pytest.mark.parametrize("tag", [None, "documents", "codebase"])
def test_built_in_search_never_runs_a_graph(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch, tag
) -> None:
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path, effective_settings)
    engine = tagged_engine(env, effective_settings(), chunks, tag)
    calls = _guarded(engine)
    engine.search(harness.load_corpus()["query"], collection_name=COLLECTION, rerank=False)
    assert calls == []


def test_the_guard_trips_on_a_user_profile_collection(
    tmp_path: Path, effective_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The spy is live: pointed at a user-profile collection it records the graph run."""
    _, engine, query = _threaded_setup(tmp_path, effective_settings, monkeypatch)
    calls = _guarded(engine)
    with pytest.raises(AssertionError, match="a graph ran"):
        engine.search(query, collection_name=COLLECTION, rerank=False)
    assert calls == ["run_pipeline"]
