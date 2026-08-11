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
`RAG_PROFILE`, `PDF_READER`, and all credentials.

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
| `core/vectordb/` | The database interface, and the ChromaDB implementation |
| `core/profiles/` | Resolve which profile a collection uses |
| `core/providers/` | Build embedding and LLM clients |
| `core/codebase/` | Codebase map and code graph |
| `core/documents/` | Document similarity graph |
| `core/settings.py` | `EffectiveSettings` — the frozen settings object passed around |

`core/ingestion/` and `core/retrieval/` do not import each other. They share
only settings.

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

### A new vector database

Implement `VectorStore` from `core/vectordb/base.py`, register it in
`compose.py`. ChromaDB is confined to `core/vectordb/chroma.py` — a contract
fails the build if `chromadb` is imported anywhere else.

### A new setting

- Belongs to one area? Add it to that area's `settings.py`
  (`core/retrieval/settings.py`, and so on), then to `defaults.yaml` under the
  matching block.
- Cross-cutting? Add it to `Settings` in `config/__init__.py` and to
  `defaults.yaml` at the top level.

A test checks the two agree, so they cannot drift apart.

---

## The rules that are actually enforced

These are not documentation. They fail the build.

| Rule | Enforced by |
|---|---|
| ChromaDB only in `core/vectordb/chroma.py` | `chromadb-confined-to-vectordb` |
| `config/` never imports business logic | `config-is-leaf` |
| `integrations/` never imports core or transports | `integrations-are-leaves` |
| `core/` never imports transports or providers | `core-business-avoids-providers-transports` |
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

**ChromaDB** ([ADR-003](../adr/003-use-chromadb-as-vector-store.md),
[ADR-034](../adr/034-phase-3-refactor-vectordb-abstraction.md)) — embedded, no
server to run, persists to a folder. Behind an interface since ADR-034, so it
can be swapped.

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
