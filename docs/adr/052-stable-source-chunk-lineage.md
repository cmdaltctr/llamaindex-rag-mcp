# ADR-052: Stable Source and Chunk Lineage

**Date:** 2026-08-28
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

Ingestion already records `source_content_hash`, `source_index_identity`,
`source_version`, `source_attempt`, `source_chunk_count`, and
`source_chunk_index` (ADR-048). Those fields detect unchanged files and make
failure-safe replacement possible, but they leave two gaps. `file_path` acts
as both the human-readable locator and the effective logical source key.
`BaseNode.id_` is deliberately attempt-specific, so the same unchanged chunk
receives a new vector-row ID on every forced replacement, and ordinary search
results strip that row ID. The system could count and order chunks for a
stored path, yet nothing named "source A" or "chunk A3" independently of one
ingestion attempt.

Two constraints shaped the design. First, the attempt-specific row ID is a
safety mechanism: promoting a stable chunk ID to the store primary key would
let a forced re-ingestion overwrite the last durable rows before the full
candidate attempt is verified. Second, the owner confirmed that no production
documents have been ingested, so a migration would be speculative work with
nothing to migrate.

## Decision

1. **`core/ingestion/source_state.py` owns all source and chunk identity.**
   The module already stamped content, index, version, attempt, count, and
   index metadata. It gains `SOURCE_ID_KEY`, `CHUNK_ID_KEY`, and the
   deterministic helpers `build_source_id`, `build_chunk_id`, and
   `build_source_row_id`. No identity service, registry, or vector-store API
   is added, and `core/vectordb/identity.py` stays focused on
   embedding-space identity.

2. **`source_id` identifies the canonical path, not the content.** The
   formula is `"src_" + SHA-256("file\0" + canonical_file_path)` over UTF-8
   input with a NUL separator and lower-case hexadecimal output.
   `pipeline.py` builds it once per source from the canonical path that
   `ingest_path_async` already resolves. Editing a file in place keeps its
   `source_id`, and the collection name is not part of the formula.

3. **`chunk_id` identifies stored chunk text within one source version.**
   After parsing, chunking, and metadata extraction, the pipeline hashes the
   `MetadataMode.NONE` text and computes `"chk_" + SHA-256(source_id + NUL +
   source_version + NUL + decimal index + NUL + text hash)`. The zero-based
   ordinal separates repeated identical text; the text hash catches changed
   chunker output at the same ordinal. The embedding payload is deliberately
   not hashed.

4. **Stable identity stays separate from row identity.** The vector row ID
   is `SHA-256(source_id + NUL + source_attempt + NUL + chunk_id)` with a
   fresh `source_attempt` per replacement. Identical re-ingestion reproduces
   the same `chunk_id` values but writes new row IDs, so candidate and
   durable attempts coexist until write-verify-delete verification succeeds
   (ADR-048). A stable `chunk_id` is never a store primary key.

5. **Move semantics are path-based and stated honestly.** Identity does not
   follow a moved or renamed file: the destination is a new logical source,
   the operator deletes the old path, and the destination is ingested
   normally. Equal bytes at two paths share `source_content_hash` and keep
   different `source_id` values; content is never deduplicated.

6. **Lineage is stamped before embedding and excluded from model text.**
   `stamp_source_lineage` writes the complete metadata set (`file_path` plus
   the eight source and chunk keys), adds every machine key to both
   `excluded_embed_metadata_keys` and `excluded_llm_metadata_keys`, and sets
   each node's `NodeRelationship.SOURCE` to `source_id` (the maintained
   LlamaIndex contract) rather than the deprecated `ref_doc_id` property.
   `file_path` remains ordinary human-readable metadata.

7. **Pre-lineage rows fail before mutation.** Before any parse, embedding,
   or store write, the pipeline compares rows selected by the canonical
   `file_path` with rows carrying the derived `source_id`. Any lack or
   disagreement raises `IncompatibleSourceLineageError` with a rebuild
   instruction, and the stored rows are left unchanged. The change adds no
   migration, no `document_hash` alias, no dual write, and no legacy
   fallback: the guard is an incompatibility boundary, not a migration path.

8. **Retrieval reads lineage as plain metadata keys.** `dense.py` defines
   `LINEAGE_METADATA_KEYS` (`source_id`, `source_version`, `chunk_id`,
   `source_chunk_index`, `source_chunk_count`) and attaches them to dense
   and BM25 rows before fusion and reranking. Retrieval never imports the
   ingestion layer; the keys are plain persisted metadata. Ordinary public
   results continue to hide the attempt-specific row ID, and existing
   metadata filters select `source_id`, `source_version`, or `chunk_id`
   without a new query API.

## Consequences

### Positive

- Citations, neighbour lookup, and ordered reconstruction survive
  replacement attempts: one `source_id` plus one `source_version` selects a
  complete chunk set whose indices run `0..N-1` under a shared
  `source_chunk_count`.
- Listing groups by `source_id`, and deletion preview plus path deletion
  resolve the same derived identity through one shared path rule, so
  `./`-prefixed and absolute paths address the same source.
- Lineage can never perturb embeddings or LLM-visible text: both exclusion
  lists carry the keys, and stamping happens before embedding.
- ADR-048 safety is intact. The write-verify-delete ordering is unchanged,
  and contract tests force stable chunk IDs alongside distinct row IDs.

### Negative

- Search results gain five additive fields and `list_documents` rows gain
  `source_id`, so consumers see a wider, still additive, result shape.
- A moved or renamed file needs explicit cleanup: the old path stays indexed
  until it is deleted, and the destination ingests as a new source.
- A collection that predates lineage turns every re-ingest of an affected
  path into a hard error until the operator rebuilds that data.

### Neutral

- No production documents were ingested, so the clean break costs nothing
  today and no migration is owed.
- Experiment indexes built through `upsert_precomputed()` keep their
  experiment-owned IDs under frozen corpus and index manifests; production
  lineage never scans them. Rows without lineage surface as `null` lineage
  fields in search results and `source_id: null` in listings.
- Ordered reconstruction recovers the indexed chunk representation only.
  The source file and `source_content_hash` remain authoritative for the
  original bytes and layout.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Stable `chunk_id` as the vector-store primary key | A forced re-ingestion would overwrite durable rows before the candidate attempt is verified, breaking ADR-048 safety. |
| Content-based `source_id` that follows moves | Equal bytes at two paths would collide, and deduplication would change deletion and listing semantics; the path-based ID stays deterministic and honest about moves. |
| Migration or alias for pre-lineage rows | Nothing to migrate: no production documents exist, and a hidden fallback in the normal path would mask schema mixing instead of surfacing it. |
| A `document_hash` alias alongside `source_content_hash` | A duplicate identity with a second name invites drift and buys nothing. |
| Previous/next chunk IDs per chunk | They duplicate the ordered invariant already carried by `source_chunk_index` and `source_chunk_count`, and every edit would invalidate them. |
| A dedicated lineage service or cross-layer model | The identity seam already existed in `source_state.py`; a new layer would add indirection without a second consumer contract. |

## References

- OpenSpec change: `openspec/changes/add-stable-source-chunk-lineage/`
- Identity seam: `src/rag_mcp/core/ingestion/source_state.py`
- Orchestration: `src/rag_mcp/core/ingestion/{pipeline,replacement}.py`
- Consumers: `src/rag_mcp/core/ingestion/{loader,writer}.py` and
  `src/rag_mcp/core/retrieval/dense.py`
- Contract tests: `tests/test_source_chunk_lineage.py`,
  `tests/test_lineage_store_contract.py`,
  `tests/test_lineage_retrieval.py`,
  `tests/test_ingestion_stage3_legacy.py`
- Related decisions: ADR-048 (bounded failure-safe ingestion), ADR-051
  (fail-closed embedding write contract)
