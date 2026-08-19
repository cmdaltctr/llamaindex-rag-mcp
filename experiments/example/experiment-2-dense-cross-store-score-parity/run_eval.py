"""Run Example Experiment 2: dense cross-store score parity (task 5.2).

Executes the pre-registered protocol ``protocol.md`` v1.0 AS WRITTEN
against ChromaDB and LanceDB with committed analytic vector fixtures.

Contracts honoured (TDR-014):

- ``plan.json`` agreement via ``ExperimentPlan.assert_runner_cells``
  before any measured work.
- One D13 runtime manifest per cell with the store-experiment mandatory
  fields non-null; embedding is honestly recorded as ``precomputed``
  with model ``fixed-fixture-vectors``.  Corpus/query/qrels identities
  are sha256 of the committed fixture files (they ARE the ground
  truth).
- D14 preflight per cell (``assert_manifest`` with the plan's
  assertions).  ``assert_no_fallback`` is not applicable (no reranker,
  no parser, no embedding provider switch) — the plan pins
  ``embedding.effective_provider == "precomputed"`` instead.
- Rows follow the D16 contract (``stats.validate_per_query_rows``);
  warm-up is phase ``warmup``; measured repetitions alternate backend
  order (protocol §10) because latency is a descriptive secondary.
- Atomic ``.tmp`` → rename checkpoints after every interleaved
  repetition group and per-cell artefacts; ``--resume`` skips completed
  groups.
- Controlled variables pinned across cells with
  ``assert_controlled_constant`` after both cells' manifests exist.
- Fresh stores under a temporary directory, deleted after raw results
  are saved (protocol §20).

Measured path: queries go through the CORE dense function
``rag_mcp.core.retrieval.dense._dense_query_rows`` with a fixture
lookup embed model installed on the LlamaIndex ``Settings`` seam, so
the production store-blind path produces the rows.  No embedding model
runs: the lookup returns the committed query vector verbatim.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from experiments._lib import manifest as manifest_lib  # noqa: E402
from experiments._lib import preflight, stats  # noqa: E402
from experiments._lib.plan import ExperimentPlan  # noqa: E402

EXPERIMENT_ID = "example-experiment-2-dense-cross-store-score-parity"
PROTOCOL_VERSION = "1.0"
PLAN_PATH = SCRIPT_DIR / "plan.json"
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
TOP_K = 10
WARMUP_REPS = 1
MEASURED_REPS = 5
COLLECTION_PREFIX = "exp2_"
EMBED_MODEL_NAME = "fixed-fixture-vectors"

sys.path.insert(0, str(SCRIPT_DIR))
from static_check import scan_dense_opacity  # noqa: E402


def _fixture_embed_model_class():
    """Build a BaseEmbedding subclass backed by the committed fixture vectors.

    The LlamaIndex ``Settings.embed_model`` setter rejects objects that
    are not ``BaseEmbedding`` instances, so the fixture lookup model is
    a real (tiny) embedding model whose every method returns the
    committed analytic vector verbatim — no model, no network, no
    computation.  A private counter records real invocations so the
    harness can prove the upsert phase caused zero embedding calls.
    """

    from llama_index.core.embeddings import BaseEmbedding
    from pydantic import PrivateAttr

    class FixtureEmbedModel(BaseEmbedding):
        """Deterministic lookup model: query text -> committed vector."""

        model_name: str = EMBED_MODEL_NAME  # type: ignore[assignment]

        _vectors: dict[str, list[float]] = PrivateAttr(default_factory=dict)
        _call_count: int = PrivateAttr(default=0)

        def model_post_init(self, __context: Any) -> None:
            self._vectors = {}
            self._call_count = 0

        def install(self, vectors_by_text: dict[str, list[float]]) -> None:
            self._vectors = dict(vectors_by_text)

        @property
        def call_count(self) -> int:
            return self._call_count

        def _get_query_embedding(self, query: str) -> list[float]:
            self._call_count += 1
            return list(self._vectors[query])

        def _get_text_embedding(self, text: str) -> list[float]:
            self._call_count += 1
            return list(self._vectors[text])

        async def _aget_query_embedding(self, query: str) -> list[float]:
            return self._get_query_embedding(query)

        async def _aget_text_embedding(self, text: str) -> list[float]:
            return self._get_text_embedding(text)

    return FixtureEmbedModel


def build_cell_matrix() -> list[dict[str, Any]]:
    """Return the runner cell matrix (must match ``plan.json``)."""
    return [
        {"id": "chroma_dense", "factors": {"vector_store_backend": "chroma"}},
        {"id": "lancedb_dense", "factors": {"vector_store_backend": "lancedb"}},
    ]


def _load_fixtures() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    corpus = json.loads((FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8"))
    queries = json.loads((FIXTURES_DIR / "queries.json").read_text(encoding="utf-8"))
    qrels = json.loads((FIXTURES_DIR / "qrels.json").read_text(encoding="utf-8"))
    return corpus, queries, qrels


def _build_store(backend: str, root: Path):  # noqa: ANN202 - dynamic store type
    """Construct a fresh store instance of *backend* under *root*."""
    if backend == "chroma":
        import chromadb

        from rag_mcp.core.vectordb.chroma import ChromaVectorStore

        client = chromadb.PersistentClient(path=str(root / "chroma"))
        return ChromaVectorStore(client=client)
    if backend == "lancedb":
        import lancedb

        from rag_mcp.core.vectordb.lancedb import LanceVectorStore

        return LanceVectorStore(connection=lancedb.connect(str(root / "lancedb")))
    raise ValueError(f"unknown backend {backend!r}")


def _seed_fixtures(store: Any, corpus: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Create one collection per fixture and upsert the committed rows.

    Returns the seeded fixture ids to their expected id sets for the
    freshness preflight.
    """
    expected: dict[str, dict[str, Any]] = {}
    for fixture_id in sorted(corpus["fixtures"]):
        docs = corpus["fixtures"][fixture_id]["documents"]
        collection = f"{COLLECTION_PREFIX}{fixture_id}"
        store.create_collection(collection)
        store.upsert_precomputed(
            collection,
            ids=[d["id"] for d in docs],
            documents=[d["text"] for d in docs],
            metadatas=[d["metadata"] for d in docs],
            embeddings=[d["embedding"] for d in docs],
        )
        expected[collection] = {
            "ids": sorted(d["id"] for d in docs),
            "count": len(docs),
        }
    return expected


def _verify_freshness(store: Any, expected: dict[str, dict[str, Any]]) -> None:
    """Protocol §12: both stores fresh and holding exactly the fixture ids."""
    for collection, want in expected.items():
        observed = sorted(doc_id for doc_id, _text, _meta in store.iter_documents(collection))
        if observed != want["ids"] or store.count(collection) != want["count"]:
            raise preflight.PreflightError(
                f"collection {collection!r} freshness check failed: ids {observed} vs {want['ids']}"
            )


def _cell_manifest(
    cell: dict[str, Any],
    corpus_path: Path,
    queries_path: Path,
    qrels_path: Path,
    *,
    embed_calls_during_upsert: int,
    query_vector_checksum: str,
) -> dict[str, Any]:
    backend = cell["factors"]["vector_store_backend"]
    corpus_identity = manifest_lib.sha256_file(corpus_path)
    return manifest_lib.build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        embedding={
            "requested_provider": "precomputed",
            "effective_provider": "precomputed",
            "model": EMBED_MODEL_NAME,
        },
        vector_store={
            "backend": backend,
            "mode": "local",
            "score_kind": "dense_similarity_v1",
        },
        retrieval={
            "top_k": TOP_K,
            "hybrid": False,
            "threshold": 0.0,
            "threshold_score_kind": "dense_similarity_v1",
        },
        corpus_path=corpus_path,
        query_set_path=queries_path,
        qrels_path=qrels_path,
        index_identity=f"exp2-fixtures::{backend}::{corpus_identity.removeprefix('sha256:')[:12]}",
        project_root=PROJECT_ROOT,
        extra={
            "cell_id": cell["id"],
            "upsert_path": "upsert_precomputed",
            "embedding_model_calls_during_upsert": embed_calls_during_upsert,
            "query_vector_checksum": query_vector_checksum,
        },
    )


def _run_fixture_query(
    store: Any,
    fixture_id: str,
    query_text: str,
    query_vector: list[float],
    thresholds: list[float],
    filters: dict[str, dict[str, Any]],
) -> tuple[dict[str, Any], float]:
    """One measured query through the CORE dense function; return metrics.

    Latency covers the core path only.  A direct adapter ``query_dense``
    call supplies the native diagnostic distance (protocol §7) and a
    recorded cross-check that the core path and the adapter agree on
    ids and scores.
    """
    from rag_mcp.core.retrieval.dense import _dense_query_rows

    collection = f"{COLLECTION_PREFIX}{fixture_id}"
    started = time.perf_counter()
    rows = _dense_query_rows(store, collection, query_text, TOP_K)
    latency_ms = (time.perf_counter() - started) * 1000.0

    adapter_rows = store.query_dense(collection, query_vector, TOP_K)

    metrics: dict[str, Any] = {
        "ids": [row["id"] for row in rows],
        "scores": [row["score"] for row in rows],
        "score_kind": rows[0]["score_kind"] if rows else None,
        "native_distances": [row["native_distance"] for row in adapter_rows],
        "adapter_ids": [row["id"] for row in adapter_rows],
        "adapter_scores": [row["score"] for row in adapter_rows],
        "threshold_membership": {
            f"{threshold:.2f}": sorted(row["id"] for row in rows if row["score"] >= threshold)
            for threshold in thresholds
        },
    }
    if filters:
        metrics["filter_membership"] = {}
        for name, where in filters.items():
            filtered = _dense_query_rows(
                store, collection, query_text, TOP_K, metadata_filter=where
            )
            metrics["filter_membership"][name] = {
                "query_ids": [row["id"] for row in filtered],
                "count_where": store.count_where(collection, where),
            }
    return metrics, latency_ms


def _atomic_write(path: Path, payload: Any) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def run(output_dir: Path, resume: bool) -> dict[str, Any]:
    # Paged reads resolve the default page size through the process
    # default settings; install a disabled-extraction default (no
    # network, no LLM) before touching any store.
    from rag_mcp.core.settings import (
        EffectiveSettings,
        MetadataBlock,
        set_default_effective_settings,
    )

    set_default_effective_settings(
        EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled"))
    )

    plan = ExperimentPlan.from_json(PLAN_PATH)
    plan.assert_runner_cells(build_cell_matrix())

    corpus, queries, qrels = _load_fixtures()
    corpus_path = FIXTURES_DIR / "manifest.json"
    queries_path = FIXTURES_DIR / "queries.json"
    qrels_path = FIXTURES_DIR / "qrels.json"
    query_vector_checksum = manifest_lib.sha256_file(queries_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / "results.raw.json"
    cells_dir = output_dir / "cells"
    cells_dir.mkdir(exist_ok=True)

    static_evidence = scan_dense_opacity()

    raw: dict[str, Any] = {
        "experiment_id": EXPERIMENT_ID,
        "protocol_version": PROTOCOL_VERSION,
        "plan_cells": plan.cell_dicts(),
        "static_check": static_evidence,
        "cleanup": [],
        "rows": [],
        "cells": {},
        "manifests": {},
    }
    if resume and raw_path.exists():
        raw = json.loads(raw_path.read_text(encoding="utf-8"))
        raw["static_check"] = static_evidence
    done_groups = {row["rep_group"] for row in raw["rows"]}

    from llama_index.core import Settings

    fixture_cls = _fixture_embed_model_class()
    embed_model = fixture_cls()
    embed_model.install({spec["text"]: spec["vector"] for spec in queries.values()})
    previous = getattr(Settings, "embed_model", None)
    Settings.embed_model = embed_model

    stores: dict[str, Any] = {}
    manifests: dict[str, dict[str, Any]] = dict(raw["manifests"])
    deleted: list[str] = []
    try:
        for cell in build_cell_matrix():
            cell_id = cell["id"]
            if cell_id in raw["cells"]:
                continue
            backend = cell["factors"]["vector_store_backend"]
            tmp_root = Path(tempfile.mkdtemp(prefix=f"exp2_{backend}_"))
            deleted.append(str(tmp_root))
            store = _build_store(backend, tmp_root)
            stores[cell_id] = (store, tmp_root)
            calls_before = embed_model.call_count
            expected = _seed_fixtures(store, corpus)
            _verify_freshness(store, expected)
            manifest = _cell_manifest(
                cell,
                corpus_path,
                queries_path,
                qrels_path,
                embed_calls_during_upsert=embed_model.call_count - calls_before,
                query_vector_checksum=query_vector_checksum,
            )
            preflight.assert_manifest(manifest, plan.required_manifest_assertions)
            manifests[cell_id] = manifest

        # Interleaved repetition groups; backend order alternates per
        # group (protocol §10) because latency is descriptive output.
        total_groups = WARMUP_REPS + MEASURED_REPS
        for group in range(total_groups):
            if group in done_groups:
                continue
            phase = "warmup" if group < WARMUP_REPS else "measured"
            order = build_cell_matrix() if group % 2 == 0 else list(reversed(build_cell_matrix()))
            for position, cell in enumerate(order):
                store, _root = stores[cell["id"]]
                for fixture_id in sorted(corpus["fixtures"]):
                    spec = queries[fixture_id]
                    metrics, latency_ms = _run_fixture_query(
                        store,
                        fixture_id,
                        spec["text"],
                        spec["vector"],
                        qrels["thresholds"],
                        qrels["filters"] if fixture_id == "f5_metadata_filters" else {},
                    )
                    raw["rows"].append(
                        {
                            "cell_id": cell["id"],
                            "query_id": spec["query_id"],
                            "phase": phase,
                            "latency_ms": latency_ms,
                            "rep_group": group,
                            "backend_order_position": position,
                            "fixture_id": fixture_id,
                            "metrics": metrics,
                        }
                    )
            _atomic_write(raw_path, raw)

        for cell in build_cell_matrix():
            cell_id = cell["id"]
            if cell_id in raw["cells"]:
                continue
            raw["cells"][cell_id] = stats.cell_record(
                status="complete",
                rows=sum(1 for r in raw["rows"] if r["cell_id"] == cell_id),
                manifest=manifests[cell_id],
            )
            raw["manifests"] = manifests
            _atomic_write(raw_path, raw)
            _atomic_write(cells_dir / f"{cell_id}.json", raw["cells"][cell_id])
    finally:
        Settings.embed_model = previous
        for _store, root in stores.values():
            shutil.rmtree(root, ignore_errors=True)
        raw["cleanup"] = sorted(set(deleted))
        _atomic_write(raw_path, raw)

    stats.validate_per_query_rows(raw["rows"])
    preflight.assert_controlled_constant(
        manifests,
        [
            "corpus_identity",
            "query_set_identity",
            "qrels_identity",
            "vector_store.score_kind",
            "retrieval.top_k",
            "retrieval.hybrid",
            "retrieval.threshold",
            "query_vector_checksum",
        ],
    )
    _atomic_write(raw_path, raw)
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR / "output" / "run1",
        help="Directory for raw artefacts (default: output/run1)",
    )
    parser.add_argument("--resume", action="store_true", help="Skip completed groups")
    args = parser.parse_args()
    raw = run(args.output_dir, args.resume)
    print(
        f"rows={len(raw['rows'])} cells={sorted(raw['cells'])} "
        f"static_check_pass={raw['static_check']['pass']} -> {args.output_dir / 'results.raw.json'}",
        flush=True,
    )


if __name__ == "__main__":
    main()
