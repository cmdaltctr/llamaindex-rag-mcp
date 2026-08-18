"""Fast regressions for the pre-calibration pipeline audit.

These tests deliberately encode defects found during the v3 audit. Some become
green in earlier hardening stages; tests for later stages intentionally remain
red until those contracts are implemented. Keep them lightweight: no live
model, vector database, network, or experiment corpus is required.
"""

from __future__ import annotations

import ast
import inspect
from pathlib import Path

from llama_index.core.node_parser import CodeSplitter

from rag_mcp.core.chunking.code import chunk_code_file_async


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _python_source(relative_path: str) -> str:
    return (_REPO_ROOT / relative_path).read_text(encoding="utf-8")


def _search_call_literal_values(source: str, keyword: str) -> set[object]:
    """Return literal values passed to ``search(..., keyword=...)`` calls."""
    tree = ast.parse(source)
    values: set[object] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name != "search":
            continue
        for item in node.keywords:
            if item.arg != keyword:
                continue
            if isinstance(item.value, ast.Constant):
                values.add(item.value.value)
            elif isinstance(item.value, ast.Name) and item.value.id == "None":
                values.add(None)
    return values


def test_code_splitter_wrapper_uses_supported_code_units() -> None:
    """Production CodeSplitter wiring must use the 0.14.x code-specific API."""
    upstream = inspect.signature(CodeSplitter)
    assert "chunk_lines" in upstream.parameters
    assert "chunk_lines_overlap" in upstream.parameters
    assert "max_chars" in upstream.parameters

    source = inspect.getsource(chunk_code_file_async)
    assert "chunk_lines=" in source
    assert "chunk_lines_overlap=" in source
    assert "max_chars=" in source
    assert "CodeSplitter(\n            language=language,\n            chunk_size=" not in source


def test_llamaindex_metadata_cap_is_not_character_slicing() -> None:
    """A max-chunks setting must cap split chunks, not ``N * tokens`` chars."""
    source = _python_source("src/rag_mcp/core/metadata/llamaindex.py")
    assert "text[: max_chunks * resolved.chunk_size]" not in source
    assert "[:max_chunks]" in source or "[: max_chunks]" in source


def test_hybrid_sparse_path_accepts_the_query_metadata_filter() -> None:
    """Hybrid filtering must constrain sparse retrieval, not dense only."""
    from rag_mcp.core.retrieval import pipeline

    sparse_signature = inspect.signature(pipeline._sparse_bm25_query)
    assert "metadata_filter" in sparse_signature.parameters

    hybrid_source = inspect.getsource(pipeline._hybrid_query_rows)
    assert "_sparse_bm25_query" in hybrid_source
    # The sparse call must receive the query constraint just as the dense call
    # does. This assertion stays intentionally red until Stage 2.3 lands.
    sparse_call_tail = hybrid_source.split("_sparse_bm25_query", 1)[1]
    assert "metadata_filter" in sparse_call_tail


def test_bm25_cache_isolated_by_store_identity() -> None:
    """Same collection name in two stores must never share sparse rows."""
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    class FakeStore:
        def __init__(self, doc_id: str, text: str) -> None:
            self.doc_id = doc_id
            self.text = text

        def get_generation(self, collection_name: str) -> int:
            return 0

        def count(self, collection_name: str) -> int:
            return 1

        def iter_documents(self, collection_name: str):
            yield self.doc_id, self.text, {"file_path": f"/{self.doc_id}.txt"}

    BM25SparseRetriever._cache.clear()
    try:
        first = BM25SparseRetriever(
            "documents", store=FakeStore("store-a", "alpha unique token")
        )
        second = BM25SparseRetriever(
            "documents", store=FakeStore("store-b", "beta unique token")
        )

        first_rows = first.query("alpha", 5)
        second_rows = second.query("beta", 5)

        assert first_rows and first_rows[0][1] == "store-a"
        assert second_rows and second_rows[0][1] == "store-b"
    finally:
        BM25SparseRetriever._cache.clear()


def test_hybrid_dense_threshold_is_not_applied_to_rrf_score(monkeypatch) -> None:
    """A qualifying dense score must not be rejected because RRF is ~0.03."""
    from rag_mcp.core.retrieval import pipeline
    from rag_mcp.core.settings import EffectiveSettings

    class FakeStore:
        def count(self, collection_name: str) -> int:
            return 1

    def fake_hybrid(*args, **kwargs):
        return [
            {
                "id": "doc-1",
                "source": "/doc-1.txt",
                "page_label": None,
                "text": "relevant",
                "metadata": {},
                "score": 2.0 / 61.0,
                "fused_score": 2.0 / 61.0,
                "dense_score": 0.9,
                "dense_rank": 1,
                "sparse_rank": 1,
                "fused_rank": 1,
                "reranked": False,
            }
        ]

    monkeypatch.setattr(pipeline, "_hybrid_query_rows", fake_hybrid)

    results = pipeline.search(
        query="relevant",
        top_k=1,
        similarity_threshold=0.3,
        rerank=False,
        hybrid=True,
        store=FakeStore(),
        effective_settings=EffectiveSettings(),
    )

    assert len(results) == 1


def test_each_vector_store_mutation_owns_generation_invalidation() -> None:
    """Chroma and Lance must expose the same store-owned mutation contract."""
    from rag_mcp.core.vectordb.chroma import ChromaVectorStore
    from rag_mcp.core.vectordb.lancedb import LanceVectorStore

    for store_cls in (ChromaVectorStore, LanceVectorStore):
        for method_name in ("write_nodes", "delete_where", "delete_collection"):
            source = inspect.getsource(getattr(store_cls, method_name))
            assert "self.bump_generation" in source, (
                f"{store_cls.__name__}.{method_name} does not own generation invalidation"
            )


def test_orchestration_does_not_duplicate_store_generation_bumps() -> None:
    """Once stores own invalidation, writer orchestration must not bump again."""
    from rag_mcp.core.ingestion import writer

    mutation_helpers = [
        writer.embed_and_write_async,
        writer.remove_document,
        writer.remove_by_metadata,
        writer.remove_collection,
    ]
    combined = "\n".join(inspect.getsource(fn) for fn in mutation_helpers)
    assert "resolved_store.bump_generation" not in combined


def test_experiment_10b_runner_contains_hybrid_and_dense_treatments() -> None:
    """10b must not claim a hybrid hypothesis while executing dense-only cells."""
    source = _python_source(
        "experiments/10b-reranker-pool-size-corrected-2026-06-29/run_eval.py"
    )
    assert _search_call_literal_values(source, "hybrid") == {False, True}
    assert _search_call_literal_values(source, "rerank") == {False, True}


def test_experiment_13_threshold_cells_do_not_force_reranking() -> None:
    """Threshold-policy cells must let the policy resolver decide reranking."""
    source = _python_source(
        "experiments/13-hard-technical-threshold-calibration-2026-06-29/run_eval.py"
    )
    rerank_values = _search_call_literal_values(source, "rerank")
    assert None in rerank_values


def test_experiment_14_build_path_reads_real_pdf_bytes() -> None:
    """The parser A/B must actually parse PDFs rather than Qasper Markdown."""
    source = _python_source(
        "experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py"
    )
    assert 'glob("*.pdf")' in source or "glob('*.pdf')" in source
    assert "get_pdf_reader" in source or "read_and_chunk_file_async" in source
