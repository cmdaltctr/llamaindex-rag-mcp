# Design: page-level OCR routing

## Context

The `pdf-reader` spec requires whole-PDF dispatch and forbids merging page fragments from two engines. That rule kept the first OCR implementation simple. Experiments 29 and 33 show its cost: OCR price scales with total pages, not with pages that need OCR, and every extra flagged page (a scan or an illustration) moves the whole document.

pdf-inspector 1.17.0 facts (Experiment 33, synthetic probe files only):

- `extract_pages_markdown(path)` returns per-page Markdown and `needs_ocr` for every page (no 8-page sample).
- `process_pdf_with_ocr(path, mode, page_numbers, dpi, minimum_confidence, hosted_recommendation_confidence, model_directory, offline)` OCRs routed pages with PP-OCRv6 Small (`oar-ocr-v0.7.0`) on ONNX Runtime and returns per-page Markdown with provenance (`source`, `ocr_confidence`, `ocr_model`, warnings) plus `pages_recommending_hosted`.
- Probe pb03: routed exactly pages 2, 10 and 14; local OCR produced no text on those heavily degraded pages and recommended hosted OCR for all three.
- Synthetic scan sy01: about 2.3 s per page; token recall against the clean source 0.66 to 0.96 on 6 pages and 0.04 to 0.15 on 4 pages, which carried confidence 0.51 to 0.61.
- It needs a PDFium shared library (`PDFIUM_LIB_PATH`). The LiteParse-bundled library worked in the probe; compatibility is not validated.

## Goals

- OCR cost proportional to pages that need OCR.
- Chart and drawing pages can be OCRed without moving the whole document.
- Keep PaddleOCR-VL quality for pages the local engine cannot read.
- Keep today's behaviour as the default until evidence supports a change.

## Non-Goals

- No default change in this proposal.
- No replacement of PaddleOCR-VL and no cloud OCR.
- No change to the `document` unit's thresholds.

## Decisions

1. **Opt-in unit.** `OCR__ROUTING_UNIT` in the OCR settings block, values `document` (default) and `page`, validated at startup.
2. **Page evidence.** `page` mode takes per-page `needs_ocr` from a full scan. No sampled evidence and no page-fraction threshold: every flagged page is handled.
3. **Tier 1: local OCR.** pdf-inspector selective OCR on flagged pages only, CPU, in-process, GIL released. Model directory and offline mode come from settings; no network in offline mode. Every flagged page is tried locally first: at 0.75 s median per page against 34 to 106 s hosted, trying and escalating costs less than any attempt to predict failure would save.
4. **Tier 2: escalation, decided after the attempt.** A page escalates when any of these holds:

   - local OCR returns empty or whitespace-only text;
   - `ocr_confidence` is below `OCR__LOCAL_MIN_CONFIDENCE` (0.8);
   - `hosted_recommended` is set.

   Experiment 33 task 6.7 supports each term. Empty output catches the classes
   the packaged model cannot read at all: all 129 Devanagari and Arabic pages
   scored recall 0.000. The 0.8 confidence cut escalates 46.9% of `needs_ocr`
   pages and leaves 11.3% of kept pages below 0.5 recall. `hosted_recommended`
   is weak on natural documents — it fired on 6 of the 206 pages below 0.5
   recall — and is kept because it costs nothing and fired on no page that
   scored recall ≥ 0.8 (n=124); all six pages it flagged scored 0.000.

   **No script or typography signal is used, because none was measured.** A
   pre-check would have to judge a page before OCR runs, when the page is still
   an image; task 6.7 measured which documents fail, not a signal that predicts
   it beforehand. Escalating after the attempt reaches the same pages on
   evidence that exists.

   Escalated pages go to the PaddleOCR-VL worker in one request with a page
   list (protocol 1.1, optional `pages`).
5. **Merge.** Pages are joined in page order. Each page keeps the text of the highest tier that produced usable text. Metadata carries scalar counts (`ocr_pages_native`, `ocr_pages_local`, `ocr_pages_worker`, `ocr_pages_unresolved`); readers with page provenance also emit per-page `source`. New keys join `EXCLUDED_EMBED_METADATA_KEYS`.
6. **Degradation.** Worker unavailable: keep tier 1 text and count unresolved pages. Local runtime or PDFium unavailable: keep native text for flagged pages, count them unresolved, warn once per operation. Never fail the file for a missing optional tier.
7. **Identity.** The routing unit, local OCR model identity and the worker fingerprint join the source index identity, so switching units re-ingests affected sources.
8. **Heading consistency.** Merged pages keep per-page Markdown; the chunker's Markdown routing is unchanged. A retrieval experiment checks chunk quality before any default change.

## Risks

- PDFium binary compatibility and packaging (ADR required).
- The `io06` blind spot is accepted and named: early-modern Latin type reads at median confidence 0.922 and median recall 0.609, so the 0.8 cut keeps it. No measured signal separates confident-but-wrong typography; task 2.3 is where that evidence would come from.
- Residual: 11.3% of pages kept at the 0.8 cut fall below recall 0.8. Task 6.1 judges whether that is acceptable for retrieval.
- Escalation is 46.9% of `needs_ocr` pages on the Experiment 33 corpus, so the tier halves worker cost rather than removing it.
- Mixed-engine Markdown can differ in heading style across pages.
- Worker protocol change touches the twin protocol copy and its byte-for-byte test.

## Evidence gate 1 result (Experiment 33 task 6.7, 2026-09-17)

pdf-inspector 1.17.0 `process_pdf_with_ocr` in `force` mode (PP-OCRv6 Small,
ONNX Runtime, CPU) on 464 natural pages the frozen Experiment 33 labels mark
`needs_ocr`, across 28 documents. 731 s wall clock, no error, no document over
the 900 s soft limit. Token recall against a vision-model reference
transcription. Source: `experiments/33-ocr-routing-natural-positive-2026-09-17/output/local_ocr/summary.json`.

| Measurement | Value |
| --- | ---: |
| Pages measured | 464 (399 body `needs_ocr`, 65 figure-only) |
| Body recall ≥ 0.8 | 0.311 |
| Body recall < 0.5 | 0.516 |
| Pages with no text | 0.003 |
| `hosted_recommended` | 0.015 |
| Seconds per page | 1.58 mean, 0.75 median |

The aggregate is bimodal. What decides the outcome is the writing system and
the typography, not page quality:

| Class | Pages | Median recall | ≥ 0.8 |
| --- | ---: | ---: | ---: |
| Modern Latin-script print | 144 | 0.977 | 0.840 |
| Early-modern Latin book (`io06`) | 66 | 0.609 | 0.015 |
| Handwriting (`rf06`, `rf07`) | 60 | 0.310 | 0.033 |
| Devanagari and Arabic (`io01`, `io02`, `io03`, `io07`) | 129 | 0.000 | 0.000 |

Confidence calibration for decision 4 and task 2.2:

| Cut | Escalation share | Kept, recall ≥ 0.8 | Kept, recall < 0.5 |
| ---: | ---: | ---: | ---: |
| 0.5 | 0.015 | 0.316 | 0.509 |
| 0.6 | 0.160 | 0.370 | 0.424 |
| 0.7 | 0.381 | 0.502 | 0.219 |
| 0.8 | 0.469 | 0.571 | 0.113 |
| 0.9 | 0.597 | 0.652 | 0.025 |

Confidence separates readable from unreadable pages well (AUC 0.949 over the
399 body pages). A 0.8 cut escalates `io01` 1.00, `io03` 1.00, `io07` 1.00,
`io02` 0.94, `tl01` 0.92, `rf07` 0.65 and `rf06` 0.63, and leaves every
modern-print document at 0.00. It has one blind spot: `io06` escalates at 0.08
while reading at median recall 0.609, because the model is confident and half
wrong on early-modern typography.

`pages_recommending_hosted` fired on 6 pages, all genuinely bad, out of 206
pages below 0.5 recall. It is precise and nearly deaf; the confidence cut has
to carry decision 4.

## Evidence gate 1 verdict (task 1.2, operator decision 2026-09-17)

**REWORK.** Evidence gate 1 half-passes. Local OCR is viable for modern
Latin-script print (84% of pages at recall ≥ 0.8, 0.75 s median) and unusable
for non-Latin scripts (129 pages, recall 0.000) and handwriting (0.310).
Confidence separates the two (AUC 0.949).

Conditions before implementation:

1. Add a pre-check before the local tier: pages whose script or typography is
   outside the supported set skip local OCR and escalate directly. The
   supported set is named from the task 6.7 per-class table: modern
   Latin-script print. Devanagari, Arabic and handwriting are outside it.
2. `OCR__LOCAL_MIN_CONFIDENCE = 0.8` (escalation 46.9%, wrongly kept 11.3%).
3. The `io06` blind spot is an accepted, named risk: early-modern Latin type
   reads at confidence 0.922 with recall 0.609, so a confidence cut keeps it.
   Do not invent a typography heuristic without measurement; it is a
   calibration task with its own evidence (task 2.3).
4. Keep `hosted_recommended` as an escalation trigger, noting it is weak here
   (fired on 6 of 206 pages below 0.5 recall).
5. Residual: 11.3% of kept pages fall below recall 0.8. The retrieval
   experiment in task 6.1 decides whether that is acceptable.

Tasks 3 to 6 proceed under these conditions.

**Amendment, 2026-09-18 (operator).** Condition 1 above called for a script and
typography pre-check. It is dropped. The failures it aimed at announce
themselves after the attempt — empty output covers the 129 unreadable pages —
and a pre-check would need a signal nobody has measured. Decision 4's
post-check rule replaces it. Conditions 2 to 5 stand unchanged.

## Evidence gates

1. Experiment 33 local-OCR stage: token recall of local OCR against the reference transcription on natural pages labelled `needs_ocr`, confidence calibration, escalation rate, seconds per page.
2. New retrieval experiment: `page` vs `document` units on a corpus with mixed documents (Recall@K, MRR@10, ingestion time) before changing the default.
