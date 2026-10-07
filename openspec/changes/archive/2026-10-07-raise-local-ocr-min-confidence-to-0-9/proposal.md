# Proposal: Raise the local OCR escalation cut to 0.9

## Why

In page mode, the local OCR tier keeps any page whose confidence is at or above `OCR_LOCAL_MIN_CONFIDENCE` (0.8). Experiment 39 re-scored 399 flagged pages. At 0.8, 24 of the 212 kept pages have body recall below 0.5, and one non-Latin page (`io02` p13, confidence 0.8046) is kept as junk. At 0.9, 4 of 161 kept pages are bad (0.025) and no non-Latin page is kept.

The 0.9 cut sends 51 more pages per 399 to the worker (238 against 187), about 31 minutes at the 37 s per page measured in Experiment 37. Experiment 37 shows the worker reads these pages: dots.mocr median recall 0.985 (Devanagari), 0.887 (Bengali), 0.873 (Arabic) and 0.812 (Latin handwriting), against 0.000 to 0.310 for the local tier.

## What Changes

- Change the default of `OCR_LOCAL_MIN_CONFIDENCE` from 0.8 to 0.9. A value set by the operator is unchanged.
- Update the docs and the example env file that state 0.8 and the Experiment 33 calibration figures.
- Update the tests that pin 0.8 or use 0.9 as the "raised" value.
- Amend ADR-069 decision 2 with the new default and the evidence.
- Add no script rule. Experiment 39 rejected both: the CJK-share rule (C1) keeps 19 of 129 non-Latin pages, and the combined rule (C3) keeps the same non-Latin page as the shipped rule.
- **Re-index once for page-unit installs.** The page-unit index identity carries the cut. The default `document` unit has no local tier and keeps its identity.

## Disclosures

- 0.9 was chosen after seeing the Experiment 39 results, on one corpus (Experiment 33, 399 flagged pages). It was not pre-registered.
- 0.9 fails Experiment 39 gate G3 (escalated share 0.596 against a bound of 0.566, 238 pages against 225). This change accepts that miss knowingly, because worker recall is high enough to justify the cost.
- `io06` (early-modern Latin book) stays open. At 0.9, one bad `io06` page is still kept. A fix needs per-line confidence from the engine.
- Worker recall is lower on Arabic (57% of pages reach 0.8) and Latin handwriting (53%). The Experiment 37 references are Gemini transcriptions, not human ground truth.
- Values between 0.8 and 0.9 were not measured. 0.9 is the only tested value that passes G1 and G2.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: adds a requirement that fixes the default local-tier cut at 0.9.

## Follow-up (not in this change)

If the Experiment 38 text-quality signal works, score it on the 464 saved local OCR texts of Experiment 33. That is the gap Experiment 39 left, and it targets the `io06` and handwriting pages a confidence cut cannot fix. Experiment 38 owns the signal. This line is here so the follow-up is not forgotten.

## Impact

- **Code:** two default values (`src/omrg/core/settings.py`, `src/omrg/config/__init__.py`).
- **Tests:** `tests/unit/test_local_ocr_tier.py`, `tests/test_ocr_identity_reingestion.py`.
- **Docs:** `.env.example`, `docs/guides/configuration.md`, `docs/guides/ingestion.md`, `docs/adr/069-page-level-ocr-routing-and-the-pdfium-runtime.md`.
- **Users:** only installs with `OCR_ROUTING_UNIT=page` and no explicit cut. They send about 13 percentage points more flagged pages to the worker and re-index once.
- **Evidence:** `experiments/39-local-tier-escalation-2026-09-30/report.md`, `experiments/37-dots-mocr-routing-acceptance-2026-09-30/report.md`.
