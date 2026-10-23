"""Hand-chained retrieval graph adapters reproduce ``search()`` (task 3.2).

Every recorded case in ``tests/fixtures/pipeline_parity/retrieval/`` runs
twice: once through the standard ``search()`` facade and once through the
registered graph adapters, chained by hand in canonical order. Both runs
share the replayed dense scores, the real BM25 backend, the real RRF and
the scripted reranker.

Graphs always receive explicit settings. The two ``policy_default_*``
cases were recorded with the process default (``settings_via=default``),
which a graph never reads. They therefore run both paths with the same
settings passed explicitly, so the profile decision applies to both.
"""

from __future__ import annotations

import pytest
from tests.fixtures.pipeline_parity.retrieval import harness
from tests.unit.test_retrieval_graph_adapters_support import FakeEmbedder, run_chain

from omrs.core.pipelines import SCORE_KIND_RERANK, SCORE_KIND_RRF
from omrs.core.retrieval import registry

_CASES = harness.load_cases()

#: Ranked-evidence fields compared with ``search(include_diagnostics=True)``.
_RANK_FIELDS = (
    "id",
    "source",
    "score",
    "score_kind",
    "reranked",
    "dense_score",
    "dense_score_kind",
    "dense_rank",
    "sparse_rank",
    "fused_rank",
)


def _explicit(case: dict, *, diagnostics: bool) -> dict:
    """Return the case with settings passed as an argument."""
    copy = dict(case)
    copy["settings_via"] = "argument"
    copy["search"] = {**case["search"], "include_diagnostics": diagnostics}
    return copy


def _graph_outputs(case: dict, corpus: dict, settings):
    """Run the hand-chained graph for ``case`` and return node outputs."""
    chunks = [] if case.get("empty_collection") else corpus["chunks"]
    mode = case.get("reranker", "success")
    scores = {c["id"]: c["rerank_score"] for c in chunks}
    reranker = harness.ParityReranker(scores, fail=mode == "fail")
    resources = {
        "store": harness.ParityStore(chunks),
        "embedder": FakeEmbedder(),
        "reranker": reranker,
    }
    search = dict(case["search"])
    query = search.pop("query", corpus["query"])
    prepare = {
        key: search[key]
        for key in ("top_k", "similarity_threshold", "rerank", "fetch_k")
        if key in search
    }
    hybrid = search.get("hybrid", settings.retrieval.hybrid_enabled)
    return run_chain(settings, resources, query, hybrid=hybrid, prepare=prepare)


def _project(rows: list[dict]) -> list[dict]:
    return [{k: row[k] for k in _RANK_FIELDS if k in row} for row in rows]


def _assert_rows_equal(got: list[dict], want: list[dict]) -> None:
    assert len(got) == len(want)
    for got_row, want_row in zip(got, want, strict=True):
        assert got_row.keys() == want_row.keys()
        for key, value in want_row.items():
            if isinstance(value, float):
                assert got_row[key] == pytest.approx(value, rel=1e-12, abs=0.0), key
            else:
                assert got_row[key] == value, key


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_graph_chain_matches_search(case, monkeypatch, effective_settings) -> None:
    """Ids, order, scores, score kinds and rank provenance agree with ``search()``."""
    corpus = harness.load_corpus()
    settings = effective_settings(**case.get("settings", {}))
    diag_rows = harness.run_search(
        _explicit(case, diagnostics=True),
        corpus,
        monkeypatch=monkeypatch,
        settings_factory=effective_settings,
    )
    public_rows = harness.run_search(
        _explicit(case, diagnostics=False),
        corpus,
        monkeypatch=monkeypatch,
        settings_factory=effective_settings,
    )

    outputs = _graph_outputs(case, corpus, settings)
    selected = outputs["select"].values["evidence"]
    bundle = outputs["context"].values["context"]

    # Public rows equal the public search() rows exactly.
    assert bundle.public_rows() == public_rows
    # Ranked evidence keeps the diagnostic rank provenance search() reports.
    _assert_rows_equal(_project(list(selected.rows)), _project(diag_rows))
    # Every row carries the evidence score kind.
    assert all(row["score_kind"] == selected.score_kind for row in selected.rows)
    # Threshold semantics and rerank reason agree with search() diagnostics.
    summary = outputs["select"].summary
    for row in diag_rows:
        assert summary["threshold_score_kind"] == row["threshold_score_kind"]
        assert summary["rerank_reason"] == row["rerank_reason"]
        if "rerank_backend" in row:
            assert summary["rerank_backend"] == row["rerank_backend"]


@pytest.mark.parametrize(
    "case",
    [c for c in _CASES if c.get("settings_via", "argument") == "argument"],
    ids=lambda c: c["name"],
)
def test_graph_chain_matches_recorded_expectation(case, monkeypatch, effective_settings) -> None:
    """The graph reproduces the expectation recorded before extraction."""
    corpus = harness.load_corpus()
    monkeypatch.setitem(
        registry._cache,
        "dense",
        harness.make_dense([] if case.get("empty_collection") else corpus["chunks"]),
    )
    settings = effective_settings(**case.get("settings", {}))
    outputs = _graph_outputs(case, corpus, settings)
    selected = outputs["select"].values["evidence"]
    want = [{k: v for k, v in row.items() if k in _RANK_FIELDS} for row in case["expected"]["rows"]]
    # Public-shape cases record no ids or ranks; compare the recorded keys only.
    got = [{k: row[k] for k in w if k in row} for row, w in zip(selected.rows, want, strict=False)]
    assert len(selected.rows) == len(want)
    _assert_rows_equal(got, want)


def test_reranker_failure_is_a_fallback_outcome(monkeypatch, effective_settings) -> None:
    """A failed hybrid rerank reports a fallback and keeps RRF semantics."""
    case = next(c for c in _CASES if c["name"] == "hybrid_rerank_failure_fallback")
    corpus = harness.load_corpus()
    monkeypatch.setitem(
        registry._cache,
        "dense",
        harness.make_dense(corpus["chunks"]),
    )
    outputs = _graph_outputs(case, corpus, effective_settings(**case["settings"]))
    assert outputs["rerank"].fallback == "inference failed: parity fixture"
    assert outputs["rerank"].values["evidence"].score_kind == SCORE_KIND_RRF
    assert outputs["select"].fallback is not None
    assert [r["id"] for r in outputs["select"].values["evidence"].rows] == ["b", "c", "a"]


def test_reranker_success_labels_reranker_scores(monkeypatch, effective_settings) -> None:
    """A successful rerank labels the evidence with the reranker score kind."""
    case = next(c for c in _CASES if c["name"] == "hybrid_rerank_success_div30")
    corpus = harness.load_corpus()
    monkeypatch.setitem(
        registry._cache,
        "dense",
        harness.make_dense(corpus["chunks"]),
    )
    outputs = _graph_outputs(case, corpus, effective_settings(**case["settings"]))
    assert outputs["rerank"].fallback is None
    evidence = outputs["select"].values["evidence"]
    assert evidence.score_kind == SCORE_KIND_RERANK
    assert outputs["select"].summary["threshold_score_kind"] == SCORE_KIND_RERANK
