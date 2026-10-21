"""``Engine.answer(on_stage=...)`` on both answer paths (add-answer-stage-progress, 2.1 and 2.4).

The built-in profile runs the direct pipeline; the user profile runs its
saved Answer graph.  Both must report the same stages for the same
question, and an edited graph must degrade to "only what ran".
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.answer.harness import (
    CASE_NAMES,
    QUERY,
    case_by_name,
    case_rows,
    case_settings,
    strip_timings,
)
from tests.unit.test_engine_profiles_answer import _build
from tests.unit.test_engine_profiles_support import (
    COLLECTION,
    PROFILE,
    make_env,
    save_slot,
    slot_graph,
)

from omrg.core.answer.progress import AnswerStage
from omrg.engine_answer import ClientCompletion

S, W, C, V = (
    AnswerStage.SEARCHING,
    AnswerStage.WRITING,
    AnswerStage.CITING,
    AnswerStage.VERIFYING,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


async def _stages(
    tmp_path: Path,
    effective_settings: Any,
    name: str,
    tag: str,
    *,
    graph: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[AnswerStage]]:
    """Answer one parity case on ``tag`` and return the result and the stages seen."""
    case = case_by_name(name)
    settings = case_settings(effective_settings(), case)
    env = make_env(tmp_path, effective_settings)
    if graph is not None:
        save_slot(env, "answer", graph)
    engine, _, _ = _build(env, case, settings, tag)
    seen: list[AnswerStage] = []
    result = await engine.answer(QUERY, collection_name=COLLECTION, on_stage=seen.append)
    return result, seen


def _default_graph(tmp_path: Path, effective_settings: Any) -> dict[str, Any]:
    return slot_graph(make_env(tmp_path / "template", effective_settings), "answer")


def _node(graph: dict[str, Any], node_id: str) -> dict[str, Any]:
    return next(node for node in graph["nodes"] if node["id"] == node_id)


# ── 2.1 User-profile path ───────────────────────────────────────────────


async def test_default_graph_with_judge_reports_four_stages(
    tmp_path: Path, effective_settings: Any
) -> None:
    result, seen = await _stages(tmp_path, effective_settings, "verification_supported", PROFILE)
    assert result.get("verified") is True, result
    assert seen == [S, W, C, V]


async def test_verification_off_in_settings_reports_three_stages(
    tmp_path: Path, effective_settings: Any
) -> None:
    _, seen = await _stages(
        tmp_path, effective_settings, "verification_off_by_default_no_judge_call", PROFILE
    )
    assert seen == [S, W, C]


async def test_claim_step_disabled_in_graph_reports_three_stages(
    tmp_path: Path, effective_settings: Any
) -> None:
    graph = _default_graph(tmp_path, effective_settings)
    _node(graph, "verify")["enabled"] = False
    _, seen = await _stages(
        tmp_path, effective_settings, "verification_supported", PROFILE, graph=graph
    )
    assert seen == [S, W, C]


async def test_no_evidence_in_a_graph_run_reports_searching_only(
    tmp_path: Path, effective_settings: Any
) -> None:
    result, seen = await _stages(tmp_path, effective_settings, "no_evidence_with_model", PROFILE)
    assert result["status"] == "no_evidence", result
    assert seen == [S]


async def test_extra_step_without_a_stage_answers_normally(
    tmp_path: Path, effective_settings: Any
) -> None:
    plain, _ = await _stages(
        tmp_path / "plain", effective_settings, "verification_supported", PROFILE
    )
    graph = _default_graph(tmp_path, effective_settings)
    extra = copy.deepcopy(_node(graph, "select"))
    extra["id"] = "select_again"
    graph["nodes"].append(extra)
    for edge in graph["edges"]:
        if edge["source"]["node"] == "select" and edge["target"]["node"] == "context":
            edge["target"]["node"] = "select_again"
    graph["edges"].append(
        {
            "source": {"node": "select_again", "port": "evidence"},
            "target": {"node": "context", "port": "evidence"},
        }
    )
    result, seen = await _stages(
        tmp_path / "edited", effective_settings, "verification_supported", PROFILE, graph=graph
    )
    assert strip_timings(result) == strip_timings(plain)
    assert seen == [S, W, C, V]


async def test_graph_without_cite_step_lists_only_what_ran(
    tmp_path: Path, effective_settings: Any
) -> None:
    graph = _default_graph(tmp_path, effective_settings)
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] not in ("cite", "verify")]
    graph["edges"] = [e for e in graph["edges"] if e["target"]["node"] not in ("cite", "verify")]
    graph["outputs"] = [{"name": "answer", "source": {"node": "synthesise", "port": "answer"}}]
    result, seen = await _stages(
        tmp_path, effective_settings, "verification_supported", PROFILE, graph=graph
    )
    assert result.get("answer"), result
    assert seen == [S, W]


async def test_several_retrieval_steps_report_searching_once(
    tmp_path: Path, effective_settings: Any
) -> None:
    from omrg.pipeline_templates import _answer_graph

    graph = _answer_graph(None, hybrid=True, rerank=False)
    graph["profile"] = "documents"
    assert {"retrieve.dense", "retrieve.sparse", "select.rerank"} <= {
        n["operation"] for n in graph["nodes"]
    }
    _, seen = await _stages(
        tmp_path, effective_settings, "verification_supported", PROFILE, graph=graph
    )
    assert seen.count(S) == 1
    assert seen == [S, W, C, V]


async def test_no_saved_answer_graph_raises_before_any_stage(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    case = case_by_name("verification_supported")
    env = make_env(tmp_path, effective_settings)
    monkeypatch.setattr(env.catalogue, "slot_document", lambda *args, **kwargs: None)
    engine, _, _ = _build(env, case, case_settings(effective_settings(), case), PROFILE)
    seen: list[AnswerStage] = []
    with pytest.raises(ValueError, match="has no saved graph"):
        await engine.answer(QUERY, collection_name=COLLECTION, on_stage=seen.append)
    assert seen == []


@pytest.mark.parametrize("name", CASE_NAMES)
async def test_both_paths_report_the_same_stages(
    name: str, tmp_path: Path, effective_settings: Any
) -> None:
    _, builtin = await _stages(tmp_path / "builtin", effective_settings, name, "documents")
    _, user = await _stages(tmp_path / "user", effective_settings, name, PROFILE)
    assert user == builtin


# ── 2.4 Unchanged behaviour without a callback ──────────────────────────


@pytest.mark.parametrize("tag", ["documents", PROFILE])
async def test_result_is_the_same_with_and_without_on_stage(
    tag: str, tmp_path: Path, effective_settings: Any
) -> None:
    case = case_by_name("verification_supported")
    settings = case_settings(effective_settings(), case)
    env = make_env(tmp_path, effective_settings)
    engine, _, _ = _build(env, case, settings, tag)
    plain = await engine.answer(QUERY, collection_name=COLLECTION)
    engine, _, _ = _build(env, case, settings, tag)
    seen: list[AnswerStage] = []
    reported = await engine.answer(QUERY, collection_name=COLLECTION, on_stage=seen.append)
    assert strip_timings(reported) == strip_timings(plain)
    assert seen == [S, W, C, V]


async def _complete(prompt: str) -> str:
    raise AssertionError("the client completion must not run")


async def test_caller_inputs_are_still_refused_on_a_user_profile(
    tmp_path: Path, effective_settings: Any
) -> None:
    case = case_by_name("verification_supported")
    env = make_env(tmp_path, effective_settings)
    engine, _, _ = _build(env, case, case_settings(effective_settings(), case), PROFILE)
    completion = ClientCompletion(complete=_complete, source="client_mrtr", max_rounds=2)
    seen: list[AnswerStage] = []
    with pytest.raises(ValueError, match="does its own retrieval"):
        await engine.answer(
            QUERY, collection_name=COLLECTION, client_completion=completion, on_stage=seen.append
        )
    with pytest.raises(ValueError, match="does its own retrieval"):
        await engine.answer(
            QUERY, collection_name=COLLECTION, rows=case_rows(case), on_stage=seen.append
        )
    assert seen == []
