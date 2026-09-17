# Experiment 33: OCR routing natural-positive study

**ID**: `33-ocr-routing-natural-positive-2026-09-17`  
**Date run**: 2026-09-17  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: FAIL (Stage A) — the shipped gate misses 8 of 18 documents that need OCR  
**Verdict**: The packaged gate does not detect most natural OCR need. The full-scan candidate helps slightly (recall 0.556 → 0.611) and costs 49 extra OCR pages; recalibration belongs in a separate proposal  
**Raw data**: [`output/arm_sampled_baseline/eval_results.summary.json`](./output/arm_sampled_baseline/eval_results.summary.json), [`output/arm_full_scan_candidate/eval_results.summary.json`](./output/arm_full_scan_candidate/eval_results.summary.json), [`output/arm_comparison.json`](./output/arm_comparison.json), [`output/page_evidence.json`](./output/page_evidence.json)  
**Change**: `openspec/changes/experiment-33-ocr-routing-natural-positive`; relates to `full-page-ocr-evidence` (PR #95, TDR-026) and `page-level-ocr-routing`  
**Protocol**: [protocol.md](protocol.md)

## Bottom line

Experiment 29 promoted the OCR routing gate without ever measuring recall: its
held-out set contained no document that needs OCR. This study built one. On 40
open-licence PDFs with page-by-page labels, the shipped gate caught 10 of the
18 documents whose text is genuinely missing (`routing_recall` 0.556, Wilson
95% interval 0.337 to 0.754) and wrongly routed 1 of 22 healthy documents. The
candidate fix from PR #95, which completes pdf-inspector's page evidence,
caught one more (0.611) and added no false alarm. Three distinct mechanisms
cause the misses, and only one of them is a threshold problem.

## What we tested and why

Does the packaged OCR routing gate send a PDF to OCR when its text really is
missing, and leave healthy PDFs alone?

Two arms, same frozen corpus, same labels, same scoring; the only difference is
the code that computes the evidence the gate reads:

| Arm | Code | Difference |
| --- | --- | --- |
| `sampled_baseline` | `5bac71e` | pdf-inspector's default detection: OCR need from at most 8 sampled pages |
| `full_scan_candidate` | `7280766` (`feat/full-page-ocr-evidence`) | For `text_based` PDFs over 8 pages, OCR need from a scan of every page |

The result decides two things: whether the `0.5` / `0.10` gate needs
recalibration (a separate proposal, never this change), and whether PR #95
merges.

## Setup at a glance

| Corpus | Labels | Gate under test | Reader chain | OCR |
| --- | --- | --- | --- | --- |
| 40 natural open-licence PDFs, 1,123 pages, 5 strata | 18 `needs_ocr`, 22 `usable`, 0 ambiguous | `OCR_FALLBACK_ENABLED=true`, `0.5` confidence, `0.10` page fraction, unconditional `scanned`/`image_based` | `pdf_inspector` → `liteparse` → `pypdf` (ADR-066) | none executed; `ocr_client=None`, costs are projections |

Labels come from an independent page assessment (poppler `pdftotext` and pypdf
text layers scored against a vision-model reference transcription), then the
operator's verdicts on 277 reviewed pages, which override the rule where they
exist. See protocol.md "Label validation exercises" and the amendments in
`plan.json`: the automatic rule and the operator disagreed on 20.2% of the
random sample even after a narrowing re-check, and the cause is named below.

## Results

### Preregistered triggers

| Trigger | Rule | `sampled_baseline` | `full_scan_candidate` |
| --- | --- | --- | --- |
| Recall evaluable | ≥ 1 natural `needs_ocr` document | 18 documents — evaluable | 18 documents — evaluable |
| False negatives | `false_negative_count >= 1` fires a calibration recommendation | 8 — **fired** | 7 — **fired** |
| False positives on born-digital | `>= 1` fires | 0 | 0 |

### Primary and secondary measurements

| Measurement | `sampled_baseline` | `full_scan_candidate` |
| --- | ---: | ---: |
| `routing_recall` (routed ÷ documents needing OCR) | 0.556 (10/18) | 0.611 (11/18) |
| Wilson 95% interval | 0.337–0.754 | 0.386–0.797 |
| `false_negative_count` | 8 | 7 |
| `routing_precision` (correct ÷ routed) | 0.909 | 0.917 |
| `false_positive_count` (healthy routed) | 1 (`mx08`) | 1 (`mx08`) |
| `unnecessary_ocr_pages` (usable pages inside routed documents) | 121 | 137 |
| Routed documents / pages | 11 / 395 | 12 / 444 |
| Projected OCR time (33.7–106.4 s per page) | 3.7–11.7 h | 4.2–13.1 h |
| Read time, all 40 documents | 9.27 s | 9.51 s |

### By stratum (`sampled_baseline`)

| Stratum | Correctly routed | Missed | Healthy kept fast | Healthy routed |
| --- | ---: | ---: | ---: | ---: |
| `image_only_scan` | 8 | 0 | 0 | 0 |
| `scan_with_text_layer` | 2 | 3 | 3 | 0 |
| `mixed` | 0 | 2 | 5 | 1 |
| `reader_failure` | 0 | 2 | 6 | 0 |
| `born_digital` | 0 | 1 | 7 | 0 |

### The 8 missed documents

| Document | What it is | `pdf_type` | Pages flagged | Pages needing OCR | Missed because |
| --- | --- | --- | ---: | ---: | --- |
| `rf06` | Handwritten Spanish academic record, 89 pp | `text_based` | 0 | 43 | LiteParse rescue accepted junk text; fast-path text recall 0.236 |
| `rf07` | Handwritten Spanish academic record, 63 pp | `text_based` | 0 | 17 | Same; fast-path text recall 0.469 |
| `mx02` | GAO report with scanned comment letters, 19 pp | `text_based` | 0 | 3 | Letter pages carry header text, so the detector does not call them scanned |
| `mx07` | GAO report with scanned comment letters, 46 pp | `text_based` | 0 | 7 | Same |
| `tl07` | US patent 1701513, 3 pp | `text_based` | 0 | 1 | Drawing sheet with a little text |
| `tl08` | US patent 2163042, 4 pp | `text_based` | 0 | 1 | Same |
| `bd04` | Born-digital mathematics paper, 31 pp | `text_based` | 0 | 6 | Words extract cleanly; the equations do not. The gate never looks at maths |
| `tl02` | NASA technical note, scanned with OCR layer, 49 pp | `text_based` | 0 → 45 | 33 | 8-page sample missed every affected page. **The candidate catches this** |

### The 1 false positive

`mx08` (13-page Peruvian thesis) classifies as `image_based`, which routes
unconditionally (ADR-065). Its body text is present on 12 of 13 pages, so the
label is `usable`. Both arms route it; the classification, not the threshold,
decides.

### Reader-quality loss (fast-path text vs the reference transcription)

| Document | Token recall on the fast path | Attributed to |
| --- | ---: | --- |
| `tl02` | 0.015 | `pdf_inspector` (candidate arm routes it instead) |
| `rf06` | 0.236 | `liteparse` |
| `rf07` | 0.469 | `liteparse` |

## Discussion

1. **Three mechanisms, not one.** The misses split cleanly. `tl02` is a
   sampling failure, fixed by PR #95. `rf06`, `rf07`, `mx02`, `mx07`, `tl07`
   and `tl08` are detection failures: pdf-inspector's page test asks whether a
   page looks like a scan, and a page with a header line, a caption or junk OCR
   text does not. `bd04` is a definition failure: the gate measures missing
   words, and this page loses only its equations. No threshold change fixes the
   last two classes, which is why the `0.5` / `0.10` values are left untouched
   here.

2. **The rescue chain can hide a scan.** ADR-066's chain exists to save a
   readable text layer that pdf-inspector cannot read, and TDR-024 zeroes
   `pages_needing_ocr` after a successful rescue. On `rf06` and `rf07` the
   rescue produced text that matches 24% and 47% of the page content, and the
   zeroed evidence then kept both documents on the fast path. Experiment 31
   measured the same effect on retrieval; here it converts into two missed
   documents.

3. **The candidate fix is a small, real gain.** One more document caught, no
   new false alarm, 49 extra OCR pages, 0.24 s extra read time across 40
   documents. The illustrated-book over-routing risk recorded in TDR-026 did
   not appear on this corpus: `unnecessary_ocr_pages` rose from 121 to 137, all
   inside documents that genuinely need OCR.

4. **The operator's labels found a second question the gate does not ask.**
   The first spot check disagreed with the automatic rule on 41.5% of the
   random sample. The narrowed re-check still disagreed on 20.2%. The cause is
   not a broken rule: on 10 of those 19 pages both text layers hold 85–100% of
   the words while equations, tables, columns or figure content are lost. The
   operator's notes name the recurring cases: equations and scientific
   notation, figures needing interpretation, two- and three-column layout,
   tables, headings and footnote numbers, old-book spelling, and non-Latin
   scripts (Hindi, Arabic). Those are document-understanding needs, not OCR
   needs, and they are kept as `understanding_label` in `spot_check.json`.

5. **Limitations.**
   1. 18 positives give a wide recall interval (0.337–0.754); the direction is
      solid, the exact value is not.
   2. The 100-page cap excludes long books, including the 991-page document
      that failed Experiment 28.
   3. `mixed` is 7 GAO reports plus 1 thesis, and `scan_with_text_layer` draws
      from two producers (NASA NTRS, Google patent images).
   4. Labels on the 846 unreviewed pages come from the automatic rule, which
      is known to miss equation loss.
   5. No OCR ran. Every cost figure is a projection at the Experiment 24 rates.

## Conclusion

The question is answered: on natural documents the shipped gate detects about
half of real OCR need (10 of 18), while over-routing almost nothing (1 of 22).
The preregistered false-negative trigger fired in both arms, so a calibration
proposal is warranted — but the evidence says thresholds are the smallest part
of the problem. Two changes address the measured causes:

1. **Merge PR #95** (`full-page-ocr-evidence`): it removes the sampling blind
   spot, catches `tl02`, and adds no false alarm here.
2. **Treat a low-quality rescue as OCR-required** rather than zero evidence.
   `rf06` and `rf07` show the current rule hides scans behind junk text; this
   needs its own proposal with a quality signal.

Page-level OCR routing (`page-level-ocr-routing`) remains the structural
answer to both the cost trade-off and the understanding needs the operator
recorded; its evidence gate is task 6.7 of this experiment.

## Artefacts

| File | Description |
| --- | --- |
| `output/arm_sampled_baseline/` | Routing rows, runtime manifest and summary for the preregistered gate |
| `output/arm_full_scan_candidate/` | Same for the PR #95 candidate |
| `output/arm_comparison.json` | Per-arm headline measurements and the documents whose route differs |
| `output/page_evidence.json` | Per-page match scores, labels, `label_source` |
| `labels.json`, `spot_check.json` | Frozen labels; operator verdicts, notes and agreement |
| `output/frozen.manifest.json` | Freeze digests for corpus, labels and protocol |
| `output/probe/`, `probe.json` | Exploratory page-fraction boundary probe and position sweep |
| `synthetic.json` | Synthetic degraded set for Stage B (CER reference) |
| `SOURCING.md`, `sources.json` | Corpus provenance, licences and hashes |
