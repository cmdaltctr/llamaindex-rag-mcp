# Tasks: page-level OCR routing

**Progress 2026-09-18:** 5 of 17 done, 3 deferred by their own terms. Settings,
index identity and per-page evidence are in. Task 4.5's merge is built and
tested as a pure function but is not yet wired into the reader, so it stays
open. Next: 4.2 (local tier), then 4.3/4.4 (worker protocol 1.1 and
escalation), then 4.5's wiring and 4.6.

## 1. Evidence gate (before implementation)

- [x] 1.1 Receive Experiment 33 local-OCR results: token recall on natural `needs_ocr` pages, confidence calibration, escalation rate, seconds per page.
- [x] 1.2 Record the go / rework / stop decision in this change's design with the Experiment 33 numbers. **REWORK**, with five conditions; see `design.md` "Evidence gate 1 verdict".

## 2. Decisions

- [ ] 2.1 Write an ADR for page-level routing and the PDFium shared-library dependency (source, version pin, packaging, licence).
- [x] 2.2 Set `OCR_LOCAL_MIN_CONFIDENCE` to `0.8` from the Experiment 33 task 6.7 calibration table (escalation 46.9%, wrongly kept 11.3%).
- [ ] 2.3 DEFERRED — io06 calibration. Waits on evidence that any signal separates confident-but-wrong early-modern typography; none is measured.

## 3. Configuration and identity

- [x] 3.1 Add `OCR_ROUTING_UNIT` (`document` default, `page`) and local OCR settings (model directory, offline, minimum confidence) with startup validation.
- [x] 3.2 Add the routing unit and local OCR model identity to the source index identity.

## 4. Page routing

- [x] 4.1 Per-page OCR evidence from a full page scan in `page` mode. `page_routing.page_evidence`, 1-based, raises on a failed scan (the page unit has no sampled evidence to fall back to). 5 tests.
- [ ] 4.2 Local OCR tier via pdf-inspector selective OCR on every flagged page.
- [ ] 4.2a Post-check escalation: a page escalates on empty or whitespace-only local output, confidence below `OCR_LOCAL_MIN_CONFIDENCE`, or `hosted_recommended`. No pre-check; no script or typography signal.
- [ ] 4.3 Worker protocol 1.1 with optional `pages` in both protocol copies; keep 1.0 compatible.
- [ ] 4.4 Escalate unreadable local pages to the worker in one request.
- [ ] 4.5 Merge pages in order; emit scalar page-source counts and per-page provenance where supported; register new metadata keys.
  - [x] 4.5a `page_routing.merge_pages`: page-order join, four counts summing to `page_count`, `ocr_backend` including `mixed`. 12 tests.
  - [x] 4.5b Register the four count keys in `EXCLUDED_EMBED_METADATA_KEYS`, scoped in the index identity so a document-unit install does not reindex. 4 tests plus the emitted-document guard.
  - [ ] 4.5c Wire the merge into the reader, so a `page`-unit ingest actually emits it. Blocked on 4.2 to 4.4.
- [ ] 4.6 Per-page degradation for missing worker, PDFium or ONNX Runtime.

## 5. Tests

- [ ] 5.1 Unit tests for every spec scenario with stubbed pdf-inspector and worker.
- [ ] 5.2 Protocol twin byte-for-byte test for 1.1.
- [ ] 5.3 Document-unit regression: default behaviour unchanged.

## 6. Validation and docs

- [ ] 6.1 DEFERRED — retrieval experiment (`page` vs `document`). Waits on a mixed-document corpus; it gates a future default change, not this one.
- [ ] 6.2 Update `docs/guides/ingestion.md` and `docs/guides/configuration.md`. Must cover the flat `OCR_ROUTING_UNIT` and `OCR_LOCAL_*` names and why they are flat.
- [ ] 6.3 DEFERRED — default change. Waits on task 6.1; belongs in its own proposal by this change's own terms. If `page` ever becomes the default, empty `PAGE_ROUTING_ONLY_EMBED_KEYS` and bump `_INDEX_IDENTITY_SCHEMA` in the same change: from then on every install can emit those keys, so subtracting them would hide a real change in embedded text.
