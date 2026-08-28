"""Source-version identity and metadata for failure-safe ingestion.

A stored source is identified by both its byte content and every input that can
change emitted chunks or vectors. Each replacement attempt uses a unique id so
old and new rows can coexist until durability is verified.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import uuid4

from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.schema import BaseNode

from ..vectordb.base import VectorStore

SOURCE_CONTENT_HASH_KEY = "source_content_hash"
SOURCE_INDEX_IDENTITY_KEY = "source_index_identity"
SOURCE_VERSION_KEY = "source_version"
SOURCE_ATTEMPT_KEY = "source_attempt"
SOURCE_CHUNK_COUNT_KEY = "source_chunk_count"
SOURCE_CHUNK_INDEX_KEY = "source_chunk_index"

_INDEX_IDENTITY_SCHEMA = 2
_SOURCE_METADATA_KEYS = (
    SOURCE_CONTENT_HASH_KEY,
    SOURCE_INDEX_IDENTITY_KEY,
    SOURCE_VERSION_KEY,
    SOURCE_ATTEMPT_KEY,
    SOURCE_CHUNK_COUNT_KEY,
    SOURCE_CHUNK_INDEX_KEY,
)


def _configured_embedding(settings: Any) -> tuple[str, str]:
    """Return the configured provider/model selectors for diagnostics."""
    provider = settings.embed_provider
    if provider == "local":
        provider = settings.local_backend
    elif provider == "cloud":
        provider = settings.cloud_backend
    models = {
        "llamacpp": settings.llamacpp_embed_model,
        "ollama": settings.embed_model,
        "openrouter": settings.openrouter_embed_model,
    }
    return provider, models.get(provider, settings.embed_model)


def _runtime_embedding_identity() -> dict[str, str | None]:
    """Fingerprint the process-global embedder that actually creates vectors.

    ADR-047 makes embedding-provider selection process scoped because
    LlamaIndex exposes one global ``Settings.embed_model``. The source identity
    therefore includes that concrete runtime object, not only per-call/profile
    selectors that cannot swap the active embedder.
    """
    model = LlamaIndexSettings.embed_model
    cls = type(model)
    selector = None
    for attr in ("model_name", "model", "model_path", "embed_model_name"):
        value = getattr(model, attr, None)
        if value is not None:
            selector = str(value)
            break
    return {
        "class": f"{cls.__module__}.{cls.__qualname__}",
        "model": selector,
    }


def build_index_identity(
    settings: Any,
    *,
    content_type: str | None,
    chunk_size: int,
    chunk_overlap: int,
) -> str:
    """Hash the complete index-shaping configuration for one source.

    The payload is deliberately conservative. Parser selectors are included
    even when a file type may not use every selector, because unnecessary
    reprocessing is safer than incorrectly reusing stale chunks or vectors.
    """
    configured_provider, configured_model = _configured_embedding(settings)
    payload = {
        "schema": _INDEX_IDENTITY_SCHEMA,
        "embedding": {
            "runtime": _runtime_embedding_identity(),
            "configured_provider": configured_provider,
            "configured_model": configured_model,
        },
        "parser": {
            "content_type": content_type,
            "document_backend": settings.document_backend,
            "pdf_reader": settings.pdf_reader,
            "liteparse_num_workers": settings.liteparse_num_workers,
            "liteparse_ocr_enabled": settings.liteparse_ocr_enabled,
            "azure_doc_intelligence_model": settings.azure_doc_intelligence_model,
        },
        "chunking": {
            "settings": settings.chunking.model_dump(mode="json"),
            "effective_chunk_size": chunk_size,
            "effective_chunk_overlap": chunk_overlap,
        },
        # Extracted metadata participates in LlamaIndex embedding text unless a
        # strategy excludes it. Timeouts and retry budgets decide whether a
        # real ingest completes extraction or falls back to degraded/local
        # metadata, so a budget change must invalidate the identity —
        # otherwise a source indexed under a degraded budget stays "current"
        # after the operator raises the budget (spec: complete index-shaping
        # identity).
        "metadata_shape": {
            "extraction_mode": settings.metadata.extraction_mode,
            "keyword_rules": settings.metadata.keyword_rules,
            "ollama_classify_model": settings.metadata.ollama_classify_model,
            "taxonomy_mode": settings.metadata.taxonomy_mode,
            "classify_max_attempts": settings.metadata.classify_max_attempts,
            "classify_timeout": settings.metadata.classify_timeout,
            "pipeline_timeout": settings.metadata.pipeline_timeout,
            "llamacpp_classify_timeout_override": (
                settings.metadata.llamacpp_classify_timeout_override
            ),
            "ollama_classify_timeout_override": (
                settings.metadata.ollama_classify_timeout_override
            ),
            "openrouter_classify_timeout_override": (
                settings.metadata.openrouter_classify_timeout_override
            ),
            "llamacpp_pipeline_timeout_override": (
                settings.metadata.llamacpp_pipeline_timeout_override
            ),
            "ollama_pipeline_timeout_override": (
                settings.metadata.ollama_pipeline_timeout_override
            ),
            "openrouter_pipeline_timeout_override": (
                settings.metadata.openrouter_pipeline_timeout_override
            ),
            "metadata_llm_provider": settings.metadata_llm_provider,
            "local_backend": settings.local_backend,
            "cloud_backend": settings.cloud_backend,
            "llamacpp_chat_model": settings.llamacpp_chat_model,
            "openrouter_llm_model": settings.openrouter_llm_model,
        },
    }
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_source_version(content_hash: str, index_identity: str) -> str:
    """Return the stable source-version id for content plus index identity."""
    return hashlib.sha256(f"{content_hash}\0{index_identity}".encode()).hexdigest()


def new_source_attempt() -> str:
    """Return a unique replacement-attempt identifier."""
    return uuid4().hex


def source_where(file_path: str) -> dict:
    """Return the store-neutral filter selecting one source path."""
    return {"file_path": file_path}


def source_version_where(
    file_path: str,
    *,
    content_hash: str,
    index_identity: str,
    source_version: str,
) -> dict:
    """Return a filter selecting rows for one exact source version."""
    return {
        "$and": [
            {"file_path": file_path},
            {SOURCE_CONTENT_HASH_KEY: content_hash},
            {SOURCE_INDEX_IDENTITY_KEY: index_identity},
            {SOURCE_VERSION_KEY: source_version},
        ]
    }


def source_attempt_where(file_path: str, source_attempt: str) -> dict:
    """Return a filter selecting one replacement attempt for a source."""
    return {
        "$and": [
            {"file_path": file_path},
            {SOURCE_ATTEMPT_KEY: source_attempt},
        ]
    }


def stale_attempts_where(file_path: str, source_attempt: str) -> dict:
    """Return a filter selecting prior attempts when backend semantics permit."""
    return {
        "$and": [
            {"file_path": file_path},
            {SOURCE_ATTEMPT_KEY: {"$ne": source_attempt}},
        ]
    }


def is_complete_current_version(
    store: VectorStore,
    collection_name: str,
    *,
    file_path: str,
    content_hash: str,
    index_identity: str,
    source_version: str,
) -> tuple[bool, int]:
    """Return whether the store contains one complete matching source version."""
    if not store.collection_exists(collection_name):
        return False, 0
    total = store.count_where(collection_name, source_where(file_path))
    if total <= 0:
        return False, 0

    version_filter = source_version_where(
        file_path,
        content_hash=content_hash,
        index_identity=index_identity,
        source_version=source_version,
    )
    version_count = store.count_where(collection_name, version_filter)
    if version_count != total:
        return False, total

    complete_filter = {
        "$and": [
            *version_filter["$and"],
            {SOURCE_CHUNK_COUNT_KEY: total},
        ]
    }
    complete_count = store.count_where(collection_name, complete_filter)
    return complete_count == total, total


def stamp_source_attempt(
    nodes: list[BaseNode],
    *,
    file_path: str,
    content_hash: str,
    index_identity: str,
    source_version: str,
    source_attempt: str,
) -> None:
    """Stamp one replacement attempt and give every candidate row a unique ID."""
    chunk_count = len(nodes)
    excluded = set(_SOURCE_METADATA_KEYS)
    for index, node in enumerate(nodes):
        original_id = node.node_id
        node.metadata.update(
            {
                "file_path": file_path,
                SOURCE_CONTENT_HASH_KEY: content_hash,
                SOURCE_INDEX_IDENTITY_KEY: index_identity,
                SOURCE_VERSION_KEY: source_version,
                SOURCE_ATTEMPT_KEY: source_attempt,
                SOURCE_CHUNK_COUNT_KEY: chunk_count,
                SOURCE_CHUNK_INDEX_KEY: index,
            }
        )
        node.excluded_embed_metadata_keys = sorted(
            set(node.excluded_embed_metadata_keys) | excluded
        )
        node.excluded_llm_metadata_keys = sorted(set(node.excluded_llm_metadata_keys) | excluded)
        node.id_ = hashlib.sha256(
            f"{file_path}\0{source_attempt}\0{index}\0{original_id}".encode()
        ).hexdigest()
