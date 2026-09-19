# Tasks: Experiment 34 Worker Sample Review

**Progress 2026-09-19:** setup and harness built (1.1, 1.2, 2.1–2.3); the
measured pass (3.1) is BLOCKED on the timing gate — one cold page
outlived 900 s and a cold+warm probe outlived 3000 s, against smoke
figures of 34–106 s/page, so `protocol.md` requires the per-page cost
on this machine before the run. The timing probe on `io06` is running
in the background; the 2 h wall cap is provisional until it reports.

## 1. Setup

- [x] 1.1 Rename the previous `experiment-34-full-document-rag-benchmark` change to `experiment-35-full-document-rag-benchmark` (folder and internal references; it was unstarted).
- [x] 1.2 Provision the OCR worker environment (`ocr-worker/provision.py`) and confirm the capability probe and one page-listed smoke parse pass. Provisioned; the capability probe reports protocol 1.1. The page-listed smoke parse is subsumed by the timing gate: cold pages on this machine exceed the smoke-fixture figures, so the probe is re-scoped as `time_worker.py` with a budget decision attached.

## 2. Sample and harness

- [x] 2.1 Freeze the sample: 42 pages from the Experiment 33 corpus (`io06` 12, `io04` 12, `bd01` 4, `bd02` 4, `tl03` 4, control 6), including every operator-spot-checked page listed in the proposal. Commit the sample manifest. `sample.json`, seed 34, control `bd03`; verified against the frozen labels.
- [x] 2.2 Write the runner: send each document's sampled pages to the worker in one page-listed request, checkpoint per document under the 900 s soft timeout and the 2 h wall-clock cap.
- [x] 2.3 Write the review page generator: original page image left, worker Markdown right, per-page checklist (text accuracy, column order, headings, table readable, ready for an LLM, note) persisting to a JSON verdicts file. `protocol.md` added per the s-experiment skill after the operator's correction.

## 3. Run and review

- [ ] 3.1 Run the worker over the sample from this worktree, reading the corpus by absolute path from the Experiment 33 worktree; commit the raw outputs.
- [ ] 3.2 Operator reviews the pages and fills the checklist; the verdicts JSON is committed unchanged.
- [ ] 3.3 Summarise the verdicts per issue (old books, triple column, two column/tables, control) and record the go/no-go for the task 2.3 signal experiment.

## 4. Close

- [ ] 4.1 PR this branch to `v3` (the rename, the change, the harness and the outputs ride together); ask the operator before opening it.
