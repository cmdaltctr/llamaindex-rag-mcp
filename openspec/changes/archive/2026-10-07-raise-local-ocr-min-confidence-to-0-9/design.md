# Design

## Context

See `proposal.md` for the evidence. Three facts in the code shape the work:

- **Two copies of the default.** `src/omrg/core/settings.py` (`ocr_local_min_confidence`, line 310) and `src/omrg/config/__init__.py` (line 205) each hold 0.8. Both must change together.
- **The cut is read in one place.** `local_ocr` in `src/omrg/integrations/pdf/page_routing.py` reads `settings.ocr_local_min_confidence` and compares with `<`. A page at exactly the cut stays local. No code needs to change there.
- **The cut is part of the page-unit index identity.** `ocr_routing_payload` in `src/omrg/core/ingestion/ocr_identity.py` adds `local_tier.min_confidence` only when the routing unit is not `document`. The identity therefore moves for page-unit installs and stays put for the default.

Machine check: this machine has 48 GiB of memory. Experiment 37 measured a dots.mocr peak of 22.2 GiB.

## Goals / Non-Goals

**Goals:**

- Move the default cut to 0.9 with docs, tests and ADR in step.
- Keep the existing re-index behaviour. No new migration code.

**Non-Goals:**

- A script or typography rule (rejected in Experiment 39).
- A per-line confidence signal for `io06`. It needs a new local OCR run and operator approval.
- A new setting, or a different default for the `document` unit.
- Scoring any text-quality model on the local OCR texts. That is the follow-up in `proposal.md`, owned by Experiment 38.

## Decisions

### D1. Change the default, not the code path

Only the two default values change. The comparison, the identity payload and the worker dispatch stay as they are. This keeps the diff to two lines of source plus tests and docs.

*Alternative: add a per-profile cut.* Rejected. No data supports different cuts per profile, and the setting is page-unit only.

### D2. 0.9, with no value in between

Experiment 39 swept 0.5, 0.6, 0.7, 0.8 and 0.9. Only 0.9 passes G1 and G2. A value such as 0.85 was not measured, so this change does not pick one.

### D3. Amend ADR-069, no new ADR

ADR-069 decision 2 set 0.8. The operator's 2026-09-18 amendment sets the precedent for a dated amendment in the same file. The amendment also corrects line 115, which says "below 0.8 recall" where the calibration table supports "below 0.5 recall".

### D4. Tests

- `test_readable_page_does_not_escalate` uses confidence 0.8 under default settings. It moves to 0.9 and gains a 0.85 case that escalates.
- The payload tests expect `min_confidence: 0.8`. They move to 0.9.
- `test_page_unit_identity_follows_the_escalation_threshold` uses 0.9 as the "raised" value. With the new default the two identities are equal and the test would fail. It moves to a value that differs from the default.
- Tests are written first and confirmed to fail on the current code, per the project rules.

## Risks / Trade-offs

- **[More worker load]** About 13 percentage points more flagged pages go to the worker. The cost is about 31 minutes per 399 flagged pages at 37 s per page. → The change is page-unit only, and the page unit is opt-in.
- **[Post-hoc choice on one corpus]** → Disclosed in `proposal.md`. A later corpus can move the cut again.
- **[One re-index for page-unit installs]** → Stated in the spec and in the docs. The default `document` unit is unaffected.
- **[Worker memory]** 22.2 GiB peak on a 48 GiB machine. → Task 3.3 confirms the peak on this machine.
- **[Residual junk]** `io06` and some handwriting stay open. → Follow-up in `proposal.md`.

## Open Questions

None.
