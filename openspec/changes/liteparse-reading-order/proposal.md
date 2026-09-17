## Why

The LiteParse adapter joins a page's text items in the order the library
returns them (`"\n".join(item.text for item in page.text_items)`). On a
multi-column page that order follows neither column. The adapter already
computes a `single` / `left` / `right` label per page from item positions and
puts it in metadata, then ignores it when joining.

Experiment 33 measured the cost. On its 87 operator-reviewed pages, liteparse
keeps almost every word (median token recall 0.991) and loses the order on
multi-column pages: reading-order score 0.53 against a reference
transcription, where plain pypdf text scores 0.98 on the same pages.

This is not a cosmetic problem, and it is not confined to liteparse. `rf04` is
a rescued document: pdf-inspector extracts nothing, so the ADR-066 chain hands
the file to liteparse, and liteparse's 0.53 is what reaches chunking,
embedding and retrieval. The operator's spot-check notes on columns and tables
judged pypdf's text, not the pipeline's, so Experiment 33's reader comparison
is the first measurement of the real reading order.

## What Changes

- The liteparse adapter classifies each page's layout from its own text items
  before joining: `single` or `multi_column`.
- A `multi_column` page is joined column by column: items are ordered by
  column, then by vertical position, then by horizontal position.
- A `single` page keeps today's order exactly.
- Pages whose layout is not confidently multi-column, including tables, keep
  today's order. A table-aware order needs its own measurement and is out of
  scope here.
- The page-level `column` metadata value gains `multi_column` alongside the
  existing values, so the emitted label names what the join actually did.

No OCR, no worker, and no routing change. Token recall is unaffected: the same
items are emitted, in a different order.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `pdf-reader`: the LiteParse bounding-box metadata requirement gains a
  layout-classification and join-order obligation, so a multi-column page is
  emitted in reading order rather than library order.

## Impact

- Code: `src/omrg/integrations/pdf/liteparse.py` only. No settings, no
  dependency, no protocol and no index identity change.
- Metadata: the existing `column` key gains the value `multi_column`. It is
  already in the excluded-embed set, so no source re-index is triggered.
- Evidence: measured from the Experiment 33 worktree against its frozen
  reference transcriptions, with `--code-root` pointing at this checkout.
- Relates to `page-level-ocr-routing` (same branch, separate change) and to
  ADR-066, whose rescue chain makes this reader's output the shipped text for
  rescued documents.
