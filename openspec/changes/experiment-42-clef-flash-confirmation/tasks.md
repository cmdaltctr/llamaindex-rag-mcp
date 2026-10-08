# Tasks: Experiment 42, Clef-flash confirmation

**Start gate:** section 3 onwards starts only after tasks 1.2 to 1.4 are done. No candidate scores a new page before section 5. Run in a sibling worktree on branch `feat/experiment-42-clef-flash-confirmation`.

## 1. Plan and operator decisions

- [ ] 1.1 Commit `experiments/42-clef-flash-confirmation-2026-10-08/protocol.md` and `plan.json` (status `planned`) before any download or score. Verify: `git log` shows the commit before any `output/` or `corpus/` file exists.
- [ ] 1.2 Operator records OD1 (gate priority, design D6) in `plan.json` `decision_register`, with the date. Verify: the entry exists and names option A or option B.
- [ ] 1.3 Operator records OD2 (reference engine, design D4) and OD3 (runtime reuse, design D7) in `decision_register`. Verify: both entries exist; any hosted route has a dated amendment.
- [ ] 1.4 Operator approves the seeded selection procedure and the source list (design D3) in `plan.json`. Verify: `sourcing.procedure` and `sourcing.seed` (42) are set and dated.

## 2. Frozen thresholds (from Experiment 38 data only)

- [ ] 2.1 Run Experiment 33 `freeze.py --check`, then fit the Clef-flash threshold on the J W1 scores of the 565 healthy LiteParse pages of all 40 Experiment 38 documents, with the Experiment 38 equal-cost rule. Write the value, the input SHA-256 and the commit to `plan.json` `thresholds.clef_flash_q8_0_w1`. Verify: a unit test reproduces the value from the committed input, and fails when one healthy score is changed.
- [ ] 2.2 Fit the candidate A threshold by the same rule on the committed candidate A scores. Write it to `plan.json` `thresholds.word_check_a`. Verify: the value equals the Experiment 38 single-threshold result 0.8834080717, else stop and report the difference.
- [ ] 2.3 Commit the frozen thresholds. Verify: the commit precedes any file under `corpus/`.

## 3. Document sourcing and labels (local only)

- [ ] 3.1 Write `prepare_corpus.py` and `sources.json` that follow the approved procedure. Download into gitignored `corpus/`. Add `.gitignore` entries for renders, references and page text under `output/`. Verify with `git check-ignore` on one path of each kind. Remove every document whose SHA-256 or source identifier matches Experiment 33 `sources.json`. Verify: a test fails when a known Experiment 33 hash is in the set; `SOURCING.md` lists removals.
- [ ] 3.2 Render pages (poppler, 150 dpi, 1,600 px long side) and make reference transcriptions with the OD2 engine on this machine. Verify: one reference per page, engine version recorded, no network call in the run log.
- [ ] 3.3 Write the body-text rule into `plan.json`, then split each reference into body text. Verify: the rule has a commit before the split runs.
- [ ] 3.4 Extract rescue text with the shipped `liteparse` (OCR off) and `pypdf` adapters and the shipped normaliser. Score body recall with the imported Experiment 33 token rule, then assign classes. Verify: `output/rescue_text.json` has one row per page and tier, with reader versions and a SHA-256 per text; a test checks the class boundaries at 0.50 and 0.80.
- [ ] 3.5 Assign document labels (Experiment 33 document rule) and mark documents with a junk text layer (design D5). Verify: `output/labels.json` holds every document, and counts match a recount by a separate script.
- [ ] 3.6 Operator reviews 60 stratified pages against the page images. Verify: three or fewer class disagreements, recorded in `output/label_check.json`; otherwise stop and amend.
- [ ] 3.7 Check every D3 target. Verify: `output/set_check.json` lists each target and its count; if a target is missed, stop and record an amendment before section 4.
- [ ] 3.8 Write `freeze.py` for this experiment and commit the frozen hashes. Verify: `freeze.py --check` prints `freeze verified`, and fails after one label is edited in a temporary copy.

## 4. Control arm and runtime checks

- [ ] 4.1 Run the shipped routing gate on every new document at a pinned commit (Experiment 33 `route.py` pattern) to get the control routes. Verify: `output/control_routing.json` holds every document and the commit.
- [ ] 4.2 Check the runtime (design D7): llama.cpp build, Q8_0 SHA-256, bind address `127.0.0.1`, one request at a time. Verify: `output/runtime_check.json` records each check as pass; any fail stops the run.
- [ ] 4.3 Score the 40 fixed Experiment 38 reproduction pages. Verify: every score is within 0.01 of the committed J W1 score; otherwise stop.

## 5. Scoring (no interim look)

- [ ] 5.1 Score candidate A on every eligible page and tier at the frozen threshold. Verify: `output/candidate_a.json` has one score per page and tier; the code hash matches Experiment 38 `candidate_a.py`.
- [ ] 5.2 Score Clef-flash Q8_0 W1 on every eligible page and tier, one request at a time, with checkpoint and `--resume`. Verify: `output/clef_flash.json` has one score per page and tier; failed requests are at most 1% and listed.
- [ ] 5.3 Measure Clef-flash speed under D7 timing. Verify: `output/speed.json` records method, mean, median and p95.
- [ ] 5.4 Hash every scoring output before any summary is opened. Verify: `output/output_hashes.json` is committed before task 6.1 runs.

## 6. Analysis and verdict

- [ ] 6.1 Write `summarise_eval.py` with design D8 metrics and the D10 outcome table under the recorded OD1. Verify: unit tests on fixed fixtures cover each gate, the margin, McNemar and the routing rule, and each test fails when its rule is removed.
- [ ] 6.2 Run the summary. Verify: `output/summary.json` holds recall, false-positive rate with intervals, routing for every document, McNemar, AUC and the verdict.
- [ ] 6.3 Write `report.md` (verdict line first) and `analysis.py`; set the protocol and `plan.json` status; update the `experiments/EXP_README.md` row. Verify: the verdict line names PASS or FAIL, OD1, and the G3 rate with its interval.

## 7. Close

- [ ] 7.1 On PASS, open a follow-up OpenSpec change to adopt the gate in production, and draft its ADR. On FAIL, record the failed gate and pages and stop text-only rescue-signal work. Verify: the report names the follow-up change id, or states the stop.
- [ ] 7.2 Copy the preserve-class gitignored artefacts before any worktree removal (AGENTS.md Critical Gotcha 15). Verify: copied hashes match.
- [ ] 7.3 Run `openspec validate experiment-42-clef-flash-confirmation --strict` and the fast test suite. Verify: both pass.
