"""Backward-compatible re-export shim for the ingestion pipeline subpackage.

.. deprecated::
    Import from ``rag_mcp.core.ingestion`` instead.  This shim will be
    removed in v2.0.0 after all five refactor phases land.

The original monolithic ``ingestion.py`` (991 lines) was split into
``rag_mcp.core.ingestion`` and ``rag_mcp.core.chunking`` submodules as
part of Phase 1.  This file re-exports every public and private name so
existing imports continue to resolve.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "rag_mcp.ingestion is deprecated; "
    "import from rag_mcp.core.ingestion instead. "
    "Removal in v2.0.0.",
    DeprecationWarning,
    stacklevel=2,
)

# ── Config variables (re-exported for backward compatibility) ───────────
from .config import (  # noqa: F401
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    CHROMA_PERSIST_DIR,
    COLLECTION_NAME,
    EMBED_BATCH_SIZE,
    EMBED_CONCURRENCY,
    MAGIKA_LABEL_TO_TREESITTER,
    MARKDOWN_CHUNK_SIZE,
    MARKDOWN_HEADING_PREPEND,
    MARKDOWN_MIN_CHUNK_FRACTION,
    SUPPORTED_EXTENSIONS,
)
# ``Settings`` is re-exported from ``llama_index.core`` (not
# ``rag_mcp.config``) to preserve the legacy meaning: pre-refactor code used
# ``Settings`` as the LlamaIndex global (``Settings.embed_model``), whereas
# ``rag_mcp.config.Settings`` is the new pydantic resolver model (ADR-031).
from llama_index.core import Settings  # noqa: F401
from .chroma_utils import iter_collection_metadatas  # noqa: F401

# ── Thread-safety primitives (old names with underscore prefix) ─────────
from .core.ingestion._state import (  # noqa: F401
    collection_generations as _collection_generations,
    embed_semaphore as _embed_semaphore,
    get_collection_generation,
    shutdown_requested as _shutdown_requested,
    write_lock as _write_lock,
)
from .core.ingestion._state import (  # noqa: F401
    bump_collection_generation as _bump_collection_generation,
)

# ── Chunking helpers (old names with underscore prefix) ─────────────────
from .core.chunking.code import chunk_code_file_async as _chunk_code_file_async  # noqa: F401
from .core.chunking.config_file import chunk_config_file as _chunk_config_file  # noqa: F401
from .core.chunking.markdown import (  # noqa: F401
    apply_heading_prepend as _apply_heading_prepend,
    drop_small_markdown_chunks as _drop_small_markdown_chunks,
    ensure_heading_metadata as _ensure_heading_metadata,
)

# ── Loader (old names with underscore prefix) ───────────────────────────
from .core.ingestion.loader import (  # noqa: F401
    gather_supported_files as _gather_supported_files,
    get_chroma_collection as _get_chroma_collection,
    list_documents,
    make_file_detail as _make_file_detail,
)

# ── Chunker dispatch (old names with underscore prefix) ─────────────────
from .core.ingestion.chunker import (  # noqa: F401
    read_and_chunk_file_async,
)
from .core.ingestion.chunker import (  # noqa: F401
    read_and_chunk_file_async as _read_and_chunk_file_async,
)

# ── Writer (old names with underscore prefix) ───────────────────────────
from .core.ingestion.writer import (  # noqa: F401
    embed_and_write_async as _embed_and_write_async,
    preview_delete,
    remove_by_metadata,
    remove_collection,
    remove_document,
)
from .core.ingestion.writer import _count_chunks  # noqa: F401

# ── Pipeline orchestrator ───────────────────────────────────────────────
from .core.ingestion.pipeline import ingest_path_async  # noqa: F401

# ── Logger (for tests that patch rag_mcp.ingestion.logger) ──────────────
import logging  # noqa: E402

logger = logging.getLogger(__name__)  # noqa: F401
