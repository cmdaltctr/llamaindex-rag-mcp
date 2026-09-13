# Experiment 29 Results: PDF routing repeat study

**ID**: `29-pdf-routing-repeat-2026-09-13`
**Date run**: 2026-09-13
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PASS (with a disclosed vacuous gate — see below)
**Raw data**: [`output/classifications.json`](./output/classifications.json), [`output/eval_results.summary.json`](./output/eval_results.summary.json)
**Change**: `openspec/changes/repeat-pdf-routing-study`

---

## Summary

**Question:** on an operator-approved collection with independent page
labels, does the post-`9bf4810` routing policy send exactly the right
documents to OCR — and does the book that broke experiment 28 stay on
the fast path?

**Observed outcome:** yes on both counts. The book does not route under
the candidate (it does under both pinned baseline arms — the false route
reproduces). Both genuinely-needy development documents route. Zero
held-out documents route under any arm.

## Frozen gate checks

| Gate | Rule | Measured | Verdict |
| --- | --- | --- | --- |
| Safety (H1) | held-out `false_routing_count == 0` | 0 | ✅ PASS |
| Recall (H2) | held-out `missed_needs_ocr_count == 0` | 0 | ✅ PASS — **vacuous**, see below |
| Dev recall check | dev_002 and dev_003 route under the candidate | both routed | ✅ PASS |

**The vacuous gate, stated plainly.** No held-out document carries
`needs_ocr=true` — the approved collection simply contains no unseen
scanned or textless document. H2's "pass" is arithmetic, not evidence:
0 missed of 0 opportunities. The recall evidence this study actually
produced lives in the development split (below), which is why the frozen
decision rule required the dev recall check explicitly.

## Collection

| Property | Value |
| --- | --- |
| Documents | 17 (3 development, 14 held-out) |
| Parse failures | 0 |
| Held-out source | operator's Zotero `RAG` collection (disclosed exp-28 members) |
| Held-out `needs_ocr` prevalence | 0/14, Wilson 95% [0.0, 0.215] — untestable at this n |
| Labels | independent pypdf per-page assessment, all pages, frozen before scoring |

## What each arm routed

| Doc | `pdf_type` | Pages | Flagged | Chars/page | Needs OCR | `baseline_exp28` | `baseline_matched` | `candidate` | `enable_only` |
| --- | --- | ---: | ---: | ---: | --- | :-: | :-: | :-: | :-: |
| dev_001 (book) | mixed | 991 | 10 | 1,127 | no | **route** | **route** | fast | fast |
| dev_002 (Kerr) | scanned | 23 | 23 | 0 | yes | route | route | route | route |
| dev_003 (Sloman) | text_based | 17 | 17 | 0 | yes | route | route | route | fast |
| hold_001–014 | text_based | 9–46 | 0–3 | 3,275–6,967 | no | fast | fast | fast | fast |

### Reading the arms

- **`baseline_matched` vs `candidate`** isolates `9bf4810` at the approved
  0.10 tolerance: the only divergence on this collection is the book —
  routed before, fast-pathed after. The measured effect of the fix.
- **`baseline_exp28` vs `baseline_matched`** isolates the tolerance change
  (0.5 → 0.10): identical outcomes here — nothing in this collection sits
  between 10% and 50% flagged.
- **`enable_only`** is the sharp edge: with thresholds at the 0.0
  sentinels, Sloman — `text_based` at confidence 1.0 extracting zero
  characters — stays on the fast path. Enabling the switch without setting
  thresholds loses the threshold-only detection. Recorded, per the
  approved enable-only judgement.

## Projected cost (labelled: PROJECTION — no real OCR authorised)

At the committed warm worst case of 106.4 s/page:

| Arm | Routed pages | Projected OCR | Note |
| --- | ---: | --- | --- |
| `baseline_exp28` | 1,031 | 30.5 h | 96% of it on a book that needed nothing |
| `baseline_matched` | 1,031 | 30.5 h | same |
| `candidate` | 40 | 71 min | the two genuinely-needy documents only |
| `enable_only` | 23 | 41 min | cheapest — by missing Sloman entirely |

Recovery quality is unmeasured; no OCR worker ran.

## The Sloman refinement

The independent assessment produced a finding experiment 28 could not
see: `dev_003` is **not** a scanned document. pypdf extracts a healthy
text layer (median 2,944 chars/page) while pdf-inspector extracts zero
characters on all 17 pages. The label `needs_ocr=true` records the
operationally true statement — the pipeline's own extractor misses all
content — but the underlying failure is a pdf-inspector extraction bug
on this file, not a missing text layer. OCR may be the wrong remedy; a
reader fallback may be the right one. Flagged as a follow-up, not folded
into the verdict.

## Limitations

- **Held-out recall is untested by construction** — disclosed at freeze,
  not discovered after.
- All 14 held-out documents were inside experiment 28's corpus; their
  labels are new but their classification evidence predates the freeze.
- n=14 held-out gives a Wilson upper bound of ~21% on needs-OCR
  prevalence — this study says nothing about prevalence and does not try.
- Whole-document dispatch means a single over-tolerance page share costs
  the whole file's page count; the 10% tolerance is the operator's
  judgement, now exercised on real documents.

## Decision, per the rule fixed before the data

Safety gate passes on held-out evidence; both dev recall checks route.
Per the frozen rule this **supports** the candidate as safe *on this
collection* — and promotion of `OCR_FALLBACK_ENABLED` remains a separate
decision this change does not take. The enable-only measurement stands
as the strongest argument *against* a bare enable: the switch without
thresholds silently misses the hardest detection.

## Reproduction

```bash
uv run python experiments/29-pdf-routing-repeat-2026-09-13/classify.py
uv run python experiments/29-pdf-routing-repeat-2026-09-13/summarise_eval.py
```

Resume is identity-bound: a changed plan, label set, collection or policy
refuses to resume. Private mappings stay in gitignored `output/` files.
