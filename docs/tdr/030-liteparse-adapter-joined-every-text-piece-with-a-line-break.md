# TDR-030: The LiteParse adapter joined every text piece with a line break — join pieces on one visual line

**Date:** 2026-09-25
**Status:** Accepted (fix `8a48510`, with 5 line-level unit tests)
**Deciders:** Aizat
**Tags:** pdf | liteparse | reading-order | experiment-34

## Context

LiteParse returns a page as text pieces with positions. The adapter
(`src/omrg/integrations/pdf/liteparse.py`) rebuilds page text from the pieces
so that it can reorder two-column pages (change `liteparse-reading-order`,
PR #96). It joined the pieces with `"\n".join(...)`, a line inherited from the
adapter's first version (`34fd595`).

### Root Cause Analysis

Symptom (Experiment 34, 2026-09-24): the LiteParse panel for `bd01` p1 showed
the title one word per line. The PDF draws each title word as its own piece;
all share `y=170.0`. LiteParse's own `page.text` keeps the line; the adapter
did not use it.

Why it was missed: PR #96 measured reading order with Experiment 33's
`order_score`, which compares lowercase token streams. A line break and a
space score the same, so one word per line scored as correct. Every synthetic
test used one piece per line.

## Decision

`_join_lines` joins consecutive pieces on one visual line and keeps order:

- same line: vertical overlap at least 0.5 × the shorter height, moving right;
- a gap under 0.1 × height is a kerning split: no space;
- a gap over 1.0 × the taller height is a column gap or sidebar: line break.
  On `bd03` p2, sidebar gaps measure 1.56–3.69 × height and real word gaps at
  most 0.73 ×.

Result on the 19 non-empty sample pages: 2,573 → 1,117 lines, characters
identical with whitespace ignored.

## Consequences

### Positive

- Headings and sentences stay whole; LiteParse output is readable again.

### Negative

- Thresholds are measured on one corpus (Experiment 34 sample).

### Neutral

- Sidebar layouts still interleave: the gutter test leaves them alone by design.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Use LiteParse's `page.text` | Cannot be reordered by column; loses the PR #96 fix. |
| Round `y` and group | Superscripts and mixed font sizes break exact grouping; overlap is robust. |

## How to Recognise / Handle This Again

1. Symptom: reader output with one word or one short fragment per line.
2. Measure lines, not only tokens: a token-stream score cannot see line breaks.

## Revisit Triggers

- A LiteParse upgrade that changes piece granularity.
- Layouts where word gaps exceed one text height (very wide justified text).

## References

- `src/omrg/integrations/pdf/liteparse.py`, `tests/unit/test_liteparse_reader.py`; commit `8a48510`
- Experiment 34 protocol A6; change `liteparse-reading-order` (task group 5); PR #96, PR #97
