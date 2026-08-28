# Tasks: validate-embedding-write-contract

> Sequencing: land before `implement-native-sparse-backend-strategy`
> and before any Chroma migration work from
> `add-per-collection-persist-dirs` (shared write/adapter path).
> `lancedb.py` (497) and `chroma.py` (499) are at the 500-line ceiling:
> shared validation logic lives in the focused helper; adapter changes
> are thin invocation calls only.
>
> Already satisfied by PR #63 — do NOT re-implement or re-specify:
> failure-safe replacement ordering, durability verification,
> store-owned generation counters, valid precomputed-upsert parity,
> exactly-once mutation/generation tests.

## 1. Pin the contract with failing tests

- [x] 1.1 Add focused validator tests for empty batches, identifier/vector cardinality mismatches in both directions (missing and surplus vectors), empty vectors, non-numeric elements, non-finite values (NaN, infinity), mixed dimensions, and an existing collection-dimension conflict.
- [x] 1.2 Assert every failure names the collection, provider/model, and each affected node or row identifier.
- [x] 1.3 Add atomicity regressions that mix valid and invalid vectors. Assert no backend write occurs and no rows or generation changes result.
- [x] 1.4 Extend the cross-backend vector-store contract suite for ChromaDB and LanceDB on direct and ingestion/replacement write paths, covering both `write_nodes`-produced embeddings and valid precomputed vectors.

## 2. Implement the shared write contract

- [x] 2.1 Add one core structural embedding validator with typed input and clear fail-closed errors, in the focused helper `src/rag_mcp/core/vectordb/validation.py` (no wrapper/service hierarchy).
- [x] 2.2 Extend the narrow `VectorStore` contract so adapters can provide an existing collection dimension without exposing backend SDK objects or creating backend state.
- [x] 2.3 Ensure all production write paths materialise vectors before the validator, and that adapter code invokes the shared validation immediately before the backend SDK mutation — the guarantee is validation before any backend SDK or persistent-store mutation, not merely before the adapter receives a write request. Require direct `upsert_precomputed` callers to supply a provider/model diagnostic explicitly; do not rely on an optional store identity.
- [x] 2.4 Implement read-only ChromaDB and LanceDB dimension discovery at their adapter boundaries as thin additions. Preserve the existing embedding-identity guard.
- [x] 2.5 Confirm no malformed batch reaches `VectorStoreIndex`, the ChromaDB SDK, or the LanceDB SDK, and no rejected batch advances generation.

## 3. Reuse the contract in Experiment 14

- [x] 3.1 Replace any Experiment 14 structural-vector guard with the shared production validator.
- [x] 3.2 Move validation before the builder's destructive rebuild steps: all embeddings must validate **before `delete_collection`/`create_collection`** on an existing collection, since the current order destroys the collection before `upsert_precomputed` runs. Add a harness regression proving malformed embedder output fails with the shared diagnostic before deletion, creation, or upsert, leaving the existing collection and output artefacts unchanged.
- [x] 3.3 Keep parser preflight separate from vector validation (the separation already exists in the builder; verify it survives and add a guard test only if the change could plausibly merge them).
- [x] 3.4 Do not modify, remove, or regenerate files in Experiment 14 `output/`.

## 4. Record and verify

- [x] 4.1 Create an ADR before implementation is complete. Record the fail-closed write contract, core/adapter boundary, and the deliberate exclusion of L2 normalisation and norm policy.
- [x] 4.2 Update affected architecture and ingestion documentation plus the docs index.
- [x] 4.3 Run `uv run openspec validate validate-embedding-write-contract --strict`.
- [x] 4.4 Run focused validator, ingestion, replacement, ChromaDB, LanceDB, and Experiment 14 harness tests. Ask before running the full fast suite.
