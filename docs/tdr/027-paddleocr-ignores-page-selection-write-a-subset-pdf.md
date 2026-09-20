# TDR-027: paddleocr ignores page selection — write a subset PDF instead of passing `page_num`

**Date:** 2026-09-19
**Status:** Accepted (fix validated by a red-first seam test and a live `bd03` two-page run)
**Deciders:** Aizat
**Tags:** ocr | ocr-worker | paddleocr | protocol-1.1 | experiment-34

## Context

The worker protocol gained a page-listed request in 1.1 (change
`page-level-ocr-routing`, task 4.3): `pages` on the request,
`pages_markdown` parallel on the response. The worker implemented
selection by forwarding the list to the pipeline:
`pipeline.predict(input=..., page_num=[28, 53])`. That forwarding was
flagged as unvalidated at the time — "the pytest suite stubs the parse
seam and cannot reach it" — and gated on the operator-run smoke test,
which had not run provisioned.

### Root Cause Analysis

`PaddleOCRVL.predict` in paddleocr 3.7.0 / paddlex 3.7.2 has **no
`page_num` parameter**. The kwarg fell into `**kwargs` and was
silently ignored; the engine processed the document from page 1.
Evidence from Experiment 34's first run (one request,
`pages=[28, 53]`, 4,897 s):

- the "page 28" output was 70,827 characters — roughly a book
  chapter, not a page — and its token overlap was 1.00 against the
  reference transcriptions of pages 1, 2, 53 and 54, and only 0.70
  against page 28's own transcript;
- the "page 53" output was 140 bytes containing a page-number "2";
- `inspect.signature(PaddleOCRVL.predict)` shows no page-selection
  parameter, and `grep -r page_num` over the installed `paddleocr`/
  `paddlex` packages finds no handling in the local predict path.

A second defect masked the first: the worker padded `pages_markdown`
to the requested length, so the protocol-level parallelism checks —
including the smoke test's — passed on a whole-document run. The
timing consequences propagated too: "69 minutes per page" was really
"the front of a 78-page book", which inflated the experiment budget
estimate to two days.

## Decision

The worker selects pages **structurally**: a page-listed request is
written to a temporary PDF containing exactly those pages
(`pypdf.PdfWriter`, 1-based, `docs/tdr`-visible in
`ocr-worker/src/omrg_ocr_worker/worker.py::_write_page_subset`), the
pipeline predicts on the subset, and the subset is unlinked in a
`finally`. Selection can no longer be a parameter the engine may
ignore.

Guards that would have caught this:

- a page-count mismatch raises `page_selection_mismatch` in the worker
  (`len(page_results) != len(pages)`, and the same check after
  restructuring) — no padding, ever;
- the experiment runner records an error when
  `metadata.page_count != len(pages)` (TDR-027 tripwire);
- the smoke test's page-listed validation compares `page_count` to
  the request, not just `pages_markdown` length.

`pypdf` joined the worker manifest (pure Python, BSD-licensed).

## Consequences

### Positive

- Page selection is honest by construction; per-page timing and cost
  estimates become measurable per page.
- The tripwires turn any future silent whole-document run into a loud
  error at three layers.

### Negative

- A temporary copy of the requested pages is written per request
  (small; pages, not the document).
- One more worker dependency to keep locked (`pypdf`).

### Neutral

- `page_count` on a page-listed response now means "pages processed",
  which equals the list length — unchanged in meaning, now enforced.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Keep `page_num`, upgrade paddleocr | No such parameter in 3.7.0; nothing in the changelog suggests one; the semantics are undocumented even where the kwarg is accepted elsewhere |
| Render page images and predict on images | Changes the pipeline's document path (PDF layout analysis vs image), risking different output for the same page |
| Trust `pages_markdown` parallelism as the guard | Proven insufficient — the padding made it pass on the buggy path |

## How to Recognise / Handle This Again

1. **Symptom:** a page-listed worker response whose Markdown is far
   larger than one page could hold, or whose content matches other
   pages of the document; "per-page" timings of tens of minutes.
2. **Diagnose:** token-overlap the response against reference
   transcriptions of neighbouring pages (Experiment 34's method), and
   check `metadata.page_count` against the requested list.
3. **Recover:** the guards now raise; if a third-party engine change
   reintroduces ignoring, the subset-PDF path still holds because it
   does not depend on engine parameters.

## Revisit Triggers

- A paddleocr release that documents a supported page-selection
  parameter (could replace the subset write, at a cost of re-trusting
  a parameter).
- Worker venv reprovisioning that drops `pypdf` (the lock pins it).

## References

- Fix commit on `feat/experiment-34-worker-sample-review` (page-subset
  + tripwires); the same defect ships latently in PR #96 until this
  branch merges after it.
- `ocr-worker/src/omrg_ocr_worker/worker.py` (`_write_page_subset`,
  `_run_document_pipeline`, `_per_page_markdown`)
- Experiment 34: `experiments/34-worker-sample-review-2026-09-19/`
  (protocol.md, worker_state.json history)
- Related upstream context: firecrawl/pdf-inspector#554 (a different
  silent-failure class in the other reader; same lesson — silent
  acceptance is the enemy)
