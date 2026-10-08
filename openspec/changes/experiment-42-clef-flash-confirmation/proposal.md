# Proposal: Experiment 42, confirm the Clef-flash rescue-quality signal on new documents

## Why

Experiment 38 ended FAIL. Clef-flash (`ggml-org/Clef-Flash-GGUF` Q8_0, llama.cpp b11510, wording W1) passed G1 and G2. It flagged 13 of 565 healthy pages against an 11-page ceiling, so it failed G3 by two pages. It caught 64 of 89 junk pages and sent no usable document to OCR. All of this comes from the same 40 documents, and `rf06` holds 41 of the 89 junk pages. The gates do not move after a run. A confirmatory test on new documents, with a threshold frozen before the run, is the only clean way to decide on adoption.

## What Changes

- Add Experiment 42 (`experiments/42-clef-flash-confirmation-2026-10-08/`), with `protocol.md` and `plan.json` committed before any document is scored.
- Fit one Clef-flash threshold on all 40 Experiment 38 documents, from the committed W1 Q8_0 scores. Record the value in `plan.json` and freeze it. The run never refits it on the new documents.
- Source a new, larger document set. It contains no Experiment 33 or Experiment 38 document. It holds at least 1,000 healthy pages, so the 2% ceiling is at least 20 pages. Junk text layers come from at least six documents, and no document holds more than a quarter of the junk pages.
- Label the new set locally: reference transcriptions, the Experiment 33 token rule and the frozen class thresholds. No page text leaves the machine.
- Score three arms on the same pages: production today (TDR-024, never flags) as the control, the Experiment 38 word check (candidate A) as the cheap comparator, and Clef-flash Q8_0 as the treatment.
- Keep gates G1 to G3, restated for the new set. G1 becomes: every document with a junk text layer routes to OCR.
- Record, before any run, the operator's decision on gate priority: G2 primary with G3 secondary, or all three gates primary as in Experiment 38.
- Check the runtime before scoring: llama.cpp build, Q8_0 file hash, server bound to `127.0.0.1`, one request at a time for timing.
- No production code changes. A PASS opens a separate OpenSpec change and an ADR to adopt the gate. A FAIL is recorded, and the work stops.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `rescue-quality-evaluation`: adds rules for a confirmatory run (unseen documents, a threshold frozen before the run, gate priority recorded before the run, a minimum sample, runtime checks for a local decision model). It also widens three existing requirements so that they apply to a new labelled set, and not only to the Experiment 33 documents.

## Impact

- **Code:** experiment scripts only, under `experiments/42-clef-flash-confirmation-2026-10-08/`. No change under `src/`, `pyproject.toml` or `uv.lock`.
- **Dependencies:** none added to OMRG. Candidate A uses `wordfreq==3.1.1` as an experiment-only tool (`uv run --with`), as in Experiment 38. llama.cpp runs as an external binary, outside the OMRG environment.
- **Downloads:** none expected. The Experiment 38 llama.cpp build and Q8_0 file are reused if their hashes match. A fresh download waits for operator approval.
- **Cloud:** none. Every arm and the reference transcription run on the operator's machine.
- **Data:** new open-licence PDFs, stored in a gitignored `corpus/` folder. The Experiment 33 and Experiment 38 files are read only, to exclude duplicates and to fit the threshold. No frozen file is edited.
- **Related records:** Experiment 38 report (Conclusion, Limits and next actions), ADR-071 decision 3, TDR-024, ADR-072 (dots.mocr), ADR-074 (Proposed: llama.cpp Q8_0 GGUF as the local decision-model runtime).
