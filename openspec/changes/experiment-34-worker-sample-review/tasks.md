# Tasks: Experiment 34 Worker Sample Review

**Progress 2026-09-25:** setup, harness and the worker run are done (1.x,
2.x, 3.1). The review was scoped to 4 pages (protocol A1). The operator's
first verdicts are committed and `report.md` records a PASS (scoped) with a
task 2.3 go. Two corrections reopened the review: the LiteParse adapter
line-join fix (A6) and the new local OCR tier column (A5). The operator
re-reviews on normalised output, so 3.2 and 3.3 wait for
`normalise-reader-markdown` (operator decision 2026-09-25) to rebuild the
review pages.

## 1. Setup

- [x] 1.1 Rename the previous `experiment-34-full-document-rag-benchmark` change to `experiment-35-full-document-rag-benchmark` (folder and internal references; it was unstarted).
- [x] 1.2 Provision the OCR worker environment (`ocr-worker/provision.py`) and confirm the capability probe and one page-listed smoke parse pass. Provisioned; the capability probe reports protocol 1.1. The page-listed smoke parse is subsumed by the timing gate: cold pages on this machine exceed the smoke-fixture figures, so the probe is re-scoped as `time_worker.py` with a budget decision attached.

## 2. Sample and harness

- [x] 2.1 Freeze the sample: 42 pages from the Experiment 33 corpus (`io06` 12, `io04` 12, `bd01` 4, `bd02` 4, `tl03` 4, control 6), including every operator-spot-checked page listed in the proposal. Commit the sample manifest. `sample.json`, seed 34, control `bd03`; verified against the frozen labels.
- [x] 2.2 Write the runner: send each document's sampled pages to the worker in one page-listed request, checkpoint per document under the 900 s soft timeout and the 2 h wall-clock cap.
- [x] 2.3 Write the review page generator: original page image left, worker Markdown right, per-page checklist (text accuracy, column order, headings, table readable, ready for an LLM, note) persisting to a JSON verdicts file. `protocol.md` added per the s-experiment skill after the operator's correction.

## 3. Run and review

- [x] 3.1 Run the worker over the sample from this worktree, reading the corpus by absolute path from the Experiment 33 worktree; commit the raw outputs. All 42 sample pages plus `eq01` p11, no errors (`output/worker_state.json`; completion run 2026-09-25, `a384f11`).
- [ ] 3.2 Operator reviews the pages and fills the checklist; the verdicts JSON is committed unchanged. First pass committed (`db19091`, 4 reviewed pages + `eq01` p11). Re-review pending: LiteParse panels (A6), local OCR tier panel (A5), and every panel the normaliser changes. Waits for `normalise-reader-markdown` to rebuild the review pages.
- [ ] 3.3 Summarise the verdicts per issue (old books, triple column, two column/tables, control) and record the go/no-go for the task 2.3 signal experiment. Draft in `report.md` (PASS scoped, 2.3 go); final after the 3.2 re-review.

## 4. Close

- [ ] 4.1 PR this branch to `v3` (the rename, the change, the harness and the outputs ride together); ask the operator before opening it.
