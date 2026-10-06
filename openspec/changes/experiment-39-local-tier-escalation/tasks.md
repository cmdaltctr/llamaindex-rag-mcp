# Tasks: Experiment 39, local tier escalation

**Start gate:** none beyond 1.1. The run needs no OCR, download or package. Branch: `feat/experiment-39-local-tier-escalation`.

## 1. Plan

- [x] 1.1 Commit `experiments/39-local-tier-escalation-2026-09-30/protocol.md` and `plan.json` with the candidates, the C1 threshold and gates G1 to G3 fixed. Verify: `git log` shows the commit before any `output/` file exists.

## 2. Implementation

- [x] 2.1 Write `score_rules.py` with the script-group helper (design D4) and the candidate rules. Verify: unit tests on fixed strings pass (a clean Spanish line has CJK share 0; a line of CJK and Latin fragments has share ≥ 0.05; empty output escalates).
- [x] 2.2 Run `freeze.py --check` for Experiment 33, then load the 464 rows and saved texts. Verify: 464 rows, 464 text files, 399 `needs_ocr` rows, and every row's `body_recall` matches `pages.json`.

## 3. Run and summarise

- [x] 3.1 Score C0, C1, C3, the sweep and C4. Verify: `output/rules.json` has one decision per page per rule.
- [x] 3.2 Run `summarise_eval.py`: O, escalated share, kept-below-0.5 share (with and without `io06`), non-Latin pages kept, per-document escalation, and C4 AUCs. Verify: `output/summary.json` committed, and the C0 values at the 0.8 cut reproduce Experiment 33 (escalation 0.469, kept-below-0.5 0.113) within 0.001.

## 4. Close

- [ ] 4.1 Write `report.md` and `analysis.py`, set the status, and update the EXP_README row. Verify: the verdict names the winning rule or none, and states the `io06` finding.
- [ ] 4.2 Update NiftyPM AIE-100 and `niftypm/omrg.json`. Verify: the task links the report.
- [ ] 4.3 If a rule other than C0 wins, open a separate proposal to change the post-check in `page_routing.py`. Verify: proposal id recorded in the report.
