"""Engine answer on a collection that follows a user profile (design D2, D16, D17, task 5.4)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.answer.harness import (
    CASE_NAMES,
    QUERY,
    case_by_name,
    case_rows,
    case_settings,
    make_seam,
    observation,
)
from tests.unit.test_answer_graph_adapters_support import UNKNOWN_PROVIDER, FakeLLM
from tests.unit.test_engine_pipelines_support import Factory
from tests.unit.test_engine_profiles_support import (
    COLLECTION,
    PROFILE,
    count_graph_runs,
    make_env,
    save_slot,
    slot_graph,
    tagged_engine,
)
from tests.unit.test_pipeline_templates_parity import _store_rows

from omrs.engine_answer import ClientCompletion


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


def _build(env: Any, case: dict[str, Any], settings: Any, tag: str) -> tuple[Any, Any, Any]:
    """Return an Engine over the case rows, with fresh scripted seams."""
    complete, judge = make_seam(case.get("complete")), make_seam(case.get("judge"))
    answer_factory = Factory(FakeLLM(complete) if complete else None)
    judge_factory = Factory(FakeLLM(judge) if judge else None)
    if case.get("verify_unavailable_reason"):
        judge_factory = Factory(error=ValueError(UNKNOWN_PROVIDER))
    engine = tagged_engine(
        env,
        settings,
        _store_rows(case_rows(case)),
        tag,
        env_overrides={"RETRIEVAL__RERANK_ENABLED": "false"},
        answer_llm_factory=answer_factory,
        verify_llm_factory=judge_factory,
    )
    return engine, complete, judge


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_answer_on_a_user_profile_equals_the_built_in_answer(
    name: str, tmp_path: Path, effective_settings: Any
) -> None:
    """Status, citations, verification and model calls equal those of the built-in profile."""
    case = case_by_name(name)
    settings = case_settings(effective_settings(), case)
    env = make_env(tmp_path, effective_settings)

    engine, complete, judge = _build(env, case, settings, "documents")
    builtin_runs = count_graph_runs(engine)
    standard = await engine.answer(QUERY, collection_name=COLLECTION, include_diagnostics=True)
    want = observation(standard, complete, judge)

    engine, complete, judge = _build(env, case, settings, PROFILE)
    user_runs = count_graph_runs(engine)
    result = await engine.answer(QUERY, collection_name=COLLECTION, include_diagnostics=True)
    assert observation(result, complete, judge) == want
    assert (builtin_runs, user_runs) == ([], ["run_pipeline"]), "the graph path must run once"


async def test_an_answer_uses_the_current_answer_revision(
    tmp_path: Path, effective_settings: Any
) -> None:
    """A saved Answer revision takes effect at once."""
    case = case_by_name(CASE_NAMES[0])
    settings = case_settings(effective_settings(), case)
    env = make_env(tmp_path, effective_settings)
    graph = slot_graph(env, "answer")
    graph["nodes"][0]["params"] = {"top_k": 1, "similarity_threshold": 0.0, "rerank": False}
    save_slot(env, "answer", graph)
    engine, _, _ = _build(env, case, settings, PROFILE)
    result = await engine.answer(QUERY, collection_name=COLLECTION, include_diagnostics=True)
    assert len(result.get("evidence", result.get("citations", []))) <= 1


async def _complete(prompt: str) -> str:
    raise AssertionError("the client completion must not run")


async def test_a_client_completion_is_refused_for_a_user_profile(
    tmp_path: Path, effective_settings: Any
) -> None:
    case = case_by_name(CASE_NAMES[0])
    env = make_env(tmp_path, effective_settings)
    engine, _, _ = _build(env, case, case_settings(effective_settings(), case), PROFILE)
    completion = ClientCompletion(complete=_complete, source="client_mrtr", max_rounds=2)
    with pytest.raises(
        ValueError, match="does its own retrieval and uses the server model"
    ) as caught:
        await engine.answer(QUERY, collection_name=COLLECTION, client_completion=completion)
    assert "server model" in str(caught.value) and PROFILE in str(caught.value)


async def test_pre_fetched_rows_are_refused_for_a_user_profile(
    tmp_path: Path, effective_settings: Any
) -> None:
    case = case_by_name(CASE_NAMES[0])
    env = make_env(tmp_path, effective_settings)
    engine, _, _ = _build(env, case, case_settings(effective_settings(), case), PROFILE)
    with pytest.raises(ValueError, match="does its own retrieval and uses the server model"):
        await engine.answer(QUERY, collection_name=COLLECTION, rows=case_rows(case))


async def test_built_in_answer_never_runs_a_graph(tmp_path: Path, effective_settings: Any) -> None:
    case = case_by_name(CASE_NAMES[0])
    env = make_env(tmp_path, effective_settings)
    engine, _, _ = _build(env, case, case_settings(effective_settings(), case), "documents")
    calls: list[str] = []

    async def spy(*args: Any, **kwargs: Any) -> Any:
        calls.append("run_pipeline")
        raise AssertionError("a graph ran")

    engine.run_pipeline = spy
    await engine.answer(QUERY, collection_name=COLLECTION)
    assert calls == []
