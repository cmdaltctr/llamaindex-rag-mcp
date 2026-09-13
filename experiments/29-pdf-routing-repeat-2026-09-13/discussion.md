# Experiment 29 — Discussion

The story in plain terms: experiment 28 found the bug but could not prove
the fix was safe, because its evidence was gathered before the fix existed
and its labels came from the same tool being tested. This study closed
that gap.

## What the four arms tell you

The middle two arms exist to answer "was it really the fix?"

- `baseline_exp28` and `baseline_matched` differ only in the tolerance
  number (0.5 vs 0.10). They made identical decisions — nothing in this
  collection sits between 10% and 50% bad pages — so the tighter
  tolerance changed nothing here. Noted, not a problem.
- `baseline_matched` and `candidate` differ only in the fix itself.
  The book flips from "route" to "fast" between exactly those two arms.
  That is the cleanest possible proof that removing `mixed` from the
  unconditional list is what saved the book — not the new threshold, not
  luck.

## The finding that matters most for later

The `enable_only` arm is the trap for the future: if someone enables the
switch without setting the thresholds, Sloman — the hardest detection in
the whole collection — is silently missed. "Switch on, thresholds off" is
a worse configuration than fully off in one specific way: it looks like
protection while missing the exact case that needs it.

## The Sloman surprise

Experiment 28 called Sloman a document that needs OCR because pdf-inspector
extracted zero characters. The independent check shows a healthy text
layer — pdf-inspector just fails on this file. So the document is really
evidence for a different feature than the one being tested: a fallback
reader for "our extractor choked", which would fix it in ~1 second rather
than ~30 minutes of OCR. Worth its own change; deliberately not decided
here.

## What this study cannot tell you

- How common needy documents are — all 14 held-out papers were healthy,
  so the prevalence question from experiment 28 stays open.
- Whether OCR actually recovers the text — no real OCR was authorised.
- Anything about libraries other than this one.
