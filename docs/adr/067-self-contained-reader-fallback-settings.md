# ADR-067: Self-Contained Reader Fallback Settings

**Date:** 2026-09-13
**Status:** Accepted (implementation verified in `tiered-reader-fallback-chain`)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Related:** [ADR-066](066-tiered-reader-fallback-chain.md), [ADR-050](050-configure-pdf-inspector-as-default-reader.md), TDR-024

## Context

ADR-066 selects pdf-inspector as the primary PDF reader, liteparse as
the first rescue tier, and pypdf as the final tier. The normal
`LiteParseReader()` reads OCR and worker-count settings installed by
the composition root.

A direct `PdfInspectorReader().load_data(...)` call can bypass that
root. Before this decision, the liteparse rescue then failed while
looking up missing global settings, before it read the PDF. The chain
caught the failure and selected pypdf. Text recovery remained correct,
but the 136-page Internet Archive test file took about 16 seconds via
pypdf instead of 0.36 seconds via liteparse.

## Decision

The rescue tier supplies every LiteParse setting it needs:

```python
LiteParseReader(ocr_enabled=False, num_workers=None)
```

A concrete `ocr_enabled` value puts the reader into self-contained
mode. It does not call `get_default_effective_settings()` in that
mode. `num_workers=None` asks LiteParse to choose automatically.

The normal `LiteParseReader()` constructor keeps its existing
behaviour. It reads both values from injected effective settings.

This separation gives the rescue path fixed, safe operation while
preserving operator configuration for normal LiteParse use. OCR remains
owned by the OCR routing seam.

## Consequences

### Positive

- Bare scripts, tests, CLI, MCP, and Engine use liteparse consistently.
- pypdf runs only after a genuine liteparse import, parse, or empty-text
  failure.
- Operator settings cannot enable OCR inside the rescue tier.
- The settings dependency is explicit and testable.

### Negative

- `LiteParseReader` has two construction modes: configured default and
  explicit self-contained mode.
- Callers using the explicit mode must pass `ocr_enabled` and should
  pass `num_workers` with it.

### Neutral

- `num_workers=None` delegates worker-count selection to LiteParse.
- The PDF routing evidence and one-document output contract do not
  change.

## Alternatives Considered

| Option | Rejected Because |
| --- | --- |
| Catch missing default settings inside `LiteParseReader.load_data` | This would silently ignore configuration during normal direct-reader use. |
| Require every direct adapter caller to run the composition root | The reader adapters are used directly in tests and small scripts; the rescue does not need application-wide configuration. |
| Keep the silent pypdf hand-over | Correct output arrives, but liteparse's measured speed benefit disappears for a setup detail unrelated to PDF readability. |

## Verification

- Red regression: without defaults, the chain selected pypdf because
  LiteParse failed before parsing.
- Green regression: the same bare call now selects liteparse and
  recovers 183,330 characters from the 136-page Internet Archive scan.
- A second test proves normal `LiteParseReader()` still reads
  `liteparse_ocr_enabled` and `liteparse_num_workers` from effective
  settings.
- Focused suite: 56 passed, 4 expected skips.
- Clean-base tripwire: 5 passed.

## References

- `src/omrg/integrations/pdf/liteparse.py`
- `src/omrg/integrations/pdf/pdf_inspector.py`
- `tests/unit/test_liteparse_reader.py`
- `tests/unit/test_pdf_inspector_reader.py`
- `openspec/changes/tiered-reader-fallback-chain/`
- `experiments/30-reader-fallback-chain-2026-09-13/report.md`
