# ADR-045: Hosted Chroma Cloud Backend for Experiment Storage

**Date:** 2026-08-15
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

Long-running retrieval calibration (`calibrate-rag-retrieval-defaults`,
experiments 10b, 10.1, 12, 9a-rerun, 13, 14) repeatedly embeds and writes
the same corpora into local ChromaDB indexes. The embedded
`PersistentClient` uses one SQLite file per persist directory, so parallel
writers contend, evaluation workers on other machines cannot share an
index, and each repetition re-pays embedding cost. The six harnesses also
carried three stale storage patterns: direct `PersistentClient`
construction, `CHROMA_PERSIST_DIR` environment mutation, and assignment to
module-level config constants deleted in v2.0.0 (ADR-037) — leaving them
unable to run at all on the current surface.

Separately, dimension locking (ADR-003) cannot prevent a subtle failure:
two distinct embedding models with the same output width (two 1024-dim
models, for example) embed incompatible vector spaces. A same-dimension
model swap corrupts retrieval quality silently.

LlamaIndex upstream already establishes the safe integration pattern:
client construction is separate from the vector-store wrapper, and the
wrapper accepts an injected collection. `chromadb.CloudClient` ships in
the existing ChromaDB dependency and exposes the same collection API as
the local client, so no new dependency is required.

## Decision

1. **Explicit deployment mode, never credential-sniffing.**
   `CHROMA_MODE=local|cloud` (default `local`) selects storage. API-key
   presence is rejected as the selector: a missing shell variable could
   silently switch a process to an empty local database. Unknown values
   fail Settings validation. Embedding compute (`EMBED_PROVIDER`) and
   vector storage (`CHROMA_MODE`) are independent axes; no third selector
   named `hybrid` exists. Cloud mode requires `CHROMA_CLOUD_API_KEY` at
   Settings construction; `CHROMA_CLOUD_TENANT` and
   `CHROMA_CLOUD_DATABASE` are optional and must be supplied together.

2. **One Chroma import and construction site.** `core/vectordb/chroma.py`
   constructs both `PersistentClient` and `CloudClient`, validates the
   cloud connection with a lightweight `heartbeat()` during runtime setup,
   and injects the client into the unchanged `ChromaVectorStore`.
   `compose.build_vector_store(settings)` passes construction-time
   primitives (mode, persist dir, key, tenant, database); credentials
   never enter `EffectiveSettings`. Cloud failures propagate as redacted,
   actionable startup errors — no local fallback after an explicit cloud
   selection (the ADR-029 silent-fallback lesson).

3. **Embedding identity in collection metadata.** Every newly indexed
   collection stores `rag_embed_provider`, `rag_embed_model`, and an
   optional `rag_index_identity`. Stamping is read-merge-write (Chroma's
   `modify` replaces the whole map, so profile tags survive). Writes and
   queries reject identity mismatches before touching the store — a
   dimension match proves nothing. Legacy collections without identity
   metadata keep working; the first identity-bearing write stamps them.

4. **Deterministic immutable-index naming for experiments.** Collection
   names derive from experiment ID, corpus/config identity, embedding
   provider/model, parser, and chunking configuration
   (`exp14-qasper-openrouter-qwen3-8b-liteparse-cs512-co100`). Cell IDs and
   repetitions that only change retrieval settings stay in
   checkpoint/result metadata and reuse the index read-only.

5. **One-writer-per-collection boundary.** The BM25 invalidation counter
   is process-local; remote storage does not make it cross-process. A
   coordinator builds each immutable index once; evaluation workers query
   it read-only. Cross-process mutation of one collection with shared BM25
   caches is unsupported and documented as such.

6. **Harnesses go through the production boundary.** All six calibration
   harnesses obtain storage via `experiments/_lib/storage.py` and the
   production factory, call `rag_mcp.core.retrieval.search` with an
   injected store and per-call retrieval knobs, and contain no direct
   `chromadb` usage — enforced by a migration-guard test. One verified
   contract method (`upsert_precomputed`) was added for their
   precomputed-embedding writes; everything else uses the existing ABC.

## Consequences

### Positive
- Calibration indexes are shareable across machines and parallel
  evaluation workers; no local SQLite lock contention.
- Same-dimension model swaps fail loudly instead of silently degrading
  retrieval quality.
- Local mode behaviour, defaults, and existing local collections are
  unchanged; the change is opt-in per deployment.
- All six active harnesses run on the v2 surface again, in local or cloud
  mode, with secret-free checkpoints.
- Credentials are confined to `.env` and construction time; redaction
  tests keep them out of logs, summaries, and errors.

### Negative
- Cloud mode adds a network dependency: a Chroma Cloud outage blocks
  startup for explicit cloud deployments (operators deliberately select
  local mode for degraded operation).
- Local experiment output directories built with the legacy `documents`
  collection name require one rebuild; migrated runners use derived
  collection names by default.
- The identity guard adds one metadata read (and a merge-write on first
  stamping) per ingest call.

### Neutral
- `CollectionReader` (a duck-typed `get(include=...)` view over
  `fetch_all`) bridges `core.documents.doc_graph`'s collection handle
  parameter without changing that production signature.
- Fireworks remains a future cloud-compute adapter (needs provider
  registration); OpenRouter supplies cloud embeddings today.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Select mode by API-key presence** | A missing shell variable would silently switch to an empty local index; explicit selection is auditable. |
| **A third `hybrid` storage selector** | `hybrid` already means dense+sparse retrieval (and ADR-024 parsing); independent EMBED_PROVIDER/CHROMA_MODE axes express all four combinations without overloading the word. |
| **Separate `ChromaCloudVectorStore` class** | Local and cloud share every operation after client construction; a second wrapper duplicates the whole contract for one construction difference. |
| **Silent local fallback on cloud failure** | Violates the ADR-029 lesson: an explicit cloud selection must fail loudly, not quietly query an empty local index. |
| **Dimension-only compatibility check** | Two distinct models with equal dimensions embed incompatible spaces; identity (provider+model+index) is required. |
| **Persisting BM25 generation counters remotely** | A cross-process concurrency design out of scope here; Qdrant or native sparse retrieval is the better long-term home for that work. |
| **Route harness embedding through LlamaIndex `write_nodes`** | The harnesses' batched clients carry custom timeouts and count-based resume that the LlamaIndex path cannot express; `upsert_precomputed` preserves experiment behaviour. |

## References

- OpenSpec change: `openspec/changes/add-chroma-cloud-backend/` (proposal,
  design, delta specs)
- Implementation: `src/rag_mcp/core/vectordb/chroma.py`,
  `src/rag_mcp/core/vectordb/identity.py`,
  `src/rag_mcp/core/vectordb/naming.py`, `src/rag_mcp/compose.py`
- Experiment helper: `experiments/_lib/storage.py`; smoke check:
  `scripts/chroma_cloud_smoke.py`
- Tests: `tests/test_chroma_cloud.py`, `tests/test_experiment_storage.py`
- Guides: `docs/guides/configuration.md` (four-mode deployment matrix),
  `docs/guides/architecture.md`, `experiments/EXP_README.md`
- Related: ADR-003 (dimension locking), ADR-024 (cloud opt-in boundary),
  ADR-029 (silent-fallback audit), ADR-034 (vector-store ABC),
  ADR-037 (architecture v2)
