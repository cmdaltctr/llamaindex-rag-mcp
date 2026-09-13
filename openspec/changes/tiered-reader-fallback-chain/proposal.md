# Proposal: tiered-reader-fallback-chain

## Why

Experiment 30 (PASS, 4/4 gates) and ADR-066: the shipped silent-empty
guard retries with pypdf alone, but liteparse rescues every known
failure class — Internet Archive GlyphLessFont scans and Acrobat-Capture
WinAnsi — up to ~45× faster (0.36 s vs 16.1 s on the largest observed
file), while omitting textless pages. pdf-inspector stays primary: it is
the only reader emitting the classification evidence the OCR routing
gate consumes, and its Markdown remains best on healthy PDFs (ADR-050).

## What Changes

- The pdf-inspector adapter's silent-empty retry becomes a chain:
  **liteparse first, pypdf last**. When liteparse is unavailable or
  yields no text, pypdf retries — preserving the shipped guard's
  coverage in every environment.
- The `extraction_fallback_backend` diagnostic now names the tier that
  produced the text (`liteparse` or `pypdf`).
- The liteparse tier runs in self-contained extraction-only mode:
  `ocr_enabled=False` and `num_workers=None` are supplied explicitly,
  so the rescue works without global settings and operator OCR settings
  cannot turn the chain into an OCR path.
- Evidence-correction semantics are unchanged: a successful retry zeroes
  `pages_needing_ocr` and preserves the flagged count under
  `pages_needing_ocr_before_fallback`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `pdf-reader`: modifies the requirement "pdf-inspector silent-empty
  extraction SHALL recover via a plain-text retry" — the retry is now
  tiered (liteparse → pypdf) with tier-honest diagnostics.

## Impact

- **Code**: `src/omrg/integrations/pdf/pdf_inspector.py` (tiered retry),
  `tests/unit/test_pdf_inspector_reader.py`,
  `tests/test_ocr_routing_seam.py`.
- **Behaviour**: rescued documents carry slightly fewer characters
  (textless pages omitted); recovery is faster; routing decisions are
  identical (Exp 30 measured no divergence).
- **Dependencies**: none added — liteparse and pypdf are base
  dependencies.
- **Docs**: `docs/guides/ingestion.md` fallback-tier mention.
