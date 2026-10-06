# Tasks

## 1. Plan and freeze

- [x] 1.1 Preserve Experiment 37's gitignored outputs in the v3 worktree (Gotcha #15). Verify: file counts, byte comparison and SHA-256 of all 18 `sources.json` documents match; `git status` shows no tracked change. _Done 2026-10-06: 257, 221, 201 and 6 files match; `diff -rq` identical; 18 of 18 documents match; links kept as links._
- [x] 1.2 Create the worktree and branch off v3. Verify: `git rev-parse --show-toplevel` and `git branch --show-current` match. _Done 2026-10-06: `feat/experiment-41-mlx-ocr-backends` at `80dcf24`._
- [x] 1.3 Write `protocol.md` and `plan.json` in `experiments/41-mlx-ocr-backends-2026-10-06/`. Verify: page lists copied from Experiment 37 with SHA-256; all four approvals `false`; gates `NOT SET`. _Done 2026-10-06._
- [ ] 1.4 Operator sets the gates (replace or accept candidates C1 to C7) and resolves DR-1, DR-2 and DR-3 in `plan.json`. Verify: `gates.status` is no longer `NOT SET`; `plan.json` SHA-256 recorded.

## 2. Approvals (operator, one by one)

- [ ] 2.1 Approve installing `mlx-vlm` into the gitignored experiment environment. Verify: `approvals.install_mlx_vlm_into_gitignored_env` is `true`.
- [ ] 2.2 Decide the licence question for `mlx-community/dots.mocr-bf16` (DR-2). Verify: decision and its date recorded in `plan.json`.
- [ ] 2.3 Approve the model downloads (about 1.8 GB and about 6 GB). Verify: `approvals.model_downloads` is `true`; target is `OMRG_OCR_MODEL_CACHE`.
- [ ] 2.4 Approve the OCR run budget. Verify: `runtime_budget_h` filled and `approved` is `true`.

## 3. Build the probe

- [ ] 3.1 Install `mlx-vlm` and KaTeX 0.16.22. Record versions in `plan.json`, `system_identity`. Verify: versions recorded; nothing installed outside the experiment folder.
- [ ] 3.2 Download the weights. Record each repository revision. Verify: revisions in `plan.json`; `HF_HUB_OFFLINE=1` works afterwards.
- [ ] 3.3 Close open items OI-1 to OI-3 (layout imports, pinned-revision loading, page-subset reuse). Verify: each item answered in `plan.json`.
- [ ] 3.4 Write `run_mlx.py`, `start_mlx.sh`, `stop_mlx.sh`, `status_mlx.py`, `similarity.py` and the wrappers for `score_recall.py` and `check_katex.mjs`. Verify: `uv run ruff check` and `ruff format --check` pass; a dry run lists 257 pages.
- [ ] 3.5 Extend the memory sampler to the server process. Verify: a test run reports client, server and sum.

## 4. Run

- [ ] 4.1 Run `S-smoke` on `eq01` p2 and p3 for `A4` and `A2`. Verify: non-empty output; compare with the scratch figures; stop if the output is empty.
- [ ] 4.2 Run `A4` alone through `E-maths`, `E-scan` and `E-script`. Verify: state file shows 257 pages; no other GPU job ran.
- [ ] 4.3 Run `A2` alone through the same runs. Verify: same check.
- [ ] 4.4 If DR-1 says yes, run `T-control` for `A1` and `A3`. Verify: subsample timings recorded apart from the Experiment 37 figures.

## 5. Score and review

- [ ] 5.1 Score KaTeX, recall and similarity for both MLX arms. Verify: `output/katex_<arm>.json`, `output/recall_<arm>.json` and the similarity file exist.
- [ ] 5.2 Build the review page from the noise list, the lowest-similarity pages and the random sample, using the Experiment 34 layout. Verify: headless-browser checks in `references/review-page-pattern.md` pass.
- [ ] 5.3 Operator reviews and downloads the verdicts. Verify: merge refuses incomplete answers and records the SHA-256.

## 6. Close out

- [ ] 6.1 Write `output/summary.json` and `report.md` (verdict, limits, formula-difference list). Verify: every number in the report traces to `summary.json` or `pages.json`.
- [ ] 6.2 Update `protocol.md` status and the `EXP_README.md` row. Verify: status shows PASS, FAIL or INCONCLUSIVE.
- [ ] 6.3 If an arm passes, propose the MLX engine OpenSpec change as a separate change. Verify: next step named in the report; no engine, route or default changed here.
- [ ] 6.4 Run `openspec validate --all --strict` and the local gates for any code added. Verify: all pass.
- [ ] 6.5 Archive and sync this change, set any ADR or TDR to Accepted, then commit and open the PR (Gotcha #16). Verify: the operator confirms before any push.
