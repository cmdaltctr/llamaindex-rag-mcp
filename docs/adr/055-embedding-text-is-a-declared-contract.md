# ADR-055: Embedding Text Is a Declared Contract

**Date:** 2026-09-01
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari

## Context

The 2026-09-01 RAG audit found that embedding text was an accident rather
than a contract. LlamaIndex prepends node metadata to the chunk before the
embedding model, and only the eight lineage keys (ADR-052) were excluded.
Every other metadata key a reader attached therefore entered the vector. On
the default PDF path this put four lines of parser telemetry
(`pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`) and a
machine-specific absolute `file_path` in front of every chunk, uniformly
diluting the chunk's own signal. The defect was silent: no error, no
warning, no failing test.

The same audit found that the heading structure `pdf_inspector` produced
was discarded one step later, because the chunker selected the
heading-aware path with a `.md` suffix check that is false for a `.pdf`.
That routing defect is fixed by the same change and recorded here because
its invalidation semantics are inseparable from the embedding-text
contract: both change what every stored vector encodes.

Three forces shaped the decision. First, `stamp_source_lineage`
(`core/ingestion/source_state.py`) is the single production write path for
metadata exclusion lists — every node passes through it exactly once, which
makes it the natural owner of the contract. Second, any change to the
exclusion set or the routing rule silently invalidates every stored vector
unless index identity records those inputs. Third, a corpus rebuild must
stay failure-safe and resumable per source (ADR-048); a change of this
kind must not force an atomic collection rebuild.

## Decision

1. **The exclusion set lives in `stamp_source_lineage` (design D1).**
   `EXCLUDED_EMBED_METADATA_KEYS` is a module constant next to
   `_SOURCE_METADATA_KEYS` in `core/ingestion/source_state.py`. It covers
   parser telemetry (`pdf_reader`, `pdf_type`, `pdf_confidence`,
   `page_count`, `page`, `page_label`, `column`, `section_bbox`,
   `bbox_schema_version`) and filesystem bookkeeping (`file_path`,
   `file_type`, `file_size`, `creation_date`, `last_modified_date`,
   `last_accessed_date`). At stamp time it is unioned into both
   `excluded_embed_metadata_keys` and `excluded_llm_metadata_keys`,
   preserving any keys the reader already excluded.

2. **The contract is a deny-list, not an allow-list.** An allow-list would
   silently drop `header_path` and any future extractor output the moment
   someone adds a metadata field. A deny-list fails visibly: a new noisy
   key gets embedded and shows up in the quality gate, rather than a new
   useful key being dropped invisibly. Visible failure is the cheaper
   failure.

3. **`file_path` is excluded; `file_name` is retained (design D2).** This
   deliberately inverts the LlamaIndex default, which excludes `file_name`
   and keeps `file_path` ("extreme important context"). For this project
   that default is backwards. `file_path` is a machine-specific absolute
   path, constant across every chunk of a document, so it adds no
   discriminative signal within a document and its directory components
   are deployment noise. `file_name` carries genuine topical signal — a
   filename such as `Kalai et al. - 2025 - Why Language Models
   Hallucinate.pdf` is useful query-matching context. Neither key is
   removed from stored metadata; `source` in every result row still comes
   from `file_path`. The retained set is named in
   `_RETAINED_EMBED_METADATA_KEYS` (`file_name`, `header_path`,
   `category`, `keywords`, `summary`, `document_title`, `content_type`)
   and is removed from reader-set exclusion lists so the declared
   contract, not the LlamaIndex default, decides what is embedded.

4. **Index identity absorbs both new inputs and the schema version bumps
   (design D6).** `_INDEX_IDENTITY_SCHEMA` goes from 2 to 3. The identity
   payload gains `embedding_text.excluded_keys` (the sorted set, read at
   call time so test-time overrides stay observable) and
   `parser.text_format` (the reader's declared emitted-text format,
   resolved before the read so a declaration change invalidates exactly
   like a chunk-size change). The schema bump alone forces a one-time
   global reprocess, which is correct here: every stored vector predates
   the contract. The key list itself means future changes to the set
   invalidate precisely, without another schema bump.

5. **Invalidation is per-source, incremental, and resumable — not an
   atomic collection rebuild.** This identity is per source row, not the
   collection embedding identity. Lineage-compatible old-era sources are
   never considered current and each re-processes on the next corpus
   ingest; an interrupted run may temporarily mix old and new eras in one
   collection, and the next run resumes rather than skips an old-era
   source. Each replacement stays failure-safe per source (ADR-048).
   Pre-lineage or incompatible rows continue to fail
   `assert_source_lineage_compatible()` before any mutation and require
   the documented explicit delete/rebuild path. The change neither weakens
   that guard nor changes provider/model mismatch rejection.

6. **The retrieval-quality gate gated decision 3.** Because D2 changes
   retrieval behaviour, the Tier-2 floors were re-measured after the
   change rather than assumed. Tier 1 held at floor and Tier 2
   (`qwen3-embedding:0.6b`, Ollama 0.32.13) measured Recall@10 1.0 and
   MRR@10 1.0 against floors of 0.97/0.97 — the ceiling, with fixture
   identities unchanged (commit `d2f6560`). No revert condition fired. If
   the floors had regressed, D2 would have been reverted and re-opened as
   an experiment rather than forced through.

## Consequences

### Positive

- Embedding text is the same for every reader: parser telemetry and
  machine-specific paths never enter a vector, regardless of which reader
  ran or what a future reader emits.
- `file_name`, `header_path`, and extractor output (category, keywords,
  summary) now contribute retrieval signal the LlamaIndex default would
  have dropped.
- A future change to the exclusion set or a reader's declared format
  invalidates exactly the affected sources; no second global schema bump
  is owed for key-list edits.
- The upgrade cost is one re-ingest that resumes cleanly when
  interrupted, rather than a manual collection rebuild.

### Negative

- Every existing corpus re-processes on the first ingest after upgrade:
  `files_skipped_unchanged` drops to zero once, and the operator sees a
  full-length run.
- An interrupted upgrade run leaves mixed-era sources in one collection
  until the next ingest completes. This is safe but must be documented,
  not merely tolerated.
- Deny-list maintenance is an obligation: a reader that emits a new noisy
  metadata key will embed it until someone adds the key to the constant.
  The quality gate is the intended detector.

### Neutral

- Retrieval floors were re-measured and re-committed at the same values;
  the gate baseline moves only through its own evidence discipline.
- `file_path` remains stored and displayed; only its contribution to
  embedding text is removed.
- Chunk counts change for markdown-emitting readers routed onto the
  heading-aware path (99 chunks with no `header_path` became 60 chunks all
  carrying it, measured on the audit's reference PDF). Experiments pin
  their own settings, and fixture-identity hashes flag the drift.

## Alternatives Considered

| Option | Rejected because |
| --- | --- |
| Per-adapter exclusion in each PDF reader | Four edit sites, no central contract, silently incomplete for `SimpleDirectoryReader` defaults and any future reader. |
| An allow-list of embedded keys | Fails invisibly: a new useful key is dropped the moment it is added. A deny-list fails visibly through the quality gate. |
| Keep the LlamaIndex default (`file_path` in, `file_name` out) | Machine-specific absolute paths carry no within-document discriminative signal; filenames carry topical signal the default discards. |
| Sniff text for markdown headers instead of a declaration | Content sniffing misfires on plain text containing `#` comments; a reader author knows the format deterministically. |
| Reuse the `structured_output` backend flag for routing | It means something else ("pre-structured paragraphs, skip file-level extraction"); overloading it couples two unrelated decisions. |
| Atomic collection rebuild on schema change | Breaks ADR-048 per-source failure safety and forces a manual rebuild for what is, per source, an ordinary replacement. |

## References

- OpenSpec change: `openspec/changes/fix-embedding-and-structure-fidelity-1/`
  (design decisions D1, D2, D6; capability spec `embedding-text-composition`)
- Contract owner: `src/rag_mcp/core/ingestion/source_state.py`
  (`EXCLUDED_EMBED_METADATA_KEYS`, `_RETAINED_EMBED_METADATA_KEYS`,
  `build_index_identity`, `stamp_source_lineage`)
- Routing consumer: `src/rag_mcp/core/ingestion/chunker.py` and
  `src/rag_mcp/integrations/pdf/registry.py` (declared `text_format`)
- Quality-gate evidence: commit `d2f6560` — Tier 1 1.0/1.0 at floor; Tier 2
  Recall@10 1.0, MRR@10 1.0 against 0.97/0.97 floors;
  `tests/quality/baseline.json`
- Upgrade notice: `docs/guides/ingestion.md` — "Upgrading to this release"
- Related decisions: ADR-048 (bounded failure-safe ingestion), ADR-051
  (fail-closed embedding write contract), ADR-052 (stable source and chunk
  lineage), ADR-050 (`pdf_inspector` default reader)
