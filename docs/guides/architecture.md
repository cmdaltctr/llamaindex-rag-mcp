# How this project is put together

This is the map. If you are trying to work out where something lives, or why a
change you made had no effect, start here.

For *why* a particular technology was chosen, see [Technology choices](#technology-choices)
at the end. For the full reasoning behind any of it, see [`docs/adr/`](../adr/).

The principle that shapes everything: **it runs on your machine**. Cloud
providers are opt-in, never required, and everything degrades back to local if
they are missing.

---

## The one-paragraph version

There is a **core** that does the actual work — reading files, chunking,
embedding, searching. There are **transports** that expose that work to the
outside world: an MCP server and a CLI. There is a **composition root** that
builds all the objects and hands them to the core. And there is **config**,
which works out what the settings are.

The rule that makes it hold together: **core never reaches out**. It does not
read global settings, does not build its own database connection, does not know
a CLI exists. Everything it needs arrives as a function argument.

---

## The four layers

```
transports/          MCP server, CLI. Thin. No business logic.
    │                Calls into core, formats the answer.
    ▼
compose.py           Builds everything: embedder, vector store, reranker,
    │                profile resolver. The ONLY place objects are constructed.
    ▼
core/                The actual work. Receives what it needs as arguments.
    │                Never imports transports. Never reads a global.
    ▼
config/              Works out what the settings are. Reads nothing else.
                     Builds nothing.
```

Two supporting folders sit off to the side:

- `integrations/` — wrappers around outside tools: Azure Document
  Intelligence, Magika, the PDF readers. Leaf modules.
- `daemon/` — the file watcher, a long-running process rather than a
  request/response transport.

These boundaries are not a convention you have to remember. `uv run lint-imports`
checks them, and the build fails if you cross one.

---

## Settings: the part that confuses everyone

Settings can come from five places. Each beats the one above it:

```
1. Model defaults          in the code, last resort
2. defaults.yaml           project-wide, committed, shared by everyone
3. profile YAML            per collection (documents / codebase)
4. .env                    your machine, your secrets
5. environment variables   highest priority, wins over everything
```

### Which one should you use?

| You want to change | Put it in |
|---|---|
| A sensible default for everyone | `defaults.yaml` |
| A token, a URL, a path on your machine | `.env` |
| How *one collection* behaves | its profile YAML |
| Something for a single command | an environment variable |

**The trap.** `.env` beats profiles. Put `RETRIEVAL__TOP_K=5` in `.env` and
every profile returns 5 results regardless of what its YAML says. Profiles stop
working and nothing warns you. Keep tuning out of `.env`.

### The five levers profiles own

Profiles do not set everything. They set five things and inherit the rest:

- `retrieval.top_k`
- `retrieval.rerank_enabled`
- `retrieval.hybrid_enabled`
- `chunking.strategy_fallback`
- `metadata.taxonomy_mode`

Anything else — chunk size, storage path, which embedding model — is shared
across all profiles.

### Variable names

Settings that belong to one area are nested. The environment variable uses a
double underscore:

```
retrieval.top_k             →  RETRIEVAL__TOP_K
chunking.chunk_size         →  CHUNKING__CHUNK_SIZE
ingestion.embed_batch_size  →  INGESTION__EMBED_BATCH_SIZE
metadata.extraction_mode    →  METADATA__EXTRACTION_MODE
```

Cross-cutting settings stay flat: `EMBED_MODEL`, `CHROMA_PERSIST_DIR`,
`VECTOR_STORE`, `LANCEDB_URI`, `RAG_PROFILE`, `PDF_READER`, and all
credentials.

Use a pre-v2 name like `TOP_K` and the app refuses to start, telling you the
replacement. It does not quietly ignore you. Full table in
[ADR-037](../adr/037-architecture-v2-conformance.md).

---

## What each piece actually does

### `config/` — works out the settings

Reads the five sources above and produces one `Settings` object holding the
final answers.

That is all it does. It builds no objects, opens no connections, calls no
models. It is a leaf: it must not import business logic from `core/`.

This matters more than it sounds. "Is LiteParse installed?" is not a setting —
it is a question about the world. Those checks live in `compose.py`. Keeping
them in config is what made config depend on retrieval, which inverted the
whole dependency direction.

- `config/__init__.py` — the `Settings` model and the resolver
- `config/sources.py` — reads `defaults.yaml` and the profile bundles
- `config/legacy.py` — catches pre-v2 names and explains the rename

### `compose.py` — builds the objects

Takes the settings and constructs the real things: the embedding model, the
vector store, the reranker, the profile resolver.

It is the only place allowed to do this, and the only place that calls
`get_settings()`. Everything else is handed what it needs.

Why one place: before the v2 work, objects were built in a dozen scattered
spots, all reading one shared global. That is how you end up unable to run two
configurations at once.

### `core/` — does the work

| Folder | Job |
|---|---|
| `core/ingestion/` | Read files, chunk them, write to the store |
| `core/retrieval/` | Search, rerank, fuse results |
| `core/chunking/` | The chunking strategies: code, markdown, sentence, config |
| `core/metadata/` | Work out a category and keywords for a document |
| `core/vectordb/` | The database interface, LanceDB default implementation, and optional Chroma implementation |
| `core/profiles/` | Resolve which profile a collection uses |
| `core/providers/` | Build embedding and LLM clients |
| `core/codebase/` | Codebase map and code graph |
| `core/documents/` | Document similarity graph |
| `core/community/` | Community-detection strategies for both graphs (Louvain default, Leiden optional) |
| `core/settings.py` | `EffectiveSettings` — the frozen settings object passed around |

`core/ingestion/` and `core/retrieval/` do not import each other. They share
only settings.

### `core/vectordb/` — the store boundary

Two stores sit behind the `VectorStore` ABC (ADR-034): `lancedb`, the
base-install default, and `chroma`, an explicit optional extra selected with
`VECTOR_STORE` (ADR-049).

`core/vectordb/chroma.py` is the single module that imports `chromadb` and
the single construction site for both deployments. Local mode builds a
`PersistentClient` over the resolved persist directory; cloud mode builds
and validates a `CloudClient`, with a heartbeat round trip so
authentication, network, and tenant/database mistakes surface at startup.
Following upstream LlamaIndex's client-construction/VectorStore split, the
constructed client is injected into `ChromaVectorStore`, which stays
deployment-agnostic.

`core/vectordb/lancedb.py` is the LanceDB implementation (ADR-046): one
`lancedb.connect(uri)` connection backs the store, and each RAG collection
maps to one LanceDB table. Table creation is lazy — the vector dimension
locks on first write — and the LlamaIndex adapter is constructed with
`mode="create"` so it can never overwrite a populated table (the adapter's
default mode is `"overwrite"`). The adapter prints to stdout when it
creates a table, so writes run with stdout redirected: stdout is the MCP
protocol channel.

Collection metadata records the embedding configuration that owns the
vector space: `rag_embed_provider`, `rag_embed_model`, and
`rag_index_identity`. Vector dimensions alone cannot prove compatibility,
so a same-dimension model swap is rejected before any write or query.
Stamping is read-merge-write: Chroma's `modify(metadata=...)` replaces the
complete map, so existing profile tags are read and merged first. The
LanceDB store keeps the same triple in each table's durable Arrow schema
metadata, merged through pylance's `update_schema_metadata`.

Supporting modules keep each store under the 500-line ceiling:

- `core/vectordb/identity.py` — the `EmbeddingIdentity` type and the
  `IdentityGuardMixin` (stamping plus write/query-path mismatch rejection)
- `core/vectordb/paged.py` — the `PagedReadMixin` (bounded and bulk
  collection reads, formerly `chroma_utils.py`)
- `core/vectordb/naming.py` — deterministic experiment collection names
  (e.g. `exp14-qasper-openrouter-qwen3-8b-liteparse-cs512-co100`)
- `core/vectordb/lance_meta.py` — the LanceDB table-metadata seam and its
  identity guard, reusing `identity.py`'s pure helpers, plus the metadata
  struct evolution that grows a table's Arrow struct when later writes
  introduce new metadata keys
- `core/vectordb/lance_filter.py` — ChromaDB `where` dict → LanceDB filter
  translation through the `lancedb.expr` value serialiser; operators are
  null-aware and schema-absent fields fold to constants, preserving
  ChromaDB missing-field semantics across backends
- `core/vectordb/lance_paged.py` — the LanceDB paged-read mixin (scanner
  pages plus `strip_internal_metadata`)
- `core/vectordb/registry.py` — lazy vector-store registry mapping
  `VECTOR_STORE` names to factories (`chroma`, `lancedb`)

`compose.build_vector_store` resolves the configured name through the
registry instead of branching over it. Each factory receives the resolved
settings; the Chroma factory consumes mode, persist directory, API key,
tenant, and database, and the LanceDB factory consumes the `LANCEDB_URI`
parent directory. Each registry entry declares its availability metadata:
required packages, optional extra, installation guidance, sparse capability,
and storage-summary resolver. An unregistered `VECTOR_STORE` name fails
startup listing the registered names. Credentials never enter
`EffectiveSettings`, profiles, YAML defaults, or operation-level objects.

`get_default_store()` returns only the instance installed by
`compose.ensure_runtime_setup`. Before composition it raises a controlled
error. It never imports settings or constructs a fallback store.

One writer per collection is an explicit boundary. The BM25 invalidation
counters are process-local, so evaluation workers reuse completed immutable
indexes read-only; mutating the same collection from several processes is
unsupported.

### `transports/` — exposes it

- `transports/mcp.py` — the MCP server, seven tools, over stdio
- `transports/cli/` — the `rag-mcp` command, one file per command group
- `transports/api/` — an OpenAPI contract for a future REST API. No code yet,
  deliberately: the contract is published before anything implements it.

Transports hold no business logic. They resolve a profile, call core, format
the answer.

---

## How a search actually flows

```
MCP client asks for a search
      │
      ▼
transports/mcp.py        works out which profile this collection uses
      │                  → EffectiveSettings (frozen)
      ▼
core/retrieval/pipeline  resolves settings ONCE here, at the boundary.
      │                  Everything below gets them as an argument.
      ├─→ dense.py       embedding search
      ├─→ sparse.py      BM25 keyword search (if hybrid is on)
      ├─→ fusion.py      merge the two rankings
      ├─→ policy.py      decide whether to rerank
      └─→ reranker.py    re-score with the cross-encoder
      │
      ▼
results back to the client
```

The settings object is frozen. Two searches running at once each hold their own
copy; neither can affect the other. That is the whole point of passing it as an
argument instead of reading a global.

---

## Adding things

### A new chunking strategy

1. Write `core/chunking/mystrategy.py`
2. Add one line to `core/chunking/registry.py`:

```python
register("mystrategy", "rag_mcp.core.chunking.mystrategy:chunk_my_file_async")
```

That is the whole job. No other file changes. Same pattern for metadata
backends and retrieval stages.

This is enforced, not just encouraged. One test fails if a dispatch module
imports a strategy directly; another fails if it branches on strategy names.

### Community strategies

Community detection follows the same pattern, with one addition: the
strategies live in `core/community/`, and both graph consumers (the codebase
code graph and the document similarity graph) dispatch through
`partition_graph` with an injected seed.

The shared contract is flat: `list[set[Hashable]]`, every node in exactly one
non-empty community. Algorithm-specific objects (igraph partitions, leidenalg
results) never cross the boundary. Graphs with fewer than five nodes bypass
partitioning entirely. No LLM is called anywhere in the pipeline, and the
default seed of `0` keeps partitions deterministic run to run.

### A new vector database

Implement `VectorStore` from `core/vectordb/base.py`, add one `register()`
line to `core/vectordb/registry.py`, and let `compose.build_vector_store`
resolve it by name — never a branch over the name (invariant #10).
ChromaDB is confined to `core/vectordb/chroma.py`; LanceDB is confined to
`core/vectordb/lancedb.py` and the filter translator
`core/vectordb/lance_filter.py`. Contracts fail the build if either
library is imported anywhere else.

### A new setting

- Belongs to one area? Add it to that area's `settings.py`
  (`core/retrieval/settings.py`, and so on), then to `defaults.yaml` under the
  matching block.
- Cross-cutting? Add it to `Settings` in `config/__init__.py` and to
  `defaults.yaml` at the top level.

A test checks the two agree, so they cannot drift apart.

---

## Registry eligibility and audit inventory

A module goes into a registry when configuration selects by name among two or
more interchangeable implementations that share one contract. That is the
whole rule. A single capability adapter does not need a registry just because
it lives under `integrations/`. An ordered fallback factory does not either.

Native versus optional is an availability property, independent of registry
eligibility. A base-install implementation still registers when it belongs to
a configured strategy family (Louvain registers next to Leiden; pypdf
registers next to liteparse and pypdfium2). An optional adapter with no named
peers stays an integration.

### Integration inventory

Every Python module under `src/rag_mcp/integrations/`, classified. A contract
test fails when a module is missing from this table.

<!-- integration-inventory:start count=10 -->
| Module | Availability | Selector | Shared contract | Fallback owner | Disposition |
|---|---|---|---|---|---|
| `rag_mcp.integrations` | Native | None | Package facade | None | Facade; exports stable integration APIs only |
| `rag_mcp.integrations.azure` | Optional `azure` extra | `DOCUMENT_BACKEND=azure` | Document parsing into LlamaIndex Documents | Split today: config handles missing credentials, Azure retries, and ingestion/local readers handle runtime fallback | Capability integration; deferred to `register-document-backend-strategies` |
| `rag_mcp.integrations.leidenalg` | Optional `community-leiden` extra | `COMMUNITY_ALGORITHM=leiden`, via `core/community/registry.py` | Flat partition callable | None; explicit selection fails startup | External adapter behind the community registry |
| `rag_mcp.integrations.magika` | Optional executable | `MAGIKA_BINARY` selects the binary path, not an implementation | `FileEntry` detection results | `core/codebase/codebase_map.py` suffix detection | Capability integration; remains unregistered |
| `rag_mcp.integrations.pdf` | Native | None | `get_pdf_reader(reader)` | None | Public facade exposing the factory |
| `rag_mcp.integrations.pdf.factory` | Native | `PDF_READER=auto` | Reader instance with `load_data` | Factory itself (LiteParse → pypdfium2 → pypdf probe, for direct `auto` callers) | Registry-backed factory; `auto` stays ordered capability resolution |
| `rag_mcp.integrations.pdf.registry` | Native | `PDF_READER` concrete values | Reader class with `load_data` | None; unknown names raise | Lazy registry for concrete PDF readers |
| `rag_mcp.integrations.pdf.liteparse` | Base dependency (despite the stale docstring naming an extra) | `PDF_READER=liteparse` | `load_data` | `compose.resolve_pdf_reader` `auto` probe | Registered reader strategy |
| `rag_mcp.integrations.pdf.pypdf` | Base, via `llama-index-readers-file` | `PDF_READER=pypdf` | `load_data` | Terminal `auto` tier | Registered reader strategy |
| `rag_mcp.integrations.pdf.pypdfium` | Optional `pdf-pypdfium2` extra | `PDF_READER=pypdfium2` | `load_data` | None | Registered reader strategy |
<!-- integration-inventory:end -->

### Strategy-family audit

The same rule applied to every name-dispatched family, inside and outside
`integrations/`:

| Family | Selector | Live registry / factory | Conclusion | Follow-up |
|---|---|---|---|---|
| Community detection | `COMMUNITY_ALGORITHM` | `core/community/registry.py` | Registered in this change: `louvain` native, `leiden` optional via `integrations/leidenalg.py` | None |
| PDF readers | `PDF_READER` | `integrations/pdf/registry.py` behind `integrations/pdf/factory.py` | Concrete readers registered behind the unchanged `auto` factory | None |
| Chunking | Content-type dispatch in `core/ingestion/chunker.py`; `CHUNKING__STRATEGY_FALLBACK` (default `markdown`) | `core/chunking/registry.py` | Already a registry | None |
| Metadata extraction | `METADATA__EXTRACTION_MODE` and provider backends | `core/metadata/registry.py` | Already a registry | None |
| Embedding providers | `EMBED_PROVIDER` | `core/providers/embeddings/registry.py` | Already a registry | None |
| LLM providers | `LOCAL_BACKEND` / `CLOUD_BACKEND` | `core/providers/llm/registry.py` | Already a registry | None |
| Sparse retrieval | `RETRIEVAL__HYBRID_SPARSE_BACKEND` | `core/retrieval/registry.py` (`bm25`) | `bm25` registered; `native` is currently a warning-to-BM25 placeholder | `openspec/changes/implement-native-sparse-backend-strategy/` |
| Reranking | `RETRIEVAL__RERANK_BACKEND`, resolved by `core/retrieval/backend.py` | `core/retrieval/registry.py` (`reranker_onnx`, `reranker_torch`) | Already registered strategies | None |
| Vector store | `VECTOR_STORE` | `core/vectordb/registry.py` | `chroma` and `lancedb` registered | None |
| Document backends | `DOCUMENT_BACKEND` | None; direct construction | `local` and `azure` do not yet form one registry contract, and fallback ownership changes with registration | `openspec/changes/register-document-backend-strategies/` |

Live registry contents, kept in step with the code by contract tests:

<!-- registry-names:community -->
`leiden` `louvain`
<!-- /registry-names:community -->

<!-- registry-names:pdf -->
`liteparse` `pypdf` `pypdfium2`
<!-- /registry-names:pdf -->

<!-- registry-names:chunking -->
`code` `config` `sentence`
<!-- /registry-names:chunking -->

<!-- registry-names:metadata -->
`keyword` `llamacpp` `llamaindex` `ollama` `openrouter`
<!-- /registry-names:metadata -->

<!-- registry-names:embeddings -->
`llamacpp` `ollama` `openrouter`
<!-- /registry-names:embeddings -->

<!-- registry-names:llm -->
`llamacpp` `ollama` `openrouter`
<!-- /registry-names:llm -->

<!-- registry-names:retrieval -->
`bm25` `dense` `fusion` `reranker_onnx` `reranker_torch`
<!-- /registry-names:retrieval -->

<!-- registry-names:vectordb -->
`chroma` `lancedb`
<!-- /registry-names:vectordb -->

### Audit conclusions

- The concrete PDF readers were the one behaviour-preserving missing registry
  family. They are now registered behind the unchanged `auto` factory.
- Magika remains a capability adapter, not a strategy family: one configured
  capability, no interchangeable named peers.
- Azure and local document backends are deferred to the strict-valid follow-up
  `openspec/changes/register-document-backend-strategies/` because fallback
  ownership changes with registration.
- Native sparse retrieval is deferred to
  `openspec/changes/implement-native-sparse-backend-strategy/` because `native`
  is currently a warning-to-BM25 placeholder and stored sparse coverage
  matters.
- Every other current family already uses a registry or a documented policy
  alias or sentinel. No migration was required for this change.

---

## The rules that are actually enforced

These are not documentation. They fail the build.

| Rule | Enforced by |
|---|---|
| ChromaDB only in `core/vectordb/chroma.py` | `chromadb-confined-to-vectordb` |
| LanceDB only in `core/vectordb/` (`lancedb.py`, `lance_filter.py`) | `lancedb-confined-to-vectordb` |
| `config/` never imports business logic | `config-is-leaf` |
| `integrations/` never imports core or transports | `integrations-are-leaves` |
| `core/` never imports transports or providers | `core-business-avoids-providers-transports` |
| `core/community/` never imports either graph consumer | `community-strategies-independent-of-consumers` |
| Settings models stay pure data | `settings-models-are-pure-data` |
| Every package covered by some contract | `tests/test_contract_coverage.py` |
| No global settings reads in core | `tests/test_no_global_settings_reads.py` |
| No file over 500 lines | `tests/test_file_size_ceiling.py` |
| Dispatch goes through registries | `tests/test_no_module_level_strategy_imports.py` |

Run them with `uv run lint-imports` and `uv run pytest -m "not slow"`.

One detail worth knowing: the contracts fail when a *suppression* becomes
unnecessary. Fix a violation, forget to delete its exception, and the build
tells you. That is deliberate — see [ADR-037](../adr/037-architecture-v2-conformance.md).

---

## Technology choices

Short version. Each links to the full reasoning.

**LlamaIndex** ([ADR-002](../adr/002-adopt-llamaindex-for-rag-pipeline.md)) —
document loaders, chunkers and vector store adapters already exist, so we write
pipeline logic instead of plumbing.

**LanceDB** ([ADR-046](../adr/046-lancedb-vector-store-backend.md),
[ADR-049](../adr/0049-lancedb-default-and-chroma-isolation.md)) — the embedded
base-install default. Each collection gets its own table and files with
optimistic concurrency instead of ChromaDB's shared SQLite write lock.

**ChromaDB** ([ADR-003](../adr/003-use-chromadb-as-vector-store.md),
[ADR-049](../adr/0049-lancedb-default-and-chroma-isolation.md)) — an explicit
optional backend. Install the `chroma` extra before setting `VECTOR_STORE=chroma`.

Vector-store selection is runtime-swappable at the deployment boundary, but
embedding-provider selection is **process/deployment scoped**, not
per-collection. The composition root assigns one LlamaIndex
`Settings.embed_model` for the process. Concurrent collections may use
different retrieval profiles and stores, but they cannot safely select
different embedding providers in the same server process. Run separate
processes for different providers until an explicit per-operation embedding
context replaces the LlamaIndex global.

**MCP** ([ADR-004](../adr/004-adopt-mcp-protocol-for-server-interface.md)) —
one server works with any MCP client, rather than a bespoke integration each
time.

**uv** ([ADR-001](../adr/001-use-uv-as-package-manager.md)) — fast, one
lockfile, no virtualenv juggling.

**ONNX Runtime for the default reranker path**
([ADR-005](../adr/005-cross-encoder-reranker-with-onnx-runtime.md),
[ADR-038](../adr/038-pluggable-reranker-backend.md)) — the default install
stays torch-free; a torch-backed reranker is available behind the `torch`
optional extra.

**qwen3-embedding:0.6b**
([ADR-009](../adr/009-switch-to-qwen3-embedding-0-6b.md)) — better retrieval
quality than nomic-embed-text, at a size that still runs locally.

**Cross-encoder reranker, off by default**
([ADR-005](../adr/005-cross-encoder-reranker-with-onnx-runtime.md),
[ADR-019](../adr/019-reranker-disabled-for-technical-workloads.md)) —
Experiment 10 found it *hurt* results on code-heavy content by 19–27%. The
`documents` profile turns it back on, because it does help on prose.

**Deterministic graphs, no LLM**
([ADR-022](../adr/022-code-graph-via-tree-sitter-ast.md),
[ADR-023](../adr/023-document-graph-via-embedding-similarity.md)) — the code
graph comes from tree-sitter parsing, the document graph from embedding
similarity. Same input, same output, every time.

---

## Where to go next

| You want to | Read |
|---|---|
| Get it running | [Getting started](getting-started.md) |
| Change a setting | [Configuration](configuration.md) |
| Use the CLI | [CLI reference](cli-reference.md) |
| Connect an MCP client | [MCP client setup](mcp-client-setup.md) |
| Understand ingestion | [Ingestion](ingestion.md) |
| Understand reranking | [Reranker](reranker.md) |
| Write tests | [Testing](testing.md) |
| Know why a decision was made | [`docs/adr/`](../adr/) |
