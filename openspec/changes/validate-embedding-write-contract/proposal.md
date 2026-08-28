# Proposal: validate-embedding-write-contract

## Why

Experiment 14 exposed a malformed-vector failure path. LiteParse first
returned empty parsed text because its harness lacked `EffectiveSettings`.
Ollama then returned empty vectors. ChromaDB raised an internal `IndexError`
instead of naming the failed documents.

Commit `86e4149` fixes the harness settings bootstrap. Production ingestion
still passes vectors to store adapters without a structural write guard. A
malformed batch can therefore reach ChromaDB or LanceDB and fail late.

## What Changes

- Add one shared production-core validator for vectors about to be written, in a small focused helper (`core/vectordb/validation.py`). No wrapper or service hierarchy around the adapters.
- Guarantee: validation completes **before any backend SDK or persistent-store mutation** — not merely before an adapter receives a write request. Adapter code invokes the shared validation immediately before its backend SDK mutation as the enforcement point.
- Apply it to every `VectorStore` write path, including `write_nodes` and `upsert_precomputed`: empty embedding batches, identifier/vector cardinality mismatches (missing or surplus vectors), inconsistent dimensions within a batch, dimension conflicts with an existing collection, non-numeric elements, and non-finite values (NaN, infinity) are all rejected. Valid precomputed vectors and embeddings produced from `write_nodes` both pass.
- Reject the complete batch before a backend write. No valid subset persists.
- Identify the collection, embedding provider/model, and affected node or row identifiers in each failure. Normal node writes use their composed embedding identity; direct precomputed-upsert callers must supply the diagnostic explicitly rather than relying on an optional store identity.
- Discover an existing collection dimension without creating or mutating backend state.
- Make Experiment 14 validate all embeddings **before deleting or recreating an existing collection**; validation immediately before the upsert alone is too late because the existing collection may already have been destroyed by then.

## Relationship to landed PR #63 groundwork (do not duplicate)

PR #63 (`harden-pipeline-correctness-before-calibration`) already added:
failure-safe replacement ordering, durability verification after writes,
store-owned collection generation counters, valid precomputed-upsert
parity, and exactly-once mutation/generation tests. This change adds the
one missing piece — the shared structural embedding validator — and
must not re-implement or re-specify the landed work.

## Sequencing

Implement **before** `implement-native-sparse-backend-strategy` and
before any Chroma migration work from `add-per-collection-persist-dirs`:
those changes share the write/adapter path, and the shared write
boundary must land first.

## Capabilities

### New Capabilities

- `embedding-write-contract`: fail-closed structural validation for every
  vector-store write, with backend dimension discovery and harness reuse.

## Scope Boundaries

This change does not add L2 normalisation, norm thresholds, cosine conversion,
or a norm-policy decision. It does not change embedding providers, models,
parser policy, retries, or retrieval score semantics.
The validator does not transform, truncate, repair, or replace vectors. It
reports invalid input and stops the write. The change preserves existing
Experiment 14 output artefacts; ordinary builder runs may still write their
documented parsed, preflight, and index-build outputs.

## Impact

**Code:** `core/vectordb/validation.py` (new focused helper),
`core/vectordb/{chroma,lancedb}.py` (validation invocation at the SDK
mutation seam), `core/ingestion/writer.py`,
`core/ingestion/replacement.py`, and the Experiment 14 builder.
`lancedb.py` (497 lines) and `chroma.py` (499 lines) sit at the
500-line ceiling — invocation is a thin call, and any shared logic
lives in the focused helper, not inline growth.

**Tests:** focused validator, direct store, ingestion, replacement, and
cross-backend contract tests for ChromaDB and LanceDB.

**Decision record:** implementation must create an ADR for this durable
write-contract and ownership decision.

## Alternatives Considered

| Alternative | Decision |
| --- | --- |
| Rely on backend validation | Rejected. It produces backend-specific late failures. |
| Duplicate checks in Experiment 14 | Rejected. Production and harness rules can drift. |
| Combine structural checks with normalisation | Rejected. Norm policy is a separate decision. |