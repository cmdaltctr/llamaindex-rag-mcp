# ADR-051: Fail-Closed Embedding Write Contract

**Date:** 2026-08-28
**Status:** Proposed
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

Experiment 14 exposed a malformed-vector failure path. LiteParse first
returned empty parsed text because its harness lacked `EffectiveSettings`
(fixed by commit `86e4149`). Ollama then returned empty vectors, and
ChromaDB raised an internal `IndexError` that named no document. Production
ingestion passed embedding batches straight to the store adapters with no
structural guard, so a malformed batch could reach the backend SDK and fail
late with a backend-specific error.

PR #63 (`harden-pipeline-correctness-before-calibration`) had already landed
failure-safe replacement ordering, durability verification, store-owned
collection generation counters, valid precomputed-upsert parity, and
exactly-once mutation/generation tests. The one missing piece was the shared
structural embedding validator.

Two constraints shaped the design. First, `core/vectordb/lancedb.py` (497
lines) and `core/vectordb/chroma.py` (499 lines) sat at the 500-line file
ceiling, so shared logic had to live outside the adapters and adapter changes
had to stay thin. Second, the change must land before
`implement-native-sparse-backend-strategy` and before the Chroma migration
work in `add-per-collection-persist-dirs`, because those changes share the
same write/adapter path.

## Decision

1. **One shared fail-closed validator in core.**
   `core/vectordb/validation.py` holds the structural write contract:
   `validate_embedding_batch` rejects an empty batch, an identifier/vector
   cardinality mismatch in either direction (reporting surplus vector
   positions), a vector that is not a sized sequence, an empty vector, a
   non-numeric element (booleans are rejected; other `Real` values, including
   integers, pass), a non-finite element (NaN or infinity), mixed dimensions
   within one batch, and a dimension that conflicts with the existing
   collection dimension. Every rejection raises
   `EmbeddingWriteContractError` (a `ValueError` subclass). The validator
   never transforms, truncates, repairs, normalises, or replaces vectors —
   it reports invalid input and stops the write.

2. **Validation completes before any backend mutation.** Adapter code
   invokes the shared validation immediately before its backend SDK
   mutation — the guarantee is validation before any backend SDK or
   persistent-store mutation, not merely before the adapter receives a
   write request. `write_nodes` calls
   `materialise_and_validate_node_embeddings` (which embeds missing
   caller-owned nodes, then validates the complete batch) before the
   collection is created and the LlamaIndex index build runs.
   `upsert_precomputed` calls `validate_embedding_batch` immediately before
   the SDK upsert. A rejected batch therefore never reaches the ChromaDB or
   LanceDB SDK, never persists a valid subset, and never advances the
   store-owned generation counter.

3. **Diagnostics are mandatory.** Every failure names the destination
   collection, the embedding provider/model, and each affected node or row
   identifier (plus element positions for element-level faults). Normal
   node writes derive the identity from the composed embedding model.
   `upsert_precomputed` takes `embedding_identity` as a required keyword
   argument: direct precomputed-upsert callers must supply the
   provider/model diagnostic explicitly rather than rely on an optional
   store identity.

4. **Read-only dimension discovery on the store contract.**
   `VectorStore.get_collection_dimension(name)` returns an established
   vector dimension without creating backend state; the default returns
   `None` so older third-party stores stay instantiable. ChromaDB reads one
   stored embedding from an existing collection. LanceDB reads the
   fixed-size-list width from the durable Arrow schema. Neither discovery
   path creates or mutates a collection, and the existing
   embedding-identity guard is unchanged.

5. **Core/adapter boundary.** The structural contract lives in
   `core/vectordb/validation.py`; adapters invoke it at their SDK mutation
   seam and add nothing else. The helper is deliberately independent of
   every backend: it only embeds missing caller-owned nodes and validates,
   performing no vector-store operation. Shared logic in the helper kept
   both adapter files under the 500-line ceiling.

6. **Experiment 14 reuses the production validator before its destructive
   rebuild.** The builder validates the complete embedding batch, against
   the existing collection dimension, before `delete_collection` and
   `create_collection` run on an existing collection. Malformed embedder
   output therefore aborts with the shared diagnostic while the existing
   collection and the documented output artefacts remain unchanged.
   Parser preflight stays separate from vector validation and continues to
   abort before the embed stage (decision D19).

7. **No L2 normalisation and no norm policy, deliberately.** The contract
   is structural correctness — can this batch be written as-is — not
   quality policy. Normalisation, norm thresholds, and cosine conversion
   would change retrieval score semantics, so they belong to a separate
   decision supported by its own experiment. Combining them with the
   structural check would make one enforcement point own two unrelated
   questions.

## Consequences

### Positive

- Every production write path — direct writes, ingestion
  (`embed_and_write_async` through `write_nodes`), and source replacement
  (also through `write_nodes`) — fails closed under the same contract.
  Backend-specific late failures such as ChromaDB's unnamed `IndexError`
  are gone.
- A rejected batch leaves durable state untouched: no rows written, no
  collection deleted or recreated, no generation counter advanced.
- Production ingestion and Experiment 14 cannot drift: the harness
  validates with the same function and receives the same diagnostics.
- Failures are actionable: collection, provider/model, and affected
  identifiers appear in every message.
- The contract is store-neutral. A new backend inherits the guard by
  calling the two helpers at its own SDK mutation seam.

### Negative

- Every write pays an element-by-element validation scan before the
  backend call.
- Writes into an existing collection add one read-only dimension discovery
  step (one stored embedding on ChromaDB; a schema read on LanceDB).
- `upsert_precomputed` now requires `embedding_identity`. Existing direct
  callers must pass it — a deliberate breaking change to the
  calibration-facing seam, chosen so failures always name the
  provider/model.
- Empty batches are hard errors. LanceDB's upsert path had treated an
  empty batch as a no-op to avoid locking a zero-dimension vector column;
  validation now rejects the batch before that branch, so the no-op is
  unreachable through the public contract.

### Neutral

- Norm policy, cosine conversion, embedding providers and models, parser
  policy, retries, and retrieval score semantics are unchanged.
- `materialise_and_validate_node_embeddings` fills in the `embedding`
  attribute on caller-owned nodes after validation. This mutation is the
  documented embedding path for `write_nodes`; the helper performs no
  vector-store operation itself.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Rely on backend validation | Backend-specific late failures; ChromaDB raised an `IndexError` that named no document. |
| Duplicate structural checks in Experiment 14 | Production and harness rules can drift apart over time. |
| Combine structural checks with L2 normalisation | Norm policy is a separate decision that needs its own evidence; mixing them couples correctness to retrieval-score semantics. |
| Optional store identity for precomputed upserts | Direct callers could omit diagnostics, and failures would name no provider/model. |
| Wrapper/service layer around the adapters | An extra layer for one check; the SDK mutation seam is where enforcement is provable, and both adapter files were near the 500-line ceiling. |

## References

- OpenSpec change: `openspec/changes/validate-embedding-write-contract/`
- Validator: `src/rag_mcp/core/vectordb/validation.py`
- Adapter seams: `src/rag_mcp/core/vectordb/{base,chroma,lancedb}.py`
- Production write paths:
  `src/rag_mcp/core/ingestion/{writer,replacement}.py`
- Experiment 14 builder:
  `experiments/14-liteparse-qasper-promotion-2026-06-29/build_indexes.py`
- Contract tests: `tests/test_embedding_write_contract.py`,
  `tests/test_vectordb_contract.py`,
  `tests/test_experiment_14_harness.py`
- Related decisions: ADR-034 (vector-store abstraction), ADR-046 (LanceDB
  backend), ADR-048 (bounded failure-safe ingestion), ADR-049 (LanceDB
  default), ADR-050 (pdf-inspector default, from Experiment 14 results)
