## Why

OCR routing sends a whole PDF to the PaddleOCR-VL worker (34 to 106 s per page) when a share of its pages needs OCR. The unit is wrong for real documents. A 40-page report with 3 scanned letter pages pays for 40 pages of OCR, and a journal article with chart pages either wastes minutes or keeps its chart text unread. The same trade-off drives the false-alarm risk in TDR-026: completing the OCR evidence also counts illustration pages, and each one can push a whole healthy book into OCR.

Experiment 33 showed pdf-inspector 1.17 already provides the building blocks. `process_pdf_with_ocr` scans every page, routed exactly the 3 hidden scanned pages of a 20-page probe file, and kept native text for the other 17. Its local engine (PP-OCRv6 Small on ONNX Runtime, CPU, about 2.3 s per page) reports low confidence or "hosted recommended" on pages it cannot read.

## What Changes

- Add an opt-in OCR routing unit: `OCR_ROUTING_UNIT=document` (default, today's behaviour) or `page`.
- In `page` mode, keep native pdf-inspector Markdown for pages that do not need OCR.
- OCR flagged pages locally with pdf-inspector's selective OCR (PP-OCRv6 Small, ONNX Runtime, no PyTorch).
- Escalate only pages the local engine cannot read (low confidence, empty output, or hosted recommended) to the PaddleOCR-VL worker, which gains an optional page list.
- Merge pages back in page order into one document, with per-page provenance (`native`, `local_ocr`, `worker`) and scalar page counts in metadata.
- Degrade per page: a missing worker keeps local OCR text; a missing local OCR runtime keeps native text; both are reported.
- Include the routing unit and the local OCR model identity in the source index identity.
- **No default change in this proposal.** `document` stays the default until the evidence tasks pass.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `pdf-reader`: the whole-PDF routing requirement becomes the `document` routing unit; a new requirement defines `page` routing, escalation, merge and provenance.

## Impact

- Code: `integrations/pdf/` (pdf-inspector adapter, OCR seam), `integrations/ocr_worker/` (protocol page list, twin copy in `ocr-worker/`), `config/` and settings blocks, `core/ingestion/source_state.py` identity.
- Dependencies: a PDFium shared library for pdf-inspector OCR (LiteParse already bundles one; version pinning needs an ADR), ONNX Runtime (already present), a 31 MB PP-OCRv6 model downloaded on first use or provided offline.
- Protocol: OCR worker protocol 1.1 with an optional `pages` field; 1.0 requests stay valid.
- Evidence: Experiment 33 local-OCR stage (quality on natural pages that need OCR) gates implementation; a retrieval experiment gates any default change.
- Supersedes nothing yet; relates to TDR-026 and draft PR #95.
