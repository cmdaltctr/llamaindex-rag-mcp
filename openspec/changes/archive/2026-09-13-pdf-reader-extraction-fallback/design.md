# Design: pdf-reader-extraction-fallback

## Context

`PdfInspectorReader.load_data` (`src/omrg/integrations/pdf/pdf_inspector.py`)
calls `pdf_inspector.process_pdf` and wraps the result in one
LlamaIndex `Document` carrying classification evidence
(`pdf_type`, `pdf_confidence`, `page_count`, scalar
`pages_needing_ocr`). The OCR seam
(`OcrRoutedPdfInspector.load_data`) reads that evidence and dispatches
to the worker when the gate fires. Experiment 29 established that
pdf-inspector 1.17.0 can return `pdf_type=text_based`, confidence 1.0,
`pages_needing_ocr=17/17`, and empty Markdown for one file whose
WinAnsi-encoded TrueType fonts have no `/ToUnicode` map — pypdf reads
the same file at ~2,944 characters per page.

## Goals / Non-Goals

**Goals**

- Recover the text of the text_based-but-empty class without OCR.
- Keep the OCR gate's evidence honest after recovery.
- Keep the one-document-per-file contract pdf-inspector already has.

**Non-Goals**

- Fixing pdf-inspector upstream (a Rust glyph-mapping bug — filed
  separately, optional).
- Fallbacks for non-`text_based` classifications (that class belongs to
  OCR routing).
- Any change to reader defaults, the registry, or `auto` resolution.

## Decisions

**D1 — The guard lives inside the adapter, not the OCR seam.**
The contradiction is a property of pdf-inspector's own output, and the
guard must run whether or not the OCR seam is active (with routing off,
the empty Markdown is ingested as-is today — the guard fixes that case
too). Placing it in the seam would leave routing-disabled users with
zero-character ingestion. Alternative: a wrapper class in
`factory.build_pdf_reader` — rejected, it duplicates the activation
matrix the seam already owns.

**D2 — Retry through the registry, not a direct import.**
Construct the pypdf reader via `integrations.pdf.registry.get("pypdf")`
inside the retry path (lazy, like every adapter import). Keeps the
no-module-level-imports rule and lets tests stub the fallback reader
the same way they stub pdf-inspector.

**D3 — Retry exceptions propagate.**
If the pypdf retry raises, the exception propagates to the existing
per-file reader error boundary — a file that opens in pdf-inspector but
crashes pypdf is genuinely broken, and swallowing it would reintroduce a
silent failure while fixing another. Alternative: catch-and-degrade to
the empty Markdown — rejected, that is the status quo we are removing.

**D4 — Evidence correction, not evidence replacement.**
On a successful retry (joined text non-empty): set `pages_needing_ocr`
to 0, keep pdf-inspector's `pdf_type` and `pdf_confidence` (the
classification was right; the extraction was wrong), and add
`extraction_fallback_backend="pypdf"` plus
`pages_needing_ocr_before_fallback=<original count>`. Without the
zeroing, the seam would read 17/17 flagged and dispatch ~30 minutes of
OCR onto text recovered in ~1 second — the exact waste the report
flags.

**D5 — One joined document, no page provenance.**
pypdf emits per-page documents; the retry joins their texts with blank
lines into one document so downstream sees the pdf-inspector shape.
`page_label` stays absent (page-provenance-honest requirement: absent
beats fabricated). The reader's declared `text_format` stays
`markdown`: plain text is a subset of Markdown, so the
`MarkdownNodeParser` branch still works; heading structure is simply
absent, which the chunker already tolerates for structure-free sources.

**D6 — Trigger is the contradiction triple.**
`pdf_type == "text_based"` AND `markdown == ""` AND `page_count > 0`.
Not "short Markdown", not a confidence band — only the observed
failure signature. A partial-extraction case would need its own
evidence before a rule exists for it.

## Risks / Trade-offs

- **Retry cost on pathological files**: bounded — pypdf parses the
  Sloman file in well under a second; the retry only runs when
  pdf-inspector already returned nothing.
- **Stale text quality**: pypdf recovers the raw text layer; for the
  Sloman class that layer is itself 1990s publisher OCR. Imperfect text
  beats zero text, and the diagnostics make the provenance visible.
- **Upstream fix later lands**: the guard stays correct — a fixed
  pdf-inspector returns non-empty Markdown, the trigger never fires,
  diagnostics never appear. No migration needed.
