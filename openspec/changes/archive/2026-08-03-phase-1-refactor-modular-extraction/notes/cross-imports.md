# Phase 1 Cross-Import Findings (task 1.3)

Per design D4: surface hidden cross-imports, never merge. Each finding is
preserved as-is (lazy imports stay lazy, just repointed to the new
`rag_mcp.core.*` path) and recorded for Phase 2 follow-up.

## Finding 1 — `sparse_retriever` → `ingestion` (retrieval↔ingestion leak)

`src/rag_mcp/sparse_retriever.py:169` (inside `BM25SparseRetriever`):

```python
from .ingestion import get_collection_generation
```

After refactor this becomes a lazy import from
`rag_mcp.core.ingestion` inside `core/retrieval/sparse.py`. This is a
**violation of AGENTS.md invariant #2** (no cross-imports between
`ingestion` and `retrieval`). It is a pre-existing leak, not introduced
by Phase 1. Preserved as lazy import; recorded for Phase 2 (the
`get_collection_generation` helper likely belongs in a shared
`chroma_utils` or a `core/ingestion` public surface consumed by both
sides).

## Finding 2 — `ingestion` → `metadata_extractor` (ingestion→metadata dep)

`src/rag_mcp/ingestion.py:418` (inside `_read_and_chunk_file_async`):

```python
from .metadata_extractor import extract_metadata_async
```

After refactor: `core/ingestion/loader.py` lazily imports
`extract_metadata_async` from `rag_mcp.core.metadata`. Not forbidden by
invariant #2 (which scopes to ingestion↔retrieval only), but it is a
cross-subpackage dependency to preserve verbatim.

## Finding 3 — `config` → `sparse_retriever` (config→retrieval leak)

`src/rag_mcp/config.py:383` (inside a function):

```python
from .sparse_retriever import _detect_native_sparse_capability
```

After refactor: lazily imports from `rag_mcp.core.retrieval.sparse`.
This is a **pre-existing violation of the spirit of invariant #1**
(`config.py` is the single source of truth and must not depend on
ingestion/retrieval). Preserved as lazy import; recorded for Phase 2
(the capability probe likely belongs in `chroma_utils` or a dedicated
probe module).

## Finding 4 — `retrieval` → `reranker` / `sparse_retriever` (intra-retrieval)

`src/rag_mcp/retrieval.py:21` and `:301`:

```python
from .reranker import CrossEncoderReranker
from .sparse_retriever import BM25SparseRetriever
```

These are intra-retrieval dependencies. After refactor they become
intra-`core/retrieval/` imports — no boundary concern.

## Finding 5 — Tests import private (`_`-prefixed) names

The compat shims cannot rely on `from ... import *` alone because
underscore-prefixed names are not exported by `*`. Each shim MUST
explicitly re-export the private names tests (and `cli.py`/`server.py`)
reach for. Inventories captured during extraction per subpackage:

- `metadata_extractor`: `_normalise_category`, `_get_seed_categories`,
  `_aggregate_llamaindex_metadata`, `_strip_llm_prefix`,
  `_load_keyword_rules`, `_DEFAULT_KEYWORD_RULES`, `_extract_keyword`,
  `_extract_llamacpp_chat_async`, `extract_metadata_async`, plus
  module-level constants.
- `ingestion`: `_shutdown_requested`, `_make_file_detail`,
  `_collection_generations`, `_read_and_chunk_file_async`,
  `_chunk_code_file_async`, `_chunk_config_file`, `_embed_and_write_async`,
  `_gather_supported_files`, `_write_lock`, `_embed_semaphore`,
  `_apply_heading_prepend`, `_drop_small_markdown_chunks`,
  `_ensure_heading_metadata`, `read_and_chunk_file_async`,
  `ingest_path_async`, `list_documents`, `preview_delete`,
  `remove_document`, `remove_by_metadata`, `remove_collection`,
  `get_collection_generation`.
- `retrieval`: `_effective_threshold`, `_distance_to_score`,
  `_resolve_fetch_k`, `_classify_query_technical`, `_resolve_rerank_policy`,
  `search`, `list_collections`, `reciprocal_rank_fusion`,
  `rrf_with_metadata`.
- `sparse_retriever`: `tokenize_english`, `BM25SparseRetriever`,
  `_detect_native_sparse_capability`.
- `reranker`: `CrossEncoderReranker`, `TOKENIZER_MAX_LENGTH`,
  `_select_onnx_variant`, `_sigmoid`.

Strategy: each shim does `from rag_mcp.core.<sub>.<mod> import *  # noqa`
plus an explicit `from rag_mcp.core.<sub>.<mod> import (<private names>)`
block, then re-asserts `__all__` is the union. This keeps the old paths
resolving to the same objects while emitting `DeprecationWarning`.
