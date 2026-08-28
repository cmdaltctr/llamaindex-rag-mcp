# Design: add-stable-source-chunk-lineage

## Context

`ingest_path_async` resolves the requested path before discovering source files.
For each source, `pipeline.py` hashes the bytes, builds the complete index-shaping
identity, and derives `source_version`. `source_state.py` then stamps version,
attempt, chunk-count, and chunk-index metadata and replaces `BaseNode.id_` with
an attempt-specific row ID. `replacement.py` embeds before that stamp, writes
the candidate attempt, verifies its durable count, and only then removes stale
rows for the same `file_path`.

This design already separates source versions from replacement attempts. It
must be extended, not replaced. In particular, the attempt-specific row ID is a
safety mechanism: using one stable chunk ID as the database primary key would
allow a forced re-ingestion to overwrite the last durable row before the full
candidate attempt is verified.

The local document backend currently uses `filename_as_id=True`, so parsed
nodes inherit the file path as their LlamaIndex `SOURCE` relationship. LlamaIndex
defines source membership through `NodeRelationship.SOURCE`; the deprecated
`ref_doc_id` property reads that relationship's node ID. The stable logical
source should therefore occupy the `SOURCE` relationship, while `file_path`
remains ordinary human-readable metadata.

## Goals

- Name one logical source independently of its current bytes and index version.
- Name one textual chunk independently of a replacement attempt.
- Preserve ordered membership for every complete source version.
- Keep identity metadata out of embedding and LLM text.
- Preserve ADR-048 bounded and failure-safe replacement.
- Keep vector stores and transports free of lineage business logic.

## Non-Goals

- Byte-perfect source-file reconstruction from chunks.
- Move/rename identity tracking, source registries, or sidecar state.
- Deduplicating equal content at different paths or collections.
- Changing parser, chunker, embedding, sparse, reranker, or citation policy.
- Adding parent-window retrieval or a reconstruction API in this change.
- Retrofitting experiment-only precomputed rows.

## Decisions

### D1: `core/ingestion/source_state.py` owns all source/chunk identity

`source_state.py` already owns source-content, index, version, attempt, count,
index, and row-ID stamping. It gains the two new constants and deterministic
helpers. No `identity` service or cross-layer model is introduced.

`core/vectordb/identity.py` remains unrelated: it protects a collection's
embedding-space identity. It must not acquire source/chunk business logic.

### D2: `source_id` identifies the canonical path, not file content

The production pipeline uses the canonical absolute `file_path` already
produced beneath `Path(path).expanduser().resolve()`. The identifier is:

```text
source_id = "src_" + sha256("file\0" + canonical_file_path)
```

The digest is lower-case hexadecimal and inputs use UTF-8 with NUL separators.
The collection name is not part of the formula, so one source has the same
identity when intentionally indexed into multiple collections.

Consequences:

- editing a file at the same canonical path keeps `source_id`;
- equal bytes at different paths produce different `source_id` values and the
  same `source_content_hash`;
- moving or renaming a source produces a new `source_id`;
- the original `file_path` remains available for display and diagnostics.

### D3: retain the existing content and index-version identities

`source_content_hash` remains SHA-256 over the exact original file bytes.
`source_version` remains SHA-256 over `source_content_hash`, a NUL separator,
and `source_index_identity`. This is necessary because equal bytes indexed with
a different parser, chunker, metadata shape, or embedding configuration are a
different searchable representation.

No `document_hash` alias is added. The name `source_content_hash` applies
equally to documents, code, and configuration files and avoids a migration for
terminology alone.

### D4: `chunk_id` identifies stored chunk text within one source version

After parsing/chunking and metadata extraction have completed, the production
pipeline derives the exact text-only content with
`node.get_content(metadata_mode=MetadataMode.NONE)`. It calculates:

```text
chunk_text_hash = sha256(text_only_chunk_utf8)

chunk_id = "chk_" + sha256(
    source_id
    + "\0" + source_version
    + "\0" + decimal_source_chunk_index
    + "\0" + chunk_text_hash
)
```

Including the zero-based ordinal distinguishes repeated identical text within
one source. Including the text hash catches a changed parser/chunker output at
the same ordinal. The embedding payload is deliberately not hashed: extracted
metadata may vary without changing the identity of the textual chunk, and
embedding execution identity already belongs to `source_index_identity` and
the replacement attempt.

### D5: stable chunk identity and vector-row identity remain separate

Every candidate attempt receives a fresh `source_attempt`. Its vector-store
row ID remains internal and attempt-specific:

```text
vector_row_id = sha256(source_id + "\0" + source_attempt + "\0" + chunk_id)
```

A forced re-ingestion of an identical version therefore reproduces the same
`chunk_id` values but writes distinct candidate row IDs. Old and candidate rows
can coexist until the existing write-verify-delete transaction shape succeeds.

### D6: stamp and exclude identity before embedding

The current code embeds first and stamps source metadata afterwards. The new
order is:

1. parse, chunk, and extract metadata;
2. calculate chunk text and stable lineage;
3. stamp lineage, source version, attempt, count, and index metadata;
4. add every machine identity/replacement key to both
   `excluded_embed_metadata_keys` and `excluded_llm_metadata_keys`;
5. set `NodeRelationship.SOURCE` to `RelatedNodeInfo(node_id=source_id)`;
6. embed missing nodes;
7. write, verify, and remove stale rows for the same `source_id`.

This order makes persisted metadata complete before the write while ensuring
identifiers never alter embedding vectors or LLM-visible content.

### D7: ordered reconstruction is a metadata invariant

For one `source_id` plus `source_version`, a complete candidate with `N` chunks
has:

- one shared `source_chunk_count == N`;
- unique, contiguous `source_chunk_index` values `0..N-1`;
- one unique `chunk_id` per index.

Consumers can select one source version, confirm the expected count, and sort
by index to reconstruct the indexed chunk sequence. This supports citations,
neighbour selection, and completeness checks. It does not reverse parser
transformations, remove overlap safely for every chunker, or reproduce original
PDF bytes/layout. The source file and `source_content_hash` remain the authority
for the original bytes.

Previous/next IDs are not stored because they duplicate the ordered invariant.

### D8: lineage persists in metadata and survives every retrieval path

Every production-ingested node stores at least `source_id`,
`source_content_hash`, `source_index_identity`, `source_version`, `chunk_id`,
`source_attempt`, `source_chunk_count`, `source_chunk_index`, and `file_path`.
Both existing stores already persist flat node metadata, so no vector-store API
or backend-specific lineage code is needed.

Public search results add `source_id`, `source_version`, `chunk_id`,
`source_chunk_index`, and `source_chunk_count` from metadata. Dense and BM25
construction attach them before fusion; fusion and reranking preserve them.
The attempt-specific row ID continues to be removed from ordinary public
results. Existing metadata filtering can select `source_id`, `source_version`,
or `chunk_id` without a new query API.

Document listing groups by `source_id` and retains the human-readable source
path. Path deletion and replacement cleanup calculate/select the same
`source_id`, so `file_path` is no longer the only machine key.

### D9: make a clean introduction, not a speculative migration

No production documents have been ingested, and experiment indexes use
`upsert_precomputed()` with experiment-owned identifiers under frozen
corpus/index manifests. The change therefore adds no alias, dual-write,
startup migration, or legacy-lineage fallback. The production lineage contract
applies to `ingest_path_async` nodes, not arbitrary precomputed rows.

Silently treating an unexpected pre-lineage row as a different source would
leave duplicate path rows after ingestion. Before mutation, the pipeline
therefore compares rows already selected by the canonical `file_path` with rows
carrying the derived `source_id`. If path rows lack or disagree on `source_id`,
the source fails with a clear rebuild instruction and the stored rows remain
unchanged. This is an incompatibility guard, not a migration path.

The current pre-ADR-048 regression that auto-replaces a row missing
`source_attempt` is superseded for production ingestion by this clean lineage
boundary: a row missing `source_id` is rejected, not upgraded. If compatibility
is needed later, it requires a separately designed migration rather than a
fallback hidden in the normal path.

### D10: deterministic tests are sufficient

The formulas, ordering, metadata exclusions, source relationship, replacement
safety, store persistence, filtering, and result propagation are correctness
properties. Focused unit and cross-backend contract tests decide them. No model
quality experiment or default calibration is required.

## Risks and Mitigations

| Risk | Mitigation |
| --- | --- |
| Stable `chunk_id` accidentally used as the row primary key | Contract tests force identical chunk IDs but distinct attempt row IDs on a forced re-ingest. |
| Identity metadata changes embeddings | Capture embedding text in tests and prove it is unchanged by lineage stamping. |
| Dense results carry lineage but BM25/hybrid loses it | Exercise dense, BM25, fusion, and reranked result paths with the same fixture. |
| A move leaves the old source indexed | State move semantics honestly; move tracking is not claimed. Delete the old path and ingest the destination. |
| Reconstruction is mistaken for original-file recovery | Specification limits the guarantee to the ordered indexed chunk representation. |
| Implementation conflicts with the open embedding validator | Sequence this change after `validate-embedding-write-contract`. |
