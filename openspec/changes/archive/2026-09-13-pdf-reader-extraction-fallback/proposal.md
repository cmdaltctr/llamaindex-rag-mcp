# Proposal: pdf-reader-extraction-fallback

## Why

pdf-inspector (the default reader, ADR-050) can silently return empty
Markdown while classifying the same file as `text_based` with confidence
1.0 — observed on Experiment 29's Sloman PDF, whose pre-2000
WinAnsi-encoded TrueType fonts carry no `/ToUnicode` map (TDR pending).
Today such files are ingested as zero characters: no error, no text, no
signal beyond a metadata count that says every page needs OCR.

## What Changes

- Add a guard in `PdfInspectorReader.load_data`: when pdf-inspector
  classifies a file `text_based` but extracts empty Markdown from a
  non-empty page count, retry the file with the registered `pypdf`
  reader and join its per-page text into one document.
- Correct the routing evidence on successful fallback: zero the scalar
  `pages_needing_ocr` (pdf-inspector flagged pages only because its own
  extraction was empty), preserve the original count under an additive
  diagnostic key so the OCR seam does not dispatch ~30 minutes of OCR
  onto text that was just recovered in ~1 second.
- Stamp additive fallback diagnostics on the emitted document
  (`extraction_fallback_backend`, original flagged count), following the
  task-2.10 additive-metadata pattern.
- Record the Sloman diagnosis as a TDR (`docs/tdr/`).
- No default change, no OCR-routing change, no registry change.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `pdf-reader`: adds one requirement — the pdf-inspector adapter SHALL
  detect the text_based-but-empty-extraction contradiction and recover
  via the plain-text reader, with honest corrected evidence.

## Impact

- **Code**: `src/omrg/integrations/pdf/pdf_inspector.py` (guard),
  `tests/unit/test_pdf_inspector_reader.py` (new tests),
  `tests/unit/test_ocr_routing_seam.py` (evidence-correction test).
- **Behaviour**: files of the Sloman class go from zero-character
  ingestion to full plain-text ingestion; OCR routing decisions for them
  flip from "route" to "fast path" (the correct decision once text is
  recovered).
- **Docs**: new TDR; `docs/guides/` mention of the fallback diagnostics.
- **Dependencies**: none added — `pypdf` is already a base dependency
  and registered.
