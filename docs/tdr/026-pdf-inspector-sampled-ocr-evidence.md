# TDR-026: pdf-inspector counts OCR pages from an 8-page sample — complete the evidence with a full page scan

**Date:** 2026-09-17
**Status:** Proposed (merge decision waits for Experiment 33 Stage A, which measures both arms)
**Deciders:** Aizat
**Tags:** pdf | ingestion | pdf-inspector | ocr-routing

## Context

The OCR routing gate sends a PDF to OCR when `pages_needing_ocr / page_count >= 0.10` (ADR-065). The Experiment 33 boundary probe built synthetic PDFs with a known share of image-only pages. One cell, 3 scanned pages out of 20 (15%), stayed on the fast path.

### Root cause analysis

- pdf-inspector 1.17.0 runs detection with its default `ScanStrategy::Sample(8)`: at most 8 evenly spread pages.
- If a sampled page is non-text, pdf-inspector scans every page, so `mixed` results are complete.
- If no sampled page is non-text, the result is `text_based` with `pages_needing_ocr = []`.
- A position sweep proved it: a single scanned page is seen only at pages 1, 3, 5, 7, 9, 11, 13 and 20 of a 20-page PDF, and at pages 1, 4, 7, 10, 13, 16, 19 and 27 of a 27-page PDF.
- The Python binding exposes no scan-strategy option (`process_pdf(path, pages=None)`).
- `pdf_inspector.extract_pages_markdown(path)` parses every page and returns the complete `pages_needing_ocr` list.

Experiment 29 could not see this defect. Its only OCR-needing document was scanned on every page, so any sample caught it.

## Decision

For `text_based` results on PDFs longer than 8 pages, the adapter counts `pages_needing_ocr` from a full page scan (`src/omrg/integrations/pdf/pdf_inspector.py`, `_complete_ocr_pages`):

```python
PDF_INSPECTOR_SAMPLED_PAGES = 8
if result.pdf_type == "text_based" and result.page_count > PDF_INSPECTOR_SAMPLED_PAGES:
    complete = pdf_inspector.extract_pages_markdown(str(file)).pages_needing_ocr
```

- `pdf_type`, `pdf_confidence` and the Markdown stay the output of `process_pdf`.
- A full-scan exception keeps the sampled count and logs a warning.
- The count feeds the silent-empty rescue unchanged: `pages_needing_ocr_before_fallback` now records the complete count.
- No new metadata key (a new key would change every source's index identity through `EXCLUDED_EMBED_METADATA_KEYS`).
- No `_INDEX_IDENTITY_SCHEMA` bump.

## Consequences

**Positive**

- Probe: 6 of 6 cells route as expected. Position sweep: a scanned page is detected at all 20 and all 27 positions.
- Extra cost is one parse of similar length to `process_pdf`: median 0.34 to 1.41 s extra on 224 to 504-page books.

**Negative**

- **False-alarm risk.** The full scan also flags illustration and photo pages in healthy books. Experiment 31's 11 born-digital distractors went from 0 flagged pages to 2 to 61. One 328-page book reached 61 pages (18.6%, 60 tagged `scanned`), which would route a healthy book to OCR (3 to 10 hours projected). For this reason the change is not merged until Experiment 33 measures both effects on natural documents.
- Already indexed unchanged PDFs keep their old route until re-ingested.

**Neutral**

- Short PDFs (8 pages or fewer) and `scanned`, `image_based` and `mixed` results take the same path as before.

## Alternatives Considered

| Option                                              | Why rejected                                                            |
| --------------------------------------------------- | ----------------------------------------------------------------------- |
| Keep the sampled evidence                           | Scanned pages outside the sample never reach the gate                   |
| Replace `process_pdf` with `extract_pages_markdown` | Loses `pdf_type` and confidence, and changes the extracted Markdown     |
| Full scan for every PDF over 8 pages                | `mixed` is already complete; extra cost for no evidence gain            |
| Count only `scanned` pages with some text           | A new threshold with no evidence behind it; revisit after Experiment 33 |
| Bump `_INDEX_IDENTITY_SCHEMA`                       | Forces every user to reindex everything                                 |

## How to Recognise / Handle This Again

1. Symptom: a PDF with visibly scanned pages has `ocr_required=false` and `pages_needing_ocr=0` or a small count.
2. Compare the two counts:
   ```bash
   uv run python -c "import pdf_inspector as p,sys; f=sys.argv[1]; print(len(p.process_pdf(f).pages_needing_ocr), len(p.extract_pages_markdown(f).pages_needing_ocr))" file.pdf
   ```
3. A larger second number means the sample missed pages. Re-ingest the file on a build that includes this TDR.
4. For a false alarm, inspect `extract_pages_markdown(f).ocr_reasons_by_page` for illustration pages tagged `scanned`.

## Revisit Triggers

- Experiment 33 Stage A reports its two arms (merge or rework decision).
- pdf-inspector exposes a scan-strategy option, or changes its default sample.
- Illustrated born-digital documents are over-routed in production.

## References

- `experiments/33-ocr-routing-natural-positive-2026-09-17/output/probe/` (probe, position sweep)
- `openspec/changes/full-page-ocr-evidence/` (proposal, spec delta, `evidence/fixed_code_check.json`)
- ADR-064, ADR-065, ADR-066; TDR-024
- Experiment 29 (`experiments/29-pdf-routing-repeat-2026-09-13`), Experiment 31 distractor corpus
