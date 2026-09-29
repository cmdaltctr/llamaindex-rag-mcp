# Experiment 36: Reader-output normalisation

**Status:** PASS  
**Verdict:** Normaliser version 2 removes reader markup from all five engines' output and loses no visible character on any of 215 pages.  
**Normaliser:** version 2 (version 1 removed image blocks with their text; see protocol A2).  
**Source:** Experiment 34 raw page Markdown after the worker fix (Experiment 34 A9); 5 engines × 43 pages (42 sampled plus `eq01` p11), protocol A1.  
**Raw data:** [`output/summary.json`](output/summary.json)  
**Change:** `openspec/changes/normalise-reader-markdown` (tasks 4.1–4.4); decision recorded in ADR-070 and TDR-028  
**Protocol:** [protocol.md](protocol.md)

## Bottom line

PDF readers and OCR engines leave HTML markup in their Markdown: underline tags, image blocks and table styling. The normaliser removes it before chunking. On the Experiment 34 outputs, every visible character survives on every page, including text that the OCR worker read inside pictures. The operator reviewed the 28 texts that version 1 dropped with their image blocks. None was a caption, but some were real printed advertisements, so version 2 keeps them and adds no `[figure]` marker.

## Results

| Measure | `pdf_inspector` | `liteparse` | `worker` | `local_ocr` | `dots_mocr` | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Pages | 43 | 43 | 43 | 43 | 43 | 215 |
| Visible-character deltas (whole page) | 0 | 0 | 0 | 0 | 0 | 0 |
| `<u>` tags removed | 228 | 0 | 0 | 224 | 0 | 452 |
| Image blocks unwrapped (`<img>` removed, text kept) | 0 | 0 | 46 | 0 | 0 | 46 |
| Text-only `<div>` blocks unwrapped | 0 | 0 | 13 | 0 | 0 | 13 |
| Table presentation attributes removed | 0 | 0 | 28 | 0 | 0 | 28 |

LiteParse and dots.mocr output needs no normalisation. The local OCR tier keeps
pdf-inspector's `<u>` tags on fused pages. Only the worker emits image blocks.
The runner confirmed that the Experiment 34 raw files stayed byte-identical.

## Operator review of image-block text (task 4.3)

| Kind | Entries | Example | Version 2 |
| --- | ---: | --- | --- |
| Publisher logos and badges | 3 | `CC BY`, `Check for updates` | kept |
| Chart labels | 1 | `bd02` p6: 14,722 characters of axis and legend labels | kept |
| Newspaper advertisements and printed headings (`io04`) | 15 | `TORNADO CORN & COB MILL …`, `SUNDRY HUMBUGS` | kept |
| Single stray characters | 9 | `港`, `福`, `鶴`, `☆`, `1` ×3, `A`, `O` | kept |

No entry is a real caption: captions sit in text-only blocks, which both versions keep.

## Discussion

1. **Why keep noisy text.** A formatting step cannot tell a useful advert from a stray `港`. Version 1 tried, by position (inside a picture), and dropped 15 real advertisement texts from an 1889 magazine. Version 2 keeps everything printed and leaves quality judgements to the engine comparison.
2. **Cost.** The `bd02` p6 chart-label dump (14,722 characters) now reaches the index as a few low-value chunks. It is one block in 215 pages.
3. **History.** The first measurement (`5cbf91e`) read worker output with the page-1 fault (Experiment 34 A9). The second (`42cb4df`, version 1) listed 28 removed texts. This run is version 2.
4. **Limits.** 43 pages per engine, one corpus. The zero-loss result is measured on this sample only. Unknown tags pass through unchanged by design and are not counted.

## Decisions

- Task 4.3: keep text inside image blocks (normaliser version 2).
- Task 4.4: no `[figure]` marker.
