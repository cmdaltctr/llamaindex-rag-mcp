# ADR-066: Tiered Reader Fallback — pdf-inspector → liteparse → pypdf

**Date:** 2026-09-13
**Status:** Accepted (evidence: Experiment 30, all four gates PASS)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** implementation pending (OpenSpec change modifying the shipped guard)
**Related:** [ADR-050](050-configure-pdf-inspector-as-default-reader.md) (pdf-inspector default), [ADR-020](020-use-liteparse-as-pdf-reader.md) (liteparse adapter), [ADR-065](065-ocr-fallback-gate-promoted-to-packaged-default.md) (routing default), TDR-024 (both failure mechanisms)

## Context

The shipped extraction guard (change `pdf-reader-extraction-fallback`)
detects pdf-inspector's silent-empty contradiction — `text_based`
classification with empty Markdown — and retries with pypdf. Two
findings dated 2026-09-13 extend that picture:

1. **A second, systematic failure class.** Internet Archive scans —
   the dominant internet scanned-book format — use a Type0
   `/GlyphLessFont` invisible OCR layer. pdf-inspector 1.17.0 extracts
   **zero characters** from these standard searchable PDFs even though
   a `/ToUnicode` map is present (TDR-024). Its classifier remains
   correct: on every file observed (IA scans, Acrobat-Capture WinAnsi,
   genuinely scanned Kerr, born-digital controls) the `pdf_type`
   verdict was right, 4/4 on pathological files where extraction was
   wrong 0/3.
2. **liteparse reads every failure class** — GlyphLessFont and
   WinAnsi-without-`/ToUnicode` — faster than pypdf, omitting
   textless pages and carrying page provenance.

Experiment 30 (`experiments/30-reader-fallback-chain-2026-09-13`)
compared the shipped pypdf-only retry against a tiered chain on five
documents. All four frozen gates passed: recovery (3/3 silent-empty
docs rescued by the liteparse tier), speed (liteparse retry 0.10–0.36 s
vs pypdf ~0.5–16 s), routing (pathological → fast path, Kerr → OCR,
healthy control untouched), and blank-page omission (121 of 136 pages
carried text on the 136-page IA scan).

## Decision

The pdf-inspector adapter's silent-empty retry becomes a **tiered
chain**:

1. **pdf-inspector stays the primary reader.** It is the only reader
   emitting the classification evidence (`pdf_type`, `pdf_confidence`,
   `pages_needing_ocr`) the OCR routing gate consumes, and its
   Markdown remains the best extraction on healthy PDFs (ADR-050,
   Experiment 14).
2. **liteparse is the first fallback tier.** On the contradiction
   trigger (`text_based` + empty Markdown + `page_count > 0`), retry
   with liteparse: fastest rescue (~45× on the largest observed file),
   textless pages omitted, page provenance preserved.
3. **pypdf is the last fallback tier.** When liteparse is absent or
   yields no text, pypdf retries — the always-available registered
   plain-text reader, matching the shipped guard's coverage.

Evidence correction semantics are unchanged from the shipped guard: a
successful retry zeroes `pages_needing_ocr`, preserves the flagged
count under `pages_needing_ocr_before_fallback`, and the
`extraction_fallback_backend` diagnostic names the tier that produced
the text (`liteparse` or `pypdf`). Routing decisions are identical to
the shipped guard — Experiment 30 measured no divergence.

## Alternatives considered

- **pypdf-only fallback (status quo):** equal coverage, slower rescue;
  rejected on the measured speed gap with no compensating advantage.
- **liteparse as primary reader:** reads every failure class but emits
  no classification evidence, which would break OCR routing (the gate
  has three pdf-inspector-only inputs). Rejected; also loses
  Markdown extraction on healthy PDFs.
- **OCR the rescue cases:** every silent-empty file found carries a
  readable text layer; OCR would spend minutes per document recovering
  what a sub-second local parse returns. Rejected.

## Consequences

- The `pdf-reader` spec requirement added by change
  `pdf-reader-extraction-fallback` must be modified to name the chain
  (implementation change pending).
- Environments without liteparse behave exactly as today (pypdf tier).
- Downstream chunking sees slightly fewer characters from rescued IA
  scans (textless pages omitted); token-level content equivalence was
  not measured and is not claimed.
- TDR-024 records both failure mechanisms; its revisit trigger
  ("a second silent-empty signature appears") fired and is now closed
  by the IA GlyphLessFont evidence.
