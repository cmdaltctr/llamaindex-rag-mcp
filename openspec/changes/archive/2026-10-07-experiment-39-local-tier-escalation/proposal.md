# Proposal: Experiment 39, local OCR tier escalation on script and typography

## Why

The local OCR tier (PP-OCRv6 Small, ONNX Runtime, CPU) scored median token recall 0.000 on all 129 non-Latin pages in Experiment 33, 0.310 on handwriting, and 0.609 on the early-modern book `io06` at median confidence 0.922. The shipped escalation rule (ADR-069: empty text, confidence below 0.8, or `hosted_recommended`) escalates most unreadable pages but still keeps some of them. It also keeps `io06`, where the model is confident and wrong. ADR-071 decision 4 asks for a rule that keys on script and typography and does not keep pages the local model cannot read.

## What Changes

- Add Experiment 39 (`experiments/39-local-tier-escalation-2026-09-30/`), with `protocol.md` and `plan.json` committed before any run.
- Re-score the existing local OCR rows (`experiments/33-…/output/local_ocr/pages.json`, 464 pages, and the saved page text in `output/.local_ocr_text/`) against the frozen recall labels. No new OCR runs.
- Candidates: a script-mismatch rule by Unicode block on the local OCR output, the shipped confidence cut, and their combination. An exploratory engine-signal probe for `io06` uses the discarded-region count the engine already reports.
- Fix the pass criteria before the run: non-Latin pages kept, pages kept with recall below 0.5, and the share escalated.
- No production code changes. A winning rule goes to a separate proposal that changes `page_routing.py`.

## Capabilities

### New Capabilities

- `local-tier-escalation-evaluation`: how OMRG evaluates an escalation rule for the local OCR tier: frozen labels, pass criteria fixed first, no new OCR, and unchanged production behaviour.

### Modified Capabilities

None.

## Impact

- **Code:** experiment scripts only. No change under `src/`.
- **Dependencies:** none. Standard library `unicodedata` only.
- **Data:** reads the gitignored Experiment 33 local OCR rows and text. Runs `freeze.py --check` first. Never edits a label.
- **Relation:** ADR-069 (shipped confidence post-check, and its 2026-09-18 amendment that dropped a script pre-check); ADR-071 decision 4 and its 2026-09-30 erratum (`io07` is Bengali); Experiment 37 (`E-script` scores dots.mocr and PaddleOCR-VL on the same non-Latin pages).
- **NiftyPM:** AIE-100.
