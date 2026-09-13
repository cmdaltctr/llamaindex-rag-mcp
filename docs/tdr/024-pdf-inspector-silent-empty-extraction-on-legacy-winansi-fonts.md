# TDR-024: pdf-inspector silently extracts nothing from WinAnsi TrueType PDFs without `/ToUnicode` — retry with pypdf in the adapter

**Date:** 2026-09-13
**Status:** Accepted
**Deciders:** Aizat
**Tags:** pdf | ingestion | pdf-inspector | pypdf | ocr-routing

## Context

Experiment 29 (`experiments/29-pdf-routing-repeat-2026-09-13`) replayed
the production OCR-routing gate over an operator-approved collection.
One development document — Sloman 1971, a 17-page scanned-era paper —
surfaced a reader defect: `pdf-inspector` 1.17.0 classified the file
`text_based` at confidence 1.0, flagged all 17 pages as needing OCR, and
returned **empty Markdown**. The pipeline would have ingested zero
characters with no error, or — under the promoted routing thresholds
(0.5 confidence, 0.10 page fraction) — dispatched ~30 minutes of OCR for
text that was never actually missing.

### Root Cause Analysis

The file's text layer uses pre-2000 WinAnsi-encoded TrueType fonts that
carry no `/ToUnicode` character map. pdf-inspector's Rust extractor
cannot map the glyphs to Unicode and returns an empty string while the
classifier (which only checks whether a text layer exists) still reports
`text_based`. pypdf reads the same file at ~2,944 characters per page —
the raw text layer is imperfect 1990s publisher OCR, but it is real
text.

The signature is a contradiction triple: `pdf_type == "text_based"` AND
`markdown == ""` AND `page_count > 0`. The classifier saw a text layer
the extractor failed to read.

## Decision

Add a guard inside `PdfInspectorReader.load_data`
(`src/omrg/integrations/pdf/pdf_inspector.py`):

1. **Trigger on the contradiction only.** `text_based` + empty Markdown
   + `page_count > 0`. No confidence band, no short-Markdown heuristic —
   only the observed failure signature.
2. **Retry through the registry.** `registry.get("pypdf")` inside the
   retry path — lazy, like every adapter import; no new dependency
   (pypdf is already a base dependency).
3. **Join per-page text into one document** with blank lines, keeping
   the one-document-per-file contract. No page provenance is fabricated.
4. **Correct the routing evidence on success.** Set
   `pages_needing_ocr` to 0 — the pages were flagged only by the failed
   extraction. Preserve the original count under
   `pages_needing_ocr_before_fallback` and stamp
   `extraction_fallback_backend="pypdf"`. Without the zeroing, the OCR
   seam would read 17/17 flagged and dispatch OCR onto recovered text.
5. **Propagate retry exceptions.** A file that opens in pdf-inspector
   but crashes pypdf is genuinely broken; swallowing the error would
   reintroduce a silent failure.
6. **Leave the failed retry unchanged.** If pypdf also yields no text,
   emit the original pdf-inspector result with its flagged count intact
   so the OCR gate still sees the evidence.

The guard lives in the adapter, not the OCR seam, so it also fixes
routing-disabled deployments (where the empty Markdown is ingested
as-is today).

## Consequences

### Positive

- Sloman-class files go from zero-character ingestion to full plain-text
  ingestion (~1 s instead of ~30 min of OCR).
- The OCR gate's evidence stays honest: recovered files take the fast
  path, genuinely unreadable files still route.
- Diagnostics make provenance visible on every retrieval result.

### Negative

- The recovered text is the raw text layer — for the Sloman class that
  layer is itself dated publisher OCR. Imperfect text beats zero text,
  and the diagnostic keys mark it.
- One extra dependency call per contradiction file. Bounded: the retry
  only runs when pdf-inspector already returned nothing.

### Neutral

- When an upstream pdf-inspector fix lands, the trigger stops firing —
  the guard stays correct with no migration.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Guard inside `OcrRoutedPdfInspector` | Routing-disabled users would still ingest zero characters — the defect is in the adapter's output, not the seam's decision |
| Wrapper class in `factory.build_pdf_reader` | Duplicates the activation matrix the seam already owns |
| Catch retry exceptions and degrade to the empty Markdown | That is the silent-failure status quo being removed |
| Fix pdf-inspector upstream | A Rust glyph-mapping bug; worth filing but not a workaround this repo controls |

## How to Recognise / Handle This Again

1. Symptom: an ingested PDF produces zero chunks (or OCR is dispatched
   for a born-digital-era file) while `pdf_type` reads `text_based` at
   high confidence.
2. Confirm: `pdf-inspector` returns empty Markdown AND
   `pages_needing_ocr == page_count`; `pypdf` extracts non-empty text.
3. Check provenance on stored nodes: `extraction_fallback_backend`
   names which reader produced the text;
   `pages_needing_ocr_before_fallback` preserves the flagged count.
4. For new classes of silent-empty extraction, add evidence before
   extending the trigger — the guard fires only on the observed
   signature.

## Revisit Triggers

- A pdf-inspector release fixes WinAnsi-without-`/ToUnicode` extraction
  (the guard stops firing; the tests remain valid as regression checks).
- A second silent-empty signature appears (e.g. partial extraction) —
  needs its own measured evidence before a rule exists.
- pypdf is replaced as the registered plain-text reader.

## References

- `src/omrg/integrations/pdf/pdf_inspector.py` — the guard
- `tests/unit/test_pdf_inspector_reader.py` — adapter tests
- `tests/test_ocr_routing_seam.py` — seam-level evidence-correction tests
- `experiments/29-pdf-routing-repeat-2026-09-13/report.md` — the Sloman
  observation and projected-cost analysis
- OpenSpec change `openspec/changes/pdf-reader-extraction-fallback/` —
  proposal, design (D1–D6) and spec deltas
