# Evidence: production document dispatch and ingestion store forwarding

Scope: tasks 1.2 (dispatch part), 2.1, 2.2, 2.3, and the ingestion half of 3.1.

Worktree: `llamaindex-rag-mcp-v3-feat-repair-modular-core-boundaries`, branch
`feat/repair-modular-core-boundaries`, base commit `3ca82a0`. Date 2026-10-13.

Interpreter (no install, no `.venv` in the worktree):

```bash
cd <worktree>
PYTHONPATH=src /Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3/.venv/bin/python \
  -m pytest <tests> -q -p no:cacheprovider
```

All tests use fake reads, fake metadata calls and fake store writes. No model,
network, Ollama or real vector store is used.

## Regression tests

New file `tests/test_document_registry_dispatch.py` (10 tests). A sentinel
`sentence` strategy is registered through the real chunking registry
(`registry._registry` and `registry._cache`), so a chunker branch that calls
private sentence helpers cannot satisfy the tests.

| Test | Proves |
|---|---|
| `test_both_document_branches_invoke_registered_sentence_strategy` (5 cases) | Structured and unstructured branches, for plain, `.md`, and reader-declared Markdown (`.pdf` + `text_format="markdown"`), await the registered callable with the documents, path, Markdown declaration, effective chunk size, overlap, settings and resolved Markdown value. `content_type`, metadata attachment and the `metadata_degraded` marker survive. |
| `test_chunk_overrides_reach_registered_strategy` | Explicit `chunk_size`/`chunk_overlap` reach the strategy. |
| `test_markdown_postprocessing_runs_exactly_once` (structured, unstructured) | `_postprocess_markdown_nodes` runs once per file; heading prefix is not doubled. |
| `test_store_keyword_reaches_metadata_extraction` | `read_and_chunk_file_async(..., store=)` forwards `store=` by keyword to `extract_metadata_with_status_async`. |
| `test_ordinary_ingestion_invokes_registered_strategy_and_forwards_store` | `ingest_path_async(..., store=S)` over a temp directory (`.txt` + `.md`) reaches the sentinel for both files and passes `S` to metadata extraction. |

## Before the fix (unchanged `chunker.py` / `pipeline.py`)

```bash
PYTHONPATH=src .../python -m pytest tests/test_document_registry_dispatch.py -q -p no:cacheprovider
```

Result: **8 failed, 2 passed**.

- 5 branch cases and the override case: sentinel never called. Output was the
  real splitter text (`'# Heading\n\nBody text.' != 'SENTINEL-STRATEGY-OUTPUT'`,
  `IndexError` on empty call list, or `AttributeError: 'object' object has no
  attribute 'model_token_aware'` because the private helper consumed the fake
  Markdown value directly).
- `test_store_keyword_reaches_metadata_extraction`: `TypeError:
  read_and_chunk_file_async() got an unexpected keyword argument 'store'`.
- Ordinary ingestion: `assert [] == ['notes.md', 'plain.txt']` (sentinel bypassed).
- The two exactly-once tests passed before the fix. They guard against a
  double post-processing regression introduced by the fix, and the mutation
  check below proves they are sensitive.

## Fix

- `src/omrg/core/ingestion/chunker.py`: new `_chunk_documents()` resolves
  `_chunking_get("sentence")` and awaits it. Both document branches call it.
  The direct `_split_documents_sync` / `_postprocess_markdown_nodes` imports
  and the chunker's own Markdown post-processing are removed, so
  post-processing runs once, inside the strategy. `asyncio` import dropped
  (unused). New keyword-only `store: Any = None`, forwarded as
  `extract_metadata_with_status_async(file_text, file_path.name, resolved, store=store)`.
- `src/omrg/core/ingestion/pipeline.py`: passes `store=resolved_store` into
  `read_and_chunk_file_async`.

Positional arguments of `read_and_chunk_file_async` are unchanged.

## After the fix

```bash
PYTHONPATH=src .../python -m pytest tests/test_document_registry_dispatch.py -q -p no:cacheprovider
```

Result: **10 passed**.

## Mutation check (fix reverted briefly, then restored and diff-verified)

| Mutation | Result |
|---|---|
| Structured branch calls private helpers again | 3 failed, 7 passed |
| Unstructured branch calls private helpers again | 4 failed, 6 passed |
| Chunker drops `store=store` on metadata call | 2 failed, 8 passed |
| Pipeline drops `store=resolved_store` | 1 failed, 9 passed |
| Chunker post-processes Markdown a second time after the strategy | 5 failed, 5 passed |

## Related existing tests (task 2.2)

Files: `test_async_ingest_responsiveness`, `test_chunking_hardening`,
`test_core_coverage_v2`, `test_coverage_gaps_v2`, `test_document_backends`,
`test_embedding_text_composition`, `test_ingestion_parallel`,
`test_ingestion_stage3_legacy`, `test_ingestion_stage3`,
`test_lineage_store_contract`, `test_magika_parser_boundaries`,
`test_markdown_chunking`, `test_metadata_degradation`,
`test_model_token_markdown_chunking`, `test_normalise_reader_chunker`,
`test_precalibration_audit_regressions`, `test_profiles`,
`unit/test_ingestion_pdf_extractor`, `unit/test_markdown_chunking_baseline`,
`unit/test_type_aware_ingestion`, `test_document_registry_dispatch`,
`test_file_size_ceiling`; with `-m "not slow"`.

1. Before agent B's extractor change landed, the chunker's `store=` keyword
   reached the old extractor signature and 75 tests failed with
   `unexpected keyword argument 'store'`. With a temporary scratch pytest
   plugin that accepted the keyword (outside the repo, not committed):
   **337 passed, 5 skipped, 0 failed**.
2. After agent B's extractor change landed (no shim):
   **333 passed, 5 skipped, 5 failed**. All 5 failures are in
   `tests/test_metadata_degradation.py` (`TestLlamaIndexSignalsDegraded` x2,
   `TestExtractMetadataWithStatusAsync` x3). Cause: local metadata-backend
   doubles (`_fake_ollama`, `_fake_llamaindex`, `_degrading_*`) do not accept
   the `store` keyword that the metadata dispatch now forwards. These doubles
   belong to the metadata scope (task 3.5), not to the chunker change.

## Stale helper-parity claim (task 2.3)

`tests/test_chunking_hardening.py::test_markdown_helper_matches_main_ingestion_postprocessing`
compared the sentence helper with main ingestion. After the fix, main
ingestion awaits that same callable, so the comparison could not fail. It is
replaced by `test_main_ingestion_applies_markdown_postprocessing`, which
asserts the expected output (`["[Section] " + "x" * 80]`) directly.

The document-strategy contract is documented in
`docs/guides/ingestion.md`, section "Document chunking strategy contract".
The documented call matches `chunk_sentence_file_async` and the call in
`_chunk_documents()`. No guide claimed helper parity.
