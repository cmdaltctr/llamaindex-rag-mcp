# Design

## Context

- **Where the fault sits.** ADR-066 reads a PDF with `pdf_inspector`, then rescues with `liteparse`, then `pypdf`. TDR-024 sets `pages_needing_ocr` to zero after a rescue returns text. Nothing checks what the text says. On `rf06` and `rf07` the text layer is an old OCR of handwriting, and it reads as junk.
- **What is frozen.** Experiment 33 holds 1,123 pages with reference transcriptions (`output/.transcripts`, body split in `output/.transcripts_split`), a token rule (`build_labels.tokens`, `build_labels.recall`) and page labels. `freeze.py --check` verified them on 2026-09-30.
- **What is not saved.** Per-page LiteParse text exists only for the 87 operator-reviewed pages (`compare_readers.py`). The run must extract rescue text for every page.
- **Size estimate.** From frozen `r_pypdf` values: 953 eligible pages, about 105 non-empty pages with recall below 0.5 and 536 pages at 0.8 or more. `rf06` gives 39 of the 105. The LiteParse counts will differ, and the run reports them.
- **Julia 1 runtime, checked 2026-09-30 (file listings and text files only, no weights).**
  - `SupersonicLabs/Julia-1` (revision `a85b127`) is a PyTorch package: `torch>=2.6`, `transformers>=5.0,<5.1`. Its encoder `julia/data.py` imports torch to build tensors.
  - `SupersonicLabs/Julia-1-ONNX` (revision `82a2fad`) ships the full graph (`model.onnx`, opset 18, inputs `input_ids`, `attention_mask`, `marker_pos`, `marker_mask`, `qtype`) and fp32 weights (`model.onnx.data`, 576.8 MB). Its adapters are JavaScript (WebGPU), Rust and WebAssembly. Its `parity.py` runs the same graph in Python `onnxruntime` with `CPUExecutionProvider`, so a Python ONNX Runtime route exists.
  - `parity-cases.json` carries 100 requests with their PyTorch logits. A numpy port of the encoder can be checked against it without PyTorch.
  - `onnxruntime` 1.28.0 and `tokenizers` 0.22.2 are already OMRG base dependencies.
  - `inference-policy.json` sets `head_length` 512. `parity.py` uses 256. The port follows the policy and records the difference.

## Goals / Non-Goals

**Goals:**

- Rank candidates A and B on the same pages, against the same labels, with the margin fixed first.
- State the false-positive cost in pages, documents and projected OCR time.
- Settle whether Julia 1 can run through ONNX Runtime with no PyTorch.

**Non-Goals:**

- Changing TDR-024, the reader chain, the gate thresholds or any default.
- Choosing the production runtime for Julia 1. That is a separate ADR.
- Fixing `mx02`, `mx07`, `tl07`, `tl08` (detection) or `bd04` (definition).

## Decisions

### D1. The text under test is each rescue tier's page text

The run extracts per-page text with the shipped `liteparse` adapter (OCR off, its default) and the shipped `pypdf` adapter, then applies the shipped reader-output normaliser. The primary population is LiteParse text, because LiteParse is the first rescue tier and the tier that hid `rf06` and `rf07`. `pypdf` text is a secondary population.

A sanity check guards the tokeniser: recomputed `pypdf` recall must equal the frozen `r_pypdf` on every page within 0.0001. If it does not, the run stops.

Alternative: score only the text the shipped chain returned for each document. Rejected as the primary population. Most documents are never rescued, so the count of scored pages would drop to a few hundred, dominated by two documents. It stays as the document-level view (D5).

### D2. Junk is defined by the frozen thresholds

`junk`: body token recall < 0.50 with at least one token. `healthy`: recall ≥ 0.80. `grey`: in between, reported only. The thresholds are the frozen page rule's `needs_ocr` and `usable` boundaries, so "junk" means the same thing as "needs OCR" in Experiment 33. Excluded: reference below 10 body tokens, frozen label `unrecoverable` or `ambiguous`, and empty rescue text (an empty rescue already fails and does not zero evidence).

### D3. Candidate A, deterministic checks

- **A1, real-word ratio.** Share of tokens (Experiment 33 token rule) with `wordfreq` Zipf frequency ≥ 1.0 in at least one of `en`, `es`, `fr`, `de`, `it`, `pt`, `nl`, `ar`, `hi`, `bn`. The list covers the corpus languages found in `sources.json` and the reference transcriptions. `wordfreq` has no Latin, which the report states for `io06`.
- **A2, script consistency.** Share of letters in the page's most frequent Unicode script, counting only letters (Common and Inherited excluded).
- **Score:** `s_A = min(A1, A2)`. Lower is junkier. Operating point as designed: flag when `s_A < 0.50`, the same boundary as the junk definition.
- **Fallback if `wordfreq` is not approved:** A1 becomes a word-shape ratio: a token is word-shaped if it is 2 to 20 letters, all in one script, has no letter repeated three times in a row, and (Latin script) holds a vowel. The switch is an amendment recorded before the run.

### D4. Candidate B, Julia 1 through ONNX Runtime

- **Request:** `type: noul`, options `["no", "yes"]` (false, true order), `state` = the page text, `question` = "Is this text readable writing in a natural language, rather than garbled or broken OCR output?". `max_length` 8192, `head_length` 512 (the published policy), strict encoding.
- **Score:** `s_B = P(yes)`. Operating point as designed: flag when `s_B < 0.50`.
- **Parity precondition P0:** on the 100 `parity-cases.json` requests, the numpy encoder plus ONNX Runtime must match the published argmax on at least 99 and stay within 0.01 absolute logit error. The published WebGPU run reached 100 of 100 and 0.00225. If P0 fails, candidate B is not scored and the operator decides the runtime (isolated PyTorch environment, or the optional `torch` extra).
- **Pins:** ONNX revision `82a2fadf8fccfccdc5fd4e1009ba8f1a265eb7a8`. The run records SHA-256 of `model.onnx`, `model.onnx.data` and `tokenizer.json`.

### D5. Gates, comparison and margin

Each candidate is scored twice on LiteParse text: at its as-designed operating point, and at the threshold where the healthy false-positive rate is 0.02 (ranking comparison at equal cost).

Gates, for a candidate to count as a usable signal (at the equal-cost threshold):

| Gate | Rule | Reason |
| --- | --- | --- |
| G1 | `rf06` and `rf07` both route | the two misses that motivate the change |
| G2 | no `usable` document newly routes | a healthy document sent whole to OCR costs 16 min (dots.mocr) to 68 min (PaddleOCR-VL) at 25 pages |
| G3 | healthy false-positive rate ≤ 0.02 | holds by construction at the equal-cost threshold; checked at the as-designed point |

Document routing is simulated with the unchanged `0.10` fraction: a document routes when flagged pages that the shipped chain rescued reach 10% of its pages, or when it already routed in the Experiment 33 `sampled_baseline` arm.

**Adoption margin (fixed now): Julia 1 is adopted only if its junk recall at the equal-cost threshold exceeds candidate A's by at least 0.10 absolute, an exact one-sided McNemar test on the junk pages gives p < 0.05, and Julia 1 passes G1 to G3.**

Reason for 0.10: with about 105 junk pages, the 95% interval on a recall between 0.5 and 0.9 has a half-width of 0.06 to 0.10. A smaller gap cannot be told apart from sampling noise on this corpus. The model also costs more than the checks: a 580 MB download, a new runtime path, a model identity in the index identity, and about 0.18 s per page on CPU (the publisher's figure: 18.23 s for 100 decisions). The checks cost nothing. McNemar guards the pairing, because both candidates score the same pages.

Reason for 0.02: 2% of about 536 healthy pages is about 11 pages. That is five times below the 10% document fraction, so scattered false positives cannot route a healthy document by themselves. G2 catches clustered false positives.

Because `rf06` holds about a third of the junk pages, the report also gives a document-cluster bootstrap interval (2,000 resamples of documents, seed 38) for each recall.

### D6. Outcome table

| A passes gates | B passes gates | B beats A by margin | Recommendation |
| --- | --- | --- | --- |
| yes | any | no | A |
| any | yes | yes | B, with a runtime ADR |
| no | no | any | neither; record why |
| no | yes | no | neither; the operator decides whether B's gain alone justifies it |

## Risks / Trade-offs

- [Junk pages cluster in `rf06`] → per-document recall and the document-cluster bootstrap interval are reported beside the pooled number.
- [Equal-cost threshold is chosen on the test pages] → both candidates get the same treatment, and the as-designed points are reported too. A production threshold needs its own check on new documents.
- [`wordfreq` lacks Latin and some scripts] → A2 covers script junk; the report lists pages where A1 had no lexicon for the page's script.
- [The Julia question wording shapes the answer] → one wording, fixed in `plan.json` before the run. No wording search.
- [ONNX parity cases may not include `noul` requests] → the report states the type mix of the parity cases. If none is `noul`, the result for B carries that caveat.
- [LiteParse output can change between versions] → the run records the LiteParse and pypdf versions and hashes each extracted page text.

## Open Questions

None that change the plan. Two operator approvals gate the run: `wordfreq` as an experiment-only tool, and the Julia 1 ONNX download.
