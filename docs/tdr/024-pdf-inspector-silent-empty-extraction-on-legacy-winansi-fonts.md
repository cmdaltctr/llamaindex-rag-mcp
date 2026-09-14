# TDR-024: pdf-inspector silently extracts nothing from WinAnsi TrueType PDFs without `/ToUnicode` — retry with pypdf in the adapter

**Date:** 2026-09-13
**Status:** Accepted (amended same day — second failure mechanism and reader matrix below)
**Deciders:** Aizat
**Tags:** pdf | ingestion | pdf-inspector | pypdf | liteparse | ocr-routing

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
- OpenSpec change `openspec/changes/archive/2026-09-13-pdf-reader-extraction-fallback/` —
  proposal, design (D1–D6) and spec deltas

## Amendment (2026-09-13): second mechanism, reader matrix, tiered chain

### Second failure mechanism: Internet Archive GlyphLessFont scans

Two operator-supplied "scanned" PDFs — both Internet Archive scans
(Producer `Internet Archive PDF 1.4.x; including mupdf and
pymupdf/skimage`) — reproduce the same silent-empty contradiction with
a **different root cause**: the text layer is a Type0 `/GlyphLessFont`
with Identity-H encoding, the invisible Tesseract OCR layer IA paints
over page images, and a `/ToUnicode` map **is present**. pdf-inspector
1.17.0 returns zero Markdown from these standard searchable PDFs
anyway. This is not an exotic edge case: IA Scribe output is the
dominant internet scanned-book format. Both files classify `text_based`
(the-prince at 0.75 confidence, managing-directories at 1.0) while
extracting nothing — the guard's trigger signature.

### Reader matrix on all three pathological files

| Reader | the-prince (136 pp, IA) | managing-directories (68 pp, IA) | Sloman (17 pp, WinAnsi) |
| --- | --: | --: | --: |
| pdf-inspector 1.17.0 | 0 chars | 0 chars | 0 chars |
| liteparse | 183,090 chars, 1.4 s | 76,719 chars, 0.1 s | 44,245 chars, 0.3 s |
| pypdf | 219,549 chars | 78,693 chars | 44,948 chars |

Classification record over the same session: pdf-inspector 4/4 correct
(`text_based` on both IA files and Sloman, `scanned` on Kerr 1998) —
the classifier is reliable even where the extractor fails. liteparse
is also Rust (over PDFium); the failures are pdf-inspector-specific.

### Routing confirmation

Replaying the production gate (promoted thresholds 0.5/0.10) on the raw
versus guarded evidence: without the guard both IA scans route to OCR
(204 pages of pointless worker time ending in the 300 s packaged
timeout — a hard file failure); with the shipped guard both stay on
the fast path with recovered text, and Kerr still routes to OCR.

### Resolution: tiered fallback chain (ADR-066, Experiment 30)

The revisit trigger below ("a second silent-empty signature appears")
fired with the IA GlyphLessFont evidence. Experiment 30
(`experiments/30-reader-fallback-chain-2026-09-13/`, PASS 4/4 gates)
validated the tiered chain — pdf-inspector primary (classification),
liteparse first fallback (fastest rescue, omits textless pages), pypdf
last (always available). Recorded in ADR-066; implementation as an
OpenSpec change modifying the shipped guard. The character deltas
between rescue tiers (liteparse ~2–16% fewer characters) are textless
pages and page furniture; token-level content equivalence is not
measured.
