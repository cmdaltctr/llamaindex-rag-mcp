# Configuration

Where settings live, which one wins, and what every setting does.

---

## The short version

Settings come from five places. Each beats the one above it:

| # | Source | What belongs here |
|---|---|---|
| 1 | Model defaults, in the code | Last resort. You never edit these directly. |
| 2 | `src/rag_mcp/config/defaults.yaml` | Project-wide defaults. Committed. Shared by everyone. |
| 3 | Profile YAML (`config/profiles/*.yaml`) | Per-collection behaviour |
| 4 | `.env` | Your machine: tokens, URLs, paths |
| 5 | Environment variables | Highest. Wins over everything. |

**Rule of thumb:**

- Sensible default for everyone → `defaults.yaml`
- Secret, or specific to your machine → `.env`
- Different for one collection → its profile
- Just for this one command → an environment variable

### The trap worth knowing

`.env` sits **above** profiles. Put a tuning value there and it overrides every
profile silently.

Real example: `RETRIEVAL__TOP_K=5` in `.env` meant the `documents` profile
(top_k 10) and the `codebase` profile (top_k 20) both returned 5 results.
Profiles looked broken. Nothing warned about it.

**Keep `.env` for connection details and secrets only.**

---

## Variable naming

Settings that belong to one area are nested. The environment variable joins the
block and the field with a double underscore:

```
retrieval.top_k             →  RETRIEVAL__TOP_K
chunking.chunk_size         →  CHUNKING__CHUNK_SIZE
ingestion.embed_batch_size  →  INGESTION__EMBED_BATCH_SIZE
metadata.extraction_mode    →  METADATA__EXTRACTION_MODE
```

Cross-cutting settings stay flat: `EMBED_MODEL`, `CHROMA_PERSIST_DIR`,
`RAG_PROFILE`, `PDF_READER`, and every credential.

In YAML the same thing looks like this:

```yaml
retrieval:
  top_k: 10
  rerank_enabled: false

chunking:
  chunk_size: 512

# cross-cutting settings stay at the top level
EMBED_MODEL: qwen3-embedding:0.6b
```

### Upgrading from v1

Pre-v2 flat names (`TOP_K`, `CHUNK_SIZE`, `METADATA_EXTRACTION_MODE`, …) are no
longer read. The app **refuses to start** and names the replacement, rather
than silently falling back to a default.

Two guards catch mistakes:

- A wrong nested key (`RETRIEVAL__TOPK`) fails immediately, listing the valid
  fields.
- An old flat name (`TOP_K`) fails with the new name.

Full rename table: [ADR-037](../adr/037-architecture-v2-conformance.md).

---

## Profiles

A profile is a named bundle of retrieval behaviour, bound to a collection.

| Profile | For | top_k | Reranker | Hybrid search |
|---|---|---|---|---|
| `documents` | Papers, reports, prose | 10 | on | off |
| `codebase` | Source code | 20 | off | on |
| `hybrid` | Not a profile — a mode selector | — | — | — |

**Profiles only control five things:**

- `retrieval.top_k`
- `retrieval.rerank_enabled`
- `retrieval.hybrid_enabled`
- `chunking.strategy_fallback`
- `metadata.taxonomy_mode`

Everything else — chunk size, storage path, embedding model — is shared.

### Choosing a profile

Server-wide default:

```bash
RAG_PROFILE=documents
```

Per collection, which is the point of the feature:

```bash
rag-mcp set-profile -c my_code -p codebase
```

Set `RAG_PROFILE=hybrid` to let each collection pick its own; untagged
collections fall back to `default_profile` in `hybrid.yaml`.

A collection cannot be tagged `hybrid` — it selects a mode, it is not one.

### Why the reranker differs

The `documents` profile turns the reranker on; `codebase` leaves it off. That
is not an oversight. Experiment 10 measured the reranker making code retrieval
**19–27% worse** and adding ~14s per query. On prose it helps. See
[ADR-019](../adr/019-reranker-disabled-for-technical-workloads.md) and
[ADR-030](../adr/030-prefer-int8-onnx-variant-for-modernbert-rerankers.md).

---

## What goes in `.env`

Only these:

```bash
# Where the vector database lives
CHROMA_PERSIST_DIR=./chroma_db
COLLECTION_NAME=documents

# Which embedding model, and where to reach it
EMBED_MODEL=qwen3-embedding:0.6b
OLLAMA_BASE_URL=http://localhost:11434

# Secrets
HF_TOKEN=...
OPENROUTER_API_KEY=...
AZURE_DOC_INTELLIGENCE_KEY=...
```

If you find yourself putting `RETRIEVAL__*` or `CHUNKING__*` in here, it
probably belongs in `defaults.yaml` or a profile instead.

---

## All settings

Defaults below are what ships in `defaults.yaml`.

### Storage

| Variable | Default | What it does |
|---|---|---|
| `CHROMA_PERSIST_DIR` | `./chroma_db` | Where the database is written |
| `COLLECTION_NAME` | `documents` | Default collection |
| `CHROMA_SCAN_PAGE_SIZE` | `10000` | Rows per page when scanning metadata |
| `VECTOR_STORE` | `chroma` | Which store implementation |

### Providers

| Variable | Default | What it does |
|---|---|---|
| `EMBED_PROVIDER` | `local` | `local`, `cloud`, `ollama`, `llamacpp`, or `openrouter` |
| `METADATA_LLM_PROVIDER` | `local` | `local` or `cloud`, independent of the above |
| `LOCAL_BACKEND` | `llamacpp` | `llamacpp` or `ollama` |
| `CLOUD_BACKEND` | `openrouter` | `openrouter` |
| `EMBED_MODEL` | — | Model name for embeddings |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama endpoint |

An unrecognised value for any of the four provider selections above
(`EMBED_PROVIDER`, `METADATA_LLM_PROVIDER`, `LOCAL_BACKEND`,
`CLOUD_BACKEND`), plus `RETRIEVAL__HYBRID_SPARSE_BACKEND` and
`DOCUMENT_BACKEND`, fails startup with a clear error naming the value
and the accepted set.  Leading and trailing whitespace is stripped
before validation, so `EMBED_PROVIDER=" local "` resolves to `local`.
An empty or whitespace-only value (`SETTING=` in `.env`) is treated
as unset and resets to the default.

Optional dependencies:

```bash
uv sync --extra llamacpp     # llama.cpp backend
uv sync --extra openrouter   # OpenRouter backend
```

Connection details for each: [Providers](providers.md).

### Chunking — `CHUNKING__*`

| Field | Default | What it does |
|---|---|---|
| `chunk_size` | `512` | Target chunk size for most files |
| `chunk_overlap` | `100` | Overlap between chunks. Calibrated ([ADR-018](../adr/018-balanced-retrieval-defaults.md)) — do not change casually |
| `markdown_chunk_size` | `1024` | Larger, because Markdown splits on headings |
| `markdown_heading_prepend` | `false` | Prepend the heading path to each chunk |
| `markdown_min_chunk_fraction` | `0.0` | Drop chunks below this fraction of the target |
| `strategy_fallback` | `markdown` | Strategy for file types we cannot identify. **Profile-owned** |

Known file types always use content-type dispatch — a `.py` file gets the code
splitter regardless of the fallback.

### Ingestion — `INGESTION__*`

| Field | Default | What it does |
|---|---|---|
| `embed_concurrency` | `4` | Parallel embedding requests. Machine-specific — lower it if the backend throttles |
| `embed_batch_size` | `100` | Documents per embedding call |

### Retrieval — `RETRIEVAL__*`

| Field | Default | What it does |
|---|---|---|
| `top_k` | `10` | Results returned. **Profile-owned** |
| `similarity_threshold` | `0.0` | Minimum score to keep a result |
| `rerank_enabled` | `false` | Cross-encoder reranking. **Profile-owned** |
| `rerank_enabled_for_semantic` | `true` | Allow reranking on prose-like queries |
| `hard_technical_threshold` | `0.3` | Above this "technical" score, skip reranking |
| `rerank_fetch_multiplier` | `3` | Fetch `top_k × 3` candidates before reranking |
| `rerank_max_fetch` | `100` | Cap on that candidate pool |
| `rerank_model` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Reranker model |
| `rerank_backend` | `onnx` | Reranker inference backend (`onnx` or `torch`). `torch` requires `uv sync --extra torch`. See [ADR-038](../adr/038-pluggable-reranker-backend.md) |
| `hybrid_enabled` | `false` | Combine keyword and embedding search. **Profile-owned** |
| `hybrid_rrf_k` | `60` | Rank-fusion constant ([ADR-017](../adr/017-hybrid-retrieval-rrf.md)) |
| `hybrid_sparse_backend` | `bm25` | `bm25`, `native`, or `auto`. Unrecognised values fail startup |

### Metadata — `METADATA__*`

| Field | Default | What it does |
|---|---|---|
| `extraction_mode` | `llamaindex` | `disabled`, `keyword`, `local`, or `llamaindex` |
| `keyword_rules` | — | JSON array of custom `{pattern, category}` rules |
| `taxonomy_mode` | `category` | `category` or `file_type`. **Profile-owned** |
| `ollama_classify_model` | `qwen3:0.6b` | Ollama model used for classification |
| `classify_max_attempts` | `3` | Maximum attempts **including** the initial request (all metadata LLM backends) |
| `classify_timeout` | `30.0` | Seconds per attempt (all metadata LLM backends) |
| `pipeline_timeout` | `180.0` | Seconds for the llamaindex pipeline (one attempt, three extractors per chunk) |
| `llamacpp_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `llamacpp`. Falls back to the shared value when unset |
| `ollama_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `ollama`. Falls back to the shared value when unset |
| `openrouter_classify_timeout_override` | `None` | Per-provider override of `classify_timeout` for `openrouter`. Falls back to the shared value when unset |
| `llamacpp_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `llamacpp`. Falls back to the shared value when unset |
| `ollama_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `ollama`. Falls back to the shared value when unset |
| `openrouter_pipeline_timeout_override` | `None` | Per-provider override of `pipeline_timeout` for `openrouter`. Falls back to the shared value when unset |

Set `extraction_mode=disabled` to skip classification entirely — much faster
ingestion, no categories. Details: [Metadata extraction](metadata-extraction.md),
including the six per-provider timeout overrides above and how
degradation from the configured mode is reported in the ingestion result.

### PDF reading

| Variable | Default | What it does |
|---|---|---|
| `PDF_READER` | `auto` | `auto`, `pypdf`, `pypdfium2`, or `liteparse` |
| `LITEPARSE_OCR_ENABLED` | `false` | OCR for scanned PDFs |
| `LITEPARSE_NUM_WORKERS` | — | Parallel workers |

`auto` uses LiteParse if installed, otherwise pypdf. Tests pin `pypdf` for
determinism.

### Document backend

| Variable | Default | What it does |
|---|---|---|
| `DOCUMENT_BACKEND` | `local` | `local` or `azure`. Unrecognised values fail startup |
| `AZURE_DOC_INTELLIGENCE_ENDPOINT` | — | Azure endpoint URL |
| `AZURE_DOC_INTELLIGENCE_KEY` | — | Azure key |
| `AZURE_DOC_INTELLIGENCE_MODEL` | `prebuilt-layout` | Azure model |

Azure is opt-in and degrades to local parsing if credentials are missing
or unreachable ([ADR-024](../adr/024-dual-deployment-modes.md)).  An
unrecognised `DOCUMENT_BACKEND` value (not `local` or `azure`) fails
startup rather than silently falling back.

### Codebase map

| Variable | Default | What it does |
|---|---|---|
| `MAGIKA_BINARY` | `magika` | File-type detection binary |
| `CODEBASE_MAP_CACHE_DIR` | `.opencode` | Cache location |
| `CODEBASE_MAP_MAX_FILES` | `5000` | File limit |
| `CODEBASE_MAP_MAX_DEPTH` | `10` | Directory depth limit |
| `DOC_SIMILARITY_THRESHOLD` | `0.85` | Similarity edge cutoff. Not yet calibrated |

The cache key is the git commit hash. Not a git repository means no caching —
the map rebuilds every call.

### Community detection

Both graph subsystems, the codebase graph and the document similarity graph,
use the same configured strategy and seed.

| Variable | Default | What it does |
|---|---|---|
| `COMMUNITY_ALGORITHM` | `louvain` | `louvain` or `leiden`. Unknown names fail startup and list the available strategies |
| `COMMUNITY_SEED` | `0` | Seed for algorithm randomness. `0` keeps partitions deterministic |

`COMMUNITY_ALGORITHM` and `COMMUNITY_SEED` are cross-cutting, so their
environment variable names are flat. An empty value
(`COMMUNITY_ALGORITHM=`) resets to `louvain`.

There is no `auto`. Whether an optional package is installed must not change
graph output silently, so the algorithm is always explicit.

**Leiden.** `leiden` requires the optional `community-leiden` extra:

```bash
uv sync --extra community-leiden
```

Setting `COMMUNITY_ALGORITHM=leiden` without the extra fails startup with the
installation instruction above. There is no silent fallback to `louvain`: an
explicit algorithm selection is an operator contract. See
[ADR-043](../adr/043-pluggable-community-detection.md).

---

## How settings reach the code

Worth understanding if you are changing anything.

`config/` works out the values and produces a `Settings` object. It builds
nothing else.

`compose.py` takes those settings and constructs the real objects — embedder,
vector store, reranker. It is the only place that calls `get_settings()`.

Core operations receive a frozen `EffectiveSettings` as an argument. There is
no global to read and nothing to patch. Two searches running at once each hold
their own settings.

For tests, this means injecting rather than patching:

```python
def test_something(effective_settings):
    settings = effective_settings(top_k=20)
    results = search("query", effective_settings=settings)
```

More in [Architecture](architecture.md) and
[ADR-031](../adr/031-three-layer-config-compose-di.md).

---

## Adding a setting

**Belongs to one area** (chunking, ingestion, retrieval, metadata):

1. Add the field to that area's `settings.py`
2. Add it to `defaults.yaml` under the matching block

**Cross-cutting:**

1. Add the field to `Settings` in `config/__init__.py`
2. Add it to `defaults.yaml` at the top level

A test checks `defaults.yaml` agrees with the model defaults, so the two cannot
drift apart. If they disagree, that test tells you.
