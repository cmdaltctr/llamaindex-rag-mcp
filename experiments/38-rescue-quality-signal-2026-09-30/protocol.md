# Experiment 38: Rescue-quality signal, deterministic checks against Julia 1

- **ID**: `38-rescue-quality-signal-2026-09-30`
- **Date planned**: 2026-09-30
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with Claude Code (plan)
- **Status**: READY TO RUN (2026-10-07: operator approved amendment A2, separating all-text sanity checks from body-only quality classes). Both dependency approvals remain recorded in `plan.json`.
- **Relation**: OpenSpec change `experiment-38-rescue-quality-signal`; ADR-071 decision 3; TDR-024; NiftyPM AIE-99
- **Plan**: [`plan.json`](plan.json)

## Why this experiment exists

Experiment 33 missed `rf06` and `rf07`, two handwritten Spanish academic records. Both carry an old OCR text layer that reads as junk. LiteParse rescued the pages with that text (fast-path token recall 0.236 and 0.469). TDR-024 then set `pages_needing_ocr` to zero, so the documents stayed on the fast path and reached the index as junk. ADR-071 decision 3 says a rescue should zero OCR evidence only when its text passes a quality signal. This experiment chooses the signal, or shows that neither candidate is good enough.

## Hypotheses

1. **H1.** Candidate A (deterministic checks) passes gates G1 to G3.
2. **H2.** Candidate B (Julia 1) passes G1 to G3 and beats candidate A's junk recall by at least 0.10 at equal cost.
3. **P0 (precondition for H2).** Julia 1 runs through ONNX Runtime, with no PyTorch, and matches the published reference logits.

## What "junk" means

Each rescue text is scored against the Experiment 33 frozen body reference transcription with the Experiment 33 token rule (`build_labels.tokens`, `build_labels.recall`, imported). The frozen page rule's thresholds decide the class:

| Class | Body token recall of the rescue text | Use |
| --- | --- | --- |
| `junk` | < 0.50, at least one token | positive |
| `healthy` | ≥ 0.80 | negative |
| `grey` | 0.50 to < 0.80 | reported only |
| `excluded` | reference < 10 body tokens; frozen label `unrecoverable` or `ambiguous`; empty rescue text | not scored |

So "junk" means exactly what "needs OCR" means in Experiment 33: less than half the page's words survive. An empty rescue is excluded, because an empty rescue already fails and does not zero evidence.

Estimate from frozen `r_pypdf`: 953 eligible pages, about 105 non-empty junk pages and 536 healthy pages. `rf06` holds 39 of the 105. The LiteParse counts will differ. The run reports them.

## Candidates

| Candidate | Signal | Score (lower is junkier) | As-designed flag |
| --- | --- | --- | --- |
| A | A1 real-word ratio (`wordfreq` Zipf ≥ 1.0 in `en es fr de it pt nl ar hi bn`) and A2 script consistency (share of letters in the most frequent Unicode script) | `s_A = min(A1, A2)` | `s_A < 0.50` |
| B | Julia 1, `noul` request, options `["no", "yes"]`, question "Is this text readable writing in a natural language, rather than garbled or broken OCR output?" | `s_B = P(yes)` | `s_B < 0.50` |
| Baseline | today (TDR-024): no signal | none | never flags |

If the operator does not approve `wordfreq`, A1 becomes the word-shape ratio in design D3. That switch is an amendment recorded before the run.

## Variables

| Type | Variable | Values |
| --- | --- | --- |
| Independent | Signal | A, B, baseline |
| Dependent | Junk recall | flagged junk ÷ junk, LiteParse text |
| Dependent | Healthy false-positive rate | flagged healthy ÷ healthy |
| Dependent | Document routing | the 40 documents under simulated routing |
| Diagnostic | `pypdf`-tier recall and false-positive rate; CPU seconds per page for B | |
| Controlled | Pages, labels, references, token rule | Experiment 33, frozen |
| Controlled | Gate thresholds | `0.5`, `0.10`, unchanged |

## Procedure

1. Run `uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/freeze.py --check`. Continue only on `freeze verified`.
2. Extract per-page text with the shipped `liteparse` adapter (OCR off, its default) and the shipped `pypdf` adapter, then apply the shipped reader-output normaliser. Write `output/rescue_text.json` with reader versions and a SHA-256 per page.
3. Check `pypdf` recall against the full transcription and frozen `r_pypdf`. Stop on any difference above 0.0001. Classify quality using body recall. Amendment A2, approved on 2026-10-07 before candidate scoring, corrects the sanity-check reference; Experiment 33 records `r_pypdf` against all text. Frozen data, quality thresholds, gates, prompt and adoption margin stay unchanged.
4. Score candidate A.
5. Download the pinned Julia 1 ONNX files (after approval). Run P0. Stop and ask if P0 fails.
6. Score candidate B. Record CPU seconds per page.
7. Summarise: `output/summary.json`, then `report.md`.

Checkpoint after each document. Write outputs atomically (`.tmp`, then rename).

## Runtime question for Julia 1

Checked on 2026-09-30 from the published file listings and text files. No weights were downloaded.

- `SupersonicLabs/Julia-1` is a PyTorch package (`torch>=2.6`, `transformers>=5.0,<5.1`). Its request encoder `julia/data.py` imports torch.
- `SupersonicLabs/Julia-1-ONNX` is **not** a JavaScript-only repository. It ships the full graph (`model.onnx`, opset 18) and fp32 weights (`model.onnx.data`, 576.8 MB). Its adapters are JavaScript (WebGPU), Rust and WebAssembly, but its own `parity.py` runs the graph in Python `onnxruntime` on `CPUExecutionProvider`.
- A usable ONNX Runtime route exists. It needs a numpy port of the request encoder (about 60 lines of tensor building) and a parity check against the published `parity-cases.json` (100 requests with PyTorch logits). No PyTorch is needed for either step.
- `onnxruntime` 1.28.0 and `tokenizers` 0.22.2 are already OMRG base dependencies. The route adds no package.

| Option | PyTorch | Approval needed | Fit |
| --- | --- | --- | --- |
| 1. ONNX Runtime route (this experiment) | none | model download | no new dependency; parity must hold |
| 2. Isolated worker environment, like dots.mocr | isolated only | download, environment | proven pattern; a second heavy environment |
| 3. Optional `torch` extra | in an OMRG extra | operator (⚠️ Ask) | simplest code; weakest isolation |

This experiment uses option 1. If P0 fails, it stops and the operator picks option 2 or 3. Choosing the production runtime is a separate ADR.

## False-positive cost

A healthy page flagged as junk counts as a page needing OCR. The cost is OCR time spent for nothing:

| Engine | Seconds per page | 25-page healthy document sent whole |
| --- | ---: | ---: |
| dots.mocr (MPS, Experiment 34 median) | 38.2 | about 16 min |
| PaddleOCR-VL (CPU, Experiment 34 runs) | 23 to 164 | 10 to 68 min |
| Fast path (Experiment 33, 40 documents in 9.27 s) | about 0.01 | under 1 s |

The run reports both views: flagged healthy pages (page unit) and newly routed `usable` documents (document unit).

## Success criteria

Scored on LiteParse text, at the equal-cost threshold (the threshold where the healthy false-positive rate is 0.02). The as-designed points are also reported.

| Gate | Rule | Reason |
| --- | --- | --- |
| G1 | `rf06` and `rf07` both route | the two misses that motivate the change |
| G2 | no `usable` document newly routes | a healthy document sent whole to OCR costs 16 to 68 min |
| G3 | healthy false-positive rate ≤ 0.02 | 2% of about 536 healthy pages is about 11 pages, five times below the 10% document fraction |
| P0 | Julia ONNX: ≥ 99 of 100 argmax matches, ≤ 0.01 absolute logit error | the published WebGPU export reached 100 of 100 and 0.00225 |

Document routing is simulated with the unchanged `0.10` fraction. A document routes when flagged pages that the shipped chain rescued reach 10% of its pages, or when it already routed in the Experiment 33 `sampled_baseline` arm.

### Adoption margin (fixed before any run)

**Julia 1 is adopted only if its junk recall at the equal-cost threshold beats candidate A's by at least 0.10 absolute, an exact one-sided McNemar test on the junk pages gives p < 0.05, and it passes G1, G2, G3 and P0.**

Why 0.10: with about 105 junk pages, the 95% interval on a recall between 0.5 and 0.9 has a half-width of 0.06 to 0.10. A smaller gap is inside sampling noise on this corpus. Julia 1 also costs more than the checks: a 580 MB download, a new runtime path, a model identity in the index identity, and about 0.18 s per page on CPU (publisher's figure). The checks cost nothing. The McNemar test uses the pairing: both candidates score the same pages.

## Interpretation rules

| A passes gates | B passes gates | B beats A by margin | Recommendation |
| --- | --- | --- | --- |
| yes | any | no | A |
| any | yes | yes | B, with a runtime ADR |
| no | no | any | neither; record why |
| no | yes | no | neither; the operator decides whether B's gain alone justifies it |

- `rf06` holds about a third of the junk pages. The report gives per-document recall and a document-cluster bootstrap interval (2,000 resamples, seed 38) beside every pooled recall.
- The equal-cost threshold is chosen on the test pages, for both candidates alike. A production threshold needs its own check on new documents.
- A recommendation changes nothing in production. It opens a separate proposal (and an ADR for the runtime, if B).

## What to do if the experiment fails

- Neither candidate passes: record which gate failed and on which pages. The next candidate is a page-image signal (OCR confidence of a local pass on rescued pages), which needs new local OCR and a new protocol.
- P0 fails: stop and ask the operator for option 2 or 3.

## Cleanup

Delete `output/.models/` after the report. Keep `output/*.json` and `report.md`.

## Artefacts expected

| File | Content |
| --- | --- |
| `protocol.md`, `plan.json` | this plan |
| `extract_rescue_text.py`, `score_candidates.py`, `julia_onnx.py`, `summarise_eval.py`, `analysis.py` | scripts |
| `output/rescue_text.json` | per-page text hashes, recall, class (text itself gitignored) |
| `output/candidate_a.json`, `output/candidate_b.json` | scores |
| `output/summary.json` | gates, margin test, routing |
| `report.md` | verdict |

## References

- `docs/adr/071-ocr-routing-natural-positive-findings.md`, decision 3
- `experiments/33-ocr-routing-natural-positive-2026-09-17/report.md`, `build_labels.py`, `output/page_evidence.json`, `output/arm_sampled_baseline/routing.json`
- https://huggingface.co/SupersonicLabs/Julia-1 (revision `a85b127321d580d65176c89ced8273f305745d85`)
- https://huggingface.co/SupersonicLabs/Julia-1-ONNX (revision `82a2fadf8fccfccdc5fd4e1009ba8f1a265eb7a8`)
