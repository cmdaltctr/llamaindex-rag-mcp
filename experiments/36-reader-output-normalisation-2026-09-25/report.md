# Experiment 36: Reader-output normalisation

**Status:** Awaiting operator decisions: removed image-block text (task 4.3) and the `[figure]` marker (task 4.4).  
**Normaliser:** version 1.  
**Source:** Experiment 34 raw page Markdown after the worker fix (Experiment 34 A9); 5 engines × 43 pages (42 sampled plus `eq01` p11). See protocol amendment A1.

## Measured result

| Measure | `pdf_inspector` | `liteparse` | `worker` | `local_ocr` | `dots_mocr` | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pages | 43 | 43 | 43 | 43 | 43 | 215 |
| Visible-character deltas outside removed image blocks | 0 | 0 | 0 | 0 | 0 | 0 |
| `<u>` tags removed | 228 | 0 | 0 | 224 | 0 | 452 |
| Image-bearing `<div>` blocks removed | 0 | 0 | 46 | 0 | 0 | 46 |
| Table presentation attributes removed | 0 | 0 | 28 | 0 | 0 | 28 |
| Text-only `<div>` blocks unwrapped | 0 | 0 | 13 | 0 | 0 | 13 |
| Removed blocks containing text | 0 | 0 | 28 | 0 | 0 | 28 |

LiteParse and dots.mocr output needs no normalisation. The local OCR tier keeps
pdf-inspector's `<u>` tags on fused pages. Only the worker emits image blocks.

The first measurement (`5cbf91e`: 129 pages, 3 engines, 54 removed texts) read
worker output with the page-1 fault. 26 of its 54 entries were duplicates of
later pages' blocks; the two 14,722-character `bd02` blocks were one block.

The page-level data, source SHA-256 hashes and all removed texts are in
[`output/summary.json`](output/summary.json). The runner confirmed that the
Experiment 34 raw files stayed byte-identical during measurement.

## Removed text, by kind (28 entries, all worker)

| Kind | Entries | Example |
| --- | ---: | --- |
| Publisher logos and badges | 3 | `CC BY`, `Check for updates` |
| Chart labels | 1 | `bd02` p6: 14,722 characters of axis and legend labels |
| Newspaper advertisements and printed headings (`io04`) | 15 | `TORNADO CORN & COB MILL …`, `J.I.C DRIVING BIT …`, `SUNDRY HUMBUGS` |
| Single stray characters | 9 | `港`, `福`, `鶴`, `☆`, `1` ×3, `A`, `O` |

## Operator decisions needed

1. Task 4.3: is any removed text a real caption? Separately: should `io04`
   advertisement text (printed on the page, but inside image blocks) be kept?
2. Task 4.4: add a `[figure]` marker where an image block is removed?
