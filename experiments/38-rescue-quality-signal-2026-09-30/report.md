# Experiment 38: BLOCKED at the recall agreement check

- **Date run**: 2026-10-07
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with Pi
- **Verdict**: No recommendation. Candidate comparison has not run.
- **Progress**: 5/16 OpenSpec tasks checked; task 2.2 blocked.
- **Plan commit before extraction**: `5c48fe9` (includes approvals and amendment A1).
- **Evidence**: [`output/recall_check.json`](output/recall_check.json), [`output/rescue_text.json`](output/rescue_text.json).

## What stopped the run

Body recall measures how many reference body tokens survive extraction. The required comparison stopped on `bd02`, page 5:

| Measure | Value |
| --- | ---: |
| Frozen `r_pypdf` | 0.3079 |
| Extracted pypdf against full transcription | 0.3078556263269639 |
| Saved Experiment 33 pypdf against full transcription | 0.3078556263269639 |
| Extracted and saved pypdf against body split | 0.9666666666666667 |
| Full reference / body reference | 471 / 150 tokens |
| Allowed absolute difference | 0.0001 |

Experiment 33's `build_labels._evidence` calculates `r_pypdf` against the full transcription. Experiment 38 requires body recall to match that value. The references differ. The extraction reproduces the saved pypdf scores against both references.

1. Approve a plan amendment that checks full-transcription recall against frozen `r_pypdf`, then classifies using body recall.
2. Keep the 0.0001 tolerance and every scientific threshold unchanged.
3. Commit the approved amendment before resuming candidate scoring.

## Checks and completed work

- `uv sync --locked`: PASS. No dependencies added to the project.
- `uv run pytest -m "not slow" --cov=omrg`: 3,307 passed, 140 skipped, 19 deselected; overall coverage 93%.
- `uv run lint-imports`: all eight contracts kept.
- `openspec validate experiment-38-rescue-quality-signal --strict`: PASS.
- Experiment tests: 40 passed. All first failed with their implementation modules absent.
- Extraction: 40 documents, 1,123 physical pages per tier, using LiteParse 2.11.1 and pypdf 6.16.2.
- Shipped normaliser: version 2. Saved text hashes verified; resume skipped all 40 completed documents.
- Source freeze checks returned `freeze verified` before extraction, classification and the diagnostic comparison.

## Remaining work

Task 2.2 saved classifications for `bd01` only. It stopped on the first mismatch in `bd02`; all-page agreement remains unverified.

Candidate A's implementation passed 12 fixed-string tests, including Spanish and mixed-script checks (task 3.1). Corpus scoring has not started. Julia files were not downloaded; P0 and G1 to G3 have no results. No adoption decision or production change was made.

`julia_onnx.py`, `summarise_eval.py`, final `analysis.py` and the experiment index update remain pending. Follow-up tasks 8.1 to 8.2, NiftyPM AIE-99, and a conditional production proposal await the main verdict. Nothing was pushed or archived.

Private page text stays in gitignored `output/.rescue_text/`. The Experiment 33 source files, production settings and indexes were not changed. The Experiment 39 change was not merged or cherry-picked.
