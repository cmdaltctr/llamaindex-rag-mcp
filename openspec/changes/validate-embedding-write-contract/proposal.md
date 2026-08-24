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

- Add one shared production-core validator for vectors about to be written.
- Apply it to every `VectorStore` write path, including `write_nodes` and
  `upsert_precomputed`.
- Reject empty vectors, non-numeric elements, mixed dimensions, and conflicts
  with an existing collection dimension.
- Reject the complete batch before a backend write. No valid subset persists.
- Identify the collection, embedding provider/model, and affected node or row
  identifiers in each failure.
- Make Experiment 14 use this validator before its precomputed upsert.

## Capabilities

### New Capabilities

- `embedding-write-contract`: fail-closed structural validation for every
  vector-store write, with backend dimension discovery and harness reuse.

## Scope Boundaries

This change does not add L2 normalisation, norm thresholds, cosine conversion,
or a norm-policy decision. It does not change embedding providers, models,
parser policy, retries, or retrieval score semantics.
The validator does not transform, truncate, repair, or replace vectors. It
reports invalid input and stops the write. Experiment 14 outputs stay untouched.

## Impact

**Code:** `core/vectordb/`, `core/ingestion/writer.py`,
`core/ingestion/replacement.py`, and the Experiment 14 builder.

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