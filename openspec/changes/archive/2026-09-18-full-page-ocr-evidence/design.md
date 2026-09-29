# Design: full-page OCR evidence for pdf-inspector

## Context

pdf-inspector 1.17.0 runs detection with its default `ScanStrategy::Sample(8)`. The Python binding exposes no scan-strategy option (`process_pdf(path, pages=None)`). When a sampled page is non-text, pdf-inspector scans the rest, so `mixed` results are already complete. The blind spot is a `text_based` result on a PDF longer than 8 pages. `extract_pages_markdown(path)` parses every page and returns a complete `pages_needing_ocr` list.

## Decisions

1. **Trigger.** Run the full scan only when `pdf_type == "text_based"` and `page_count > 8`. Other results are complete or route unconditionally.
2. **Evidence only.** Replace the count behind `pages_needing_ocr`. Keep `pdf_type`, `pdf_confidence` and the Markdown from `process_pdf`, so extraction output is unchanged.
3. **No new metadata key.** A new diagnostic key must join `EXCLUDED_EMBED_METADATA_KEYS`, which changes the index identity of every source. The INFO log names files where the full scan found pages the sample missed.
4. **No identity schema bump.** Bumping `_INDEX_IDENTITY_SCHEMA` forces every user to reindex. Already indexed PDFs keep their old route until re-ingested; TDR-026 records this.
5. **Failure isolation.** Any exception from the full scan keeps the sampled count and logs a warning.
6. **Order with the rescue chain.** The full-scan count is computed before the silent-empty guard, so `pages_needing_ocr_before_fallback` records the complete count.

## Risks

- Extra parse time on long text PDFs. Mitigation: the trigger limits it to `text_based` PDFs over 8 pages; TDR-026 records measured cost.
- A pdf-inspector upgrade may change its default sample. The constant `PDF_INSPECTOR_SAMPLED_PAGES` names the assumption; a larger default only reduces extra scans.
