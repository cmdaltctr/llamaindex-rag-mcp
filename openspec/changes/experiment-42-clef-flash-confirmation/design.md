# Design

## Context

- **Prior result.** See proposal.md, Why. Experiment 38 report, sections Conclusion and Limits and next actions, is the source of every Experiment 38 number below.
- **Where the fault sits.** ADR-066 reads a PDF with `pdf_inspector`, then rescues with `liteparse`, then `pypdf`. TDR-024 sets `pages_needing_ocr` to zero after a rescue returns text. Nothing checks what the text says. ADR-071 decision 3 says a rescue should zero OCR evidence only when its text passes a quality signal.
- **Treatment as run in Experiment 38 (candidate J).** `ggml-org/Clef-Flash-GGUF`, file `Clef-Flash-Q8_0.gguf` (9.7 GB, Apache 2.0), `llama-server` build b11510 (includes the Metal fix from PR #30100), server on `127.0.0.1`, `/v1/systemone` `noul` request, wording W1, state = first 2,000 characters of page text, no criteria. Correlation with hosted Clef-flash on W1 was 0.9997 over 1,322 page/tier pairs. Speed was 0.84 s per page, one request at a time.
- **Experiment 38 gate result for J, W1, held-out thresholds.** 64/89 junk pages, 13/565 healthy pages (2.3%), G1 PASS, G2 PASS, G3 FAIL. Word check (A): 37/89 junk, 18/565 healthy, G2 FAIL on `rf05`.
- **Committed inputs.** `experiments/38-rescue-quality-signal-2026-09-30/output/wording_clefgguf_w1.json` (J, W1 scores) and the Experiment 38 class labels are in git. The fit in D2 needs no model call.
- **Runtime record.** ADR-074 (Proposed) records llama.cpp Q8_0 GGUF as the local decision-model runtime. AGENTS.md Critical Gotcha 16 sets 8-bit or higher for decision models. This experiment follows both and does not depend on ADR-074 being accepted.

## Goals / Non-Goals

**Goals:**

- Decide, on documents the threshold has never seen, whether Clef-flash Q8_0 W1 passes the gates.
- Make G3 decidable: at least 20 pages under the 2% ceiling, so one page does not decide it.
- Spread junk text layers across several documents, so no document dominates junk recall.
- Record the gate priority before any score exists.

**Non-Goals:**

- Changing TDR-024, the reader chain, the `0.5` and `0.10` gate thresholds or any default.
- Testing other wordings (W2, W3), other builds (MLX, hosted) or other models (Jev, OpenJev, Julia 1). Experiment 38 already reports them.
- Tuning the threshold, the wording or the 2,000-character head on the new set.
- Sending page images to the model.
- Choosing the production integration (where the check runs, caching, index identity). A PASS opens that change.

## Decisions

### D1. Three arms on the same pages

| Arm | What it is | Flag rule |
| --- | --- | --- |
| Control | Production today (TDR-024): no quality check | never flags |
| Comparator | Candidate A from Experiment 38, code unchanged: `s_A = min(A1, A2)`, `wordfreq==3.1.1` | `s_A` < frozen A threshold (D2) |
| Treatment | Clef-flash Q8_0, W1, request as in Experiment 38 | `P(yes)` < frozen Clef threshold (D2) |

The request is the Experiment 38 W1 request, byte for byte: `type: noul`, options `["no", "yes"]`, question "Is this text readable writing in a natural language, rather than garbled or broken OCR output?", `state` = first 2,000 characters of the normalised page text, no `criteria`. The run reuses the Experiment 38 client code. A copy is allowed only if its hash matches.

Alternative: add W3 or a per-document wording choice. Rejected. On Experiment 38, W2 and W3 sent `tl06` to OCR on every build. Only W1 passed G2.

### D2. Thresholds are fitted once on Experiment 38 and frozen

- **Clef-flash.** Input: the J W1 scores on the 565 healthy LiteParse pages of all 40 Experiment 38 documents. Rule: the Experiment 38 equal-cost rule (the threshold where the healthy false-positive rate is 0.02, ties kept, flag when the score is strictly below it). One threshold on all 40 documents, not leave-one-document-out.
- **Word check (A).** Same rule on the committed candidate A scores. Experiment 38 reported 0.8834080717 for this single-threshold fit. The fit task checks that value.
- The fit task records each value, the SHA-256 of each input file and the git commit in `plan.json`, before sourcing ends. The values are frozen.
- No refit on the new set. No second threshold. A threshold fitted on the new set is a diagnostic only, and the report labels it so.

Alternative: fit on part of the new set and test on the rest. Rejected. It halves the test set and repeats the selection problem the confirmation exists to remove.

### D3. Document set and sample size

Sources: open-licence or public-domain PDFs, as in Experiment 33 (`SOURCING.md` strata). A seeded selection procedure (seed 42) is written in `plan.json` before any download.

| Target | Value | Reason |
| --- | --- | --- |
| Healthy LiteParse pages | ≥ 1,000 | 2% of 1,000 is 20 pages; one page moves the rate by 0.1 points, not 0.18 |
| Junk LiteParse pages | ≥ 100 (target 150) | at 72% recall the 95% Wilson interval is 0.63 to 0.80 at 100 pages and 0.64 to 0.79 at 150 (Experiment 38, 89 pages: 0.62 to 0.80); the main gain is the spread across documents |
| Documents with a junk text layer (D5) | ≥ 6 | Experiment 38 had two (`rf06`, `rf07`) |
| Of those, missed by the control arm | ≥ 4 | the case the change exists for |
| Largest single-document share of junk pages | ≤ 25% | Experiment 38: `rf06` held 41 of 89 (46%) |
| `usable` documents (D5) | ≥ 40 | G2 needs enough documents that could be sent to OCR by mistake |
| Overlap with Experiment 33 and 38 | 0 | checked by SHA-256 and by source identifier |

Expected size: Experiment 38 had 565 healthy pages in 1,123 (50%). About 2,000 to 2,400 pages and 70 to 90 documents meet the targets. At 0.84 s per page, Clef-flash scoring takes about 30 to 35 minutes.

Junk text layers are rare in born-digital PDFs. The selection adds a stratum for scans with old OCR layers: handwriting, poor print, non-Latin scripts. Archive.org text PDFs, historical government scans and old patents are candidate sources. A document enters the set on its metadata and its labels only. No candidate score is computed before the set is frozen.

Why 1,000 healthy pages and not more: the frozen threshold gives a false-positive rate near 2% if the new pages behave like the old ones. The chance of a pass on G3 is then close to one half at any size: 0.56 at 1,000 pages if the true rate is 2.0%, and 0.31 if it is 2.3% (Experiment 38). More pages make the estimate narrower; they do not make a pass more likely. At 1,000 pages the 95% interval at 2% is about 1.3% to 3.1%. That is precise enough to tell a 1% signal from a 3% signal. This is the reason for decision OD1.

### D4. Labels are made locally with the Experiment 33 rules

- **Reference transcription.** A local engine transcribes each rendered page. The proposed engine is dots.mocr (ADR-072 primary engine, already installed, no cloud). Page renders follow Experiment 33: poppler, 150 dpi, 1,600 px long side. See OD2.
- **Body text.** The Experiment 33 body-text amendment applies: running text, headings, lists and tables count; text inside figures and drawing labels does not. The labelling task writes the exact rule into `plan.json` before labelling starts.
- **Token rule.** Imported from Experiment 33: `build_labels.tokens` and `build_labels.recall`. Not copied.
- **Classes.** Frozen thresholds: `junk` body recall < 0.50 with at least one token, `healthy` ≥ 0.80, `grey` in between (reported only). Excluded: reference below 10 body tokens, illegible page, empty rescue text.
- **Operator check.** The operator reviews a stratified sample of 60 pages (20 `junk`, 20 `healthy`, 20 `grey` or near a boundary) against the page image. More than three class disagreements stop the run. The fix is then an amendment, recorded before any score.
- **Freeze.** A `freeze.py` for this experiment hashes the corpus, renders, references and labels. Every later step runs `freeze.py --check` first.
- **Privacy.** PDFs, renders, references and page text stay in gitignored folders. Committed files hold hashes, counts and labels only.

### D5. Gates, restated for the new set

Document labels follow the Experiment 33 document rule: `needs_ocr` when `needs_ocr` pages reach 10% of pages; `usable` when `needs_ocr` and `ambiguous` pages together stay below 10%.

A **document with a junk text layer** has LiteParse `junk` pages that reach 10% of its pages. These are the documents that a perfect signal would send to OCR.

Routing is simulated with the unchanged `0.10` fraction. A document routes when flagged pages that the shipped chain rescued reach 10% of its pages, or when the control arm already routes it. The control arm's routes come from the shipped gate, run on the new documents at a pinned commit (the Experiment 33 `route.py` pattern).

| Gate | Rule | Reason |
| --- | --- | --- |
| G1 | every document with a junk text layer routes | replaces "`rf06` and `rf07` both route" |
| G2 | no `usable` document newly routes (compared with the control arm) | a healthy document sent whole to OCR costs about 16 to 68 minutes at 25 pages |
| G3 | healthy false-positive rate ≤ 0.02 at the frozen threshold | the page-level cost ceiling from Experiment 38 |

**Adoption margin, unchanged from Experiment 38.** Clef-flash also needs junk recall at least 0.10 above candidate A, with an exact one-sided McNemar test on the junk pages at p < 0.05.

### D6. Gate priority is an operator decision, recorded before the run (OD1)

Experiment 38 treated G1, G2 and G3 as equal. This experiment asks the operator to choose, and to record the choice in `plan.json` `decision_register` before any page is scored.

| Option | PASS needs | Effect |
| --- | --- | --- |
| **A. G2 primary, G3 secondary (recommended)** | G1, G2 and the adoption margin. G3 is reported with its interval and does not decide the verdict. | Judges the signal on the cost that production pays |
| B. All gates primary (as Experiment 38) | G1, G2, G3 and the adoption margin | Keeps the Experiment 38 rule; G3 stays close to a coin toss (D3) |

Rationale for option A. A flagged healthy page costs OCR time only when it helps push its document over the 10% routing share. Scattered flags below that share cost nothing. G2 measures exactly the documents that cross it. On Experiment 38, the 13 flags sent no usable document to OCR, so the two pages over the ceiling cost no OCR time. With a threshold fitted at 2%, G3 is about a coin toss on new data, even for a signal that behaves as before.

Counter-argument for option B. G2 depends on how flags fall inside this document set. A different set could cluster the same flags in one document. G3 measures the page rate that drives that risk. Option A keeps G3 in the report and keeps G2 as a hard gate, so a cluster still fails the run.

The agent does not choose. Until the operator records OD1, the run does not start (task 1.3).

### D7. Runtime checks before scoring

| Check | Pass rule | On fail |
| --- | --- | --- |
| llama.cpp build | `llama-server --version` reports build b11510 or later | stop |
| Model file | SHA-256 of `Clef-Flash-Q8_0.gguf` equals the hash recorded in `plan.json` (taken from the Hugging Face LFS metadata) | stop |
| Bind address | server listens on `127.0.0.1` only | stop |
| Concurrency | one request at a time (Experiment 38: llama-server stalled with four overlapping requests) | stop |
| Reproduction | 40 fixed Experiment 38 pages reproduce the committed J W1 scores within 0.01 | stop; record the build difference |
| Timing | measured one request at a time, two warm-up requests excluded, nothing else on the GPU | timing is reported as not valid |

### D8. Analysis

On LiteParse text (primary) and `pypdf` text (diagnostic only), per arm:

- Junk recall and healthy false-positive rate, each with a Wilson 95% interval and a document-cluster bootstrap interval (2,000 resamples, seed 42).
- Per-document recall, and routing for every document at the unchanged `0.10` fraction: newly routed documents, missed junk-layer documents, projected OCR time for each newly routed document.
- Exact one-sided McNemar on junk pages, Clef-flash against A, with the recall difference.
- AUC (junk scored below healthy) for both signals. Diagnostic only; it decides nothing.
- Seconds per page for Clef-flash under D7 timing.

### D9. Stopping rules and amendments

- Stop before scoring if any D3 target is missed after sourcing. The operator then extends sourcing or accepts a smaller set. Either choice is a dated amendment with a new power statement, written before any score.
- Stop if D4's operator check or `freeze.py --check` fails.
- Stop if any D7 check fails.
- Stop scoring if more than 1% of requests fail after three retries. The failed pages are reported, never dropped in silence.
- Amendments are dated, committed and listed in `plan.json` `amendments` before the data they affect is scored. An amendment never changes the frozen thresholds, the wording, the gates, the margin or OD1 after any score exists.
- No interim look. No score, count or plot is opened until scoring of every arm ends and the outputs are hashed.

### D10. Outcome mapping

| Clef-flash passes the primary gates and the margin | A passes the primary gates | Verdict | Next step |
| --- | --- | --- | --- |
| yes | any | PASS | Open a follow-up OpenSpec change to adopt the gate in production, and an ADR for it |
| no | yes | FAIL for Clef-flash | Record; the operator decides whether A alone justifies a proposal |
| no | no | FAIL | Record which gate failed and on which pages. Stop work on text-only rescue signals |

"Primary gates" follows OD1. Under option A, a G3 result above 0.02 goes into the follow-up change as a known cost. A PASS changes nothing in production by itself.

## Risks / Trade-offs

- [Local reference engine makes errors that look like junk in the rescue text] → operator check of 60 pages (D4); pages the engine marks illegible are excluded.
- [Old-OCR scans are hard to find without looking at their text] → selection uses metadata and labels only; no candidate score exists before the freeze.
- [New documents differ in kind from Experiment 33] → strata and counts are reported; per-document recall shows where the signal fails.
- [Junk still clusters in one or two documents] → the 25% cap (D3) and the cluster bootstrap.
- [llama.cpp or model file drift] → build and hash checks plus the 40-page reproduction check (D7).
- [The threshold sits on a steep part of the score distribution] → the report gives the false-positive rate at thresholds 10% above and below the frozen value as a sensitivity view. It decides nothing.
- [OD1 option A lowers the bar] → G2 stays a hard gate, and the G3 rate and interval appear in the verdict line.

## Migration Plan

None. Nothing ships. A PASS leads to a separate change with its own rollout.

## Operator decisions before the run

1. **OD1, gate priority.** Option A (recommended) or option B, see D6. Recorded in `plan.json` `decision_register`.
2. **OD2, reference transcription engine.** dots.mocr (recommended: local, installed, ADR-072 primary engine) or another local engine the operator names. A hosted transcription model, as used in Experiment 33, needs a dated amendment and approval, because page text would leave the machine.
3. **OD3, model and runtime reuse.** Reuse the Experiment 38 llama.cpp b11510 build and Q8_0 file if their hashes match (recommended), or approve a fresh download of a later build.
