# Design: LiteParse reading order

## Context

`src/omrg/integrations/pdf/liteparse.py` builds each page's text with
`"\n".join(item.text for item in page.text_items)`. LiteParse returns items in
its own order, which on a multi-column page interleaves the columns. The same
function already derives a `column` label from item x positions and stores it
in metadata, so the geometry needed to do better is in hand and unused.

Experiment 33's reader comparison, over the 87 operator-reviewed pages with
frozen reference transcriptions, measured what this costs. Two scores per page
and reader: token recall (did the words survive) and reading order (longest
common subsequence of the reader's token stream against the reference stream,
divided by the reference length).

| Reader | Median recall | Median order | Pages with no text |
| --- | ---: | ---: | ---: |
| `pdf_inspector` | 0.683 | 0.683 | 19 of 41 |
| `liteparse` | 0.991 | 0.982 | 2 of 41 |
| `pypdf` | 0.990 | 0.964 | 2 of 41 |

Counted over the 41 reviewed pages labelled `usable`. Liteparse keeps the words
and, on the operator's column pages, loses the order:

| Page | Operator note | `liteparse` | `pypdf` |
| --- | --- | ---: | ---: |
| `bd01` p4 | needs better support for two columns | 1.00 / 0.53 | 0.99 / 0.98 |
| `rf04` p4 | needs dual column support | 0.98 / 0.53 | 0.98 / 0.98 |
| `rf04` p6 | needs dual column and table support | 0.98 / 0.53 | 0.98 / 0.97 |

Recall / order. `rf04` is a rescued document, so liteparse's 0.53 is the text
that reaches retrieval.

## Goals

- Multi-column pages reach the reference's reading order.
- Every other page is byte-for-byte unchanged.
- Token content never changes; only order does.
- No new dependency, setting, protocol field or index identity input.

## Non-Goals

- Table-aware ordering. Tables keep today's order until measured separately.
- Any change to pdf-inspector, pypdf, the OCR gate or the routing unit.
- Retrieval-side use of the `column` metadata.

## Decisions

1. **Classify, then join.** A pure function takes a page's text items and
   returns `single` or `multi_column` with the gutter position. The join uses
   it. Nothing else in the adapter changes.

2. **The classifier is a gutter test, chosen by measurement.** Reject the naive
   45% split: Experiment 33 measured it dropping a journal front page from 0.67
   to 0.52 and a table page from 0.74 to 0.40. The rule that passed is:

   - Drop items wider than 60% of the page's horizontal text extent, so running
     heads, full-width figures and rules do not bridge the gutter.
   - Require at least 10 items to remain.
   - Build a 200-bin coverage histogram of the remaining items across that
     extent. A bin is part of a gutter when its coverage is at most 5% of the
     peak bin.
   - Take the widest such band whose centre lies between 0.35 and 0.65 of the
     extent, and require it to be at least 1% of the extent wide.
   - Require both sides to hold items, the smaller side to hold at least half
     as many items as the larger, and each side's vertical span to be at least
     half the page's vertical text extent.

   Every threshold above is a measured boundary, not a guess; the per-page
   numbers are in the Experiment 33 artefacts named below. Anything that fails
   is `single`.

3. **Order within a multi-column page** is `(side, y rounded to 0.1, x)`, where
   side is 0 for items whose horizontal centre falls left of the gutter centre
   and 1 otherwise. Rounding y keeps items on one visual line together when
   their baselines differ slightly.

4. **Two columns only.** The measured corpus has no three-column page among the
   reviewed set, and a rule fitted to nothing is a guess. The classifier finds
   one gutter; three-column layouts stay `single` until measured.

5. **Metadata names the order.** A reordered page carries
   `column="multi_column"`, so a reader of the metadata can tell what the text
   order means. Unreordered pages keep `single`, `left` or `right` exactly as
   today. The key is already excluded from embedding, so no re-index follows.

## Risks

- A page with a decorative vertical gap could be misread as two columns. The
  balance and vertical-span conditions exist for that, and the measurement
  found no such case in 87 pages; a larger corpus may.
- Three-column pages are untested and deliberately left alone.
- The classifier runs per page over the page's items, which is linear in items
  and negligible beside parsing; confirm on the largest reviewed document
  rather than asserting it.

## Evidence gate

Measured from the Experiment 33 worktree, never from this one, against the
frozen reference transcriptions, with `--code-root` pointing at this checkout:

1. Multi-column body pages reach reading order at or above 0.90, up from 0.53.
2. No regression on `bd02` p1 (0.67) or `tl03` p5 (0.74).
3. Token recall unchanged, within ±0.01 per page.
4. Scores reported per page class: single, multi-column, table.

Measured against this adapter by
`experiments/33-ocr-routing-natural-positive-2026-09-17/reading_order.py`, over
the 65 reviewed pages that have liteparse items and a reference transcription
(the other 22 have no text to order):

| Page class | Pages | Median order before | Median order after | Median recall before | Median recall after |
| --- | ---: | ---: | ---: | ---: | ---: |
| `multi_column` | 6 | 0.5309 | **0.9613** | 0.977 | 0.977 |
| `single` | 59 | 0.9409 | 0.9409 | 0.9679 | 0.9679 |

| Gate | Result |
| --- | --- |
| Multi-column order ≥ 0.90 | 0.9613 |
| `bd02` p1 no regression | classified `single`, 0.6703 unchanged |
| `tl03` p5 no regression | classified `single`, 0.7401 unchanged |
| Recall within ±0.01 | no page changed; item multiset preserved on every page |
| Order regressions | none, on any page |

Per multi-column page: `rf03` p6 0.53 → 0.98, `rf04` p6 0.53 → 0.97, `bd01` p4
0.53 → 0.97, `rf02` p7 0.66 → 0.95, `rf04` p4 0.53 → 0.94, and `rf06` p65
0.44 → 0.69, a handwritten record whose recall is 0.72 before order is
considered.

Decision 2's single-gutter condition earned itself during implementation: a
regular four-column table has a qualifying gutter at its centre, so an
earlier one-gutter-anywhere rule reordered it. Requiring exactly one gutter
leaves tables alone, and also stops the rule reordering `tl01` p59, a figure
page that gains nothing from it. Raw data: `output/reading_order.json`.
