"""Shared harness helpers for the ingestion boundedness experiment.

Provides the deterministic fake embedding model, the real Ollama runtime
pins, isolated store construction, embedding/write call counters, a
boundedness probe over the replacement seam, D13 runtime manifests built
through ``experiments._lib.manifest`` (the TDR-014 Stage 5 requirement —
experiment 18's inline manifest style is not reused), and atomic
checkpoint writes.

Every measured cell runs in its own subprocess (driver pattern from
experiment 18) so ``ru_maxrss`` peaks stay attributable to one cell.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT_DIR = (
    PROJECT_ROOT / "experiments" / "example" / "experiment-6-ingestion-boundedness-and-atomicity"
)
OUTPUT_DIR = EXPERIMENT_DIR / "output"
CORPUS_MANIFESTS_DIR = EXPERIMENT_DIR / "corpus_manifests"

FAKE_MODEL_NAME = "mock-deterministic-v1"
FAKE_DIM = 32
REAL_EMBED_MODEL = "nomic-embed-text"
EXPERIMENT_ID = "6-ingestion-boundedness-and-atomicity"
PROTOCOL_VERSION = "1.0"
PIPELINE_VARIANT = "stage3b_narrow_lock_current"


def ensure_import_path() -> None:
    """Make ``rag_mcp`` and ``experiments._lib`` importable from source."""
    for entry in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def build_fake_embed_model() -> Any:
    """Return the deterministic mock embedding model (no network, no load).

    ``MockEmbedding`` is the same deterministic text-hash embedding the test
    suite installs.  A real ``BaseEmbedding`` subclass is required because
    LlamaIndex asserts the assigned model type at resolve time.
    """
    from llama_index.core.embeddings import MockEmbedding

    model = MockEmbedding(embed_dim=FAKE_DIM)
    model.model_name = FAKE_MODEL_NAME
    return model


def build_fake_settings(collection_name: str, persist_dir: Path) -> Any:
    """Return an explicit EffectiveSettings with extraction disabled.

    ADR-037: ad-hoc scripts never rely on a default EffectiveSettings.
    Mirrors the deterministic test defaults so no real LLM call can hang.
    """
    ensure_import_path()
    from rag_mcp.core.settings import EffectiveSettings, MetadataBlock

    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        collection_name=collection_name,
        chroma_persist_dir=str(persist_dir),
    )


def _install_default_settings(collection_name: str, persist_dir: Path) -> None:
    """Install the process-default EffectiveSettings for this cell process.

    The harness bypasses ``compose.ensure_runtime_setup`` (it would register
    the production persist directory), so the harness is this process's
    composition root and must install the default itself — the store's
    stale-cleanup path reads it via ``get_default_effective_settings``.
    """
    from rag_mcp.core.settings import set_default_effective_settings

    set_default_effective_settings(build_fake_settings(collection_name, persist_dir))


def install_fake_runtime(persist_dir: Path) -> dict[str, Any]:
    """Configure a fake-embedding runtime with an isolated Chroma store."""
    ensure_import_path()
    from llama_index.core import Settings as LlamaIndexSettings

    from rag_mcp.core.vectordb import reset_default_store, set_default_store
    from rag_mcp.core.vectordb.chroma import ChromaVectorStore

    reset_default_store()
    store = ChromaVectorStore(persist_dir=str(persist_dir))
    set_default_store(store)
    LlamaIndexSettings.embed_model = build_fake_embed_model()
    _install_default_settings("documents", persist_dir)
    return {
        "embedding": {
            "requested_provider": "fake_deterministic",
            "effective_provider": "fake_deterministic",
            "model": FAKE_MODEL_NAME,
        },
        "vector_store": {
            "backend": "chroma",
            "mode": "persistent_local",
            "persist_dir": str(persist_dir),
        },
        "store": store,
    }


def install_real_runtime(persist_dir: Path) -> dict[str, Any]:
    """Configure the real Ollama embed model with an isolated store.

    Builds the embed model through the composition-root builder (never
    ``ensure_runtime_setup``).  The local Ollama provider is pinned by
    explicit environment assignment because the repository ``.env`` selects
    an optional provider (llamacpp) whose extra is not installed; env
    variables take precedence over ``.env`` in settings resolution, and
    each cell is a fresh process.
    """
    ensure_import_path()
    os.environ["EMBED_PROVIDER"] = "local"
    os.environ["LOCAL_BACKEND"] = "ollama"
    os.environ["EMBED_MODEL"] = REAL_EMBED_MODEL
    os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"

    from llama_index.core import Settings as LlamaIndexSettings

    from rag_mcp.compose import build_embed_model
    from rag_mcp.config import get_settings
    from rag_mcp.core.vectordb import reset_default_store, set_default_store
    from rag_mcp.core.vectordb.chroma import ChromaVectorStore

    config = get_settings()
    model = build_embed_model(config)
    reset_default_store()
    store = ChromaVectorStore(persist_dir=str(persist_dir))
    set_default_store(store)
    LlamaIndexSettings.embed_model = model
    _install_default_settings("documents", persist_dir)
    effective = str(getattr(model, "model_name", type(model).__name__))
    return {
        "embedding": {
            "requested_provider": "ollama",
            "effective_provider": "ollama",
            "model": effective,
        },
        "vector_store": {
            "backend": "chroma",
            "mode": "persistent_local",
            "persist_dir": str(persist_dir),
        },
        "store": store,
    }


def install_embed_counter() -> dict[str, int]:
    """Count embedding work at the production seam ``_embed_missing_nodes``.

    Harness-level wrap of ``replacement._embed_missing_nodes`` — the exact
    function the pipeline calls to embed a bounded node set (and the same
    seam the fault injector uses).  LlamaIndex embedding models are pydantic
    models whose methods cannot be patched at class level, so the module
    seam is both the honest and the only clean observation point.  H5
    evidence: an unchanged second ingest must show zero seam calls with
    missing nodes.
    """
    ensure_import_path()
    from rag_mcp.core.ingestion import replacement as replacement_module

    counts = {"embed_seam_calls": 0, "nodes_embedded": 0}
    original = replacement_module._embed_missing_nodes

    def _counting(nodes):
        missing = [node for node in nodes if node.embedding is None]
        if missing:
            counts["embed_seam_calls"] += 1
            counts["nodes_embedded"] += len(missing)
        return original(nodes)

    replacement_module._embed_missing_nodes = _counting
    return counts


def install_store_write_counter(store: Any) -> dict[str, int]:
    """Count ``write_nodes`` calls on the isolated store instance.

    Harness-level seam only (instance attribute); H5 evidence: an unchanged
    second ingest must show zero store writes.
    """
    counts = {"write_calls": 0, "nodes_written": 0}
    original = store.write_nodes

    def _counting(nodes, collection_name, **kwargs):
        counts["write_calls"] += 1
        counts["nodes_written"] += len(nodes)
        return original(nodes, collection_name, **kwargs)

    store.write_nodes = _counting
    return counts


def install_replacement_probe() -> dict[str, int]:
    """Probe the bounded unit: simultaneously-live replacement batches.

    Wraps ``pipeline.replace_source_nodes_async`` (the name pipeline.py
    resolves at call time) with a concurrency high-water mark plus the
    maximum node count per batch.  Direct H1 observable: the high-water
    mark must stay at the number of concurrent ingest streams, independent
    of corpus file count.  Harness-level seam; production source untouched.
    """
    ensure_import_path()
    from rag_mcp.core.ingestion import pipeline as pipeline_module

    state = {"live": 0, "max_live": 0, "max_nodes": 0, "batches": 0}
    original = pipeline_module.replace_source_nodes_async

    async def _probed(*args, **kwargs):
        state["batches"] += 1
        nodes = args[0] if args else kwargs.get("nodes")
        if nodes is not None:
            state["max_nodes"] = max(state["max_nodes"], len(nodes))
        state["live"] += 1
        state["max_live"] = max(state["max_live"], state["live"])
        try:
            return await original(*args, **kwargs)
        finally:
            state["live"] -= 1

    pipeline_module.replace_source_nodes_async = _probed
    return state


def compute_index_identity(settings: Any) -> str:
    """Return the index-shaping identity for plain-text corpus files.

    Recorded as ``vector_store.index_identity`` so the unchanged-skip
    preflight (same index-shaping identity) is checkable from manifests.
    Computed with ``content_type=None``: Magika's per-file label is a
    pipeline-internal value; the identity here is the cross-cell constant.
    """
    ensure_import_path()
    from rag_mcp.core.ingestion.source_state import build_index_identity

    return build_index_identity(
        settings,
        content_type=None,
        chunk_size=settings.chunking.chunk_size,
        chunk_overlap=settings.chunking.chunk_overlap,
    )


def manifest_for_cell(
    *,
    cell_id: str,
    run_phase: str,
    embedding: dict[str, Any],
    vector_store: dict[str, Any],
    corpus_manifest_path: Path | None,
    settings: Any,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one D13 manifest through the shared ``_lib`` builder.

    Ingestion-systems experiment: the retrieval/qrels sections are absent
    by design and surface as nulls-with-reasons (TDR-014's retrieval-field
    mandatory list applies to retrieval experiments).
    """
    ensure_import_path()
    from experiments._lib.manifest import build_runtime_manifest

    merged_extra: dict[str, Any] = {
        "cell_id": cell_id,
        "run_phase": run_phase,
        "pipeline_variant": PIPELINE_VARIANT,
        **(extra or {}),
    }
    return build_runtime_manifest(
        experiment_id=EXPERIMENT_ID,
        protocol_version=PROTOCOL_VERSION,
        embedding=embedding,
        vector_store=vector_store,
        index_identity=compute_index_identity(settings),
        corpus_path=corpus_manifest_path,
        project_root=PROJECT_ROOT,
        extra=merged_extra,
    )


def peak_rss_bytes() -> int | None:
    """Return this process's peak RSS via the production sampler."""
    ensure_import_path()
    from rag_mcp.core.ingestion.metrics import sample_peak_rss_bytes

    return sample_peak_rss_bytes()


def atomic_json_write(path: Path, payload: Any) -> None:
    """Write JSON atomically via ``.tmp`` then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def ollama_available(timeout_s: float = 3.0) -> bool:
    """Return whether a local Ollama daemon answers."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=timeout_s):
            return True
    except Exception:
        return False


def ollama_model_present(model: str) -> bool:
    """Return whether ``model`` is already pulled locally."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    names = [m.get("name", "") for m in payload.get("models", [])]
    return any(name == model or name.split(":")[0] == model for name in names)


def child_environment() -> dict[str, str]:
    """Return a subprocess env pinned to unbuffered output.

    Storage isolation is by explicit paths inside each cell (persist dir
    under the experiment output directory); no global env store is set.
    """
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    return env


def timestamp_utc() -> str:
    """Return the current UTC timestamp used in progress output."""
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
