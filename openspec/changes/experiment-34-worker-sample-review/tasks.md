# Tasks: Experiment 34 Worker Sample Review

**Progress 2026-09-25:** all tasks done. The review (4 pages plus `eq01` p11, A1) is complete on normalised output; `report.md` is final (PASS, scoped). Code fixes found on the way shipped in PR #97.

## 1. Setup

- [x] 1.1 Rename the previous `experiment-34-full-document-rag-benchmark` change to `experiment-35-full-document-rag-benchmark` (folder and internal references; it was unstarted).
- [x] 1.2 Provision the OCR worker environment (`ocr-worker/provision.py`) and confirm the capability probe and one page-listed smoke parse pass. Provisioned; the capability probe reports protocol 1.1. The page-listed smoke parse is subsumed by the timing gate: cold pages on this machine exceed the smoke-fixture figures, so the probe is re-scoped as `time_worker.py` with a budget decision attached.

## 2. Sample and harness

- [x] 2.1 Freeze the sample: 42 pages from the Experiment 33 corpus (`io06` 12, `io04` 12, `bd01` 4, `bd02` 4, `tl03` 4, control 6), including every operator-spot-checked page listed in the proposal. Commit the sample manifest. `sample.json`, seed 34, control `bd03`; verified against the frozen labels.
- [x] 2.2 Write the runner: send each document's sampled pages to the worker in one page-listed request, checkpoint per document under the 900 s soft timeout and the 2 h wall-clock cap.
- [x] 2.3 Write the review page generator: original page image left, worker Markdown right, per-page checklist (text accuracy, column order, headings, table readable, ready for an LLM, note) persisting to a JSON verdicts file. `protocol.md` added per the s-experiment skill after the operator's correction.

## 3. Run and review

- [x] 3.1 Run the worker over the sample from this worktree, reading the corpus by absolute path from the Experiment 33 worktree; commit the raw outputs. All 42 sample pages plus `eq01` p11, no errors (`output/worker_state.json`; completion run 2026-09-25, `a384f11`).
- [x] 3.2 Operator reviews the pages and fills the checklist; the verdicts JSON is committed unchanged. First pass committed (`db19091`, 4 reviewed pages + `eq01` p11). Re-review pending: LiteParse panels (A6), local OCR tier panel (A5), and every panel the normaliser changes. Waits for `normalise-reader-markdown` to rebuild the review pages. Second pass committed 2026-09-25 on normalised pages (export `2026-09-25T13:32:24Z`): local OCR tier panels added; other answers unchanged.
- [x] 3.3 Summarise the verdicts per issue (old books, triple column, two column/tables, control) and record the go/no-go for the task 2.3 signal experiment. Final in `report.md`: PASS (scoped), task 2.3 go for `io06`-class pages; `io04` and `tl03` not evaluated; follow-ups include the local-tier `fused` repetition (A10).

## 4. Close

- [x] 4.1 PR this branch to `v3` (the rename, the change, the harness and the outputs ride together); ask the operator before opening it. 2026-09-25: PR #97, rebased onto `v3` (PR #96 was squash-merged); the operator's re-review (3.2) lands as a follow-up commit on it.
