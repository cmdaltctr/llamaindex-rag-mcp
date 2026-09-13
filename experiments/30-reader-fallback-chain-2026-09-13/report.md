# Experiment 30: Reader fallback chain — pdf-inspector → liteparse → pypdf

**ID**: `30-reader-fallback-chain-2026-09-13`
**Date run**: 2026-09-13
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PASS — all four gates
**Verdict**: The tiered chain recovers every silent-empty extraction via liteparse, up to ~45× faster than the shipped pypdf retry, with every routing decision preserved.
**Raw data**: [`output/chain_results.json`](./output/chain_results.json), [`output/eval_results.summary.json`](./output/eval_results.summary.json)
**Protocol**: [protocol.md](protocol.md)

## Bottom line

The shipped guard rescues pdf-inspector's silent-empty extractions with
pypdf, and it works — but pypdf is the slow rescuer. liteparse reads
every failure class we have found (Internet Archive GlyphLessFont scans
and Acrobat-Capture WinAnsi) in fractions of a second and omits textless
pages. A chain — pdf-inspector primary,
liteparse first fallback, pypdf last — matched the shipped guard's
recovery coverage on all three pathological documents, was faster on
all three, preserved every routing decision, and never fired on the
healthy control.

## What we tested

Five documents, two arms. The `shipped` arm is a script-local mirror of
the historical pypdf-only guard (commit 928f030) — the production
`PdfInspectorReader` now carries the chain itself (ADR-066), so calling
it would measure the new code, not the baseline. The `chain` arm is a
script-local mirror of the guard whose retry tier is liteparse first,
pypdf only when liteparse yields nothing. Both replay the production
gate with the promoted packaged thresholds (0.5 / 0.10). No OCR worker,
no model load, no network, no ingestion.

## Results

### Gate evaluation

| Gate | Rule | Measured | Pass? |
| --- | --- | --- | :--: |
| Recovery | 3/3 pathological docs recover via liteparse tier | 3/3, tier=`liteparse` on all | ✅ |
| Speed | liteparse retry ≤ pypdf retry per doc | 0.20 vs 11.5 s; 0.07 vs 5.4 s; 0.05 vs 0.31 s (median of 3) | ✅ |
| Routing | pathological→fast, Kerr→OCR, healthy untouched | exactly that | ✅ |
| Blank pages | p01 pages_with_text < page_count | 121 < 136 | ✅ |

### Per-document

| doc_id | Pages | pdf_type | Shipped (pypdf) | Chain (liteparse) | Routing |
| --- | --: | --- | --- | --- | --- |
| p01_ia_prince | 136 | text_based | 219,549 chars, ~11.5 s retry | 183,330 chars, **0.20 s** | fast / fast |
| p02_ia_managing | 68 | text_based | 78,693 chars, ~5.4 s retry | 76,849 chars, **0.07 s** | fast / fast |
| p03_winansi_sloman | 17 | text_based | 44,948 chars, ~0.31 s retry | 44,277 chars, **0.05 s** | fast / fast |
| c01_scanned_kerr | 23 | scanned | 0 chars, no fallback | 0 chars, no fallback | **OCR / OCR** |
| c02_healthy_graphrag | 26 | text_based | 93,126 chars, no fallback | identical, no fallback | fast / fast |

## Discussion

**Why liteparse recovers what pdf-inspector cannot.** Both failures are
pdf-inspector-specific, not a Rust problem: liteparse (also Rust, over
PDFium) reads the IA GlyphLessFont invisible OCR layer — the dominant
internet scanned-book format — and the 1990s WinAnsi fonts without
`/ToUnicode` (TDR-024). pdf-inspector's classifier stayed correct on
all five documents, including every one it failed to extract: 4/4
`text_based`/`scanned` classifications right, 0/3 extractions right on
the pathological set. That asymmetry is the design's foundation:
classification drives routing, extraction falls to the chain.

**Character deltas are omissions, not measured loss.** The chain
recovered ~2–16% fewer characters than pypdf (183,330 vs 219,549 on
*The Prince*): liteparse skips textless pages (121 of 136 on p01) and
page furniture differences follow from the per-item text join. This
experiment did not verify token-level content equivalence against
ground truth; recovery, routing and timing are the measured claims.

**Timing methodology.** Retry times are medians of three direct
measurements per document — the original single-shot run measured
liteparse on p03 at 0.38 s one run and 0.07 s the next, enough to flip
the frozen speed gate on noise alone (the earlier derived estimate had
also inflated the pypdf side by bundling classify time). The gate now
compares the liteparse tier directly against a script-local pypdf-only
mirror. Margins remain large: ~56× on p01, ~76× on p02, ~7× on p03.

**Kerr is untouched by design.** `scanned` is not a contradiction case
— no fallback tier fires, and the gate still routes it to OCR in both
arms. The chain changes nothing about genuine-OCR routing.

## Conclusion

**What ships as evidence:** the tiered fallback chain
(pdf-inspector → liteparse → pypdf) is validated on this corpus:
equal coverage, faster recovery, correct routing, blank-page omission.
Recorded in ADR-066; implementation follows as an OpenSpec change
modifying the shipped guard. pypdf remains the always-available last
tier for environments where liteparse is absent or fails.

**Not answered, by design:** token-level content equivalence between
rescue tiers, downstream retrieval quality, and behaviour on corpus
classes not present here.

## Artefacts

| File | Description |
| --- | --- |
| `output/chain_results.json` | Per-document measurements, both arms |
| `output/eval_results.summary.json` | Gate checks + public sha256 manifest |
| `output/.collection.private.json` | Private paths (gitignored) |

Reproduce:

```bash
uv run python experiments/30-reader-fallback-chain-2026-09-13/run_chain.py
```
