# Design: validate-embedding-write-contract

## Context

PR #63 (`harden-pipeline-correctness-before-calibration`) landed the
write-path groundwork: failure-safe replacement ordering, durability
verification after writes, store-owned collection generation counters,
valid precomputed-upsert parity, and exactly-once mutation/generation
tests. What it did not add is a shared structural embedding validator.

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

A dedicated focused helper, `core/vectordb/validation.py`, accepts
aligned identifiers and vectors, a collection name, provider/model
diagnostic, and a known existing dimension. No wrapper or service
hierarchy is introduced around the adapters — current architecture
makes a plain module sufficient. It returns only when the complete
batch is structurally valid. It rejects an empty batch, any identifier/vector
cardinality mismatch (whether vectors are missing or surplus), an empty
vector, a non-numeric element, a non-finite value (NaN, infinity), mixed
dimensions in one batch, or a batch dimension that conflicts with an
existing collection. Failures name the rule, collection,
provider/model, and affected identifiers. They do not include raw
vector values or credentials.

### D2: Adapters expose dimension facts only

`VectorStore` gains a narrow read capability that returns an established
collection vector dimension, or `None` before a vector schema exists. This
lookup is read-only: it must not create a collection, table, schema, row, or
other persistent state. ChromaDB and LanceDB obtain the fact from their own
representations. The shared validator owns the comparison rule.

This preserves the boundary: core owns business rules; adapters own SDK access.
It keeps settings injection and existing embedding-identity checks unchanged.

### D3: Complete candidate batches validate before any backend SDK or persistent-store mutation

The guarantee is that validation completes before **any backend SDK or
persistent-store mutation** — one step stronger than "before an adapter
receives a write request", because adapters perform collection
creation, schema derivation, and row conversion before the SDK write
itself, and any of those can durably change state. Adapter code invokes
the shared validation immediately before its backend SDK mutation as
the enforcement point, so the rule holds even for callers that bypass
the ingestion orchestration.

Normal ingestion, failure-safe replacement, and precomputed upserts
must materialise their candidate embeddings before validation.
Validation precedes collection or schema creation, `VectorStoreIndex`,
backend upsert, row conversion, and generation change. Both write
entry points are covered: embeddings produced from `write_nodes` and
valid precomputed vectors pass through the same rule.

The diagnostic identity cannot be inferred reliably from a directly
constructed store because its attached embedding identity may be `None`.
`write_nodes` uses the composed provider/model identity already associated
with the write path; every direct `upsert_precomputed` caller supplies an
explicit provider/model diagnostic at call time. The diagnostic is sanitised
metadata only and never contains credentials.

A rejected batch never writes a valid subset. It must not create a collection
dimension or advance generation.

### D4: Experiment 14 imports the production validator — before destructive rebuild steps

The Experiment 14 builder calls the shared validator with its row
identifiers, vectors, collection, and model diagnostic **before
deleting or recreating an existing collection**. The current builder
order (`delete_collection` → `create_collection` → `upsert_precomputed`)
means validation placed only at the upsert seam runs after the existing
collection has already been destroyed; validation must precede the
delete. Parser preflight stays separate — that separation already
exists in the builder today and this change must not merge the two.
The builder's normal run writes parsed artefacts, preflight results, and index
build output. This change must not delete, rename, or regenerate existing
`output/` files merely to add validation.

### D5: Sequence before adapter-heavy follow-ons

This change lands before `implement-native-sparse-backend-strategy`
and before any Chroma migration work from `add-per-collection-persist-dirs`,
because they share the write/adapter path and need this boundary in
place first.

## Risks and Validation

Materialising embeddings before validation must keep ADR-048's bounded
per-source lifetime. Tests cover the pure validator, normal ingestion,
replacement, direct precomputed writes, and both backends.