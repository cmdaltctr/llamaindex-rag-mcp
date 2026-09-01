"""Source-version identity and metadata for failure-safe ingestion.

A stored source is identified by both its byte content and every input that can
change emitted chunks or vectors. Each replacement attempt uses a unique id so
old and new rows can coexist until durability is verified. On top of that
attempt-scoped identity, every source carries a stable ``source_id`` derived
from its canonical path and every stored chunk a stable ``chunk_id`` derived
from its text, ordinal, and source version, so citations and reconstruction
survive replacement attempts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from llama_index.core import Settings as LlamaIndexSettings
from llama_index.core.schema import (
    BaseNode,
    MetadataMode,
    NodeRelationship,
    RelatedNodeInfo,
)

from ..vectordb.base import VectorStore

SOURCE_CONTENT_HASH_KEY = "source_content_hash"
SOURCE_ID_KEY = "source_id"
CHUNK_ID_KEY = "chunk_id"
SOURCE_INDEX_IDENTITY_KEY = "source_index_identity"
SOURCE_VERSION_KEY = "source_version"
SOURCE_ATTEMPT_KEY = "source_attempt"
SOURCE_CHUNK_COUNT_KEY = "source_chunk_count"
SOURCE_CHUNK_INDEX_KEY = "source_chunk_index"

_INDEX_IDENTITY_SCHEMA = 2
_SOURCE_METADATA_KEYS = (
    SOURCE_CONTENT_HASH_KEY,
    SOURCE_ID_KEY,
    CHUNK_ID_KEY,
    SOURCE_INDEX_IDENTITY_KEY,
    SOURCE_VERSION_KEY,
    SOURCE_ATTEMPT_KEY,
    SOURCE_CHUNK_COUNT_KEY,
    SOURCE_CHUNK_INDEX_KEY,
)

#: Metadata keys excluded from embedding text and LLM-visible text on every
#: ingest path — the declared embedding-text contract (spec capability
#: ``embedding-text-composition``, design D1). A key belongs here when its
#: value is machine identity, parser telemetry, or filesystem bookkeeping:
#: constant within a document and carrying no retrievable meaning. A key
#: carrying topical signal a query could plausibly match belongs in
#: ``_RETAINED_EMBED_METADATA_KEYS`` instead.
EXCLUDED_EMBED_METADATA_KEYS = (
    # Parser telemetry — diagnostics about how a file was parsed, constant
    # across every chunk of a document (``pdf_inspector`` emits the first
    # four; page/layout keys cover the other readers).
    "pdf_reader",
    "pdf_type",
    "pdf_confidence",
    "page_count",
    "page",
    "page_label",
    "column",
    "section_bbox",
    "bbox_schema_version",
    # Filesystem bookkeeping — machine-specific paths and timestamps that
    # differ between the machine that ingested and any other.
    "file_path",
    "file_type",
    "file_size",
    "creation_date",
    "last_modified_date",
    "last_accessed_date",
)

#: Metadata keys that MUST stay in embedding text (design D2). This
#: deliberately INVERTS the LlamaIndex default: ``SimpleDirectoryReader``
#: excludes ``file_name`` and keeps ``file_path`` as "extreme important
#: context". For this project that default is backwards — ``file_path`` is
#: a machine-specific absolute path that is constant within a document and
#: pure deployment noise between machines, while ``file_name`` carries
#: genuine topical signal ("Kalai et al. - 2025 - Why Language Models
#: Hallucinate.pdf" is useful query-matching text). ``stamp_source_lineage``
#: removes these keys from reader-set exclusion lists so the declared
#: contract wins over the upstream default. Do NOT "fix" this back to the
#: LlamaIndex behaviour. The same reasoning keeps structure and extraction
#: output — ``header_path``, ``category``, ``keywords``, ``summary``,
#: ``document_title``, ``content_type`` — embedded: each carries signal a
#: query could plausibly match. Exclusion removes nothing from stored
#: metadata or retrieval results; ``source`` still comes from ``file_path``.
_RETAINED_EMBED_METADATA_KEYS = (
    "file_name",
    "header_path",
    "category",
    "keywords",
    "summary",
    "document_title",
    "content_type",
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


class IncompatibleSourceLineageError(RuntimeError):
    """Rows for a source path predate stable lineage identity.

    Raised before any parse, embedding, or store mutation so the operator
    can rebuild the affected data instead of mixing schemas.
    """


def canonical_source_path(path: str | Path) -> str:
    """Return the canonical absolute source path used for identity.

    This is the single path rule shared by ingestion, deletion preview, and
    deletion so every consumer derives the same ``source_id`` for one file.
    """
    return str(Path(path).expanduser().resolve())


def build_source_id(canonical_file_path: str) -> str:
    """Return the deterministic logical identity for one canonical path.

    The identifier is stable while the source is edited in place and
    intentionally changes when the source moves or is copied to another
    path. The collection name is not part of the formula, so one source
    keeps its identity when indexed into multiple collections. Equal bytes
    at different paths keep different ``source_id`` values while sharing
    ``source_content_hash``.
    """
    digest = hashlib.sha256(f"file\0{canonical_file_path}".encode())
    return f"src_{digest.hexdigest()}"


def build_chunk_id(
    *,
    source_id: str,
    source_version: str,
    chunk_index: int,
    text: str,
) -> str:
    """Return the deterministic identity of one stored chunk.

    The zero-based ordinal distinguishes repeated identical text within one
    source version, and the text hash catches changed parser or chunker
    output at the same ordinal. The embedding payload is deliberately not
    hashed: extracted metadata may vary without changing the identity of
    the textual chunk, and embedding execution identity already belongs to
    ``source_index_identity`` and the replacement attempt.
    """
    text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    payload = f"{source_id}\0{source_version}\0{chunk_index}\0{text_hash}"
    return f"chk_{hashlib.sha256(payload.encode('utf-8')).hexdigest()}"


def build_source_row_id(source_id: str, source_attempt: str, chunk_id: str) -> str:
    """Return the attempt-specific vector-store row ID for one chunk.

    A forced re-ingestion of an identical version reproduces the same
    ``chunk_id`` values but writes distinct row IDs, so candidate and
    durable attempts coexist until replacement is verified. Stable chunk
    identity must never become the store primary key.
    """
    payload = f"{source_id}\0{source_attempt}\0{chunk_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assert_source_lineage_compatible(
    store: VectorStore,
    collection_name: str,
    *,
    file_path: str,
    source_id: str,
) -> None:
    """Fail before mutation when a source path carries pre-lineage rows.

    Compares rows selected by the canonical ``file_path`` with rows that
    also carry the derived ``source_id``. Any lack or disagreement means
    the collection mixes schemas; ingestion must stop and the operator
    rebuild the affected data. This is an incompatibility guard, not a
    migration path: existing rows are never inferred, upgraded, or
    deleted here.
    """
    if not store.collection_exists(collection_name):
        return
    path_where = {"file_path": file_path}
    path_count = store.count_where(collection_name, path_where)
    if path_count == 0:
        return
    lineage_where = {"$and": [path_where, {SOURCE_ID_KEY: source_id}]}
    lineage_count = store.count_where(collection_name, lineage_where)
    if lineage_count != path_count:
        raise IncompatibleSourceLineageError(
            f"Rows for '{file_path}' predate stable source lineage: "
            f"{path_count - lineage_count} row(s) lack or disagree on the "
            f"derived source_id. Rebuild the affected data by deleting the "
            f"source or collection and re-ingesting it; the existing rows "
            f"were left unchanged."
        )


def source_where(source_id: str) -> dict:
    """Return the store-neutral filter selecting one logical source."""
    return {SOURCE_ID_KEY: source_id}


def source_version_where(
    source_id: str,
    *,
    content_hash: str,
    index_identity: str,
    source_version: str,
) -> dict:
    """Return a filter selecting rows for one exact source version."""
    return {
        "$and": [
            {SOURCE_ID_KEY: source_id},
            {SOURCE_CONTENT_HASH_KEY: content_hash},
            {SOURCE_INDEX_IDENTITY_KEY: index_identity},
            {SOURCE_VERSION_KEY: source_version},
        ]
    }


def source_attempt_where(source_id: str, source_attempt: str) -> dict:
    """Return a filter selecting one replacement attempt for a source."""
    return {
        "$and": [
            {SOURCE_ID_KEY: source_id},
            {SOURCE_ATTEMPT_KEY: source_attempt},
        ]
    }


def stale_attempts_where(source_id: str, source_attempt: str) -> dict:
    """Return a filter selecting prior attempts when backend semantics permit."""
    return {
        "$and": [
            {SOURCE_ID_KEY: source_id},
            {SOURCE_ATTEMPT_KEY: {"$ne": source_attempt}},
        ]
    }


def is_complete_current_version(
    store: VectorStore,
    collection_name: str,
    *,
    source_id: str,
    content_hash: str,
    index_identity: str,
    source_version: str,
) -> tuple[bool, int]:
    """Return whether the store contains one complete matching source version."""
    if not store.collection_exists(collection_name):
        return False, 0
    total = store.count_where(collection_name, source_where(source_id))
    if total <= 0:
        return False, 0

    version_filter = source_version_where(
        source_id,
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


def stamp_source_lineage(
    nodes: list[BaseNode],
    *,
    file_path: str,
    source_id: str,
    content_hash: str,
    index_identity: str,
    source_version: str,
    source_attempt: str,
) -> None:
    """Stamp stable lineage and one replacement attempt on candidate nodes.

    Every node receives its stable ``chunk_id`` derived from the text-only
    content, the shared source/version/attempt metadata, a zero-based
    ordinal, and an attempt-specific row ID. The LlamaIndex ``SOURCE``
    relationship is set to the stable ``source_id`` so source membership
    survives replacement attempts, while ``file_path`` stays ordinary
    human-readable metadata. Every machine identity and replacement key,
    plus the declared embedding-text exclusion set
    (``EXCLUDED_EMBED_METADATA_KEYS``), is added to both metadata exclusion
    lists so identifiers, parser telemetry, and filesystem bookkeeping never
    enter embedding vectors or LLM-visible content. Keys the reader already
    excluded stay excluded (set union) — except the retained keys of design
    D2, which are removed from reader-set exclusion lists so the declared
    contract, not the LlamaIndex default, decides what is embedded.
    """
    chunk_count = len(nodes)
    excluded = set(_SOURCE_METADATA_KEYS) | set(EXCLUDED_EMBED_METADATA_KEYS)
    retained = set(_RETAINED_EMBED_METADATA_KEYS)
    for index, node in enumerate(nodes):
        chunk_id = build_chunk_id(
            source_id=source_id,
            source_version=source_version,
            chunk_index=index,
            text=node.get_content(metadata_mode=MetadataMode.NONE),
        )
        node.metadata.update(
            {
                "file_path": file_path,
                SOURCE_ID_KEY: source_id,
                CHUNK_ID_KEY: chunk_id,
                SOURCE_CONTENT_HASH_KEY: content_hash,
                SOURCE_INDEX_IDENTITY_KEY: index_identity,
                SOURCE_VERSION_KEY: source_version,
                SOURCE_ATTEMPT_KEY: source_attempt,
                SOURCE_CHUNK_COUNT_KEY: chunk_count,
                SOURCE_CHUNK_INDEX_KEY: index,
            }
        )
        node.excluded_embed_metadata_keys = sorted(
            (set(node.excluded_embed_metadata_keys) | excluded) - retained
        )
        node.excluded_llm_metadata_keys = sorted(
            (set(node.excluded_llm_metadata_keys) | excluded) - retained
        )
        node.relationships[NodeRelationship.SOURCE] = RelatedNodeInfo(node_id=source_id)
        node.id_ = build_source_row_id(source_id, source_attempt, chunk_id)
