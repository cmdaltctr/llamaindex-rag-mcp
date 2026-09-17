# Tasks: full-page OCR evidence for pdf-inspector

## 1. Tests first

- [x] 1.1 Add reader tests: text_based 20 pages counts full-scan pages; ≤8 pages and scanned/image_based/mixed skip the scan; scan failure keeps the sampled count; silent-empty rescue records the full-scan count before fallback.
- [x] 1.2 Confirm the full-scan and rescue tests fail on the current adapter.

## 2. Implement

- [x] 2.1 Add `PDF_INSPECTOR_SAMPLED_PAGES = 8` and the full-page scan in `integrations/pdf/pdf_inspector.py` before the silent-empty guard.
- [x] 2.2 Keep the sampled evidence and log a warning when the full scan raises; log INFO when it finds pages the sample missed.
- [x] 2.3 Run the reader, seam and gate tests, then the fast suite with coverage.

## 3. Evidence and docs

- [x] 3.1 Measure extra read time on Experiment 33 natural text_based PDFs over 8 pages.
- [x] 3.2 Re-run the Experiment 33 boundary probe and position sweep on the fixed code.
- [x] 3.3 Write TDR-026 (cause, evidence, fix, cost, reindex note).
- [x] 3.4 Update `docs/guides/ingestion.md` for complete `pages_needing_ocr` evidence.

## 4. Close

- [x] 4.1 Run `./scripts/local_ci.sh` and `openspec validate --all --strict`.
- [x] 4.2 Open a PR to `v3`.
