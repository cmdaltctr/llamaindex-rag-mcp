# Proposal: Experiment 38, a quality signal for reader-rescue text

## Why

Experiment 33 missed `rf06` and `rf07`, two handwritten Spanish records. LiteParse rescued their pages with junk text (fast-path token recall 0.236 and 0.469). TDR-024 then set `pages_needing_ocr` to zero, so both documents stayed on the fast path. ADR-071 decision 3 says a rescue should zero OCR evidence only when its text passes a quality signal. The mechanism is open. This experiment picks it with evidence before any production change.

## What Changes

- Add Experiment 38 (`experiments/38-rescue-quality-signal-2026-09-30/`), with `protocol.md` and `plan.json` committed before any run.
- Score two candidate signals on the rescue text of the 1,123 Experiment 33 pages, against the frozen reference transcriptions and the frozen recall thresholds:
  - **A. Deterministic checks:** a real-word ratio and a script-consistency share.
  - **B. Julia 1** (SupersonicLabs, Apache 2.0, 144M parameters), asked one yes/no question about the text, run locally through ONNX Runtime.
- Fix the adoption margin before the run. Julia 1 is adopted only if it beats candidate A by that margin.
- Measure the false-positive cost (healthy pages and documents sent to OCR for nothing) at page and document level.
- Answer the runtime question for Julia 1 with a parity check of the ONNX route. Adopting any runtime in production stays a separate decision.
- No production code changes. The winning signal, if any, goes to a separate proposal and ADR.

## Capabilities

### New Capabilities

- `rescue-quality-evaluation`: how OMRG evaluates a quality signal on reader-rescue text: junk defined by the frozen recall labels, a margin fixed before the run, false-positive cost, local-only models, and unchanged production behaviour.

### Modified Capabilities

None.

## Impact

- **Code:** experiment scripts only, under `experiments/38-rescue-quality-signal-2026-09-30/`. No change under `src/`.
- **Dependencies:** none added to OMRG. Candidate A1 needs `wordfreq`, run as an experiment-only tool (`uv run --with`), after operator approval. Candidate B uses `onnxruntime` and `tokenizers`, which are already base dependencies.
- **Downloads:** Julia 1 ONNX graph and weights (about 580 MB) and tokenizer (34 MB), after operator approval. No PyTorch.
- **Cloud:** none. Hosted Jev (TypeSafe AI) is rejected: closed weights, and it would send page text, including personal records, to a third party.
- **Data:** reads the gitignored Experiment 33 corpus, labels and transcriptions. Runs `freeze.py --check` first. Never edits a label.
- **NiftyPM:** AIE-99.
