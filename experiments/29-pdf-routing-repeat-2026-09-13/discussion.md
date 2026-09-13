# Experiment 29 — Discussion

## What the repeat established that experiment 28 could not

Experiment 28's result was real but procedurally unusable: classifier-derived
labels, a convenience scan, measurements taken before the fix. This study
re-ran the question under the repaired rules and the answer held: the
post-`9bf4810` policy false-routes nothing on an approved collection with
independent labels, and both genuinely-needy documents still route.

The four-arm design paid for itself in one line of the table. The book
routes under `baseline_exp28` AND `baseline_matched` — the false route is
reproduced on demand — and falls to the fast path only when the
unconditional set changes. That isolates `9bf4810` as the active
ingredient: the tolerance tightening to 0.10 contributed nothing on this
collection because nothing sits between 10% and 50% flagged.

## The enable-only arm is the most policy-relevant finding

At `OCR_FALLBACK_ENABLED=true` with the packaged 0.0 sentinels, a
`text_based`-at-confidence-1.0 document extracting zero characters stays
on the fast path. The switch alone buys the unconditional types and loses
the threshold-only detection — the same detection experiment 28 credited
as the good part. Any future promotion discussion should treat "enable
without thresholds" as a distinct, worse configuration, not a midpoint.

## The Sloman finding reframes a known case

`dev_003` was labelled needs-OCR in experiment 28 on density evidence
(zero extracted characters). The independent pypdf assessment shows a
healthy text layer — this is a pdf-inspector *extraction failure*, not a
scan. The routing verdict is unchanged (the pipeline still cannot read
it, so routing is correct), but the remedy class shifts: an OCR worker
re-OCRs a page that already has text, while a reader fallback would
recover the existing layer at ~1 s instead of ~100 s/page. Recorded as a
follow-up question, deliberately not resolved here.

## What this study does not establish

- Nothing about prevalence. n=14 held-out, all needs-OCR-false; the
  Wilson interval reaches 21%.
- Nothing about OCR recovery quality — no real OCR was authorised, and
  every cost figure is a labelled projection.
- Nothing about corpora beyond this collection. The approval-gated
  selection is honest about being exactly what it is.
