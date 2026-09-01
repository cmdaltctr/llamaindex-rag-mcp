# Tasks: fix-embedding-and-structure-fidelity-1

Order matters. Group 1 is red-first: write the failing assertions before the
implementation, because every defect here is currently invisible to the suite.

## 1. Red-first coverage for the current defects

- [x] 1.1 Add a test asserting that a `pdf_inspector`-parsed chunk's
  `MetadataMode.EMBED` text contains none of `pdf_reader`, `pdf_type`,
  `pdf_confidence`, `page_count`, `file_path`, `file_type`, `file_size`, or
  the three date keys. Confirm it FAILS today.
- [x] 1.2 Add a test asserting the same chunk's EMBED text still contains
  `file_name`, `category`, `keywords`, `summary` when present.
- [x] 1.3 Add a test asserting that a `.pdf` read by a markdown-declaring
  reader produces chunks carrying `header_path`. Confirm it FAILS today.
- [x] 1.4 Add tests asserting `liteparse` and `pypdfium2` emit
  `page_label`. Confirm both FAIL today.
- [x] 1.5 Add a test that ingests a real `.py` file through
  `ingest_path_async` under the `codebase` profile **without patching
  `gather_supported_files`**, asserting `effective_strategy == "code"`.
  Confirm it FAILS today.
- [x] 1.6 Add a test asserting that changing the exclusion set changes
  `source_index_identity` and that an otherwise identical source is
  reprocessed rather than skipped.

## 2. Embedding-text composition

- [x] 2.1 Define `EXCLUDED_EMBED_METADATA_KEYS` in
  `core/ingestion/source_state.py` next to `_SOURCE_METADATA_KEYS`, covering
  parser telemetry (`pdf_reader`, `pdf_type`, `pdf_confidence`, `page_count`,
  `page`, `page_label`, `column`, `section_bbox`, `bbox_schema_version`) and
  filesystem bookkeeping (`file_path`, `file_type`, `file_size`,
  `creation_date`, `last_modified_date`, `last_accessed_date`).
- [x] 2.2 Union it into both exclusion lists inside `stamp_source_lineage`,
  preserving any keys the reader already excluded.
- [x] 2.3 Explicitly do NOT exclude `file_name`, `header_path`, `category`,
  `keywords`, `summary`, `document_title`, `content_type`. Add a comment
  naming D2 so the inversion of the LlamaIndex default is not "fixed" later
  by someone reading the upstream docstring.
- [x] 2.4 Verify 1.1 and 1.2 now pass.

## 3. Index identity

- [x] 3.1 Bump `_INDEX_IDENTITY_SCHEMA` 2 → 3.
- [x] 3.2 Add `embedding_text.excluded_keys` (sorted list) to the identity
  payload.
- [x] 3.3 Resolve the effective reader and `parser.text_format` before the
  unchanged check, add that value to the identity payload, and assert the
  later `BackendRead.text_format` agrees. Cover direct `auto` callers.
- [x] 3.4 Verify 1.6 passes and the existing change-detection tests still pass.

## 4. Reader text-format declaration

- [x] 4.1 Extend `integrations/pdf/registry.py` `register()` with required
  `text_format` and `page_provenance` metadata and a `describe(name)` accessor
  mirroring the document-backend registry.
- [x] 4.2 Declare `markdown` for `pdf_inspector`; `plain` for `liteparse`,
  `pypdf`, `pypdfium2`.
- [x] 4.3 Make registration fail when `text_format` is omitted.
- [x] 4.4 Add the same field to `core/ingestion/backends/registry.py` so the
  document backends declare it too (`local` → resolved from the PDF reader for
  PDFs, `plain` otherwise; `azure` → `plain`, it already sets `structured`).
- [x] 4.5 Carry the resolved format on `BackendRead` alongside `structured`.

## 5. Markdown routing by declared format

- [x] 5.1 Replace `is_markdown = file_path.suffix.lower() == ".md"` in
  `core/ingestion/chunker.py` with a check on the source suffix **or** the
  `BackendRead` declared format.
- [x] 5.2 Ensure the Markdown chunk-size budget and the three post-processing
  hooks apply on the reader-produced path identically to the `.md` path.
- [x] 5.3 Verify 1.3 passes.
- [x] 5.4 Confirm `.txt` and plain-reader `.pdf` chunk counts are byte-for-byte
  unchanged (guards the "Plain-format reader output is unchanged" scenario).

## 6. Page provenance

- [x] 6.1 Emit `page_label` (string) alongside `page` in both
  `integrations/pdf/liteparse.py` and `integrations/pdf/pypdfium.py`.
- [x] 6.2 Verify 1.4 passes for both direct readers and the `auto` chain.
- [x] 6.3 Make `page_label` optional (not required) in
  `transports/api/openapi.yaml` `SearchResult`.
- [x] 6.4 Hide the CLI Page column when every row's `page_label` is empty
  (`transports/cli/search.py`).
- [x] 6.5 Update `docs/guides/pdf-reader.md` (or the reader section of the
  configuration guide) with the per-reader page-provenance matrix, and test
  that `registry.describe()` exposes the same capability.

## 7. Profile-scoped ingestible extensions

- [x] 7.1 Add `ingest_extensions` to the chunking or ingestion settings block
  with the current seven as the default.
- [x] 7.2 Add source extensions to `config/profiles/codebase.yaml`.
- [x] 7.3 Thread the resolved set into `gather_supported_files` instead of
  reading the module constant; keep the constant as the default value.
- [x] 7.4 Build the watcher's patterns from the resolved set so watch and
  manual ingest cannot diverge.
- [x] 7.5 Verify 1.5 passes, and that a `documents`-profile ingest of the same
  directory still reports the source files as `skipped`.

## 8. Re-measure the quality gate

- [ ] 8.1 Re-run Tier 1 and confirm it still passes at its floors.
- [ ] 8.2 Re-run Tier 2 against real Ollama and record the new measurement.
- [ ] 8.3 If Recall@10 or MRR@10 regressed below the committed floor, revert
  D2 (`file_path` exclusion) and re-open it as an experiment. Do not lower the
  floor to fit.
- [ ] 8.4 Commit the re-measured baseline with the updated fixture-identity
  hashes.

## 9. Validation and documentation

- [ ] 9.1 `uv run pytest -m "not slow" --cov=rag_mcp` — all green, coverage
  floors held.
- [ ] 9.2 `uv run lint-imports` — no contract violations, no stale ignores.
- [ ] 9.3 `openspec validate fix-embedding-and-structure-fidelity-1 --strict`.
- [ ] 9.4 Update `AGENTS.md` gotcha #8 to name the new content-format routing
  rule alongside the existing `content_type` precedence note.
- [ ] 9.5 Add a CHANGELOG entry stating plainly that this release requires a
  re-ingest and why; document resumable mixed-era behaviour for compatible v3
  rows and the explicit delete/rebuild path for rows rejected by the lineage
  compatibility guard.
- [ ] 9.6 Write ADR: "Embedding text is a declared contract" recording D1, D2
  and D6.
