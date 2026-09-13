# Tasks: tiered-reader-fallback-chain

## 1. Tiered retry

- [ ] 1.1 Red tests: stub the contradiction (process_pdf returns
  `text_based`, non-zero pages, empty Markdown) and a stubbed-liteparse
  registry tier; assert the emitted document text is the joined
  liteparse extraction and `extraction_fallback_backend == "liteparse"`.
  Confirm the tests fail on the current adapter (it names pypdf).
- [ ] 1.2 Implement the chain in
  `src/omrg/integrations/pdf/pdf_inspector.py` per design D1–D5:
  liteparse first (extraction-only, `ocr_enabled=False` forced),
  pypdf last, tier hand-over on raise-or-empty, original result when
  both tiers yield nothing, last-tier exceptions propagate.
- [ ] 1.3 Tests for the fall-through: liteparse unavailable (import
  error) or yielding no text → pypdf tier produces the text and the
  diagnostic names pypdf.
- [ ] 1.4 Test both-tiers-empty: original pdf-inspector result emitted
  unchanged with the original flagged count; no fallback diagnostics.
- [ ] 1.5 Unchanged-path tests: non-empty Markdown (no retry, no
  diagnostics), non-`text_based` classification (no retry), zero
  `page_count` (no retry).
- [ ] 1.6 Test the forced `ocr_enabled=False`: a stubbed LiteParse
  constructor records the flag; operator settings enabling liteparse
  OCR do not reach the retry tier.

## 2. Routing evidence and seam

- [ ] 2.1 Seam test: contradiction file with promoted thresholds
  (0.5/0.10) takes the fast path after the liteparse rescue — no worker
  dispatch; `pages_needing_ocr` zeroed,
  `pages_needing_ocr_before_fallback` preserved.
- [ ] 2.2 Seam test: both-tiers-empty still routes to OCR under the
  same thresholds.

## 3. Docs

- [ ] 3.1 Update the fallback-tier mention in `docs/guides/ingestion.md`
  (tier order, `extraction_fallback_backend` values, forced
  extraction-only liteparse).
- [ ] 3.2 Cross-reference ADR-066 and TDR-024 in the change's archive
  note (no ADR edit needed — ADR-066 already anticipates this change).

## 4. Verification

- [ ] 4.1 `uv run pytest tests/unit/test_pdf_inspector_reader.py tests/test_ocr_routing_seam.py -v` green.
- [ ] 4.2 `uv run pytest -m "not slow" --cov=omrg` meets coverage
  floors for touched modules.
- [ ] 4.3 `uv run openspec validate tiered-reader-fallback-chain --strict` passes.
