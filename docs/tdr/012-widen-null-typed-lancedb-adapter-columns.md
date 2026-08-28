# TDR-012: Widen Null-Typed LanceDB Adapter Columns Before Write

**Date:** 2026-08-19
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** lancedb | pyarrow | ingestion | stage3a

## Context

During Pause Gate 3A validation, `tests/test_ingestion_stage3_legacy.py` failed
deterministically on the LanceDB backend with:

```text
ValueError: Invalid input, cannot cast field 'doc_id' from Utf8 to Null
```

The Stage 3A replacement writes candidate chunks through `write_nodes`. A
legacy-seeded table blocked that write at the store level.

### Root Cause Analysis

The LlamaIndex LanceDB adapter derives the top-level `doc_id` column from the
node's SOURCE relationship. A node without that relationship writes `None`,
so Arrow types the column as `null`. The ingestion pipeline always sets the
SOURCE relationship, so every real table — including all pre-Stage-3 legacy
tables — carries `doc_id` as Utf8. The Null-typed state appeared only in a
test fixture that hand-built a bare `TextNode` (fixed separately in commit
`87023bc`).

Repair options verified against lancedb 0.37.1 / pylance 10.0.0:

- `table.add()` with typed data → `cannot cast field 'doc_id' from Utf8 to Null`.
- `table.alter_columns({"path": "doc_id", "data_type": pa.string()})` →
  `Cannot cast column "doc_id" from Null to Utf8`.
- `LanceTable` has no `add_column` in 0.37, so drop-and-re-add is unavailable
  (`drop_columns` succeeds but leaves the table unwritable).

## Decision

1. Fix the fixture to seed realistic legacy rows (SOURCE relationship set),
   commit `87023bc`.
2. Add a defensive store guard, commit with this TDR:
   `LanceVectorStore._widen_null_adapter_columns` in
   `src/rag_mcp/core/vectordb/lancedb.py`, called from `write_nodes` before
   `_evolve_for_nodes`. It mirrors the rebuild in
   `LanceTableMetadataMixin.evolve_metadata_fields`: read the table, cast to
   a schema where any top-level Null-typed column in
   `_ADAPTER_STRING_COLUMNS` (`id`, `doc_id`, `text`) becomes `pa.string()`,
   and overwrite in place, carrying the schema metadata bag across. A
   Null-typed column holds only nulls, so the re-type is lossless.

The guard is deliberate defence in depth: the pipeline cannot produce the
pathological state, but a hand-shaped or externally-written table no longer
wedges the store. It logs a warning naming the columns and this TDR.

Scope: the `write_nodes` path only. Tables created by `upsert_precomputed`
already carry `doc_id` as nullable string (`upsert_schema`), and the nested
metadata struct has its own null-upgrade rule inside
`evolve_metadata_fields`. A Null-typed `vector` column is out of scope: the
correct list type cannot be inferred from nulls.

## Consequences

### Positive

- Any existing LanceDB table with a Null-typed scalar adapter column becomes
  writable again without manual intervention.
- The failure mode now surfaces as a warning plus a successful write instead
  of a hard error.

### Negative

- The repair rewrites the whole table once (read, cast, overwrite), the same
  cost as a metadata-struct evolution. Acceptable because the state is
  pathological and the rewrite happens at most once per table.

### Neutral

- Table version history restarts at the rewrite, as with struct evolution.

## Alternatives Considered

| Option                                   | Rejected Because                                                                                          |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Fixture fix only (no store guard)        | Leaves the store wedged by any externally-created Null-typed table; the guard costs little.                |
| `alter_columns` cast                     | LanceDB 0.37 rejects the Null→Utf8 cast outright.                                                         |
| Drop the column, let the adapter re-add  | 0.37 has no `add_column`; the adapter merges rather than re-creates, so the write fails on a missing field. |
| Widen every Null-typed column, any name  | `vector` and `metadata` need their own types; widening those to string would corrupt the schema.           |

## How to Recognise / Handle This Again

1. Symptom: ingestion of one source fails with
   `cannot cast field '<col>' from Utf8 to Null` on LanceDB only.
2. Diagnose: `store._open_table(name).schema` shows the named column with
   type `null`.
3. Recovery: none needed on current code — the next `write_nodes` call
   widens the column and logs
   `Widened null-typed column(s) [...] to string (TDR-012)`. On older code,
   rebuild the collection or re-ingest after deleting the affected table.

## Revisit Triggers

- A lancedb release that supports `alter_columns` Null→Utf8 casts or exposes
  `add_column` (cheaper in-place repair).
- Any new write path that constructs nodes outside the ingestion pipeline
  (would make the guarded state reachable rather than pathological).

## References

- Commit `87023bc` — realistic legacy fixture (SOURCE relationship).
- Store guard: `src/rag_mcp/core/vectordb/lance_meta.py`
  (`LanceTableMetadataMixin._widen_null_adapter_columns`,
  `_ADAPTER_STRING_COLUMNS`); called from `write_nodes` in
  `src/rag_mcp/core/vectordb/lancedb.py`. Extracted from `lancedb.py` in
  `65695da` after the guard tripped the 500-line file ceiling.
- Regression test: `tests/test_lancedb_store.py::test_write_nodes_widens_null_typed_doc_id_column`.
- Related: ADR-048 (bounded failure-safe ingestion), TDR-011 (pre-calibration
  audit validation), `evolve_metadata_fields` in
  `src/rag_mcp/core/vectordb/lance_meta.py`.
