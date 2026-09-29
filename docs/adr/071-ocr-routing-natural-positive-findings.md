# ADR-071: OCR Routing on Natural Documents: Findings and Decisions

**Date:** 2026-09-29
**Status:** Accepted (2026-09-29)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `openspec/changes/experiment-33-ocr-routing-natural-positive/`
**Related:** [ADR-065](065-ocr-fallback-gate-promoted-to-packaged-default.md) (gate and unconditional types), [ADR-066](066-tiered-reader-fallback-chain.md) (reader chain), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (page-level routing and local tier), TDR-024 (rescue zeroes OCR evidence), TDR-026 (sampled OCR evidence), Experiments 29, 30, 31, 34
**Evidence:** `experiments/33-ocr-routing-natural-positive-2026-09-17/report.md`

## Read this first: what the evidence cannot show

Four limits apply to every decision below.

1. **The operator's understanding notes are not OCR findings.** The operator
   reviewed 277 pages and recorded a second kind of need: equations and
   scientific notation, figures and charts that need interpretation, two- and
   three-column layout, tables, headings, footnotes and sidebars, old-book
   spelling, and non-Latin scripts (Hindi, Arabic). Many of these pages already
   held 80% or more of their body words. OCR does not fix them. They are kept as
   `understanding_label` and notes in `spot_check.json`. No routing score uses
   them.
2. **Task 5.3, the print-and-rescan tier, was skipped.** The operator skipped
   it on 2026-09-17. Real physical scan artefacts are untested: page curl,
   uneven lighting, bleed-through and paper texture.
3. **The labels are partly automatic.** The automatic rule disagreed with the
   operator on 41.5% of the random sample, and on 20.2% after a narrower
   re-check. The final labels take the operator's verdict on the 277 reviewed
   pages and the rule on the other 846. The rule is known to miss equation loss
   on those 846 pages.
4. **The sample is small.** There are 18 documents that need OCR, so the recall
   interval is wide. Documents over 100 pages are outside the corpus.

## Context

Experiment 29 promoted the OCR routing gate (`OCR_FALLBACK_ENABLED=true`,
confidence `0.5`, page fraction `0.10`). Its held-out set had no document that
needed OCR, so recall was never measured. Experiment 33 built that set: 40
open-licence PDFs, 1,123 pages, 5 strata, with 18 documents labelled
`needs_ocr` and 22 labelled `usable`. It ran the packaged gate through the
production `read_documents` path with no OCR worker, in two arms: the gate as
shipped (`sampled_baseline`) and the full-page evidence candidate
(`full_scan_candidate`).

Results:

| Arm | Recall | Missed | Healthy documents routed |
| --- | --- | ---: | ---: |
| `sampled_baseline` | 0.556 (10 of 18, Wilson 0.337 to 0.754) | 8 | 1 of 22 |
| `full_scan_candidate` | 0.611 (11 of 18, Wilson 0.386 to 0.797) | 7 | 1 of 22 |

The preregistered false-negative trigger fired in both arms. The misses have
three separate causes:

1. **Sampling.** `tl02` had its scanned pages outside the 8-page sample.
2. **Detection.** `mx02`, `mx07`, `tl07` and `tl08` are scans with a header line
   or little text, so the page test does not call them scans. `rf06` and `rf07`
   are handwritten records where the LiteParse rescue accepted junk text
   (fast-path recall 0.236 and 0.469). TDR-024 then set `pages_needing_ocr` to
   zero, which hid the scan.
3. **Definition.** `bd04` keeps its words and loses its equations. The gate
   measures missing words, so it cannot see this.

The one false positive, `mx08`, is classified `image_based` and routed by
type (ADR-065). Classification decided it, not a threshold.

The local OCR tier (pdf-inspector selective OCR, PP-OCRv6 Small, ONNX Runtime,
CPU) ran in `force` mode on 464 pages. It reads modern Latin print well
(median token recall 0.977) and handwriting badly (0.310). It scored 0.000 on
all 129 Arabic and Hindi pages, because the packaged model has no recogniser
for those scripts. Its confidence score separates good from bad pages well
(AUC 0.949). It is confident and wrong on `io06`, an early-modern Latin book.
The median cost was 0.75 s per page.

## Decision

1. **Leave the thresholds at `0.5` and `0.10`.** Two of the three causes,
   detection and definition, do not respond to a threshold. No calibration
   proposal follows from this experiment.
2. **Keep the full-page evidence fix.** It moved `tl02` from missed to caught
   and added no false alarm on this corpus. Page-level routing (ADR-069)
   already scans every page.
3. **Proposed follow-up: a low-quality rescue must not zero the OCR
   evidence.** This is the fix for `rf06` and `rf07`, and it is a separate
   change after this ADR. A rescue that returns text should zero the evidence
   only when the text passes a quality signal. The mechanism is open. Two
   candidates exist: deterministic checks (real-word ratio, script mismatch),
   and Julia 1 (Supersonic Labs, Apache 2.0, 144M parameters, CPU) asked one
   yes/no question about the text. A small follow-up experiment scores both on
   the 1,123 pages of this corpus against the frozen recall labels. Julia 1 is
   adopted only if it beats the deterministic baseline by a margin fixed before
   the run. It needs PyTorch or an ONNX Runtime route, so adopting it needs its
   own decision on the runtime.
4. **Proposed follow-up: the local tier escalates on script and typography,
   not on confidence alone.** A confidence cut of 0.8 escalates every class the
   model cannot read and leaves modern print alone. It still keeps `io06`,
   where the model is confident and wrong. The escalation rule must not admit
   pages the local model cannot read. The mechanism is open. Script detection by
   Unicode block covers Arabic and Devanagari. The `io06` case needs a signal
   from the OCR engine, because a text model cannot see typography.
5. **dots.mocr is the primary OCR engine and PaddleOCR-VL is the fallback.**
   The operator decided this on 2026-09-24 (`modular-ocr-workers-dots-mocr`).
   The local tier stays on PP-OCRv6 Small. dots.mocr needs PyTorch and 7 to
   9 GB, so it cannot replace a CPU tier that runs on ONNX Runtime. The
   experiment protocol is frozen and is not edited to match.
6. **Stage B stays unauthorised.** A real OCR engine on named pages needs a
   separate operator decision naming the document subset, timeout and runtime
   budget. If authorised, it runs dots.mocr first.
7. **Experiment 37 scores both engines on the pages the local tier cannot
   read.** It adds `io01`, `io02`, `io03`, `io07`, `rf06` and `rf07` from this
   corpus, using the frozen labels and reference transcriptions (PR #102).

## Consequences

### Positive

- The gate has natural-positive recall evidence with a stated interval.
- Every miss has a named cause and a named owner: PR #95 for sampling, the
  proposed rescue-quality change for detection, and the understanding notes for
  definition.
- Leaving the thresholds alone avoids a change that would have fixed none of
  the causes and could have raised false positives.

### Negative

- The gate still misses about half of the natural OCR need until the
  decision 3 follow-up ships. `rf06`, `rf07`, `mx02`, `mx07`, `tl07`, `tl08` and `bd04` stay on the
  fast path.
- The recall figure has a wide interval (18 positives).
- The OCR time projections (3.7 to 11.7 h baseline, 4.2 to 13.1 h candidate)
  use the Experiment 24 PaddleOCR-VL rates of 33.7 to 106.4 s per page. They do
  not describe dots.mocr. Experiment 34 measured dots.mocr at 1.4 to 3.6 times
  faster per page, on GPU against Paddle on CPU, so the two rates do not
  compare directly.
- Physical scan artefacts remain untested (limit 2).

### Neutral

- The understanding needs stay outside the OCR pipeline. They are a separate
  problem, recorded for later work.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| **Lower the page fraction or raise the confidence threshold** | Detection and definition failures do not depend on either value. `tl07`, `tl08` and `bd04` carry no scanned-page signal to threshold. |
| **Replace the LiteParse rescue** | The rescue reads most healthy pages well (median recall 0.991). The fault is that its output zeroes the OCR evidence, not that it runs. |
| **Replace the local tier with dots.mocr** | dots.mocr needs PyTorch and a GPU class of memory. The base install allows ONNX Runtime only. |
| **Hosted Jev (TypeSafe AI) for either follow-up** | Closed weights and hosted only. It would send page text, including personal records, to a third party, and the project needs an ADR and a local fallback for any cloud dependency. |
| **Rely on the confidence score alone for escalation** | It misses `io06`, where the local model is confident and about 40% wrong. |
| **Do nothing** | The preregistered trigger fired. Half of natural OCR need reaches the index as junk or nothing. |

## References

- `experiments/33-ocr-routing-natural-positive-2026-09-17/report.md`,
  `protocol.md`, `plan.json`, `spot_check.json`, `labels.json`
- `experiments/33-ocr-routing-natural-positive-2026-09-17/output/arm_comparison.json`
- `experiments/34-worker-sample-review-2026-09-19/report.md`
- `openspec/changes/modular-ocr-workers-dots-mocr/`
- PR #95 (full-page OCR evidence), PR #96 (page-level routing), PR #102
