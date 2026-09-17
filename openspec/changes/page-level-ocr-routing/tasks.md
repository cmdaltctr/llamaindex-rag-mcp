# Tasks: page-level OCR routing

## 1. Evidence gate (before implementation)

- [ ] 1.1 Receive Experiment 33 local-OCR results: token recall on natural `needs_ocr` pages, confidence calibration, escalation rate, seconds per page.
- [ ] 1.2 Record the go / rework / stop decision in this change's design with the Experiment 33 numbers.

## 2. Decisions

- [ ] 2.1 Write an ADR for page-level routing and the PDFium shared-library dependency (source, version pin, packaging, licence).
- [ ] 2.2 Set `OCR__LOCAL_MIN_CONFIDENCE` from Experiment 33 calibration.

## 3. Configuration and identity

- [ ] 3.1 Add `OCR__ROUTING_UNIT` (`document` default, `page`) and local OCR settings (model directory, offline, minimum confidence) with startup validation.
- [ ] 3.2 Add the routing unit and local OCR model identity to the source index identity.

## 4. Page routing

- [ ] 4.1 Per-page OCR evidence from a full page scan in `page` mode.
- [ ] 4.2 Local OCR tier via pdf-inspector selective OCR on flagged pages.
- [ ] 4.3 Worker protocol 1.1 with optional `pages` in both protocol copies; keep 1.0 compatible.
- [ ] 4.4 Escalate unreadable local pages to the worker in one request.
- [ ] 4.5 Merge pages in order; emit scalar page-source counts and per-page provenance where supported; register new metadata keys.
- [ ] 4.6 Per-page degradation for missing worker, PDFium or ONNX Runtime.

## 5. Tests

- [ ] 5.1 Unit tests for every spec scenario with stubbed pdf-inspector and worker.
- [ ] 5.2 Protocol twin byte-for-byte test for 1.1.
- [ ] 5.3 Document-unit regression: default behaviour unchanged.

## 6. Validation and docs

- [ ] 6.1 Retrieval experiment: `page` vs `document` units (Recall@K, MRR@10, ingestion time) on mixed documents.
- [ ] 6.2 Update `docs/guides/ingestion.md` and `docs/guides/configuration.md`.
- [ ] 6.3 Default change, if any, in a separate proposal.
