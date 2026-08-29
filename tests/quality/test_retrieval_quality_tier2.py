"""Real-Ollama Tier 2 retrieval-quality regression gate."""

from __future__ import annotations

import json
import platform
import urllib.error
import urllib.request
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings

from rag_mcp.compose import (
    build_embed_model,
    build_vector_store,
    settings_to_effective,
)
from rag_mcp.config import Settings
from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.core.retrieval import search
from rag_mcp.core.retrieval.dense import _cached_query_embedding
from rag_mcp.core.vectordb import set_default_store
from tests.quality.runner import (
    CORPUS_DIR,
    assert_metric_floors,
    fixture_identities,
    load_baseline,
    load_golden_queries,
    measure_rows,
    measurement_record,
    validate_baseline,
)

pytestmark = pytest.mark.slow

MODEL_TAG = "qwen3-embedding:0.6b"
OLLAMA_BASE_URL = "http://127.0.0.1:11434"
_COLLECTION = "quality_tier2"


def _ollama_json(path: str) -> dict[str, Any]:
    """Read one required Ollama API response or fail the gate."""
    try:
        with urllib.request.urlopen(
            f"{OLLAMA_BASE_URL}{path}",
            timeout=10,
        ) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        pytest.fail(f"Ollama is required for Tier 2: {exc}")
    if not isinstance(payload, dict):
        pytest.fail(f"Ollama {path} returned a non-object response")
    return payload


def _ollama_identity() -> tuple[str, str]:
    version_payload = _ollama_json("/api/version")
    version = version_payload.get("version")
    if not isinstance(version, str) or not version:
        pytest.fail("Ollama did not report a version")

    tags_payload = _ollama_json("/api/tags")
    models = tags_payload.get("models")
    if not isinstance(models, list):
        pytest.fail("Ollama did not report an installed model list")
    matches = [
        model
        for model in models
        if isinstance(model, dict) and model.get("name") == MODEL_TAG
    ]
    if len(matches) != 1:
        pytest.fail(f"Ollama must expose exactly one {MODEL_TAG!r} model")
    digest = matches[0].get("digest")
    if not isinstance(digest, str) or not digest:
        pytest.fail(f"Ollama model {MODEL_TAG!r} did not report a digest")
    return version, digest


async def _run_tier2(tmp_path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    ollama_version, model_digest = _ollama_identity()
    config = Settings(
        embed_provider="ollama",
        embed_model=MODEL_TAG,
        ollama_base_url=OLLAMA_BASE_URL,
        vector_store="lancedb",
        lancedb_uri=str(tmp_path / "lancedb"),
        collection_name=_COLLECTION,
        pdf_reader="pypdf",
        chunking={"chunk_size": 1024, "chunk_overlap": 64},
        metadata={"extraction_mode": "disabled"},
        retrieval={
            "top_k": 10,
            "similarity_threshold": 0.0,
            "rerank_enabled": False,
            "rerank_enabled_for_semantic": False,
            "hybrid_enabled": True,
            "hybrid_rrf_k": 60,
            "hybrid_sparse_backend": "bm25",
        },
    )
    effective = settings_to_effective(config)
    store = build_vector_store(config)
    set_default_store(store)
    LlamaIndexSettings.embed_model = build_embed_model(config)
    _cached_query_embedding.cache_clear()

    ingest_result = await ingest_path_async(
        str(CORPUS_DIR),
        collection_name=_COLLECTION,
        effective_settings=effective,
    )
    assert ingest_result["status"] == "ok", ingest_result
    assert ingest_result["files_indexed"] == 20, ingest_result

    rows: list[dict[str, Any]] = []
    for query in load_golden_queries():
        results = search(
            query=query["query"],
            top_k=10,
            similarity_threshold=0.0,
            rerank=False,
            hybrid=True,
            collection_name=_COLLECTION,
            include_diagnostics=True,
            store=store,
            effective_settings=effective,
        )
        rows.append(
            {
                "id": query["id"],
                "query": query["query"],
                "expected_sources": query["expected_sources"],
                "sources": [result["source"] for result in results],
            }
        )

    corpus_id, query_set_id = fixture_identities()
    identity = {
        "model_tag": MODEL_TAG,
        "model_digest": model_digest,
        "ollama_version": ollama_version,
        "runner_os": platform.system(),
        "runner_architecture": platform.machine(),
        "corpus_id": corpus_id,
        "query_set_id": query_set_id,
    }
    return rows, identity


@pytest.mark.asyncio
async def test_tier2_quality_floors_and_identity(tmp_path) -> None:
    """Real Ollama retrieval remains above its identity-bound floors."""
    rows, identity = await _run_tier2(tmp_path)
    actual = measure_rows(rows)
    print(
        "TIER2_MEASUREMENT="
        + json.dumps(
            measurement_record(rows, extra=identity),
            sort_keys=True,
        )
    )

    baseline = load_baseline()
    validate_baseline(baseline, require_tier1=False, require_tier2=True)
    expected = baseline["tier2"]
    for field in (
        "model_tag",
        "model_digest",
        "ollama_version",
        "runner_os",
        "runner_architecture",
    ):
        assert expected[field] == identity[field], (
            f"tier2 {field} mismatch: baseline={expected[field]!r}, "
            f"actual={identity[field]!r}"
        )
    assert baseline["corpus_id"] == identity["corpus_id"]
    assert baseline["query_set_id"] == identity["query_set_id"]
    assert_metric_floors(tier="tier2", actual=actual, baseline=baseline)
