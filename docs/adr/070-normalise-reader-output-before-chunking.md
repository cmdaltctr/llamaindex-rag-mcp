# ADR-070: Normalise Reader Output Before Chunking — Remove Markup, Never Content

**Date:** 2026-09-25
**Status:** Proposed (implementation complete on `feat/experiment-34-worker-sample-review`; awaiting operator acceptance at PR #97 review)
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Change:** `openspec/changes/normalise-reader-markdown/`
**Related:** [ADR-055](055-embedding-text-is-a-declared-contract.md) (declared text contract, Markdown routing), [ADR-069](069-page-level-ocr-routing-and-the-pdfium-runtime.md) (page-level OCR routing), TDR-028 (rule list), TDR-029 (worker page-1 fault), TDR-030 (LiteParse line join)

## Context

PDF readers and OCR engines put HTML into the Markdown they return.
pdf-inspector wraps links, and sometimes whole running headers, in `<u>`.
The PaddleOCR-VL worker wraps pictures in `<div><img></div>` blocks and
styles its tables. Nothing in the pipeline removed this markup, so the tags
reached stored chunks, embeddings and BM25 as literal characters.

Experiment 34 put five engines side by side on the same pages and made the
markup visible. It also showed that an operator reviewing reader quality
judges the markup as much as the text. Experiment 36 then counted it on 215
page outputs: 452 `<u>` tags, 46 image blocks, 13 text-only blocks and 28
table styling attributes. LiteParse and dots.mocr emit none.

## Decision

1. **One pipeline stage.** A pure, deterministic, stdlib-only function,
   `normalise_reader_text` (`src/omrg/core/ingestion/normalise.py`), runs on
   PDF text right after `read_document` and before chunking. It is the only
   cleanup point, so a new reader or OCR engine gets it without extra work.
   A `.md` source is left as written.
2. **Remove markup, never content.** The rules are a closed list (TDR-028):
   formatting tags and every `<div>` are unwrapped and their text kept;
   `<img>` tags are removed with no placeholder; tables keep only structural
   tags and `colspan`/`rowspan`; code, links and LaTeX maths are protected.
   Unknown tags pass through. The gate is that no visible character is lost.
3. **Text read inside a picture is content** (normaliser version 2). A
   formatting step cannot tell a useful advertisement from a stray character,
   so it does not try. Noisy image-region OCR is an engine-quality question.
4. **Part of the index identity.** The setting
   (`INGESTION__NORMALISE_READER_OUTPUT`, default on) and
   `NORMALISER_VERSION` join the index identity, which advances to schema 6.
   Every source reprocesses once on its next ingest, as with schema 5, and
   any later rule change is a version bump that reprocesses again.

## Consequences

### Positive

- Chunks, embeddings and BM25 carry document text, not tags, from every engine.
- Engine comparisons compare text, not markup.
- pdf-inspector's `<u>` misfires are repaired without an upstream fix.

### Negative

- One-off re-ingestion of every source (schema 6).
- Low-value text stays: the 14,722-character chart-label dump on `bd02` p6,
  logos and stray characters that the worker read inside pictures.
- Regex rules on HTML: malformed input (an unclosed `<div>`) is left
  untouched rather than guessed.

### Neutral

- Tables stay as HTML. The chunker already handles them as text.
- The setting can be turned off for reader comparisons; that also changes
  the identity.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Clean in each reader adapter** | Duplicates the rules; every new engine needs the same work; adapters drift apart. |
| **HTML-to-Markdown library** (`markdownify`, `html2text`) | A new core dependency (⚠️ Ask). It rewrites Markdown it did not need to touch and changes table shape. |
| **Drop image blocks with their text** (version 1) | Operator review of the 28 dropped texts found no caption, but 15 were real printed advertisements and headings (`io04`). Dropping content by position is a content judgement. |
| **Keep block text under a size limit** | The limit is arbitrary; a full-page advert over the limit would vanish silently. |
| **`[figure]` placeholder** | Most image blocks are logos and badges; captions are separate text and stay; a marker carries no searchable content. |
| **Do nothing** | Tags stay in the index and in every engine comparison. |

## History — how this decision came about

| Date | Event | Record |
| --- | --- | --- |
| 2026-09-24 | Experiment 34 review page shows stray `<u>` and `<div>` in reader panels | Experiment 34 A3, TDR-028 (Proposed) |
| 2026-09-24 | LiteParse panel shows one word per line: the adapter joined every text piece with a line break | TDR-030, Experiment 34 A6 |
| 2026-09-25 | Operator decides the review must see normalised text; the normaliser is built before Experiment 34 closes | `normalise-reader-markdown` start gate |
| 2026-09-25 | Experiment 36 finds the same removed blocks on several `io04` pages: the worker put every requested page into page 1 | TDR-029, Experiment 34 A9 |
| 2026-09-25 | Worker re-run; Experiment 36 re-measured on five engines; version 1 drops 28 image-block texts | Experiment 36 A1 |
| 2026-09-25 | Operator keeps image-block text and declines a `[figure]` marker: version 2, no visible character lost on 215 pages | Experiment 36 A2, this ADR |
| 2026-09-25 | Review pages rebuilt on normalised output; PR #97 to `v3` | Experiment 34 A7 |

## References

- `src/omrg/core/ingestion/normalise.py`, `chunker.py` (call site), `source_state.py` (identity schema 6)
- `docs/guides/ingestion.md#reader-output-normalisation`, `docs/guides/configuration.md`
- Experiment 34: `experiments/34-worker-sample-review-2026-09-19/` (protocol amendments A1–A9)
- Experiment 36: `experiments/36-reader-output-normalisation-2026-09-25/` (report, `output/summary.json`)
- TDR-028, TDR-029, TDR-030; PR #97
