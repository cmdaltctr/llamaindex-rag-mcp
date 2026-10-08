# Experiment 42: Clef-flash rescue-quality signal, confirmation on new documents

- **ID**: `42-clef-flash-confirmation-2026-10-08`
- **Date planned**: 2026-10-08
- **Operator**: Dr Muhammad Aizat Bin Md Hawari, with Claude Code (plan)
- **Status**: PLANNED. Not ready to run: operator decisions OD1 to OD3 are open.
- **Relation**: OpenSpec change `experiment-42-clef-flash-confirmation`; Experiment 38 (FAIL); ADR-071 decision 3; TDR-024; ADR-072; ADR-074 (Proposed)
- **Plan**: [`plan.json`](plan.json)

## Why this experiment exists

Experiment 38 ended FAIL. Clef-flash on llama.cpp Q8_0 with wording W1 (candidate J) caught 64 of 89 junk pages and sent no usable document to OCR. It passed G1 and G2. It flagged 13 of 565 healthy pages against an 11-page ceiling (2.3%), so it failed G3 by two pages. Every number came from the same 40 documents, and `rf06` held 41 of the 89 junk pages.

The gates do not move after a run. This experiment tests the same signal, with a threshold frozen before the run, on documents it has never seen. It answers one question: does Clef-flash Q8_0 W1 pass the gates on new data?

## Hypotheses

1. **H1 (primary).** Clef-flash Q8_0 W1, at the threshold frozen on Experiment 38, passes every primary gate on the new set (primary gates follow OD1).
2. **H2 (margin).** Its junk recall beats candidate A by at least 0.10, with an exact one-sided McNemar test on junk pages at p < 0.05.
3. **H3 (control).** Production today (TDR-024) leaves at least four documents with a junk text layer on the fast path. This confirms the set holds the failure the change targets.

## Background

- Experiment 38: `experiments/38-rescue-quality-signal-2026-09-30/report.md`, sections Conclusion and Limits and next actions.
- Experiment 33: token rule, page rule and document rule (`build_labels.py`, `protocol.md`).
- ADR-074 (Proposed): llama.cpp Q8_0 GGUF as the local decision-model runtime. AGENTS.md Critical Gotcha 16: decision models at 8-bit or higher.

| Experiment 38 arm (held-out thresholds, LiteParse) | Junk caught | Healthy flagged | G1 | G2 | G3 |
| --- | ---: | ---: | --- | --- | --- |
| Production today (no check) | 0/89 | 0/565 | FAIL | PASS | PASS |
| Word check (A) | 37/89 | 18/565 | PASS | FAIL (`rf05`) | FAIL |
| Clef-flash Q8_0, W1 (J) | 64/89 | 13/565 | PASS | PASS | FAIL |

## Arms

| Arm | Signal | Flag rule |
| --- | --- | --- |
| Control | Production today (TDR-024): no quality check | never flags |
| Comparator | Candidate A, code unchanged from Experiment 38: `s_A = min(A1, A2)`, `wordfreq==3.1.1` | `s_A` < frozen A threshold |
| Treatment | `ggml-org/Clef-Flash-GGUF`, `Clef-Flash-Q8_0.gguf`, llama.cpp b11510 or later, `/v1/systemone` | `P(yes)` < frozen Clef threshold |

Treatment request, unchanged from Experiment 38 W1:

| Field | Value |
| --- | --- |
| `type` | `noul` |
| options | `["no", "yes"]` (false, true) |
| question | "Is this text readable writing in a natural language, rather than garbled or broken OCR output?" |
| `state` | first 2,000 characters of the normalised page text |
| `criteria` | none |
| score | `P(yes)`; lower is junkier |

## Frozen thresholds

Both thresholds are fitted once, on all 40 Experiment 38 documents, before sourcing ends.

1. Input for Clef-flash: `experiments/38-rescue-quality-signal-2026-09-30/output/wording_clefgguf_w1.json`, LiteParse tier, the 565 healthy pages.
2. Input for A: the committed Experiment 38 candidate A scores, same pages.
3. Rule: the Experiment 38 equal-cost rule. The threshold is where the healthy false-positive rate is 0.02. Ties are kept. A page is flagged when its score is strictly below the threshold.
4. Record each value, the input SHA-256 and the git commit in `plan.json` `thresholds`.
5. Never refit on the new documents. A threshold fitted on the new set is a diagnostic only.

Expected A value: 0.8834080717 (Experiment 38 single-threshold result). A different value stops the run.

## What "junk" means

Each rescue text is scored against a local reference transcription with the Experiment 33 token rule (`build_labels.tokens`, `build_labels.recall`, imported).

| Class | Body token recall of the rescue text | Use |
| --- | --- | --- |
| `junk` | < 0.50, at least one token | positive |
| `healthy` | ≥ 0.80 | negative |
| `grey` | 0.50 to < 0.80 | reported only |
| `excluded` | reference < 10 body tokens; page illegible; empty rescue text | not scored |

Document labels follow the Experiment 33 document rule. `needs_ocr`: `needs_ocr` pages reach 10% of pages. `usable`: `needs_ocr` and `ambiguous` pages together stay below 10%.

A **document with a junk text layer** has LiteParse `junk` pages that reach 10% of its pages.

## Corpus and labels

| Item | Value |
| --- | --- |
| Source | open-licence or public-domain PDFs; strata as Experiment 33 `SOURCING.md`, plus a stratum for scans with old OCR layers (handwriting, poor print, non-Latin scripts) |
| Selection | seeded (seed 42), procedure fixed in `plan.json` before any download |
| Exclusion | any SHA-256 or source identifier in Experiment 33 `sources.json` (Experiment 38 used these same 40 documents and has no corpus of its own) |
| Local path | `experiments/42-clef-flash-confirmation-2026-10-08/corpus/` (gitignored) |
| Renders | poppler, 150 dpi, 1,600 px long side (gitignored) |
| Reference | local engine chosen in OD2 (proposed: dots.mocr), body text per the Experiment 33 body-text amendment (gitignored) |
| Labels | `output/labels.json` (hashes, recall, classes; no page text) |
| Freeze | this experiment's `freeze.py --check` before every later step |

Selection uses metadata and labels only. No candidate score is computed before the freeze.

Operator check: 60 stratified pages (20 `junk`, 20 `healthy`, 20 `grey` or near a boundary) against the page image. More than three class disagreements stop the run.

## Sample size

| Target | Minimum | Reason |
| --- | --- | --- |
| Healthy LiteParse pages | 1,000 | 2% of 1,000 is 20 pages; one page moves the rate by 0.1 points (Experiment 38: 0.18) |
| Junk LiteParse pages | 100 (target 150) | at 72% recall the 95% Wilson interval is 0.63 to 0.80 at 100 pages and 0.64 to 0.79 at 150 (Experiment 38 at 89 pages: 0.62 to 0.80). The main gain is the spread across documents, not the width |
| Documents with a junk text layer | 6 | Experiment 38 had two |
| Of those, not routed by the control | 4 | the case the change exists for (H3) |
| Largest one-document share of junk pages | 25% at most | Experiment 38: `rf06` held 46% |
| `usable` documents | 40 | G2 needs documents that could be sent to OCR by mistake |

Expected size: 2,000 to 2,400 pages in 70 to 90 documents (Experiment 38: 50% of pages were healthy).

**Why not more healthy pages.** The threshold is fitted at a 2% rate. If new pages behave like old ones, the true rate on the new set is near 2%, and G3 is close to a coin toss at any size:

| Healthy pages | Ceiling (2%) | P(pass G3) if true rate 1.5% | 2.0% | 2.3% | 95% interval at an observed 2% |
| ---: | ---: | ---: | ---: | ---: | --- |
| 565 | 11 | 0.85 | 0.54 | 0.35 | 1.1% to 3.5% |
| 1,000 | 20 | 0.92 | 0.56 | 0.31 | 1.3% to 3.1% |
| 1,500 | 30 | 0.95 | 0.55 | 0.25 | 1.4% to 2.8% |

Exact binomial and Wilson intervals, computed for this plan. More pages narrow the estimate. They do not raise the chance of a pass. This is the reason for OD1.

## Gates

| Gate | Rule | Reason |
| --- | --- | --- |
| G1 | every document with a junk text layer routes | replaces "`rf06` and `rf07` both route" |
| G2 | no `usable` document newly routes, compared with the control | a healthy document sent whole to OCR costs about 16 to 68 minutes at 25 pages |
| G3 | healthy false-positive rate ≤ 0.02 at the frozen threshold | the page-level ceiling from Experiment 38 |
| Margin | Clef-flash junk recall ≥ A + 0.10, exact one-sided McNemar p < 0.05 | unchanged from Experiment 38 |

Routing is simulated with the unchanged `0.10` fraction. A document routes when flagged pages that the shipped chain rescued reach 10% of its pages, or when the control already routes it. The control routes come from the shipped gate on the new documents, at a pinned commit.

## Operator decisions (record before any run)

| Id | Decision | Options | Recommendation |
| --- | --- | --- | --- |
| OD1 | Gate priority | A: G2 primary, G3 secondary. B: G1, G2 and G3 all primary (as Experiment 38). G1 and the margin are primary in both. | A |
| OD2 | Reference transcription engine | dots.mocr (local); another named local engine; a hosted model (needs a dated amendment, page text leaves the machine) | dots.mocr |
| OD3 | Runtime and model file | reuse the Experiment 38 b11510 build and Q8_0 file if their hashes match; or approve a fresh download | reuse |

**OD1 rationale.** A flagged healthy page costs OCR time only when it helps push its document over the 10% routing share. Scattered flags below that share cost nothing. G2 counts exactly the documents that cross it. In Experiment 38, the 13 flags sent no usable document to OCR, so the two pages over the ceiling cost no OCR time. Under option A, G3 stays in the verdict line with its interval, and G2 stays a hard gate, so clustered flags still fail the run.

**Against OD1 option A.** G2 depends on how flags fall in this document set. Another set could cluster the same flags in one document. G3 measures the page rate behind that risk. The operator weighs this.

Until OD1 is in `plan.json` `decision_register`, no page is scored.

## Procedure

1. Run Experiment 33 `freeze.py --check`. Continue only on `freeze verified`.
2. Fit and commit both frozen thresholds (section Frozen thresholds).
3. Source the documents with the approved procedure. Remove overlaps. Write `SOURCING.md`.
4. Render pages. Make local reference transcriptions. Split body text.
5. Extract rescue text with the shipped `liteparse` (OCR off) and `pypdf` adapters and the shipped normaliser. Assign page and document classes.
6. Do the 60-page operator check.
7. Check every sample-size target. Stop if one is missed.
8. Write and commit this experiment's `freeze.py`. Run `freeze.py --check`.
9. Run the shipped routing gate on every document for the control.
10. Do the runtime checks (section Runtime checks).
11. Score A, then Clef-flash, one request at a time. Checkpoint after each document. Write outputs atomically (`.tmp`, then rename).
12. Hash every scoring output and commit the hashes.
13. Summarise: `output/summary.json`, then `report.md`.

## Runtime checks

| Check | Pass rule | On fail |
| --- | --- | --- |
| llama.cpp build | `llama-server --version` reports b11510 or later | stop |
| Model file | SHA-256 of `Clef-Flash-Q8_0.gguf` equals `plan.json` `treatment.model_sha256` (from Hugging Face LFS metadata) | stop |
| Bind address | server listens on `127.0.0.1` only | stop |
| Concurrency | one request at a time | stop |
| Reproduction | the 40 fixed Experiment 38 speed pages (`measure_speed.py`) score within 0.01 of the committed J W1 scores | stop; record the build difference |
| Timing | one request at a time, two warm-up requests excluded, nothing else on the GPU | timing reported as not valid |

## Analysis

Primary population: LiteParse text. `pypdf` text is a diagnostic only.

| Measure | Detail |
| --- | --- |
| Junk recall | flagged junk ÷ junk; Wilson 95% interval; document-cluster bootstrap (2,000 resamples, seed 42) |
| Healthy false-positive rate | flagged healthy ÷ healthy; same intervals |
| Per-document recall | every document with junk pages |
| Routing | every document at the `0.10` fraction: newly routed `usable` documents, missed junk-layer documents, projected OCR time |
| McNemar | exact one-sided, Clef-flash against A, on junk pages, with the recall difference |
| AUC | junk scored below healthy, both signals; diagnostic only |
| Sensitivity | false-positive rate at thresholds 10% above and below the frozen value; diagnostic only |
| Speed | seconds per page, Clef-flash, under the timing rule |

## Stopping rules

- A sample-size target is missed after sourcing: stop before scoring. The operator extends sourcing or accepts the smaller set in a dated amendment with a new power statement.
- The operator check or `freeze.py --check` fails: stop.
- A runtime check fails: stop.
- More than 1% of requests fail after three retries: stop scoring and report the failed pages.

## Amendment rule

Every amendment is dated, committed and listed in `plan.json` `amendments` before the data it affects is scored. After any score exists, no amendment changes the frozen thresholds, the wording, the gates, the margin or OD1. There is no interim look: no score, count or plot is opened until every arm has finished and its output is hashed.

## Interpretation rules

| Clef-flash passes primary gates and margin | A passes primary gates | Verdict | Next step |
| --- | --- | --- | --- |
| yes | any | PASS | follow-up OpenSpec change to adopt the gate in production, and its ADR |
| no | yes | FAIL for Clef-flash | record; the operator decides whether A alone justifies a proposal |
| no | no | FAIL | record the failed gate and pages; stop text-only rescue-signal work |

A PASS changes nothing in production by itself. Under OD1 option A, a G3 rate above 0.02 goes into the follow-up change as a known cost.

## Privacy and cloud

None. Every arm and the reference transcription run on this machine. PDFs, renders, references and page text stay in gitignored folders. Committed files hold hashes, counts, scores and labels only.

## Cleanup

Keep `output/*.json`, `report.md` and the frozen hashes. Before any worktree removal, copy the preserve-class gitignored artefacts (AGENTS.md Critical Gotcha 15).

## Artefacts expected

| File | Content |
| --- | --- |
| `protocol.md`, `plan.json` | this plan |
| `SOURCING.md`, `sources.json` | document selection and removals |
| `prepare_corpus.py`, `label_pages.py`, `freeze.py`, `score_arms.py`, `summarise_eval.py`, `analysis.py` | scripts |
| `output/labels.json`, `output/rescue_text.json` | classes, hashes, recall (no text) |
| `output/control_routing.json`, `output/runtime_check.json` | control routes and runtime checks |
| `output/candidate_a.json`, `output/clef_flash.json`, `output/speed.json` | scores and timing |
| `output/summary.json`, `report.md` | gates, margin, routing, verdict |

## References

- `experiments/38-rescue-quality-signal-2026-09-30/report.md`, `plan.json` (candidate J, wordings)
- `experiments/33-ocr-routing-natural-positive-2026-09-17/protocol.md`, `build_labels.py`, `SOURCING.md`
- `docs/adr/071-ocr-routing-natural-positive-findings.md`, decision 3
- ADR-074 (Proposed), llama.cpp Q8_0 GGUF as the local decision-model runtime
- https://huggingface.co/ggml-org/Clef-Flash-GGUF
