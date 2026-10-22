"""Shared retrieval seams: sizing, policy, filtering and fallback (task 3.1).

``core/retrieval/operations.py`` holds the one implementation of these
rules. The standard ``search()`` path and the later graph adapters both
call it, so these tests pin each rule directly and prove ``search()``
delegates to it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from omrs.core.retrieval import operations as ops

_OPS_SOURCE = Path(ops.__file__)


def _row(row_id: str, score: float, kind: str = "dense_similarity_v1") -> dict:
    return {"id": row_id, "score": score, "score_kind": kind, "reranked": False}


# ── Lever resolution ─────────────────────────────────────────────────


def test_levers_fall_back_to_injected_settings(effective_settings) -> None:
    settings = effective_settings(top_k=7, hybrid_enabled=True, similarity_threshold=0.4)
    levers = ops.resolve_search_levers(settings)
    assert levers == ops.SearchLevers(top_k=7, hybrid=True, similarity_threshold=0.4)


def test_explicit_falsy_levers_are_not_replaced(effective_settings) -> None:
    settings = effective_settings(top_k=7, hybrid_enabled=True, similarity_threshold=0.4)
    levers = ops.resolve_search_levers(settings, top_k=3, hybrid=False, similarity_threshold=0.0)
    assert levers == ops.SearchLevers(top_k=3, hybrid=False, similarity_threshold=0.0)


# ── Rerank policy ────────────────────────────────────────────────────


def test_caller_settings_carry_the_profile_rerank_decision(effective_settings) -> None:
    settings = effective_settings(rerank_enabled=True)
    assert ops.resolve_rerank_decision(None, "q", settings, caller_settings=settings) == (
        True,
        "profile-resolved reranker enabled",
    )


def test_without_caller_settings_the_semantic_policy_applies(effective_settings) -> None:
    settings = effective_settings(rerank_enabled=False, rerank_enabled_for_semantic=True)
    effective, reason = ops.resolve_rerank_decision(None, "`a_b` x.y", settings)
    assert effective is False
    assert reason.startswith("disabled by technical policy")
    effective, reason = ops.resolve_rerank_decision(
        None, "how do plants grow", settings, technical_fraction=0.0
    )
    assert (effective, reason) == (
        True,
        "enabled by semantic policy (fraction=0.00 < threshold=0.3)",
    )


def test_explicit_rerank_flag_beats_caller_settings(effective_settings) -> None:
    settings = effective_settings(rerank_enabled=True)
    assert ops.resolve_rerank_decision(False, "q", settings, caller_settings=settings) == (
        False,
        "explicit rerank=False override",
    )


# ── Candidate sizing ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("top_k", "rerank", "count", "override", "expected"),
    [
        (10, False, 500, None, 10),  # no rerank: pool equals top_k
        (10, True, 500, None, 100),  # max(rerank_max_fetch=100, 10*3)
        (50, True, 500, None, 150),  # max(100, 50*3)
        (10, True, 40, None, 40),  # clamped to the collection size
        (10, True, 500, 7, 7),  # experiment override bypasses the formula
        (10, True, 3, 7, 3),  # override still clamped
        (0, False, 500, None, 1),  # never below one candidate
    ],
)
def test_candidate_pool_sizing(effective_settings, top_k, rerank, count, override, expected):
    settings = effective_settings()
    assert (
        ops.size_candidate_pool(top_k, rerank, count, settings, fetch_k_override=override)
        == expected
    )


# ── Dense eligibility (hybrid first stage) ───────────────────────────


def test_first_stage_dense_threshold_only_without_rerank() -> None:
    assert ops.first_stage_dense_threshold(0.3, rerank=False) == 0.3
    assert ops.first_stage_dense_threshold(0.3, rerank=True) == 0.0


def test_dense_eligibility_drops_low_dense_and_sparse_only_rows() -> None:
    dense = [_row("a", 0.9), _row("b", 0.2)]
    sparse = [{"id": "b"}, {"id": "s"}, {"id": "a"}]
    kept_dense, kept_sparse = ops.apply_dense_eligibility(dense, sparse, 0.3)
    assert [r["id"] for r in kept_dense] == ["a"]
    assert [r["id"] for r in kept_sparse] == ["a"]


def test_dense_eligibility_is_a_no_op_at_zero() -> None:
    dense = [_row("a", 0.1)]
    sparse = [{"id": "s"}]
    assert ops.apply_dense_eligibility(dense, sparse, 0.0) == (dense, sparse)


# ── Reranking outcome ────────────────────────────────────────────────


class _Reranker:
    backend_name = "fake"

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.last_failure_reason: str | None = None

    def rerank(self, query, results, top_k):
        if self.fail:
            self.last_failure_reason = "inference failed: boom"
            for row in results:
                row["_reranked"] = False
            return results[:top_k]
        for row in results:
            row["score"] = 0.5
            row["_reranked"] = True
        return results[:top_k]


def test_run_reranker_marks_rows_and_reports_backend(effective_settings) -> None:
    timing: dict = {}
    outcome = ops.run_reranker(
        "q",
        [_row("a", 0.9), _row("b", 0.8)],
        top_k=1,
        settings=effective_settings(),
        reranker=_Reranker(),
        timing_report=timing,
    )
    assert [(r["id"], r["reranked"], r["score_kind"]) for r in outcome.rows] == [
        ("a", True, ops.RERANK_SCORE_KIND)
    ]
    assert "_reranked" not in outcome.rows[0]
    assert outcome.backend == "fake"
    assert outcome.failure_reason is None
    assert timing["rerank_seconds"] >= 0.0


def test_run_reranker_failure_keeps_dense_kind_and_reason(effective_settings) -> None:
    outcome = ops.run_reranker(
        "q", [_row("a", 0.9)], top_k=5, settings=effective_settings(), reranker=_Reranker(fail=True)
    )
    assert outcome.rows[0]["reranked"] is False
    assert outcome.rows[0]["score_kind"] == "dense_similarity_v1"
    assert outcome.failure_reason == "inference failed: boom"
    assert ops.rerank_succeeded(True, outcome.rows) is False


def test_run_reranker_builds_from_settings_when_none_injected(
    effective_settings, monkeypatch
) -> None:
    from omrs.core.retrieval import backend

    seen: list = []

    def _build(settings):
        seen.append(settings)
        return _Reranker()

    monkeypatch.setattr(backend, "build_reranker_from_settings", _build)
    settings = effective_settings()
    outcome = ops.run_reranker("q", [_row("a", 0.9)], top_k=5, settings=settings)
    assert seen == [settings]
    assert outcome.rows[0]["reranked"] is True


@pytest.mark.parametrize(
    ("requested", "rows", "expected"),
    [
        (True, [{"reranked": True}, {"reranked": True}], True),
        (True, [{"reranked": True}, {"reranked": False}], False),
        (True, [], False),
        (False, [{"reranked": True}], False),
    ],
)
def test_rerank_succeeded_requires_every_row(requested, rows, expected) -> None:
    assert ops.rerank_succeeded(requested, rows) is expected


@pytest.mark.parametrize(
    ("rerank", "hybrid", "succeeded", "threshold", "expected"),
    [
        (True, True, False, 0.3, True),
        (True, True, True, 0.3, False),
        (True, True, False, 0.0, False),
        (True, False, False, 0.3, False),
        (False, True, False, 0.3, False),
    ],
)
def test_dense_fallback_only_for_failed_hybrid_rerank_with_threshold(
    rerank, hybrid, succeeded, threshold, expected
) -> None:
    assert (
        ops.needs_dense_fallback(
            rerank=rerank, hybrid=hybrid, succeeded=succeeded, similarity_threshold=threshold
        )
        is expected
    )


# ── Threshold filtering (the calibrated ÷30 transform) ───────────────


def test_successful_rerank_divides_threshold_by_thirty() -> None:
    cut = 0.3 / 30
    rows = [_row("keep", cut, "reranker_sigmoid_v1"), _row("drop", 0.0099, "reranker_sigmoid_v1")]
    kept, kind = ops.apply_score_threshold(rows, 0.3, succeeded=True, hybrid=False)
    assert [r["id"] for r in kept] == ["keep"]
    assert kind == ops.RERANK_SCORE_KIND


def test_failed_rerank_uses_the_undivided_dense_threshold() -> None:
    rows = [_row("keep", 0.3), _row("drop", 0.29)]
    kept, kind = ops.apply_score_threshold(rows, 0.3, succeeded=False, hybrid=False)
    assert [r["id"] for r in kept] == ["keep"]
    assert kind == "dense_similarity_v1"


def test_unreranked_hybrid_rows_are_not_filtered_after_fusion() -> None:
    rows = [_row("rrf", 0.016, "rrf_v1")]
    kept, kind = ops.apply_score_threshold(rows, 0.3, succeeded=False, hybrid=True)
    assert kept == rows
    assert kind == "dense_similarity_v1"


def test_zero_threshold_filters_nothing() -> None:
    rows = [_row("a", 0.0)]
    assert ops.apply_score_threshold(rows, 0.0, succeeded=False, hybrid=False)[0] == rows


def test_rank_and_truncate_is_stable_descending() -> None:
    rows = [_row("low", 0.1), _row("tie1", 0.5), _row("tie2", 0.5), _row("top", 0.9)]
    assert [r["id"] for r in ops.rank_and_truncate(rows, 3)] == ["top", "tie1", "tie2"]


# ── One implementation, injected resources only ──────────────────────


def test_search_delegates_to_the_shared_seams(monkeypatch) -> None:
    """``search()`` calls the seams; it keeps no private copy of the rules."""
    from omrs.core.retrieval import pipeline
    from omrs.core.settings import EffectiveSettings

    called: list[str] = []
    for name in (
        "resolve_search_levers",
        "resolve_rerank_decision",
        "size_candidate_pool",
        "first_stage_dense_threshold",
        "run_reranker",
        "rerank_succeeded",
        "needs_dense_fallback",
        "apply_score_threshold",
        "rank_and_truncate",
    ):
        real = getattr(ops, name)

        def _spy(*args, _real=real, _name=name, **kwargs):
            called.append(_name)
            return _real(*args, **kwargs)

        monkeypatch.setattr(ops, name, _spy)

    monkeypatch.setattr(pipeline, "_hybrid_query_rows", lambda *a, **k: [_row("a", 0.03, "rrf_v1")])
    store = type("S", (), {"count": lambda self, name: 1})()
    pipeline.search(
        "q",
        top_k=1,
        similarity_threshold=0.3,
        rerank=True,
        hybrid=True,
        reranker=_Reranker(fail=True),
        store=store,
        effective_settings=EffectiveSettings(),
    )
    assert called == [
        "resolve_search_levers",
        "resolve_rerank_decision",
        "size_candidate_pool",
        "first_stage_dense_threshold",
        "run_reranker",
        "rerank_succeeded",
        "needs_dense_fallback",
        "apply_score_threshold",
        "rank_and_truncate",
    ]


def test_pipeline_holds_no_private_threshold_transform() -> None:
    source = Path(ops.__file__).with_name("pipeline.py").read_text(encoding="utf-8")
    assert "_effective_threshold" not in source
    assert "_resolve_fetch_k" not in source
    assert "_resolve_rerank_policy" not in source


def test_seams_read_no_process_defaults() -> None:
    from tests.test_no_global_settings_reads import _scan_default_accessors

    assert _scan_default_accessors(_OPS_SOURCE.read_text(encoding="utf-8")) == []


def test_seams_work_with_poisoned_process_defaults(effective_settings, monkeypatch) -> None:
    """Every seam uses only what it is given, never a process default."""
    import omrs.core.settings as settings_mod
    import omrs.core.vectordb as vectordb_mod

    def _poison(*_a, **_k):
        raise AssertionError("seam read a process default")

    settings = effective_settings(top_k=4)
    monkeypatch.setattr(settings_mod, "get_default_effective_settings", _poison)
    monkeypatch.setattr(settings_mod, "resolve_effective_settings", _poison)
    monkeypatch.setattr(vectordb_mod, "get_default_store", _poison)

    levers = ops.resolve_search_levers(settings)
    rerank, _ = ops.resolve_rerank_decision(None, "q", settings, caller_settings=settings)
    pool = ops.size_candidate_pool(levers.top_k, rerank, 9, settings)
    outcome = ops.run_reranker(
        "q", [_row("a", 0.9)], top_k=levers.top_k, settings=settings, reranker=_Reranker()
    )
    kept, _ = ops.apply_score_threshold(outcome.rows, 0.3, succeeded=True, hybrid=False)
    assert (levers.top_k, rerank, pool, len(ops.rank_and_truncate(kept, 4))) == (4, False, 4, 1)


def test_importing_seams_loads_no_concrete_strategy_module() -> None:
    concrete = [
        "omrs.core.retrieval.dense",
        "omrs.core.retrieval.sparse",
        "omrs.core.retrieval.native_sparse",
        "omrs.core.retrieval.fusion",
        "omrs.core.retrieval.reranker",
        "omrs.core.retrieval.reranker_torch",
        "omrs.core.retrieval.backend",
    ]
    code = (
        "import sys, omrs.core.retrieval.operations\n"
        f"print([m for m in {concrete!r} if m in sys.modules])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout.strip()
    assert out == "[]"
