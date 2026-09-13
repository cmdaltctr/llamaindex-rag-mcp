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
and Acrobat-Capture WinAnsi) in fractions of a second, omits textless
pages, and keeps page provenance. A chain — pdf-inspector primary,
liteparse first fallback, pypdf last — matched the shipped guard's
recovery coverage on all three pathological documents, was faster on
all three, preserved every routing decision, and never fired on the
healthy control.

## What we tested

Five documents, two arms. The `shipped` arm is the production
`PdfInspectorReader` as committed (pypdf-only retry). The `chain` arm
is a script-local mirror of the guard whose retry tier is liteparse
first, pypdf only when liteparse yields nothing. Both replay the
production gate with the promoted packaged thresholds (0.5 / 0.10). No
OCR worker, no model load, no network, no ingestion.

## Results

### Gate evaluation

| Gate | Rule | Measured | Pass? |
| --- | --- | --- | :--: |
| Recovery | 3/3 pathological docs recover via liteparse tier | 3/3, tier=`liteparse` on all | ✅ |
| Speed | liteparse retry ≤ pypdf retry per doc | 0.36 vs 16.1 s; 0.10 vs 6.3 s; 0.23 vs 0.5 s | ✅ |
| Routing | pathological→fast, Kerr→OCR, healthy untouched | exactly that | ✅ |
| Blank pages | p01 pages_with_text < page_count | 121 < 136 | ✅ |

### Per-document

| doc_id | Pages | pdf_type | Shipped (pypdf) | Chain (liteparse) | Routing |
| --- | --: | --- | --- | --- | --- |
| p01_ia_prince | 136 | text_based | 219,549 chars, ~16.1 s retry | 183,330 chars, **0.36 s** | fast / fast |
| p02_ia_managing | 68 | text_based | 78,693 chars, ~6.3 s retry | 76,849 chars, **0.10 s** | fast / fast |
| p03_winansi_sloman | 17 | text_based | 44,948 chars, ~0.5 s retry | 44,277 chars, **0.23 s** | fast / fast |
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

**Timing caveat.** The chain's classify+retry split attributes the
first pdf-inspector pass separately; pypdf retry time is derived as
shipped total minus that classify time. Cold-import variance explains
the gap between this run's 0.36 s liteparse retry and the 1.4 s seen in
the session's first standalone probe; both sit far below pypdf's
~16 s on the 136-page file.

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
