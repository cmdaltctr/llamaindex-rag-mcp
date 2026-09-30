# Tasks: Experiment 38, rescue-quality signal

**Start gate:** sections 2 onwards start only after the operator approves the two items in 1.2 and 1.3. Branch for the run: `feat/experiment-38-rescue-quality-signal`.

## 1. Plan and approvals

- [x] 1.1 Commit `experiments/38-rescue-quality-signal-2026-09-30/protocol.md` and `plan.json` before any run, with the margin (0.10), the false-positive ceiling (0.02), the junk definition and the Julia question fixed. Verify: `git log` shows the commit before any `output/` file exists.
- [ ] 1.2 Operator approves `wordfreq` as an experiment-only tool (`uv run --with wordfreq==<pin>`), or chooses the word-shape fallback. Verify: decision recorded in `plan.json` `decision_register`; a fallback choice is an amendment dated before the run.
- [ ] 1.3 Operator approves the Julia 1 ONNX download (about 580 MB, revision `82a2fad`). Verify: decision recorded in `plan.json` `decision_register`.

## 2. Rescue text extraction

- [ ] 2.1 Run `freeze.py --check` for Experiment 33, then extract per-page text with the shipped `liteparse` (OCR off) and `pypdf` adapters and the shipped normaliser for all 40 documents. Verify: `output/rescue_text.json` has 1,123 rows per tier, with reader versions and a SHA-256 per page text.
- [ ] 2.2 Score each text against the body reference with the imported Experiment 33 token rule, and assign `junk`, `healthy`, `grey` or `excluded`. Verify: recomputed `pypdf` recall equals the frozen `r_pypdf` within 0.0001 on every page, else stop.

## 3. Candidate A

- [ ] 3.1 Implement A1, A2 and `s_A` as in design D3. Verify: unit tests on fixed strings (a clean Spanish sentence scores ≥ 0.8; a mixed CJK and Latin junk line scores < 0.5).
- [ ] 3.2 Score every eligible page. Verify: `output/candidate_a.json` has one score per eligible page and tier.

## 4. Candidate B runtime

- [ ] 4.1 Download the pinned Julia 1 ONNX files into gitignored `output/.models/` and record their SHA-256. Verify: hashes in `plan.json`.
- [ ] 4.2 Port the request encoder to numpy and run parity check P0 on `parity-cases.json`. Verify: ≥ 99 of 100 argmax matches and ≤ 0.01 absolute logit error, and the type mix of the cases recorded. On failure, stop and ask the operator.

## 5. Candidate B

- [ ] 5.1 Score every eligible page with the fixed request (design D4). Verify: `output/candidate_b.json` has `P(yes)` per page and tier, and CPU seconds per page.

## 6. Summarise

- [ ] 6.1 Run `summarise_eval.py`: junk recall and healthy false-positive rate at both operating points, per-document recall, document-cluster bootstrap intervals (seed 38), McNemar, document routing for all 40 documents, and G1 to G3. Verify: `output/summary.json` committed, and the outcome follows the design D6 table.

## 7. Close

- [ ] 7.1 Write `report.md` and `analysis.py`, set the status, and update the EXP_README row. Verify: the verdict line names the recommended signal or none.
- [ ] 7.2 Update NiftyPM AIE-99 and `niftypm/omrg.json`. Verify: the task description links the report.
- [ ] 7.3 If a candidate is recommended, open a separate proposal for the production change (and a runtime ADR if it is Julia 1). Verify: proposal id recorded in the report.
