"""Retrieval graph adapters: contracts, empty branches, provenance (task 3.2).

The parity file proves the hand-chained adapters equal ``search()``. This
file checks the contracts around them: published port types and score
kinds, preflight of real graphs, empty branches, rank provenance through
RRF, explicit fallback outcomes, lineage preservation, cancellation, and
that no adapter reads a process default.
"""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest
from tests.fixtures.pipeline_parity.retrieval import harness
from tests.test_no_global_settings_reads import _scan_default_accessors
from tests.unit.test_retrieval_graph_adapters_support import (
    FakeEmbedder,
    RaisingReranker,
    build_catalogue,
    node_context,
    run_chain,
    run_node,
)

from omrg.core.pipelines import (
    SCORE_KIND_DENSE,
    SCORE_KIND_RERANK,
    SCORE_KIND_RRF,
    CancellationFlag,
    EmbeddingRef,
    HostContext,
    PipelineCancelledError,
    Provenance,
    check_port_compatibility,
    parse_definition,
    preflight,
)
from omrg.core.retrieval import graph_adapters as ga
from omrg.core.retrieval import registry

_QUERY = "hybrid fusion rank reranker"
_BM25 = {"retrieval.hybrid_sparse_backend": "bm25"}


def _port(op: str, name: str, direction: str = "outputs"):
    descriptor = build_catalogue().get(op).descriptor
    return next(p for p in getattr(descriptor, direction) if p.name == name).type


def _resources(chunks, reranker=None):
    return {
        "store": harness.ParityStore(chunks),
        "embedder": FakeEmbedder(),
        "reranker": reranker or RaisingReranker(),
    }


@pytest.fixture
def corpus(monkeypatch):
    data = harness.load_corpus()
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(data["chunks"]))
    return data


# ── Published contracts ───────────────────────────────────────────────


def test_output_ports_declare_score_kinds_and_identity() -> None:
    """Each producer names the score kind it emits; dense binds the embedding."""
    dense = _port("retrieve.dense", "evidence")
    assert dense.score_kinds == {SCORE_KIND_DENSE} and dense.embedding_identity
    assert _port("retrieve.sparse", "evidence").score_kinds == {ga.SCORE_KIND_SPARSE_RANK}
    assert _port("combine.rrf", "evidence").score_kinds == {SCORE_KIND_RRF}
    assert _port("select.rerank", "evidence").score_kinds == {
        SCORE_KIND_RERANK,
        SCORE_KIND_DENSE,
        SCORE_KIND_RRF,
    }
    for op in ("retrieve.dense", "retrieve.sparse", "combine.rrf", "select.rerank"):
        assert {Provenance.COLLECTION, Provenance.CHUNK_LINEAGE} <= _port(op, "evidence").provenance


def test_reranker_declares_bypass_and_threshold_rejects_rank_only_scores() -> None:
    """Rerank can pass evidence through; a rank-only ranking cannot be thresholded."""
    descriptor = build_catalogue().get("select.rerank").descriptor
    assert descriptor.bypass is not None
    assert (descriptor.bypass.input_port, descriptor.bypass.output_port) == ("evidence", "evidence")
    threshold_in = _port("select.threshold", "evidence", "inputs")
    assert check_port_compatibility(_port("retrieve.sparse", "evidence"), threshold_in)
    assert not check_port_compatibility(_port("combine.rrf", "evidence"), threshold_in)
    assert not check_port_compatibility(_port("select.rerank", "evidence"), threshold_in)


def _graph(rerank_enabled: bool = True, *, sparse_to_select: bool = False) -> dict:
    edges = [
        ("prepare", "query", "dense", "query"),
        ("prepare", "query", "sparse", "query"),
        ("dense", "evidence", "fuse", "ranked"),
        ("sparse", "evidence", "fuse", "ranked"),
        ("fuse", "evidence", "rerank", "evidence"),
        ("rerank", "evidence", "select", "evidence"),
        ("select", "evidence", "context", "evidence"),
    ]
    if sparse_to_select:
        edges[5] = ("sparse", "evidence", "select", "evidence")
    ops = {
        "prepare": "retrieve.prepare_query",
        "dense": "retrieve.dense",
        "sparse": "retrieve.sparse",
        "fuse": "combine.rrf",
        "rerank": "select.rerank",
        "select": "select.threshold",
        "context": "context.assemble",
    }
    nodes = [{"id": k, "operation": v} for k, v in ops.items()]
    nodes[4]["enabled"] = rerank_enabled
    return {
        "schema_version": 1,
        "nodes": nodes,
        "edges": [
            {"source": {"node": a, "port": b}, "target": {"node": c, "port": d}}
            for a, b, c, d in edges
        ],
        "inputs": [
            {"name": "query", "kind": "query", "targets": [{"node": "prepare", "port": "query"}]}
        ],
        "outputs": [{"name": "context", "source": {"node": "context", "port": "context"}}],
    }


def test_canonical_hybrid_graph_passes_preflight() -> None:
    """The registered descriptors connect into a valid hybrid search graph."""
    host = HostContext(
        capabilities={"store": None, "embedder": None, "reranker": None},
        embedding=EmbeddingRef("local", "fake-embed"),
    )
    catalogue = build_catalogue()
    assert preflight(parse_definition(_graph()), catalogue, host=host).ok
    assert preflight(parse_definition(_graph(rerank_enabled=False)), catalogue, host=host).ok
    report = preflight(parse_definition(_graph(sparse_to_select=True)), catalogue, host=host)
    assert "incompatible_ports" in {issue.code for issue in report.issues}


# ── Empty branches and rank provenance ───────────────────────────────


def test_empty_dense_branch_joins_sparse_branch(monkeypatch, effective_settings) -> None:
    """An empty dense list is valid data: RRF fuses the sparse ranking alone."""
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense([]))
    out = run_chain(
        effective_settings(**_BM25),
        _resources(chunks),
        _QUERY,
        hybrid=True,
        prepare={"top_k": 3, "rerank": False, "similarity_threshold": 0.0},
    )
    assert out["dense"].values["evidence"].rows == ()
    assert out["dense"].values["evidence"].score_kind == SCORE_KIND_DENSE
    fused = out["fuse"].values["evidence"].rows
    assert fused, "sparse rows must survive an empty dense branch"
    assert all(r["dense_rank"] is None and r["sparse_rank"] for r in fused)
    assert all(r["score_kind"] == SCORE_KIND_RRF for r in fused)


def test_empty_collection_flows_to_empty_context(effective_settings) -> None:
    """An empty collection gives empty evidence at every node, never an error."""
    out = run_chain(
        effective_settings(**_BM25),
        _resources([]),
        _QUERY,
        hybrid=True,
        prepare={"rerank": True, "similarity_threshold": 0.3},
    )
    for node in ("dense", "sparse", "fuse", "rerank", "select"):
        assert out[node].values["evidence"].rows == (), node
    assert out["context"].values["context"].rows == ()
    assert out["rerank"].fallback is None


def test_rrf_keeps_rank_provenance(corpus, effective_settings) -> None:
    """Fused rows carry branch ranks and the RRF score computed from them."""
    out = run_chain(
        effective_settings(**_BM25),
        _resources(corpus["chunks"]),
        _QUERY,
        hybrid=True,
        prepare={"top_k": 6, "rerank": False, "similarity_threshold": 0.0},
    )
    dense_ids = [r["id"] for r in out["dense"].values["evidence"].rows]
    sparse_ids = [r["id"] for r in out["sparse"].values["evidence"].rows]
    k = effective_settings().retrieval.hybrid_rrf_k
    for position, row in enumerate(out["fuse"].values["evidence"].rows, start=1):
        assert row["fused_rank"] == position
        expected = 0.0
        if row["id"] in dense_ids:
            assert row["dense_rank"] == dense_ids.index(row["id"]) + 1
            expected += 1.0 / (k + row["dense_rank"])
        if row["id"] in sparse_ids:
            assert row["sparse_rank"] == sparse_ids.index(row["id"]) + 1
            expected += 1.0 / (k + row["sparse_rank"])
        assert row["score"] == pytest.approx(expected)


def test_rrf_rejects_two_dense_rankings(corpus, effective_settings) -> None:
    """Fusion takes one dense and one other ranking; it never guesses roles."""
    settings = effective_settings(**_BM25)
    out = run_chain(settings, _resources(corpus["chunks"]), _QUERY, hybrid=False)
    dense = out["dense"].values["evidence"]
    ctx = node_context("fuse", settings, _resources(corpus["chunks"]))
    with pytest.raises(ValueError, match="one dense"):
        asyncio.run(run_node(build_catalogue(), "combine.rrf", ctx, {"ranked": (dense, dense)}))


# ── Fallback outcomes and score-kind guard ───────────────────────────


def test_disabled_reranker_bypasses_inference(corpus, effective_settings) -> None:
    """A node parameter that disables reranking never calls the model."""
    out = run_chain(
        effective_settings(**_BM25),
        _resources(corpus["chunks"], RaisingReranker()),
        _QUERY,
        hybrid=False,
        prepare={"rerank": True, "top_k": 3},
        rerank_params={"enabled": False},
    )
    assert out["rerank"].values["evidence"] is out["dense"].values["evidence"]
    assert out["rerank"].summary["reranked"] is False
    assert out["select"].values["evidence"].score_kind == SCORE_KIND_DENSE


def test_reranker_failure_returns_fallback_not_exception(corpus, effective_settings) -> None:
    """A failed dense rerank keeps dense scores and the undivided threshold."""
    reranker = harness.ParityReranker({}, fail=True)
    out = run_chain(
        effective_settings(**_BM25),
        _resources(corpus["chunks"], reranker),
        _QUERY,
        hybrid=False,
        prepare={"rerank": True, "top_k": 5, "similarity_threshold": 0.3},
    )
    assert out["rerank"].fallback == "inference failed: parity fixture"
    selected = out["select"].values["evidence"]
    assert selected.score_kind == SCORE_KIND_DENSE
    assert [r["id"] for r in selected.rows] == ["a", "b", "c"]
    assert out["select"].summary["threshold_score_kind"] == SCORE_KIND_DENSE


def test_rerank_does_not_mutate_input_evidence(corpus, effective_settings) -> None:
    """Fan-out safety: the reranker re-scores copies, never upstream rows."""
    scores = {c["id"]: c["rerank_score"] for c in corpus["chunks"]}
    out = run_chain(
        effective_settings(**_BM25),
        _resources(corpus["chunks"], harness.ParityReranker(scores, fail=False)),
        _QUERY,
        hybrid=False,
        prepare={"rerank": True, "top_k": 3},
    )
    dense_rows = out["dense"].values["evidence"].rows
    assert all(r["score_kind"] == SCORE_KIND_DENSE and not r["reranked"] for r in dense_rows)
    assert out["rerank"].values["evidence"].score_kind == SCORE_KIND_RERANK


def test_threshold_refuses_rank_only_evidence(corpus, effective_settings) -> None:
    """The score-kind guard never applies a dense threshold to other scores."""
    settings = effective_settings(**_BM25)
    resources = _resources(corpus["chunks"])
    catalogue = build_catalogue()
    sparse = asyncio.run(
        run_node(
            catalogue, "retrieve.sparse", node_context("s", settings, resources), {"query": _QUERY}
        )
    )
    with pytest.raises(ValueError, match="score kind"):
        asyncio.run(
            run_node(
                catalogue,
                "select.threshold",
                node_context("t", settings, resources),
                {"evidence": sparse.values["evidence"]},
            )
        )


def test_native_sparse_degradation_is_a_fallback(corpus, effective_settings) -> None:
    """Native sparse that cannot serve reports a fallback and labels BM25."""
    settings = effective_settings(**{"retrieval.hybrid_sparse_backend": "native"})
    out = asyncio.run(
        run_node(
            build_catalogue(),
            "retrieve.sparse",
            node_context("sparse", settings, _resources(corpus["chunks"])),
            {"query": _QUERY},
        )
    )
    assert out.fallback is not None and "bm25" in out.fallback
    assert out.summary["sparse_backend"] == "bm25"
    assert out.values["evidence"].rows


# ── Lineage, cancellation and process defaults ───────────────────────


def _lineage_chunks() -> list[dict]:
    texts = ["alpha beta gamma delta", "gamma delta epsilon zeta", "unrelated other text"]
    chunks = []
    for index, text in enumerate(texts):
        source = "s1" if index < 2 else "s2"
        chunks.append(
            {
                "id": f"row{index}",
                "text": text,
                "dense_score": 0.9 - index * 0.1,
                "rerank_score": 0.5,
                "metadata": {
                    "file_name": f"{source}.md",
                    "source_id": source,
                    "source_version": "v1",
                    "chunk_id": f"{source}-c{index if index < 2 else 0}",
                    "source_chunk_index": index if index < 2 else 0,
                    "source_chunk_count": 2 if index < 2 else 1,
                },
            }
        )
    return chunks


class _LineageStore(harness.ParityStore):
    """Parity store that also serves canonical dense rows."""

    def query_dense(self, collection_name, query_embedding, n_results, where=None):
        ordered = sorted(self._chunks, key=lambda c: c["dense_score"], reverse=True)
        return [
            {
                "id": c["id"],
                "score": c["dense_score"],
                "score_kind": SCORE_KIND_DENSE,
                "metadata": dict(c["metadata"]),
                "document": c["text"],
            }
            for c in ordered[:n_results]
        ]


def test_lineage_survives_every_stage_and_assembly_merges(effective_settings) -> None:
    """Chunk lineage travels through every port; assembly merges adjacent chunks."""
    chunks = _lineage_chunks()
    resources = {
        "store": _LineageStore(chunks),
        "embedder": FakeEmbedder(),
        "reranker": RaisingReranker(),
    }
    out = run_chain(
        effective_settings(**_BM25),
        resources,
        "gamma delta",
        hybrid=True,
        prepare={"top_k": 3, "rerank": False, "similarity_threshold": 0.0},
    )
    for node in ("dense", "sparse", "fuse", "select"):
        evidence = out[node].values["evidence"]
        assert evidence.provenance.collection == "parity"
        for row in evidence.rows:
            assert row["source_id"] in {"s1", "s2"} and row["chunk_id"], node
    assert out["dense"].values["evidence"].provenance.embedding == EmbeddingRef(
        "local", "fake-embed"
    )
    assert set(out["select"].values["evidence"].provenance.source_ids) == {"s1", "s2"}
    bundle = out["context"].values["context"]
    merged = [r for r in bundle.public_rows() if r.get("chunk_ids")]
    assert merged and merged[0]["chunk_ids"] == ["s1-c0", "s1-c1"]
    assert bundle.provenance.collection == "parity"


def test_cancellation_stops_before_store_work(corpus, effective_settings) -> None:
    """A cancelled run stops at the next safe boundary."""
    flag = CancellationFlag()
    flag.cancel()
    ctx = node_context(
        "dense", effective_settings(**_BM25), _resources(corpus["chunks"]), cancellation=flag
    )
    with pytest.raises(PipelineCancelledError):
        asyncio.run(run_node(build_catalogue(), "retrieve.dense", ctx, {"query": _QUERY}))


def test_missing_resource_is_reported(corpus, effective_settings) -> None:
    """Adapters ask the host for resources and never build their own."""
    ctx = node_context("dense", effective_settings(**_BM25), {"store": harness.ParityStore([])})
    with pytest.raises(LookupError, match="embedder"):
        asyncio.run(run_node(build_catalogue(), "retrieve.dense", ctx, {"query": _QUERY}))


def test_poisoned_process_defaults_are_never_read(monkeypatch, effective_settings) -> None:
    """The full chain runs with every process default poisoned."""
    import llama_index.core

    from omrg.core import settings as settings_mod
    from omrg.core import vectordb
    from omrg.core.retrieval import backend, pipeline

    def poisoned(*args, **kwargs):
        raise AssertionError("process default read")

    settings = effective_settings(**_BM25)
    for target, name in (
        (settings_mod, "get_default_effective_settings"),
        (settings_mod, "resolve_effective_settings"),
        (vectordb, "get_default_store"),
        (pipeline, "get_default_store"),
        (pipeline, "resolve_effective_settings"),
        (backend, "build_reranker_from_settings"),
    ):
        monkeypatch.setattr(target, name, poisoned)
    monkeypatch.setattr(
        type(llama_index.core.Settings), "embed_model", property(poisoned), raising=False
    )
    chunks = _lineage_chunks()
    scores = {c["id"]: c["rerank_score"] for c in chunks}
    resources = {
        "store": _LineageStore(chunks),
        "embedder": FakeEmbedder(),
        "reranker": harness.ParityReranker(scores, fail=False),
    }
    out = run_chain(
        settings, resources, "gamma delta", hybrid=True, prepare={"rerank": True, "top_k": 2}
    )
    assert out["select"].values["evidence"].score_kind == SCORE_KIND_RERANK


def test_adapter_modules_have_no_default_accessor_reads() -> None:
    """The accessor guard's AST scan finds nothing in the adapter modules."""
    from pathlib import Path

    root = Path(ga.__file__).parent
    for path in sorted(root.glob("graph_adapters*.py")):
        assert _scan_default_accessors(path.read_text(encoding="utf-8")) == [], path.name


def test_importing_adapters_loads_no_concrete_strategy() -> None:
    """Registry contract: concrete strategy modules load only on use."""
    code = (
        "import sys, omrg.core.retrieval.graph_adapters as g\n"
        "mods = ['dense', 'sparse', 'native_sparse', 'reranker', 'reranker_torch', 'fusion']\n"
        "print([m for m in mods if f'omrg.core.retrieval.{m}' in sys.modules])\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == "[]"
