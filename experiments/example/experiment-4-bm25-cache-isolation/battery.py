"""The Experiment 4 namespace battery (protocol §8) for one cell.

One battery run exercises one ``(backend, sequence order)`` cell:

- builds two distinct runtime store instances (A and B) of the same
  backend, each with a collection literally named ``documents``, plus
  ``other`` in A, seeded from the committed fixtures via
  ``upsert_precomputed``;
- runs the full 9-step sequence (forward, or reversed initial query
  order for the §10 order-dependence regression);
- records per-step rows (D16 shape), a mutation generation trace, and
  cache build diagnostics.

The ACTUAL cache keying mechanism is reported as-is with evidence:
``BM25SparseRetriever._cache`` (sparse.py:183) is a class-level dict
keyed by ``(store.cache_identity, collection_name)`` where
``cache_identity`` defaults to the store object itself
(vectordb/base.py:22-25).  Build counts are instrumented by wrapping
the module-level ``_read_collection_rows`` seam (sparse.py:266),
called exactly once per rebuild.

Step 9 drives the REAL production orchestration path: the ingestion
writer's ``embed_and_write_async`` with pre-embedded nodes (no
embedding model call) and ``remove_document``/``delete_collection``
equivalents, then compares generation deltas against the direct-store
mutation sequence.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any


def run_battery(
    backend: str,
    order: str,
    corpus: dict[str, Any],
    tmp_root: Path,
    top_n: int = 5,
) -> dict[str, Any]:
    """Run one cell's battery; return rows, mutation trace, diagnostics."""
    import rag_mcp.core.retrieval.sparse as sparse_mod
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    if backend == "chroma":
        import chromadb

        from rag_mcp.core.vectordb.chroma import ChromaVectorStore

        store_a = ChromaVectorStore(
            client=chromadb.PersistentClient(path=str(tmp_root / "store_a"))
        )
        store_b = ChromaVectorStore(
            client=chromadb.PersistentClient(path=str(tmp_root / "store_b"))
        )
    elif backend == "lancedb":
        import lancedb

        from rag_mcp.core.vectordb.lancedb import LanceVectorStore

        store_a = LanceVectorStore(connection=lancedb.connect(str(tmp_root / "store_a")))
        store_b = LanceVectorStore(connection=lancedb.connect(str(tmp_root / "store_b")))
    else:
        raise ValueError(f"unknown backend {backend!r}")

    stores = {"A": store_a, "B": store_b}
    labels = {id(store_a): "A", id(store_b): "B"}
    ns_spec = corpus["namespaces"]
    collection_of = {ns: spec["collection"] for ns, spec in ns_spec.items()}
    store_of = {ns: spec["store"] for ns, spec in ns_spec.items()}

    # ── Cache build instrumentation (module seam, restored in finally) ──
    builds: dict[tuple[str, str], int] = {}
    original_read = sparse_mod._read_collection_rows

    def counting_read(store: Any, collection_name: str) -> list[Any]:
        builds[(labels[id(store)], collection_name)] = (
            builds.get((labels[id(store)], collection_name), 0) + 1
        )
        return original_read(store, collection_name)

    rows: list[dict[str, Any]] = []
    mutations: list[dict[str, Any]] = []

    def query(namespace: str, token: str, step: str) -> dict[str, Any]:
        store = stores[store_of[namespace]]
        collection = collection_of[namespace]
        before = builds.get((store_of[namespace], collection), 0)
        generation = store.get_generation(collection)
        retriever = BM25SparseRetriever(collection, store=store)
        started = time.perf_counter()
        results = retriever.query(token, top_n)
        latency_ms = (time.perf_counter() - started) * 1000.0
        entry = BM25SparseRetriever._cache.get((store, collection))
        row = {
            "cell_step": step,
            "query_id": f"{step}::{namespace}::{token}",
            "phase": "measured",
            "latency_ms": latency_ms,
            "namespace": namespace,
            "token": token,
            "metrics": {
                "result_ids": [doc_id for _rank, doc_id, _text, _meta in results],
                "generation_at_query": generation,
                "build_count_before": before,
                "build_count_after": builds.get((store_of[namespace], collection), 0),
                "cache_entries_total": len(BM25SparseRetriever._cache),
                "namespace_entry_cached": entry is not None,
                "namespace_cached_generation": entry.generation if entry else None,
                "documents_key_entries": sum(
                    1 for key in BM25SparseRetriever._cache if key[1] == "documents"
                ),
            },
        }
        rows.append(row)
        return row

    def record_mutation(step: str, kind: str, namespace: str, mutate: Any) -> dict[str, Any]:
        store = stores[store_of[namespace]]
        collection = collection_of[namespace]
        before = store.get_generation(collection)
        mutate()
        after = store.get_generation(collection)
        record = {
            "step": step,
            "kind": kind,
            "namespace": namespace,
            "generation_before": before,
            "generation_after": after,
            "generation_delta": after - before,
        }
        mutations.append(record)
        return record

    def upsert(namespace: str, doc: dict[str, Any]) -> None:
        store = stores[store_of[namespace]]
        store.upsert_precomputed(
            collection_of[namespace],
            ids=[doc["id"]],
            documents=[doc["text"]],
            metadatas=[doc["metadata"]],
            embeddings=[doc["vector"]],
        )

    sparse_mod._read_collection_rows = counting_read
    try:
        BM25SparseRetriever._cache.clear()

        # ── Setup: seed all namespaces (one mutation per collection) ──
        for namespace in sorted(ns_spec):
            spec = ns_spec[namespace]
            store = stores[spec["store"]]
            store.create_collection(spec["collection"])
            docs = spec["documents"]
            record_mutation(
                "setup",
                "create+upsert_precomputed",
                namespace,
                lambda s=store, c=spec["collection"], d=docs: s.upsert_precomputed(
                    c,
                    ids=[x["id"] for x in d],
                    documents=[x["text"] for x in d],
                    metadatas=[x["metadata"] for x in d],
                    embeddings=[x["embedding"] for x in d],
                ),
            )

        # ── Preflight observations (§12) recorded as diagnostics ──
        preflight_obs = {
            "stores_distinct_instances": store_a is not store_b
            and store_a.cache_identity is not store_b.cache_identity,
            "both_have_documents_collection": store_a.collection_exists("documents")
            and store_b.collection_exists("documents"),
            "a_documents_ids": sorted(
                doc_id for doc_id, _t, _m in store_a.iter_documents("documents")
            ),
            "b_documents_ids": sorted(
                doc_id for doc_id, _t, _m in store_b.iter_documents("documents")
            ),
            "generations_after_setup": {
                f"{store_of[ns]}/{col}": stores[store_of[ns]].get_generation(col)
                for ns, col in collection_of.items()
            },
            "cache_starts_empty": len(BM25SparseRetriever._cache) == 0,
        }
        preflight_obs["contents_differ"] = (
            preflight_obs["a_documents_ids"] != preflight_obs["b_documents_ids"]
        )
        preflight_obs["collision_generations_equal"] = store_a.get_generation(
            "documents"
        ) == store_b.get_generation("documents")

        delta_doc = corpus["mutation_docs"]["direct_upsert"]
        orch = corpus["mutation_docs"]["orchestration_node"]
        other_ns = "A/other"
        documents_ns = "A/documents"

        if order == "forward":
            initial = [
                ("s1", documents_ns, "alpha_only"),
                ("s2", documents_ns, "alpha_only"),
                ("s3", "B/documents", "beta_only"),
                ("s4", other_ns, "gamma_only"),
            ]
            cross_probe = ("s3x", documents_ns, "beta_only")
        else:
            initial = [
                ("s1", other_ns, "gamma_only"),
                ("s2", other_ns, "gamma_only"),
                ("s3", "B/documents", "beta_only"),
                ("s4", documents_ns, "alpha_only"),
            ]
            cross_probe = ("s3x", "B/documents", "alpha_only")

        for step, namespace, token in initial:
            query(namespace, token, step)
        query(cross_probe[1], cross_probe[2], cross_probe[0])

        # 5. direct-store mutation: upsert the delta document.
        record_mutation(
            "s5",
            "direct upsert_precomputed",
            documents_ns,
            lambda: upsert(documents_ns, delta_doc),
        )
        # 6. rebuild contains the mutation; reuse for the old token.
        query(documents_ns, "delta_only", "s6a")
        query(documents_ns, "alpha_only", "s6b")
        # 7. unaffected namespaces must not rebuild.
        query("B/documents", "beta_only", "s7a")
        query(other_ns, "gamma_only", "s7b")

        # 8. filtered delete from A/documents; rebuild drops the row.
        store_a = stores["A"]
        record_mutation(
            "s8",
            "direct delete_where",
            documents_ns,
            lambda: store_a.delete_where("documents", delta_doc["delete_where"]),
        )
        query(documents_ns, "delta_only", "s8a")
        query(documents_ns, "alpha_only", "s8b")

        # 9. orchestration comparison (production ingestion writer path).
        from llama_index.core import Settings
        from llama_index.core.embeddings import MockEmbedding
        from llama_index.core.schema import TextNode

        from rag_mcp.core.ingestion import writer

        previous_embed_model = getattr(Settings, "embed_model", None)
        Settings.embed_model = MockEmbedding(embed_dim=corpus["dimension"])
        try:
            node = TextNode(
                id_=orch["id"],
                text=orch["text"],
                embedding=list(orch["vector"]),
                metadata=dict(orch["metadata"]),
            )

            def _orch_write() -> None:
                asyncio.run(
                    writer.embed_and_write_async(
                        [node], collection_name="documents", store=stores["A"]
                    )
                )

            record_mutation("s9a", "orchestration embed_and_write_async", documents_ns, _orch_write)
            query(documents_ns, "epsilon_only", "s9a-q")

            def _orch_remove() -> None:
                result = writer.remove_document(
                    orch["remove_document_file_path"],
                    collection_name="documents",
                    store=stores["A"],
                )
                if result.get("status") != "ok":
                    raise RuntimeError(f"orchestration remove failed: {result}")

            record_mutation("s9b", "orchestration remove_document", documents_ns, _orch_remove)
            query(documents_ns, "epsilon_only", "s9b-q")
        finally:
            Settings.embed_model = previous_embed_model

        # Factor C level 4: collection delete/recreate on A/other.
        record_mutation(
            "s9c",
            "direct delete_collection",
            other_ns,
            lambda: stores["A"].delete_collection("other"),
        )
        query(other_ns, "gamma_only", "s9c-q")
        other_spec = ns_spec[other_ns]
        record_mutation(
            "s9d",
            "recreate create+upsert_precomputed",
            other_ns,
            lambda: (
                stores["A"].create_collection("other"),
                stores["A"].upsert_precomputed(
                    "other",
                    ids=[x["id"] for x in other_spec["documents"]],
                    documents=[x["text"] for x in other_spec["documents"]],
                    metadatas=[x["metadata"] for x in other_spec["documents"]],
                    embeddings=[x["embedding"] for x in other_spec["documents"]],
                ),
            ),
        )
        query(other_ns, "gamma_only", "s9d-q")

        return {
            "preflight_observations": preflight_obs,
            "rows": rows,
            "mutation_trace": mutations,
            "build_counters": {f"{a}::{b}": v for (a, b), v in sorted(builds.items())},
            "cache_key_mechanism": {
                "location": "src/rag_mcp/core/retrieval/sparse.py:183,244-247",
                "key_shape": "(store.cache_identity, collection_name)",
                "cache_identity_default": "the store object itself (vectordb/base.py:22-25)",
            },
        }
    finally:
        sparse_mod._read_collection_rows = original_read
        BM25SparseRetriever._cache.clear()
