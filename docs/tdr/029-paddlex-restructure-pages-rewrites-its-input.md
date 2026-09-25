# TDR-029: paddlex `restructure_pages` rewrites its input — build per-page Markdown first, from a deep copy

**Date:** 2026-09-25
**Status:** Accepted (fix `d3460bf`, validated by a red-first seam test and a live `bd03` two-page run)
**Deciders:** Aizat
**Tags:** ocr | ocr-worker | paddleocr | protocol-1.1 | experiment-34

## Context

A protocol 1.1 page-listed request returns the joined Markdown and
`pages_markdown`, one entry per requested page. The worker built both from
one `pipeline.predict` result: first `restructure_pages(concatenate_pages=True)`
for the joined text, then `restructure_pages(concatenate_pages=False)` on the
same results for the per-page text, to avoid predicting twice. The seam tests
stubbed the pipeline, and the stub returned fresh objects, so the path was
never exercised against real paddlex (Experiment 34 Implementation notes).

### Root Cause Analysis

Symptom (Experiment 36, 2026-09-25): the same removed image blocks appeared on
`io04` p1 and on later `io04` pages. Every multi-page worker run had page 1 =
the whole request: `bd03` p1 was p1 + p2 (7,894 characters), `io04` p1 was all
12 pages (107,889 characters). Later pages and the joined Markdown were right.

Cause, in `paddlex/inference/pipelines/paddleocr_vl/pipeline.py`: with
`concatenate_pages=True`, `restructure_pages` sets
`res_list[0]["parsing_res_list"] = all_blocks` and gathers every page's images
onto `res_list[0]`. `res_list[0]` is the caller's own first page result, not a
copy. The per-page pass then read a page 1 that held every block. It also
re-levelled titles a second time (`io04` p47, p52 headings one level off).

## Decision

Run the per-page pass first, on a deep copy, then the joined pass on the
originals (`ocr-worker/src/omrg_ocr_worker/worker.py`):

```python
per_page_results = list(
    pipeline.restructure_pages(
        copy.deepcopy(page_results), merge_tables=True, relevel_titles=True, concatenate_pages=False
    )
)
pages_markdown = _per_page_markdown(per_page_results, len(pages))
structured_results = list(
    pipeline.restructure_pages(
        page_results, merge_tables=True, relevel_titles=True, concatenate_pages=True
    )
)
```

Validation: `tests/test_ocr_worker_client.py::test_page_listed_request_keeps_each_page_to_its_own_text`
uses a stand-in pipeline that copies the in-place rewrite; it fails on the old
order. Live `bd03` p1–2: page 1 4,158 characters (was 7,894), page 2 and the
joined Markdown byte-identical. The seven affected Experiment 34 runs were
re-run (`run_worker.py --force`; old records kept under `superseded`).

## Consequences

### Positive

- `pages_markdown` is one page per entry. Page-level OCR routing (ADR-069)
  no longer indexes the first routed page's neighbours twice.
- Headings are levelled once.

### Negative

- A deep copy of the page results per request (images included): more memory
  for long page lists.

### Neutral

- The joined Markdown is unchanged.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Predict twice | The expensive step; doubles worker time per request. |
| Build the joined Markdown by concatenating `pages_markdown` | Loses paddlex's cross-page table merge and title re-levelling in the joined text. |
| Copy only `parsing_res_list` | paddlex also rewrites images and other keys; a partial copy depends on internals that can change. |

## How to Recognise / Handle This Again

1. Symptom: the first page of a multi-page OCR result contains later pages' text, or the same blocks appear on several pages.
2. Diagnose: for each run, check whether any later page's opening text appears in page 1 (Experiment 34 A9 check).
3. General rule: never run two `restructure_pages` passes over the same result objects. Copy first.

## Revisit Triggers

- A paddlex upgrade: check whether `restructure_pages` still mutates its input.
- A new OCR engine behind the worker protocol (`modular-ocr-workers-dots-mocr`).

## References

- `ocr-worker/src/omrg_ocr_worker/worker.py`; commit `d3460bf`
- Experiment 34 protocol A9; TDR-027 (page selection); ADR-069; PR #97
