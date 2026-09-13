# Experiment 29: PDF routing repeat study

**ID**: `29-pdf-routing-repeat-2026-09-13`
**Date run**: 2026-09-13
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent
**Status**: PASS — with one caveat spelled out below
**Raw data**: [`output/classifications.json`](./output/classifications.json), [`output/eval_results.summary.json`](./output/eval_results.summary.json)
**Change**: `openspec/changes/repeat-pdf-routing-study`

---

## The answer in plain English

**The fix works.** The book that experiment 28 would have sent to 30
hours of pointless OCR now stays on the fast path. Both baseline arms —
the old buggy policy, replayed from the pinned commit — still route it.
That proves the fix is what changed the outcome, not something else.

**The needy documents still get caught.** The scanned Kerr paper and the
Sloman paper (which the pipeline cannot read at all) both correctly
route to OCR under the new policy.

**Nothing innocent gets routed.** All 14 held-out papers from the RAG
collection stay on the fast path under every policy.

## What we did

Classified 17 approved PDFs once each (5.2 seconds total), then asked
the production routing function "would you send this to OCR?" under four
versions of the policy:

| Arm | What it is | Why it exists |
| --- | --- | --- |
| `baseline_exp28` | The old buggy policy, exactly as experiment 28 ran it | Proves the old behaviour is reproducible |
| `baseline_matched` | The old buggy policy at the new 10% tolerance | Same thresholds as the candidate — any difference is the fix alone |
| `candidate` | The fixed policy at the approved 10% tolerance | The thing being tested |
| `enable_only` | The fixed policy with thresholds switched off | What happens if someone flips the enable switch and nothing else |

The two middle arms are the control: `baseline_exp28` and
`baseline_matched` made identical decisions (nothing in this collection
sits between 10% and 50% bad pages), so the tolerance change did
nothing here. `baseline_matched` and `candidate` differ only in the fix
— and the book flips from "route" to "fast" between exactly those two
arms. That is the cleanest possible proof that removing `mixed` from the
unconditional list saved the book.

## What each arm decided

| Document | What it is | Needs OCR? | `baseline_exp28` | `baseline_matched` | `candidate` | `enable_only` |
| --- | --- | --- | :-: | :-: | :-: | :-: |
| dev_001 | The book — 991 pages, 10 flagged | no | **route** | **route** | fast | fast |
| dev_002 | Kerr 1998 — scanned, 23 pages | yes | route | route | route | route |
| dev_003 | Sloman 1971 — pipeline reads 0 chars | yes | route | route | route | fast |
| hold_001–014 | 14 healthy born-digital papers | no | fast | fast | fast | fast |

## The gates

| Gate | Rule | Measured | Verdict |
| --- | --- | --- | --- |
| Safety | zero held-out documents wrongly routed | 0 | ✅ PASS |
| Recall | zero held-out needs-OCR documents missed | 0 | ✅ PASS — see caveat |
| Dev recall check | Kerr and Sloman must route under the candidate | both routed | ✅ PASS |

## The two caveats, no spin

1. **The held-out recall gate passed with nothing to prove.** No
   held-out document actually needs OCR, so "0 missed of 0" is
   arithmetic, not evidence. The real catch-evidence lives in the dev
   set — which is why the frozen rules required Kerr and Sloman to route
   explicitly.
2. **A bare enable is strictly worse.** With `OCR_FALLBACK_ENABLED=true`
   and thresholds left at the off position, Sloman gets missed entirely.
   It looks like protection while missing the exact case that needs it.
   Anyone flipping the switch later must set the thresholds too.

## The Sloman surprise

Sloman is not actually a scanned document. pypdf reads its text layer
fine (about 2,944 characters per page) — pdf-inspector simply fails on
this particular file. Routing it is still correct, because the pipeline
cannot read it either way, but the right long-term fix is probably a
reader fallback, not OCR — that would recover the page in ~1 second
instead of ~30 minutes of OCR. Flagged as a follow-up, not decided here.

## What it would have cost (projection — no real OCR was run)

| Arm | Pages sent to OCR | Projected time | Honest reading |
| --- | ---: | --- | --- |
| `baseline_exp28` | 1,031 | ~30.5 hours | 96% of it on a book that needed nothing |
| `baseline_matched` | 1,031 | ~30.5 hours | same |
| `candidate` | 40 | ~71 minutes | only the two genuinely-needy documents |
| `enable_only` | 23 | ~41 minutes | cheapest — by missing Sloman entirely |

These are projections at the worst measured per-page cost (106.4 s).
Whether OCR actually recovers the text was not measured — that needed a
separate authorisation, which was not given.

## Conclusion

**The OCR routing fix works and is safe to enable — with the thresholds
set.**

Concretely:

- The old policy's bug (send any `mixed` PDF wholly to OCR) is confirmed
  real and reproducible: both baseline arms still route the 991-page
  book.
- The fixed policy routes it correctly — stays fast — while still
  catching both documents that genuinely can't be read (scanned Kerr,
  unreadable Sloman).
- Zero false routes on all 14 held-out papers.

So the deferred question now has an answer: `OCR_FALLBACK_ENABLED` can
be promoted — but only together with the thresholds (0.5 confidence,
0.10 page fraction). The one thing the experiment warns against is
enabling the switch bare: at the default 0.0 sentinels it silently
misses the hardest case.

Two things it did not answer, by design:

- Whether OCR actually recovers the text (no real OCR authorised).
- Whether this generalises beyond this library — small selected
  collection, and held-out recall had nothing to test on.

**Next actions if you want them:** archive the change, then a separate
promotion decision for the enable flag + thresholds, and a follow-up on
Sloman (it's a pdf-inspector extraction failure, not a scan — a reader
fallback would fix it in ~1 s instead of ~30 min of OCR).

## Reproduction

```bash
uv run python experiments/29-pdf-routing-repeat-2026-09-13/classify.py
uv run python experiments/29-pdf-routing-repeat-2026-09-13/summarise_eval.py
```

Resume is identity-bound: a changed plan, label set, collection or
policy refuses to resume. Private mappings stay in gitignored `output/`
files.
