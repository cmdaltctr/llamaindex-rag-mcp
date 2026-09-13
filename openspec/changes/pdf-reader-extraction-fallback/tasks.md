# Tasks: pdf-reader-extraction-fallback

## 1. Adapter guard

- [x] 1.1 Write red tests for the guard trigger: stub
  `pdf_inspector.process_pdf` to return `pdf_type="text_based"`,
  `page_count=3`, empty Markdown, `pages_needing_ocr=3`; assert the
  adapter's emitted document text is non-empty pypdf text. Confirm the
  tests fail on the current adapter.
- [x] 1.2 Implement the guard in
  `src/omrg/integrations/pdf/pdf_inspector.py` per design D1–D6:
  registry-based pypdf retry, blank-line join into one document,
  additive diagnostics (`extraction_fallback_backend`,
  `pages_needing_ocr_before_fallback`), zeroed `pages_needing_ocr` on
  success, untouched original result when the retry yields no text,
  propagating retry exceptions.
- [x] 1.3 Tests for the no-retry paths: non-empty Markdown (no retry,
  no diagnostics), non-`text_based` classification with empty Markdown
  (no retry), zero `page_count` (no retry).
- [x] 1.4 Test the failed-retry path: pypdf stub returns empty text →
  original pdf-inspector result emitted unchanged with original flagged
  count.

## 2. Routing evidence

- [x] 2.1 Red test through `OcrRoutedPdfInspector`: a stubbed
  contradiction file with thresholds at the promoted values
  (0.5/0.10) must take the fast path after the guard recovers text —
  no worker dispatch. Confirm it fails pre-guard (would dispatch).
- [x] 2.2 Test that the failed-retry path still routes to OCR under the
  same thresholds (evidence unchanged).

## 3. Docs and records

- [x] 3.1 Write the TDR for the Sloman diagnosis: WinAnsi TrueType
  without `/ToUnicode`, pdf-inspector 1.17.0 silent-empty extraction,
  the reproduction, and the guard as the workaround.
- [x] 3.2 Mention `extraction_fallback_backend` and
  `pages_needing_ocr_before_fallback` in the relevant
  `docs/guides/` metadata table.

## 4. Verification

- [x] 4.1 `uv run pytest tests/unit/test_pdf_inspector_reader.py tests/test_ocr_routing_seam.py -v` green.
- [x] 4.2 `uv run pytest -m "not slow" --cov=omrg` meets the coverage
  floors for touched modules.
- [x] 4.3 `uv run openspec validate pdf-reader-extraction-fallback --strict` passes.
