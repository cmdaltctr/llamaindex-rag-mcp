# Design: tiered-reader-fallback-chain

## Context

The shipped guard (`src/omrg/integrations/pdf/pdf_inspector.py`,
change `pdf-reader-extraction-fallback`) retries silent-empty
extractions with pypdf only. Experiment 30
(`experiments/30-reader-fallback-chain-2026-09-13/`, PASS 4/4) and
ADR-066 establish liteparse as the better first tier: same coverage on
every observed failure class (IA GlyphLessFont, Acrobat-Capture
WinAnsi), ~45× faster on the largest file, textless pages omitted,
page provenance available per page. This change swaps the retry tier
order; evidence-correction semantics are untouched.

## Goals / Non-Goals

**Goals**

- liteparse-first retry with pypdf as the always-available last tier.
- Tier-honest diagnostics (`extraction_fallback_backend` ∈
  {`liteparse`, `pypdf`}).
- Identical routing behaviour to the shipped guard.

**Non-Goals**

- Page-aware fallback (per-page rescue inside otherwise-readable PDFs)
  — The Prince's 15 textless pages remain un-rescued by design.
- Changing pdf-inspector's primary role, the OCR seam, or the routing
  gate.
- Emitting per-page documents or `page_label` on the rescued document —
  the one-document-per-file contract stays (surgical tier swap only).

## Decisions

**D1 — Tier order is fixed in the adapter, not the registry.** The
guard owns the chain: `liteparse` then `pypdf`, both resolved through
`integrations.pdf.registry` lazily inside the retry path. The registry
gains no chain concept, `auto` resolution is untouched, and a
registry-ordered chain would silently drag `pypdfium2` (not installed
here, unmeasured on the failure classes) into a measured decision.

**D2 — The liteparse tier is self-contained and extraction-only.** The
retry passes both values it needs: `ocr_enabled=False` and
`num_workers=None` (LiteParse automatic worker selection). It therefore
never reads default effective settings. This keeps bare direct-adapter
scripts on the fast liteparse tier and prevents an operator's LiteParse
OCR setting from turning the rescue into an OCR path. A normal
`LiteParseReader()` still reads both values from injected defaults. OCR
belongs to the routing seam (ADR-062/065), not the fallback chain.

**D3 — Tier failure semantics.** A tier that raises (import or parse
error) or yields zero text hands over to the next tier; only when the
final tier yields nothing does the original pdf-inspector result stand.
This deliberately relaxes the shipped guard's D3 (propagating retry
exceptions): a liteparse crash must not prevent the pypdf rescue that
the shipped guard guarantees. Exceptions from the last tier still
propagate to the per-file error boundary.

**D4 — Join contract unchanged.** Each tier joins its per-page texts
with blank lines into one document, exactly as the shipped pypdf guard
does. liteparse's `page_label`/bbox metadata is dropped in the join
(honest page provenance stays absent on the merged document — same as
today).

**D5 — Character-count deltas are accepted, not compensated.** The
liteparse tier recovers ~2–16% fewer characters (textless pages, page
furniture). Exp 30 measured no content-equivalence claim; the report
records this plainly. Padding or double-tiring (both tiers) to close
the gap would double cost for unmeasured benefit.

## Risks / Trade-offs

- **liteparse absent**: pypdf tier reproduces today's behaviour exactly;
  environments without liteparse are unaffected.
- **Two-tier failure surface**: more code paths than one tier; mitigated
  by the scenario set (contradiction, fall-through, both-fail, normal,
  scanned) mirroring the shipped guard's tests plus the new
  fall-through case.
- **Timing variance**: liteparse cold-import cost (~1 s worst observed)
  still dominates nothing — the shipped pypdf retry on the same file
  took ~16 s.
