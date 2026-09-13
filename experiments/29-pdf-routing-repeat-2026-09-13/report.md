# Experiment 29: PDF routing repeat study

**ID**: `29-pdf-routing-repeat-2026-09-13`  
**Date run**: 2026-09-13  
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent  
**Status**: PASS — with one caveat spelled out in Discussion  
**Verdict**: The OCR routing fix works. Enable `OCR_FALLBACK_ENABLED` — but only with the thresholds set.  
**Raw data**: [`output/classifications.json`](./output/classifications.json), [`output/eval_results.summary.json`](./output/eval_results.summary.json)  
**Change**: `openspec/changes/repeat-pdf-routing-study`  
**Protocol**: [protocol.md](protocol.md)

## Bottom line

The fix works. The 991-page book that experiment 28 would have sent to
~30 hours of pointless OCR now stays on the fast path, while the two
documents that genuinely need OCR still get caught, and none of the 14
held-out papers are wrongly routed. `OCR_FALLBACK_ENABLED` is safe to
promote — provided the thresholds go with it. Flipping the switch bare
silently misses the hardest case.

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
| Recall | zero held-out needs-OCR documents missed | 0 | ✅ — vacuous, see Discussion |
| Dev recall check | Kerr and Sloman must route under the candidate | both routed | ✅ |

### What each arm decided

| Document | What it is | Needs OCR? | `baseline_exp28` | `baseline_matched` | `candidate` | `enable_only` |
| --- | --- | --- | :-: | :-: | :-: | :-: |
| dev_001 | The book — 991 pages, 10 flagged | no | **route** | **route** | fast | fast |
| dev_002 | Kerr 1998 — scanned, 23 pages | yes | route | route | route | route |
| dev_003 | Sloman 1971 — pipeline reads 0 chars | yes | route | route | route | **fast** |
| hold_001–014 | 14 healthy born-digital papers | no | fast | fast | fast | fast |

### Projected OCR cost

| Arm | Pages sent to OCR | Projected time | Honest reading |
| --- | ---: | --- | --- |
| `baseline_exp28` | 1,031 | ~30.5 hours | 96% of it on a book that needed nothing |
| `baseline_matched` | 1,031 | ~30.5 hours | same |
| `candidate` | 40 | ~71 minutes | only the two genuinely-needy documents |
| `enable_only` | 23 | ~41 minutes | cheapest — by missing Sloman entirely |

## Discussion

**The fix — not the tolerance — is what saved the book.** The two middle
arms are the control: `baseline_exp28` and `baseline_matched` made
identical decisions (nothing in this collection sits between 10% and 50%
bad pages), so the tolerance change did nothing here. `baseline_matched`
and `candidate` differ only in the fix — and the book flips from "route"
to "fast" between exactly those two arms. That is the cleanest possible
proof that removing `mixed` from the unconditional list caused the
change.

**The held-out recall gate passed with nothing to prove.** No held-out
document actually needs OCR, so "0 missed of 0" is arithmetic, not
evidence — the Wilson 95% upper bound on held-out needs-OCR prevalence
is ~21.5%, meaning up to one in five unseen documents could still need
OCR without this collection showing it. The real catch-evidence lives in
the dev set, which is why the frozen rules required Kerr and Sloman to
route explicitly.

**A bare enable is strictly worse.** With `OCR_FALLBACK_ENABLED=true`
and thresholds left at the off position, Sloman gets missed entirely.
It looks like protection while missing the exact case that needs it.
Anyone flipping the switch later must set the thresholds too.

**The Sloman surprise.** Sloman is not actually a scanned document —
pypdf reads its text layer fine (about 2,944 characters per page);
pdf-inspector simply fails on this particular file. Routing it is still
correct, because the pipeline cannot read it either way, but the right
long-term fix is probably a reader fallback, not OCR — that would
recover the page in ~1 second instead of ~30 minutes of OCR. Flagged as
a follow-up, not decided here.

**Limitations.** OCR costs are projections at the worst measured
per-page cost (106.4 s); whether OCR actually recovers the text was not
measured — that needed a separate authorisation, which was not given.
The collection is small and operator-selected, so the result validates
the committed rule on this library, not universally.

## Conclusion

The experiment answered its question: the committed fix routes correctly
on an operator-approved collection, with zero false routes on all 14
held-out papers and both needy documents still caught.

**What ships:** `OCR_FALLBACK_ENABLED` can be promoted — only together
with the thresholds (0.5 confidence, 0.10 page fraction). The one thing
the experiment warns against is enabling the switch bare: at the default
0.0 sentinels it silently misses the hardest case.

**Not answered, by design:** whether OCR recovers the text (no real OCR
authorised), and whether the result generalises beyond this library.

**Next actions:** archive the change, then a separate promotion decision
for the enable flag + thresholds, and a follow-up on Sloman — a reader
fallback would fix it in ~1 s instead of ~30 min of OCR.

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
