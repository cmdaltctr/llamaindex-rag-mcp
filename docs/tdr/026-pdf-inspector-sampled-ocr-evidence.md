# TDR-026: pdf-inspector counts OCR pages from an 8-page sample — complete the evidence with a full page scan

**Date:** 2026-09-17
**Status:** Accepted (Experiment 33 Stage A measured both arms on natural documents; see "Experiment 33 Stage A result")
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

- **False-alarm risk, measured and not observed here.** The full scan also flags illustration and photo pages in healthy books. Experiment 31's 11 born-digital distractors went from 0 flagged pages to 2 to 61. One 328-page book reached 61 pages (18.6%, 60 tagged `scanned`), which would route a healthy book to OCR (3 to 10 hours projected). Experiment 33 Stage A tested this on 40 natural documents and the effect did not appear: the false-positive count stayed at 1 in both arms, and the same document (`mx08`) causes it through its `image_based` classification, not through page evidence. The risk stands for illustrated books, which that corpus caps at 100 pages.
- Already indexed unchanged PDFs keep their old route until re-ingested.

**Neutral**

- Short PDFs (8 pages or fewer) and `scanned`, `image_based` and `mixed` results take the same path as before.

## Experiment 33 Stage A result

Both arms ran on the same frozen corpus of 40 natural open-licence PDFs (1,123
pages, 18 documents labelled `needs_ocr`, 22 `usable`) with the same labels and
scoring. The only difference is this change.

| Measurement | Sampled evidence (`5bac71e`) | Full scan (this change, `7280766`) |
| --- | ---: | ---: |
| `routing_recall` | 0.556 (10/18) | 0.611 (11/18) |
| `false_negative_count` | 8 | 7 |
| `false_positive_count` | 1 (`mx08`) | 1 (`mx08`) |
| `routing_precision` | 0.909 | 0.917 |
| `unnecessary_ocr_pages` | 121 | 137 |
| Routed documents / pages | 11 / 395 | 12 / 444 |
| Read time, all 40 documents | 9.27 s | 9.51 s |

The change catches `tl02`, a 49-page NASA technical note scanned with a broken
OCR layer, whose 33 affected pages all fell outside the 8-page sample. It adds
no false alarm, 49 OCR pages and 0.24 s of read time across the whole corpus.
The 16 extra `unnecessary_ocr_pages` all sit inside documents that genuinely
need OCR.

The 7 remaining false negatives are not sampling failures and this change does
not address them: four are detection failures where a scanned page carries a
header line or junk OCR text, two are rescue failures where a low-quality
LiteParse rescue zeroed the evidence, and one is a born-digital mathematics
paper that loses only its equations. See
`experiments/33-ocr-routing-natural-positive-2026-09-17/report.md`.

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

- ~~Experiment 33 Stage A reports its two arms (merge or rework decision).~~ Fired 2026-09-17: merge.
- pdf-inspector exposes a scan-strategy option, or changes its default sample.
- Illustrated born-digital documents are over-routed in production.

## References

- `experiments/33-ocr-routing-natural-positive-2026-09-17/output/probe/` (probe, position sweep)
- `experiments/33-ocr-routing-natural-positive-2026-09-17/report.md` and `output/arm_comparison.json` (Stage A, both arms)
- `openspec/changes/full-page-ocr-evidence/` (proposal, spec delta, `evidence/fixed_code_check.json`)
- ADR-064, ADR-065, ADR-066; TDR-024
- Experiment 29 (`experiments/29-pdf-routing-repeat-2026-09-13`), Experiment 31 distractor corpus
