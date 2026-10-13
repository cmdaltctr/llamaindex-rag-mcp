"""Canonical search template and template contracts (task 4.5).

The search template runs through ``Engine.run_pipeline`` on every recorded
retrieval parity case. Its results must equal ``Engine.search`` on an
Engine with the same settings, store, embedder and reranker. The tests
also check that each template validates, publishes only summary or result
outputs, and stays editable.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.retrieval import harness
from tests.unit.test_engine_pipelines_support import FakeStore, build_engine

from omrg.compose_pipelines import build_operation_catalogue, pipeline_templates
from omrg.core.pipelines import (
    AdmissionSnapshot,
    PortKind,
    PreflightReport,
    RunStatus,
    parse_definition,
)
from omrg.core.retrieval import registry
from omrg.pipeline_templates import (
    TEMPLATE_NAMES,
    answer_template,
    canonical_templates,
    search_template,
)

_CASES = harness.load_cases()

#: Search keywords that map to ``retrieve.prepare_query`` parameters.
_PREPARE_KEYS = ("top_k", "similarity_threshold", "rerank", "fetch_k")

#: Rank provenance compared between the graph rows and ``search()`` diagnostics.
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

#: Port kinds a template may publish as a graph output.
_RESULT_KINDS = {PortKind.COMMIT_SUMMARY, PortKind.CONTEXT, PortKind.ANSWER}


def _reranker(case: dict[str, Any], chunks: list[dict[str, Any]]) -> Any:
    mode = case.get("reranker", "success")
    if mode == "none":
        return None
    scores = {c["id"]: c["rerank_score"] for c in chunks}
    return harness.ParityReranker(scores, fail=mode == "fail")


def _case_engine(case: dict[str, Any], chunks: list[dict[str, Any]], settings: Any) -> Any:
    return build_engine(settings, FakeStore(chunks), reranker=_reranker(case, chunks))


def _search_kwargs(case: dict[str, Any], settings: Any) -> tuple[str, bool, dict[str, Any]]:
    kwargs = dict(case["search"])
    kwargs.pop("include_diagnostics", None)
    query = kwargs.pop("query", harness.load_corpus()["query"])
    hybrid = kwargs.pop("hybrid", settings.retrieval.hybrid_enabled)
    return query, hybrid, kwargs


def _template_run(case: dict[str, Any], chunks: list[dict[str, Any]], settings: Any) -> Any:
    """Run the search template for ``case`` on a fresh Engine."""
    query, hybrid, kwargs = _search_kwargs(case, settings)
    engine = _case_engine(case, chunks, settings)
    data = search_template(
        "parity", hybrid=hybrid, rerank=case.get("reranker") != "none"
    ).model_dump(mode="json")
    prepare = next(n for n in data["graph"]["nodes"] if n["id"] == "prepare")
    prepare["params"] = {k: kwargs[k] for k in _PREPARE_KEYS if k in kwargs}
    return asyncio.run(engine.run_pipeline(data, inputs={"query": query}))


def _standard(
    case: dict[str, Any], chunks: list[dict[str, Any]], settings: Any, *, diagnostics: bool
) -> list[dict]:
    """Run ``Engine.search`` for ``case`` on a fresh Engine."""
    query, hybrid, kwargs = _search_kwargs(case, settings)
    engine = _case_engine(case, chunks, settings)
    return engine.search(
        query,
        hybrid=hybrid,
        collection_name="parity",
        include_diagnostics=diagnostics,
        **kwargs,
    )


def _project(rows: list[dict]) -> list[dict]:
    return [{k: row[k] for k in _RANK_FIELDS if k in row} for row in rows]


@pytest.mark.parametrize("case", _CASES, ids=[c["name"] for c in _CASES])
def test_search_template_matches_engine_search(case, monkeypatch, effective_settings) -> None:
    """Rows, scores, score kinds, rank provenance and fallbacks equal ``Engine.search``."""
    chunks = [] if case.get("empty_collection") else harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    settings = effective_settings(**case.get("settings", {}))

    result = _template_run(case, chunks, settings)

    assert result.status is RunStatus.SUCCEEDED, result.error
    bundle = result.outputs["results"]
    assert bundle.public_rows() == _standard(case, chunks, settings, diagnostics=False)
    diagnostic = _standard(case, chunks, settings, diagnostics=True)
    assert _project(list(bundle.rows)) == _project(diagnostic)
    fallbacks = {n.node_id: n.fallback for n in result.nodes if n.fallback}
    for row in diagnostic:
        if row.get("rerank_reason", "").startswith("inference failed"):
            assert fallbacks["rerank"] == row["rerank_reason"]


def test_search_parity_covers_every_recorded_case() -> None:
    """The template parity run covers all fifteen recorded retrieval cases."""
    assert len(_CASES) == 15


# ── Template contracts ────────────────────────────────────────────────


@pytest.mark.parametrize("hybrid", [False, True])
@pytest.mark.parametrize("with_reranker", [False, True])
def test_every_template_passes_engine_validation(
    hybrid: bool, with_reranker: bool, effective_settings
) -> None:
    """Each published template validates as a draft and admits with inputs."""
    settings = effective_settings(**{"retrieval.hybrid_enabled": hybrid})
    reranker = harness.ParityReranker({}, fail=False) if with_reranker else None
    engine = build_engine(settings, reranker=reranker)
    templates = pipeline_templates(engine)
    assert tuple(t.name for t in templates) == TEMPLATE_NAMES
    inputs = {"ingestion": {"path": "."}, "search": {"query": "q"}, "answer": {"query": "q"}}
    for template in templates:
        report = engine.validate_pipeline(template.definition)
        assert isinstance(report, PreflightReport) and report.ok, template.name
        snapshot = engine.validate_pipeline(template.definition, inputs=inputs[template.name])
        assert isinstance(snapshot, AdmissionSnapshot)
    node_ids = {n.id for n in templates[1].definition.graph.nodes}
    assert ({"sparse", "fuse"} <= node_ids) is hybrid
    rerank = next(n for n in templates[1].definition.graph.nodes if n.id == "rerank")
    assert rerank.enabled is with_reranker


def test_template_outputs_are_summaries_or_results() -> None:
    """No template publishes chunks, documents or vectors as a graph output."""
    catalogue = build_operation_catalogue()
    for template in canonical_templates(hybrid=True):
        graph = template.definition.graph
        operations = {n.id: n.operation for n in graph.nodes}
        for output in graph.outputs:
            descriptor = catalogue.get(operations[output.source.node]).descriptor
            port = next(p for p in descriptor.outputs if p.name == output.source.port)
            assert port.type.kind in _RESULT_KINDS, (template.name, output.name)


def test_templates_have_empty_layout_and_named_collection() -> None:
    """Templates carry no presentation data; the collection argument is kept."""
    for template in canonical_templates("notes"):
        assert template.definition.graph.collection == "notes"
        assert template.definition.layout.model_dump(exclude_defaults=True) == {}


def test_answer_template_extends_the_search_chain() -> None:
    """The answer graph is the search graph plus the four answer operations."""
    search = [n.operation for n in search_template(hybrid=True).graph.nodes]
    answer = [n.operation for n in answer_template(hybrid=True).graph.nodes]
    assert answer[: len(search)] == search
    assert answer[len(search) :] == [
        "answer.prepare_evidence",
        "answer.synthesise",
        "answer.cite",
        "verify.claims",
    ]


def test_template_copy_without_reranker_validates_and_runs(monkeypatch, effective_settings) -> None:
    """A copy with the rerank node removed is a valid graph that still runs."""
    case = next(c for c in _CASES if c["name"] == "hybrid_no_rerank_no_threshold")
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    settings = effective_settings(**case["settings"])
    data = search_template("parity", hybrid=True).model_dump(mode="json")
    graph = data["graph"]
    graph["nodes"] = [n for n in graph["nodes"] if n["id"] != "rerank"]
    graph["edges"] = [
        e for e in graph["edges"] if "rerank" not in (e["source"]["node"], e["target"]["node"])
    ]
    graph["edges"].append(
        {
            "source": {"node": "fuse", "port": "evidence"},
            "target": {"node": "select", "port": "evidence"},
        }
    )
    query, _, kwargs = _search_kwargs(case, settings)
    graph["nodes"][0]["params"] = {k: kwargs[k] for k in _PREPARE_KEYS if k in kwargs}
    engine = build_engine(settings, FakeStore(chunks))

    assert engine.validate_pipeline(parse_definition(data)).ok
    result = asyncio.run(engine.run_pipeline(data, inputs={"query": query}))

    assert result.status is RunStatus.SUCCEEDED, result.error
    assert "rerank" not in {n.node_id for n in result.nodes}
    rows = result.outputs["results"].public_rows()
    assert rows == _standard(case, chunks, settings, diagnostics=False)
