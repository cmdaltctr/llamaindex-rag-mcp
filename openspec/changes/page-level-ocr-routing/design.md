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
3. **Tier 1: local OCR.** pdf-inspector selective OCR on flagged pages only, CPU, in-process, GIL released. Model directory and offline mode come from settings; no network in offline mode.
4. **Tier 2: escalation.** A page escalates when local OCR returns no text, confidence below `OCR__LOCAL_MIN_CONFIDENCE` (calibrated by Experiment 33, not guessed), or `hosted_recommended`. Escalated pages go to the PaddleOCR-VL worker in one request with a page list (protocol 1.1, optional `pages`).
5. **Merge.** Pages are joined in page order. Each page keeps the text of the highest tier that produced usable text. Metadata carries scalar counts (`ocr_pages_native`, `ocr_pages_local`, `ocr_pages_worker`, `ocr_pages_unresolved`); readers with page provenance also emit per-page `source`. New keys join `EXCLUDED_EMBED_METADATA_KEYS`.
6. **Degradation.** Worker unavailable: keep tier 1 text and count unresolved pages. Local runtime or PDFium unavailable: keep native text for flagged pages, count them unresolved, warn once per operation. Never fail the file for a missing optional tier.
7. **Identity.** The routing unit, local OCR model identity and the worker fingerprint join the source index identity, so switching units re-ingests affected sources.
8. **Heading consistency.** Merged pages keep per-page Markdown; the chunker's Markdown routing is unchanged. A retrieval experiment checks chunk quality before any default change.

## Risks

- PDFium binary compatibility and packaging (ADR required).
- Local OCR quality on natural scans is unproven; escalation rate decides the real cost.
- Mixed-engine Markdown can differ in heading style across pages.
- Worker protocol change touches the twin protocol copy and its byte-for-byte test.

## Evidence gates

1. Experiment 33 local-OCR stage: token recall of local OCR against the reference transcription on natural pages labelled `needs_ocr`, confidence calibration, escalation rate, seconds per page.
2. New retrieval experiment: `page` vs `document` units on a corpus with mixed documents (Recall@K, MRR@10, ingestion time) before changing the default.
