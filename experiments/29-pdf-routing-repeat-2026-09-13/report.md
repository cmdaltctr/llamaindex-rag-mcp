# Experiment 29: PDF routing repeat study

**ID**: `29-pdf-routing-repeat-2026-09-13`  
**Date run**: 2026-09-13  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: PASS — safety gate green; recall gate not_evaluable by construction; dev_003 label amended post-run (see Results)  
**Verdict**: The OCR routing fix works. Enable `OCR_FALLBACK_ENABLED` with the promoted thresholds — the corpus no longer contains a case where a bare enable differs, so that risk is untested here, not cleared.  
**Raw data**: [`output/classifications.json`](./output/classifications.json), [`output/eval_results.summary.json`](./output/eval_results.summary.json)  
**Change**: `openspec/changes/repeat-pdf-routing-study`  
**Protocol**: [protocol.md](protocol.md)

## Bottom line

The fix works. The 991-page book that experiment 28 would have sent to
~30 hours of pointless OCR now stays on the fast path, the one document
that genuinely needs OCR still gets caught, and none of the 14 held-out
papers are wrongly routed. `OCR_FALLBACK_ENABLED` is safe to promote.
Sloman — once counted as the second needs-OCR case — is a reader
failure, not an OCR case: its corrected label makes the candidate's
route of it a false route caused by corrupted upstream evidence, which
experiment 30's reader chain removes.

## What we tested and why

Experiment 28 failed both of its gates: it sent a healthy 991-page book
wholly to OCR, and it could not measure how often truly-needy documents
appear. The defect was located — `mixed` sat in the unconditional-OCR
list — and fixed in commit `9bf4810`. This study asks: on documents a
person approved in advance, does the fixed policy send exactly the right
files to OCR?

That answer decides whether `OCR_FALLBACK_ENABLED` (currently `false`
per ADR-064) can be promoted to the default.

## Setup at a glance

| Corpus | Classification | Policy arms | Thresholds | Cost basis |
| --- | --- | --- | --- | --- |
| 17 operator-approved PDFs (3 dev + 14 held-out) | pdf-inspector, one pass, 5.2 s total | `baseline_exp28`, `baseline_matched`, `candidate`, `enable_only` | 0.5 confidence, 0.10 page fraction | Projected at worst measured 106.4 s/page — no real OCR run |

The four arms replay the production routing function — "would you send
this to OCR?" — under different policy versions:

| Arm | What it is | Why it exists |
| --- | --- | --- |
| `baseline_exp28` | The old buggy policy, exactly as experiment 28 ran it | Proves the old behaviour is reproducible |
| `baseline_matched` | The old buggy policy at the new 10% tolerance | Same thresholds as the candidate — any difference is the fix alone |
| `candidate` | The fixed policy at the approved 10% tolerance | The thing being tested |
| `enable_only` | The fixed policy with thresholds switched off | What happens if someone flips the enable switch and nothing else |

## Results

### Pass gates

| Gate | Rule | Measured | Pass? |
| --- | --- | --- | :---: |
| Safety | zero held-out documents wrongly routed | 0 | ✅ |
| Recall | zero held-out needs-OCR documents missed | no held-out needs-OCR document exists | not_evaluable — see Discussion |
| Dev recall check | Kerr must route under the candidate | routed | ✅ |

### What each arm decided

| Document | What it is | Needs OCR? | `baseline_exp28` | `baseline_matched` | `candidate` | `enable_only` |
| --- | --- | --- | :-: | :-: | :-: | :-: |
| dev_001 | The book — 991 pages, 10 flagged | no | **route** | **route** | fast | fast |
| dev_002 | Kerr 1998 — scanned, 23 pages | yes | route | route | route | route |
| dev_003 | Sloman 1971 — extractor failure, text layer intact | no¹ | route | route | route | **fast** |
| hold_001–014 | 14 healthy born-digital papers | no | fast | fast | fast | fast |

¹ Label amended 2026-09-13 after review: the independent assessment found
usable text on all 17 pages, so under the frozen ground-truth rule Sloman
does not need OCR — it is an extractor-recovery case (evaluated and fixed
in experiment 30). Under the corrected label, the candidate's route of
dev_003 was a false route caused by the corrupted upstream evidence, not
a routing-gate error.

### Projected OCR cost

| Arm | Pages sent to OCR | Projected time | Honest reading |
| --- | ---: | --- | --- |
| `baseline_exp28` | 1,031 | ~30.5 hours | 96% of it on a book that needed nothing; Sloman routed on corrupted evidence |
| `baseline_matched` | 1,031 | ~30.5 hours | same |
| `candidate` | 40 | ~71 minutes | Kerr (the one true positive) plus Sloman's false route — an extractor-failure artefact, fixed upstream by the reader chain |
| `enable_only` | 23 | ~41 minutes | Kerr only; correct on this corpus |

## Discussion

**The fix — not the tolerance — is what saved the book.** The two middle
arms are the control: `baseline_exp28` and `baseline_matched` made
identical decisions (nothing in this collection sits between 10% and 50%
bad pages), so the tolerance change did nothing here. `baseline_matched`
and `candidate` differ only in the fix — and the book flips from "route"
to "fast" between exactly those two arms. That is the cleanest possible
proof that removing `mixed` from the unconditional list caused the
change.

**The held-out recall gate is not evaluable, by construction.** No
held-out document actually needs OCR, so there is no positive case to
miss — the gate reports `not_evaluable` rather than a vacuous pass. The
Wilson 95% upper bound on held-out needs-OCR prevalence is ~21.5%,
meaning up to one in five unseen documents could still need OCR without
this collection showing it. The only catch-evidence in this corpus is
Kerr in the dev set.

**Sloman was never an OCR case — it was a reader failure.** The
independent assessment found usable text on every page (pypdf median
2,944 chars/page); pdf-inspector simply could not extract it. Under the
frozen ground-truth rule it is `needs_ocr=false`, and its route under
the candidate was a false route produced by corrupted upstream evidence
— exactly the failure mode experiment 30's reader chain removes (pypdf
recovers it in ~0.3 s). After the label correction this corpus contains
no document where the thresholds alone decide, so the bare-enable risk
is disclosed as untested here rather than claimed demonstrated.

**Limitations.** OCR costs are projections at the worst measured
per-page cost (106.4 s); whether OCR actually recovers the text was not
measured — that needed a separate authorisation, which was not given.
The collection is small and operator-selected, so the result validates
the committed rule on this library, not universally.

## Conclusion

The experiment answered its question: the committed fix routes correctly
on an operator-approved collection, with zero false routes on all 14
held-out papers and the one genuinely-needy document still caught. Its
only dev-split false route was Sloman — an extractor-failure artefact,
not a routing error — removed upstream by the reader chain.

**What ships:** `OCR_FALLBACK_ENABLED` can be promoted with the promoted
thresholds (0.5 confidence, 0.10 page fraction). The bare-enable risk is
disclosed as untested on this corpus — after the label correction, no
document here exercises the thresholds alone.

**Not answered, by design:** whether OCR recovers the text (no real OCR
authorised), whether the bare-enable risk materialises on corpora with
threshold-decided documents, and whether the result generalises beyond
this library.

**Next actions:** archive the change, then a separate promotion decision
for the enable flag + thresholds. The Sloman follow-up — a reader
fallback — was executed as experiment 30 and shipped as ADR-066.

## Artefacts

| File | Description |
| --- | --- |
| `output/classifications.json` | Per-document classification records |
| `output/eval_results.summary.json` | Per-arm routing decisions and gate evaluation |
| `output/collection.public.json` | The operator-approved collection manifest |
| `classify.py` | Classification runner |
| `summarise_eval.py` | Gate evaluation and report data |

Reproduce:

```bash
uv run python experiments/29-pdf-routing-repeat-2026-09-13/classify.py
uv run python experiments/29-pdf-routing-repeat-2026-09-13/summarise_eval.py
```

Resume is identity-bound: a changed plan, label set, collection or
policy refuses to resume. Private mappings stay in gitignored `output/`
files.
