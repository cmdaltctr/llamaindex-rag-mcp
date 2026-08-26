# Tasks: validate-embedding-write-contract

## 1. Pin the contract with failing tests

- [ ] 1.1 Add focused validator tests for empty vectors, non-numeric elements,
  mixed dimensions, and an existing collection-dimension conflict.
- [ ] 1.2 Assert every failure names the collection, provider/model, and each
  affected node or row identifier.
- [ ] 1.3 Add atomicity regressions that mix valid and invalid vectors. Assert
  no backend write occurs and no rows or generation changes result.
- [ ] 1.4 Extend the cross-backend vector-store contract suite for ChromaDB and
  LanceDB on direct and ingestion/replacement write paths.

## 2. Implement the shared write contract

- [ ] 2.1 Add one core structural embedding validator with typed input and
  clear fail-closed errors.
- [ ] 2.2 Extend the narrow `VectorStore` contract so adapters can provide an
  existing collection dimension without exposing backend SDK objects.
- [ ] 2.3 Ensure all production write paths materialise vectors before the
  validator and invoke it before either adapter mutates a collection.
- [ ] 2.4 Implement ChromaDB and LanceDB dimension discovery at their adapter
  boundaries. Preserve the existing embedding-identity guard.
- [ ] 2.5 Confirm no malformed batch reaches `VectorStoreIndex`, ChromaDB, or
  LanceDB, and no rejected batch advances generation.

## 3. Reuse the contract in Experiment 14

- [ ] 3.1 Replace any Experiment 14 structural-vector guard with the shared
  production validator.
- [ ] 3.2 Add a harness regression proving malformed embedder output fails
  with the shared diagnostic before `upsert_precomputed`.
- [ ] 3.3 Keep parser preflight separate from vector validation.
- [ ] 3.4 Do not modify, remove, or regenerate files in Experiment 14 `output/`.

## 4. Record and verify

- [ ] 4.1 Create an ADR before implementation is complete. Record the
  fail-closed write contract, core/adapter boundary, and the deliberate
  exclusion of L2 normalisation and norm policy.
- [ ] 4.2 Update affected architecture and ingestion documentation plus the
  docs index.
- [ ] 4.3 Run `uv run openspec validate validate-embedding-write-contract --strict`.
- [ ] 4.4 Run focused validator, ingestion, replacement, ChromaDB, LanceDB,
  and Experiment 14 harness tests. Ask before running the full fast suite.
