# Tasks: Experiment 34 Worker Sample Review

**Progress 2026-09-19:** 0 of 8 done. Change proposed from the
`feat/experiment-34-worker-sample-review` worktree forked off
`feat/page-level-ocr-routing`; the operator authorised the bounded
worker run (sample, timeouts, budget in the proposal).

## 1. Setup

- [ ] 1.1 Rename the previous `experiment-34-full-document-rag-benchmark` change to `experiment-35-full-document-rag-benchmark` (folder and internal references; it was unstarted).
- [ ] 1.2 Provision the OCR worker environment (`ocr-worker/provision.py`) and confirm the capability probe and one page-listed smoke parse pass.

## 2. Sample and harness

- [ ] 2.1 Freeze the sample: 42 pages from the Experiment 33 corpus (`io06` 12, `io04` 12, `bd01` 4, `bd02` 4, `tl03` 4, control 6), including every operator-spot-checked page listed in the proposal. Commit the sample manifest.
- [ ] 2.2 Write the runner: send each document's sampled pages to the worker in one page-listed request, checkpoint per document under the 900 s soft timeout and the 2 h wall-clock cap.
- [ ] 2.3 Write the review page generator: original page image left, worker Markdown right, per-page checklist (text accuracy, column order, headings, table readable, ready for an LLM, note) persisting to a JSON verdicts file.

## 3. Run and review

- [ ] 3.1 Run the worker over the sample from this worktree, reading the corpus by absolute path from the Experiment 33 worktree; commit the raw outputs.
- [ ] 3.2 Operator reviews the pages and fills the checklist; the verdicts JSON is committed unchanged.
- [ ] 3.3 Summarise the verdicts per issue (old books, triple column, two column/tables, control) and record the go/no-go for the task 2.3 signal experiment.

## 4. Close

- [ ] 4.1 PR this branch to `v3` (the rename, the change, the harness and the outputs ride together); ask the operator before opening it.
