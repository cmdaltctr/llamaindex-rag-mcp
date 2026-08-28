## Context

See `proposal.md` for the motivation. Current construction has two relevant
properties:

- `compose.build_vector_store(settings)` owns store composition but calls
  `build_chroma_vector_store()` without passing the supplied settings.
- `ChromaVectorStore._get_client()` lazily reads the process default and always
  constructs `chromadb.PersistentClient(path=...)`.

The upstream LlamaIndex Chroma integration separates client construction from
store behaviour: it accepts an injected collection and provides local
`PersistentClient` and remote `HttpClient` construction paths. Chroma's
current SDK adds `CloudClient(api_key, tenant?, database?)` with the same
collection API. This change copies that injection pattern into the project's
existing `VectorStore` wrapper rather than adopting a second wrapper.

The project's BM25 cache uses process-local collection generation counters.
Remote storage does not make that counter cross-process; one writer per
collection is therefore an explicit boundary.

## Goals / Non-Goals

**Goals:** explicit local/cloud mode; startup credential validation; injected
client; unchanged local behaviour; cloud experiment indexes shareable across
machines; no secrets in output.

**Non-Goals:** cloud embedding default flip, Qdrant, native sparse search,
automatic local-to-cloud migration, same-collection multi-writer BM25 cache
coherence, and production SLA claims.

## Decisions

### 1. Use an explicit mode, not API-key presence

`CHROMA_MODE=local|cloud`, default `local`. API-key presence was rejected as
the selector: a missing shell variable could silently switch a process to an
empty local database. Unknown modes fail settings validation.

Embedding compute and vector storage remain independent axes. Documentation
uses this deployment matrix; no new selector named `hybrid` is added:

| Mode | Embeddings | Vector store | Use |
| --- | --- | --- | --- |
| Full local | llama.cpp | local Chroma | Private/offline; strong local hardware |
| Cloud compute, local store | OpenRouter/Fireworks | local Chroma | Fast embeddings, local single-machine index |
| Full cloud | OpenRouter/Fireworks | Chroma Cloud | Shared indexes, parallel read cells, no SQLite lock |
| Local compute, cloud store | llama.cpp | Chroma Cloud | Local model with a shared remote index |

OpenRouter is the existing cloud-provider implementation used by this change.
Fireworks is shown as a compatible future cloud-compute option; registering a
Fireworks provider remains a separate change.

### 2. Inject a Chroma client into the existing store

`ChromaVectorStore` gains an optional `ClientAPI` input. An injected client is
used directly; the local direct-call fallback may still construct a
`PersistentClient` lazily. `build_chroma_vector_store(...)` receives primitive
resolved values, constructs the selected SDK client inside
`core/vectordb/chroma.py`, validates it, then injects it.

This follows upstream LlamaIndex's injected collection/client pattern and
preserves the project's single `chromadb` import boundary. Creating a separate
`ChromaCloudVectorStore` was rejected because local and cloud share every
operation after client construction.

### 3. Compose passes construction-time settings

`compose.build_vector_store(settings)` passes mode, persist directory, API
key, tenant, and database to the Chroma factory. Credentials do not enter
`EffectiveSettings`, profiles, YAML defaults, or operation-level objects.
This also removes the production builder's current discarded-settings path.

### 4. Validate explicit cloud mode during runtime setup

Cloud mode requires an API key. Tenant and database are supplied together or
both omitted so `CloudClient` can resolve them from the key. The builder runs
a lightweight SDK operation before returning the store. Authentication,
network, and tenant/database failures propagate as actionable startup errors.
No fallback occurs after explicit cloud selection (ADR-029 silent-fallback
lesson).

### 5. Keep local behaviour and tests deterministic

Local mode uses the existing `PersistentClient`. Tests patch both
`PersistentClient` and `CloudClient`; no test contacts Chroma Cloud. Focused
contract tests assert the constructor arguments, connection check, unchanged
local path, missing-secret validation, and key redaction.

### 6. Bound sparse-cache consistency honestly

Each experiment cell uses a unique collection and one writer. Other processes
may read a completed collection. Mutating the same collection from several
processes while reusing BM25 caches is unsupported because generation counters
are process-local. Persisting generation state remotely was rejected here as a
larger concurrency design; Qdrant/native sparse work is the better long-term
place to remove the in-process BM25 cache.

### 7. Route calibration harnesses through the production store boundary

The six active calibration harnesses currently mix three stale patterns:
direct `PersistentClient` imports, `CHROMA_PERSIST_DIR` env mutation, and
assignment to deleted module-level config constants. Each runner sets its
cell-specific environment before importing runtime modules, resets runtime
composition between cells/processes, and obtains the `VectorStore` through
the production construction path.

Where a harness reads raw Chroma collections, use existing ABC methods
(`fetch_all`, collection lifecycle, paged metadata). Add an ABC method only
for a verified need that the current contract cannot express.

The coordinator derives one deterministic collection name per immutable index:
experiment ID, corpus/config identity, provider/model, parser, and chunking
configuration. It builds that index once; retrieval-only cells and repetitions
reuse it read-only. Cell/repetition IDs stay in checkpoints and results unless
they change indexed content. Names follow Chroma's 3–512 character rule and
lowercase letter/digit boundary requirement.

Collection metadata records the effective concrete embedding backend
(`llamacpp`, `openrouter`, or a future registered provider), model, and an
index-identity hash. Existing profile metadata is read and merged before `modify`, because
Chroma replaces the complete metadata map rather than patching individual
keys. Query and write paths reject identity mismatches even when vector
dimensions happen to match.

## Risks / Trade-offs

- [Cloud outage blocks explicit cloud mode] → Fail startup; operator selects
  local mode deliberately if degraded operation is acceptable.
- [Credentials leak through diagnostics] → Redaction tests; summaries include
  identifiers only.
- [Cloud/local indexes diverge] → Mode and database identifiers are explicit;
  switching mode requires intentional ingestion.
- [Embedding dimension changes] → Existing dimension lock fails clearly;
  experiment protocol allocates a fresh collection per model/cell.
- [Chroma Cloud SDK/API drift] → Use only the stable `ClientAPI` collection
  surface already covered by local tests; add a small opt-in smoke script.
- [Conflict with `add-per-collection-persist-dirs`] → That change remains
  local-mode-only; rebase it after this constructor split.

## Migration Plan

1. Ship with `CHROMA_MODE=local` so existing installs remain unchanged.
2. Create a Chroma Cloud database and API key outside the repository.
3. Set cloud variables in the operator's `.env` (never commit the key).
4. Run an opt-in smoke ingest/search against a disposable collection.
5. Run calibration cells with unique collection names and checkpointed output.
6. Roll back by setting `CHROMA_MODE=local`; remote data remains untouched.

No automatic data copy is attempted. Moving an existing collection requires
re-ingestion with the same embedding provider/model or a separate migration
change.
