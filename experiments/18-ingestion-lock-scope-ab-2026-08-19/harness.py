"""Shared harness helpers for the ingestion lock-scope experiment.

Provides the deterministic fake embedding model, explicit ingestion
settings, isolated store construction, runtime manifests, and atomic
checkpoint writes. Every measured cell runs in its own subprocess so
``ru_maxrss`` peaks stay attributable to one cell.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_DIR = PROJECT_ROOT / "experiments" / "18-ingestion-lock-scope-ab-2026-08-19"
OUTPUT_DIR = EXPERIMENT_DIR / "output"

FAKE_MODEL_NAME = "mock-deterministic-v1"
FAKE_DIM = 32


def ensure_import_path() -> None:
    """Make ``omrg`` and ``experiments._lib`` importable from source."""
    for entry in (str(PROJECT_ROOT), str(PROJECT_ROOT / "src")):
        if entry not in sys.path:
            sys.path.insert(0, entry)


def build_fake_embed_model() -> Any:
    """Return the deterministic mock embedding model (no network, no load).

    ``MockEmbedding`` is the same deterministic text-hash embedding the test
    suite installs (``tests/conftest.py::_patch_embed_model``). A real
    ``BaseEmbedding`` subclass is required because LlamaIndex asserts the
    assigned model type at resolve time.
    """
    from llama_index.core.embeddings import MockEmbedding

    model = MockEmbedding(embed_dim=FAKE_DIM)
    model.model_name = FAKE_MODEL_NAME
    return model


def build_fake_settings(collection_name: str, persist_dir: Path) -> Any:
    """Return an explicit EffectiveSettings with extraction disabled.

    ADR-037: ad-hoc scripts never rely on a default EffectiveSettings.
    Mirrors the deterministic test defaults (extraction_mode disabled) so
    no real LLM call can hang the harness.
    """
    ensure_import_path()
    from omrg.core.settings import EffectiveSettings, MetadataBlock

    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        collection_name=collection_name,
        chroma_persist_dir=str(persist_dir),
    )


def _install_default_settings(collection_name: str, persist_dir: Path) -> None:
    """Install the process-default EffectiveSettings for this cell process.

    The experiment bypasses ``compose.ensure_runtime_setup`` (it would
    register the production persist directory), so the harness is this
    process's composition root and must install the default itself — the
    store's stale-cleanup path reads it via ``get_default_effective_settings``.
    """
    from omrg.core.settings import set_default_effective_settings

    set_default_effective_settings(build_fake_settings(collection_name, persist_dir))


def install_fake_runtime(persist_dir: Path) -> dict[str, Any]:
    """Configure a fake-embedding runtime with an isolated Chroma store.

    Assigns the deterministic fake embed model on the shared LlamaIndex
    Settings (the same object ``replacement._embed_missing_nodes`` reads)
    and registers an isolated default store. Returns a summary of what
    was installed for the run manifest.
    """
    ensure_import_path()
    from llama_index.core import Settings as LlamaIndexSettings

    from omrg.core.vectordb import reset_default_store, set_default_store
    from omrg.core.vectordb.chroma import ChromaVectorStore

    reset_default_store()
    store = ChromaVectorStore(persist_dir=str(persist_dir))
    set_default_store(store)
    LlamaIndexSettings.embed_model = build_fake_embed_model()
    _install_default_settings("documents", persist_dir)
    return {
        "embedding": {
            "requested_provider": "fake_deterministic",
            "effective_provider": "fake_deterministic",
            "effective_model": FAKE_MODEL_NAME,
            "dim": FAKE_DIM,
        },
        "vector_store": {
            "backend": "chroma_local",
            "mode": "persistent_local",
            "persist_dir": str(persist_dir),
        },
        "store": store,
    }


def install_real_runtime(persist_dir: Path) -> dict[str, Any]:
    """Configure the real Ollama embed model with an isolated store.

    Builds the embed model through the composition root builder (never
    ``ensure_runtime_setup`` — that would register the production persist
    directory as the default store). The local Ollama provider is pinned
    via environment overrides because the repository ``.env`` selects an
    optional provider (llamacpp) that the locked environment does not
    install; env variables take precedence over ``.env`` in settings
    resolution, and each cell is a fresh process.
    """
    ensure_import_path()
    os.environ.setdefault("EMBED_PROVIDER", "local")
    os.environ.setdefault("LOCAL_BACKEND", "ollama")
    os.environ.setdefault("EMBED_MODEL", "nomic-embed-text")
    os.environ.setdefault("OLLAMA_BASE_URL", "http://localhost:11434")

    from llama_index.core import Settings as LlamaIndexSettings

    from omrg.compose import build_embed_model
    from omrg.config import get_settings
    from omrg.core.vectordb import reset_default_store, set_default_store
    from omrg.core.vectordb.chroma import ChromaVectorStore

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
            "requested_provider": str(getattr(config, "embed_provider", "local")),
            "requested_model": str(getattr(config, "embed_model", "")),
            "effective_provider": type(model).__name__,
            "effective_model": effective,
        },
        "vector_store": {
            "backend": "chroma_local",
            "mode": "persistent_local",
            "persist_dir": str(persist_dir),
        },
        "store": store,
    }


def build_runtime_manifest(
    *, embedding: dict, vector_store: dict, corpus_identity: str
) -> dict[str, Any]:
    """Return a D13-style manifest slice for one cell."""
    return {
        "repo_commit": git_commit(),
        "git_dirty": git_dirty(),
        "dependency_lock_hash": lock_hash(),
        "experiment_id": "18-ingestion-lock-scope-ab",
        "protocol_version": "1.0",
        "python_version": sys.version.split()[0],
        "platform": f"{platform.system()}-{platform.machine()}",
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "corpus_identity": corpus_identity,
        "embedding": embedding,
        "vector_store": vector_store,
    }


def git_commit() -> str:
    """Return the current repository commit SHA."""
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607 — PATH resolution is intended
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=True,
    )
    return result.stdout.strip()


def git_dirty() -> bool:
    """Return whether the working tree differs from the recorded commit."""
    result = subprocess.run(
        ["git", "status", "--porcelain"],  # noqa: S607 — PATH resolution is intended
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=True,
    )
    return bool(result.stdout.strip())


def lock_hash() -> str:
    """Return the SHA-256 of the dependency lockfile."""
    data = (PROJECT_ROOT / "uv.lock").read_bytes()
    return hashlib.sha256(data).hexdigest()


def atomic_json_write(path: Path, payload: Any) -> None:
    """Write JSON atomically via ``.tmp`` then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def ollama_available(timeout_s: float = 3.0) -> bool:
    """Return whether a local Ollama daemon answers."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=timeout_s):
            return True
    except Exception:
        return False


def ollama_model_present(model: str) -> bool:
    """Return whether ``model`` is already pulled locally."""
    import json as _json
    import urllib.request

    try:
        with urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3.0) as response:
            payload = _json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    names = [m.get("name", "") for m in payload.get("models", [])]
    return any(name == model or name.split(":")[0] == model for name in names)


def child_environment(persist_dir: Path) -> dict[str, str]:
    """Return a subprocess env pinned to isolated storage."""
    env = os.environ.copy()
    env["VECTOR_STORE"] = "chroma"
    env["CHROMA_PERSIST_DIR"] = str(persist_dir)
    env["PYTHONUNBUFFERED"] = "1"
    return env
