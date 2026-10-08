# Tasks

## 1. Tests first

- [x] 1.1 Update `tests/unit/test_local_ocr_tier.py`: the 0.8 readable-page case moves to 0.9, add a 0.85 page that escalates under default settings, and the payload expectations move to `min_confidence: 0.9`. Verify: the changed tests fail on the current 0.8 default.
- [x] 1.2 Update `tests/test_ocr_identity_reingestion.py` so the "raised" cut differs from the new default (for example 0.95). Verify: the test fails if the identity ignores the cut, and the old 0.9 value would make it pass for the wrong reason.

## 2. Change the default

- [x] 2.1 Set `ocr_local_min_confidence` to 0.9 in `src/omrg/core/settings.py` and `src/omrg/config/__init__.py`, with a comment naming Experiments 33, 37 and 39. Verify: the tests from 1.1 and 1.2 pass, and both defaults agree (add one assertion test if none compares them).

## 3. Docs and ADR

- [x] 3.1 Update `.env.example`, `docs/guides/configuration.md` and both mentions in `docs/guides/ingestion.md`, including the calibration figures (escalation 59.6%, wrongly kept 2.5%). Verify: `grep -rn "OCR_LOCAL_MIN_CONFIDENCE" docs .env.example` shows 0.9 only, and `grep -rn "46\.9\|11\.3" docs/guides` finds nothing.
- [x] 3.2 Amend `docs/adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md` decision 2 with a dated note, and correct line 115 ("below 0.8 recall" to "below 0.5 recall"). Verify: the amendment names Experiments 37 and 39 and the G3 miss.

## 4. Verify

- [x] 4.1 Run `uv run pytest -m "not slow" --cov=omrg` and `uv run ruff check src tests`. Verify: both pass.
- [x] 4.2 Run `openspec validate raise-local-ocr-min-confidence-to-0-9 --strict` and `openspec validate --all --strict`. Verify: both pass.
- [x] 4.3 Confirm dots.mocr fits in memory on this machine (48 GiB total, 22.2 GiB peak in Experiment 37). Verify: cite an Experiment 37 run on this machine, or record the peak resident memory of one worker request.
- [x] 4.4 Run `graphify update .` after the code change. Verify: the command finishes without error.

## 5. Follow-up

- [x] 5.1 Add a follow-up line to the Experiment 38 change (separate worktree, use `/opsx:update`): after its gates, score the chosen text-quality signal on the 464 saved local OCR texts of Experiment 33. Verify: the line is present in Experiment 38's `tasks.md` or `design.md`.
