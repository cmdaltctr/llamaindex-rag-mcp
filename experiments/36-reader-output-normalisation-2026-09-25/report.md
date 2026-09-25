# Experiment 36: Reader-output normalisation

**Status:** Awaiting operator review of removed image-block text (task 4.3).  
**Normaliser:** version 1.  
**Source:** Experiment 34 raw page Markdown; 43 pages per engine (42 sampled plus `eq01` p11).

## Measured result

| Measure | Result |
| --- | ---: |
| Reader-page outputs | 129 |
| Visible-character count deltas outside removed image blocks | 0 |
| `<u>` tags removed | 228 |
| Image-bearing `<div>` blocks removed | 88 |
| Table presentation attributes removed | 56 |
| Text-only `<div>` blocks unwrapped | 24 |
| Removed blocks containing text | 54, on 15 worker pages |

The page-level data, source SHA-256 hashes, and all removed texts are in
[`output/summary.json`](output/summary.json). The runner confirmed that the
Experiment 34 raw files remained byte-identical during measurement.
The zero-delta result excludes text inside removed image blocks. It does not
show whether removing that text is safe.

## Operator decision needed

Review all 54 entries in `output/summary.json` under `removed_image_block_texts`.
Pay particular attention to `worker/bd02/p001.md` and `p006.md`: each removed
block contains 14,722 characters of repeated chart labels. The `io04` pages
include long advertisement text. Record whether any block contains a real caption
that must remain visible. If so, tighten the normaliser rule, bump its version,
and repeat task 4.2 before any Experiment 34 review-page rebuild.

The `[figure]` marker decision (task 4.4) also remains open. Record the
operator's verdict here before task 4.5 starts.
