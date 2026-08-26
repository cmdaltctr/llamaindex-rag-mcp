# Design: validate-embedding-write-contract

## Context

`core/ingestion/writer.py` delegates node writes without checking vector
contents. `core/ingestion/replacement.py` checks only whether an embedding
provider returned the expected vector count. ChromaDB forwards precomputed
vectors to its SDK. LanceDB derives a new table schema dimension from the
first supplied vector.

These paths need one structural rule before mutation. The rule belongs in
core. Backend adapters retain backend-specific collection inspection.

## Goals

- Reject malformed vectors before every store mutation.
- Preserve batch atomicity for malformed input.
- Give callers actionable diagnostics without leaking credentials or vectors.
- Reuse one validator from production writes and Experiment 14.

## Non-Goals

- L2 normalisation, norm thresholds, semantic-quality checks, or repair.
- Replacing existing embedding-identity checks.
- Changing parser results, experiment measurements, or output artefacts.

## Decisions

### D1: A shared core validator owns structural checks

A dedicated `core/vectordb/` validator accepts aligned identifiers and
vectors, a collection name, provider/model diagnostic, and a known existing
dimension. It returns only when the complete batch is structurally valid.
It rejects an empty vector, a non-numeric element, mixed dimensions in one
batch, or a batch dimension that conflicts with an existing collection.
Failures name the rule, collection, provider/model, and affected identifiers.
They do not include raw vector values or credentials.

### D2: Adapters expose dimension facts only

`VectorStore` gains a narrow read capability that returns an established
collection vector dimension, or `None` before a vector schema exists. ChromaDB
and LanceDB obtain this fact from their own representations. The shared
validator owns the comparison rule.

This preserves the boundary: core owns business rules; adapters own SDK access.
It keeps settings injection and existing embedding-identity checks unchanged.

### D3: Complete candidate batches validate before mutation

Normal ingestion, failure-safe replacement, and precomputed upserts must
materialise their candidate embeddings before validation. Validation precedes
collection or schema creation, `VectorStoreIndex`, backend upsert, row
conversion, and generation change.

A rejected batch never writes a valid subset. It must not create a collection
dimension or advance generation.

### D4: Experiment 14 imports the production validator

The Experiment 14 builder calls the shared validator with its row identifiers,
vectors, collection, and model diagnostic before `upsert_precomputed`. Parser
preflight stays separate. The builder does not write, delete, rename, or
regenerate files in its `output/` directory.

## Risks and Validation

Materialising embeddings before validation must keep ADR-048's bounded
per-source lifetime. Tests cover the pure validator, normal ingestion,
replacement, direct precomputed writes, and both backends.