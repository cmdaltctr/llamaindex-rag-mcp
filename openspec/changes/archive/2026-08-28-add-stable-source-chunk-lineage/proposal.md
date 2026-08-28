# Proposal: add-stable-source-chunk-lineage

## Why

Production ingestion already records `source_content_hash`,
`source_index_identity`, `source_version`, `source_attempt`,
`source_chunk_count`, and `source_chunk_index`. These fields make unchanged-file
detection and failure-safe replacement possible, but they do not provide two
stable public identities:

- `file_path` is both the human-readable locator and the effective logical
  source key;
- `BaseNode.id_` is deliberately attempt-specific, so the same unchanged chunk
  receives a different vector-row ID during a forced replacement;
- public search removes that internal row ID, leaving no stable chunk reference
  for citations, neighbour lookup, or ordered reconstruction.

As a result, the system can count and order chunks for one stored path, but it
cannot name “source A” and “chunk A3” independently of one ingestion attempt.
The missing distinction becomes more important when one source has many chunks,
when a source is re-indexed under new settings, and when later features need to
retrieve adjacent chunks or verify that a complete chunk sequence is present.

## What Changes

- Add a deterministic `source_id` for the canonical absolute source path. It
  stays stable while that path is edited and intentionally changes when the
  source moves or is copied to another path.
- Add a deterministic `chunk_id` for one exact stored-text chunk at one ordinal
  within one `source_version`.
- Keep `source_content_hash` as the canonical SHA-256 identity of original file
  bytes. Do not add or alias a duplicate `document_hash` field.
- Keep `source_attempt` and the vector-store row ID attempt-specific. Stable
  `chunk_id` values SHALL NOT become database primary keys because candidate
  and durable attempts must coexist until replacement is verified.
- Stamp lineage after parsing/chunking and metadata extraction, but before
  embedding. Exclude all lineage and replacement metadata from embedding and
  LLM metadata text.
- Set each LlamaIndex node's `SOURCE` relationship to `source_id`, while
  retaining `file_path` as human-readable metadata.
- Make every production-ingested source version an ordered chunk set through
  the existing zero-based `source_chunk_index` and `source_chunk_count` fields.
- Persist the lineage fields through both vector-store implementations and
  expose stable lineage in dense, BM25, hybrid, and reranked public search
  results without exposing the attempt-specific row ID.
- Resolve document listing, unchanged-version selection, replacement cleanup,
  deletion preview, and path deletion through `source_id` rather than using
  `file_path` as the sole machine identity.

## Capabilities

### New Capabilities

- `source-chunk-lineage`: deterministic source/chunk identity, ordered chunk
  membership, LlamaIndex source relationships, persistence, retrieval, and
  reconstruction boundaries.

### Modified Capabilities

- `document-deletion`: path deletion resolves the same canonical `source_id`,
  and the stale delete-before-read re-ingestion wording is corrected to the
  accepted write-verify-delete replacement behaviour.

## Scope Boundaries

- No persistent identity registry, sidecar manifest, or caller-supplied source
  identity.
- No identity preservation across a move or rename. A new canonical path is a
  new logical source; removing the old path remains a separate deletion event.
- No content deduplication. Equal bytes at two paths share
  `source_content_hash` but retain different `source_id` values.
- No previous/next chunk IDs. Neighbours derive from `source_id`,
  `source_version`, and `source_chunk_index`.
- No promise to reconstruct original PDF bytes or layout from vector-store
  chunks. The contract reconstructs the ordered indexed chunk representation;
  the original source file remains authoritative.
- No metadata alias, dual write, startup migration, or automatic legacy
  collection migration. The owner confirmed that no production documents have
  been ingested. If an unexpected row for the same `file_path` lacks the new
  lineage, ingestion fails before mutation with a rebuild instruction rather
  than mixing schemas.
- No lineage requirement for experiment-only `upsert_precomputed()` rows.
  Existing experiment indexes retain their experiment-specific IDs and remain
  governed by their frozen corpus/index manifests.
- No new dependency, configuration flag, vector-store method, registry, or
  transport business logic.

## Impact

**Code:** `core/ingestion/source_state.py` remains the identity owner;
`pipeline.py` and `replacement.py` orchestrate it. Focused consumers change in
`core/ingestion/{loader,writer}.py` and `core/retrieval/{dense,pipeline}.py`.
Vector-store adapters retain their existing generic node/metadata persistence
contract and receive no lineage business logic.

**Stored data:** new production-ingested rows add `source_id` and `chunk_id`.
Existing source/version/attempt/order fields and `file_path` remain. No
migration is provided or needed for the confirmed project state; an
incompatible pre-lineage source is rejected without modifying its rows.

**Public results:** search results gain stable additive lineage fields. The
internal attempt-specific row ID remains hidden unless existing diagnostics
explicitly request internal IDs.

**Tests:** deterministic formula, ordering, exclusion, replacement, deletion,
listing, retrieval-path preservation, and real ChromaDB/LanceDB contract
coverage. No empirical model-quality experiment is required.

## Sequencing

Implement after `validate-embedding-write-contract`, because both changes touch
`core/ingestion/replacement.py` and the embedding/write boundary. Do not
implement concurrently with `implement-native-sparse-backend-strategy`, because
both touch sparse result construction in `core/retrieval/pipeline.py`.
