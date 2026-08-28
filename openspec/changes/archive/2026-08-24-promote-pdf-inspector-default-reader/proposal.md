## Why

Experiment 14 found that `pdf_inspector` parsed all 35 Qasper PDFs without errors,
was the fastest reader, and produced the best reranked Hit@5 result. The shipped
configuration still selects `auto`, which resolves to LiteParse when available.

## What Changes

- Set `pdf_inspector` as the packaged `PDF_READER` default in `config/`.
- Keep reader selection configuration-driven through `PDF_READER` and the PDF
  reader registry. Do not add reader-specific preference rules to `auto`.
- Promote the existing `pdf-inspector` dependency to the base install so the
  packaged default is available after `uv sync`.
- Preserve explicit environment overrides and the existing `auto` fallback policy.
- Correct explicit `PDF_READER=pdf_inspector` resolution at the composition root.
- Update the PDF-reader contract, ADRs, configuration guides, and test coverage.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `pdf-reader`: Change the packaged PDF-reader default to `pdf_inspector` while preserving configurable dispatch and fallback behaviour.

## Impact

- Affects `config/`, the composition root, PDF-reader tests, dependency metadata,
  configuration documentation, and ADR-020.
- Adds `pdf-inspector` to the base dependency set. Operators can still select
  `liteparse`, `pypdfium2`, `pypdf`, or `auto` with `PDF_READER`.
- References Experiment 14 evidence in the decision record.
