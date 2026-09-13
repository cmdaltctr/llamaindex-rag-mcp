# Experiment 30: Reader fallback chain — pdf-inspector → liteparse → pypdf

**ID**: `30-reader-fallback-chain-2026-09-13`
**Date planned**: 2026-09-13
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PASS — run 2026-09-13, all four gates
**Relation**: Experiment 29 (routing); archived change `pdf-reader-extraction-fallback` (shipped pypdf-only guard); TDR-024; ADR-050

## Why this experiment exists

The shipped extraction guard (change `pdf-reader-extraction-fallback`)
recovers pdf-inspector's silent-empty extractions with pypdf alone.
Session evidence on 2026-09-13 found two additional facts: a **second
failure mechanism** (Internet Archive GlyphLessFont scans — the dominant
internet scanned-book format, where pdf-inspector extracts 0 characters
from a standard searchable PDF), and that **liteparse reads every
failure class** faster than pypdf while omitting textless pages and
carrying page provenance. The candidate design is a tiered fallback
chain — pdf-inspector primary (classification), liteparse first
fallback, pypdf last — replacing the shipped single-tier pypdf retry.

**In plain terms:** when pdf-inspector says a file has text but
extracts nothing, who should rescue it — liteparse (fast, spatial) or
pypdf (always available)? And does the rescue keep every routing
decision correct?

## Hypotheses

```
H1 (recovery). The liteparse tier recovers text (>0 characters) on
   every silent-empty document. Success: all 3 pathological docs
   recover via the liteparse tier. Failure: any pathological doc
   falls through to pypdf or recovers nothing.

H2 (speed). The liteparse retry is at least as fast as the pypdf
   retry per document. Success: liteparse_retry_seconds <=
   pypdf_retry_seconds for every pathological doc. Failure: any doc
   where liteparse is slower.

H3 (routing). The chain preserves every routing decision under the
   promoted gates (0.5 / 0.10): pathological docs fast path, Kerr
   routes to OCR, healthy doc untouched (no fallback fires).

H4 (blank-page omission). The liteparse tier emits documents for
   fewer pages than the PDF page count when textless pages exist.
   Success: p01 pages_with_text < page_count. Failure: equality.
```

## Variables

| Type | Variable | Values / treatment |
| --- | --- | --- |
| Independent | fallback policy | `shipped_pypdf_only` vs `chain_liteparse_then_pypdf` |
| Dependent | recovered chars, retry seconds, tier used, routing decision, pages with text | measured per document |
| Controlled | classifier (pdf-inspector 1.17.0), gate (production `ocr_required_by_gate`, thresholds 0.5/0.10), no OCR worker, no model load, no network, no ingestion | — |

Not changed: the shipped production code (the candidate chain runs as a
script-local mirror of the guard, never importing or patching the
adapter under test beyond calling it).

## Corpus

| doc_id | What it is | Split | Expected |
| --- | --- | --- | --- |
| p01_ia_prince | Internet Archive scan, 136 pp, GlyphLessFont | pathological | rescue, fast path |
| p02_ia_managing | Internet Archive scan, 68 pp, GlyphLessFont | pathological | rescue, fast path |
| p03_winansi_sloman | Acrobat-Capture era, 17 pp, WinAnsi no `/ToUnicode` | pathological | rescue, fast path |
| c01_scanned_kerr | Genuinely scanned paper, 23 pp | control | routes to OCR |
| c02_healthy_graphrag | Born-digital paper (Exp 29 hold_001) | control | no fallback, fast path |

Paths live in gitignored `output/.collection.private.json`; public
artefacts carry `doc_id`, `sha256` and split only.

## Frozen gates

| Gate | Rule | Basis |
| --- | --- | --- |
| Recovery | 3/3 pathological docs recover >0 chars via liteparse tier | The chain must match the shipped guard's coverage |
| Speed | liteparse retry ≤ pypdf retry per pathological doc | The chain's justification is efficiency |
| Routing | pathological→fast, kerr→OCR, healthy→fast with no fallback | Experiment 29 decisions preserved |
| Blank pages | p01 pages_with_text < p01 page_count | liteparse omits textless pages (measured 121/136) |

## Interpretation

- All gates pass → ADR records the tiered chain; implementation
  follows as an OpenSpec change modifying the shipped guard.
- Recovery or routing fails → keep the shipped pypdf-only guard;
  record the negative result.
- Speed fails → chain unjustified; keep shipped guard.

## Procedure

```bash
uv run python experiments/30-reader-fallback-chain-2026-09-13/run_chain.py
```

Writes `output/chain_results.json` (per-document rows) and
`output/eval_results.summary.json` (gate evaluation).

## Cost

Local extraction only: pdf-inspector + liteparse + pypdf over five
PDFs. No OCR worker, no model weights, no network. Under a minute.

## Artefacts expected

| File | Description | Required |
| --- | --- | :-: |
| `protocol.md` | this plan | ✅ |
| `run_chain.py` | runner + gate evaluation | ✅ |
| `output/chain_results.json` | per-document measurements | ✅ |
| `output/eval_results.summary.json` | gate checks | ✅ |
| `report.md` | verdict and evidence | ✅ |
