# TDR-028: Normalise reader Markdown before chunking — strip formatting-only HTML, keep links and tables

**Date:** 2026-09-24
**Status:** Accepted (2026-09-25; OpenSpec change `normalise-reader-markdown`, evidence Experiment 36)
**Deciders:** Aizat
**Tags:** ingestion | markdown | pdf-inspector | ocr-worker | experiment-34

## Context

No step cleans reader output. `read_document` returns a `BackendRead`
(`core/ingestion/backends/orchestrator.py`), and its `documents` text goes
straight to the chunker, then into stored chunks and embeddings. Each
engine's inline HTML therefore reaches the index as literal characters.

Experiment 34 put the three engines' outputs side by side on the same pages.
The operator saw stray tags during review (2026-09-24).

### Root Cause Analysis

The tags come from the engines. The pipeline does not create them, and
nothing removes them. Counts across the Experiment 34 outputs:

| Engine | Inline HTML | Examples |
| --- | --- | --- |
| pdf-inspector | 112 `<u>…</u>` pairs | Links (valid). Also misfires: whole running headers (`<u>ARTICLE HUMANITIES AND SOCIAL SCIENCES COMMUNICATIONS \| …</u>`) and half a sentence (`signifi- <u>cantly different at p≤ 0.05…</u>`). |
| OCR worker (PaddleOCR-VL) | 104 `<div …><img …></div>` image placeholders; HTML `<table>` blocks | The placeholders carry no text. The tables are real structure. |
| LiteParse | none | — |

Effects:
1. Tag characters take up chunk budget and add noise to embeddings and BM25.
2. An LLM reading a chunk sees markup instead of text.
3. The same page gives different text per engine, which makes engine comparisons noisy.

## Decision

Add one shared, deterministic normalisation function. It runs on every
`Document` after the backend read and before chunking, whatever backend
produced the text. Rules:

| Input | Output |
| --- | --- |
| Formatting-only tags: `<u>`, `<span>`, `<div>`, `<font>`, `<center>`, `<b>`/`<strong>`, `<i>`/`<em>` | Remove the tag and keep the inner text. `<b>`/`<strong>` become `**text**`. `<i>`/`<em>` become `*text*`. |
| `<div>` wrapping an image, with or without text | Remove the tags and the `<img>`, keep the text, and leave no `[figure]` marker (normaliser version 2, operator decisions after Experiment 36, 2026-09-25). The text an engine read inside a picture is document text: besides badges and chart labels it includes real printed advertisements (`io04`). Version 1 removed the block with its text; none of the 28 texts it dropped was a caption, but 15 were printed advertisements and headings. |
| `<div>` wrapping text only | Remove the tags, keep the text. These are figure captions (22 in Experiment 34, for example "FIGURE 2 Statistical description of…"). Deleting the whole block would lose them. |
| A bare `<img …>` | Remove. |
| Markdown links, bare URLs | Keep unchanged. |
| `<table>` (with `colspan`/`rowspan`) | Keep. Strip `style`, `border` and other presentational attributes only. Converting to a Markdown table is out of scope: merged cells do not survive it. |
| `<br>` | Newline. |
| HTML entities | Decode (`&amp;` becomes `&`). |
| Fenced code blocks | Never touched. |

Open item for the OpenSpec change: the worker also wraps plain text in LaTeX.
Examples: author superscripts as `$ ^{1} $`, and a word as
`$ \underline{\text{Supporting}} $`. Unwrap LaTeX only when it contains no
mathematics. The rule needs its own test set before it joins the list.

Constraints:
- **Pure function in `core/ingestion/`**, with no reader imports. It takes a string and returns a string. It follows Architecture Invariant 2 (no cross-imports).
- **Folded into the index identity.** Normalised text differs from raw text, so the normaliser version must join `source_index_identity`. Otherwise old and new chunks would mix in one collection.
- **Configurable off** through a nested setting (`INGESTION__NORMALISE_READER_OUTPUT`, see change `normalise-reader-markdown`). The default is on. Set it off only for comparison experiments.
- **Measured before and after** on the Experiment 34 outputs (Experiment 36): 215 pages across five engines, no visible character lost, 452 `<u>` tags removed, 46 image blocks and 13 text blocks unwrapped, 28 table styling attributes removed.

## Consequences

### Positive

- One cleanup point for every reader. A new engine gets it without extra work.
- Engine comparisons compare text, not markup.
- It repairs pdf-inspector's `<u>` misfires without depending on an upstream fix.

### Negative

- Existing collections need re-ingestion to benefit, because the identity changes.
- A tag that carries meaning in some corpus (for example `<sup>` in chemistry) could be lost. The rule list above is deliberately closed: unknown tags pass through unchanged.

### Neutral

- Tables stay as HTML. The chunker already handles them as text.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Fix each reader adapter separately | Duplicates the rules. Each new engine needs the same work. Adapters drift apart. |
| Full HTML-to-Markdown library (`markdownify`, `html2text`) | A new core dependency (⚠️ Ask). It rewrites Markdown it did not need to touch. It changes table shape. |
| Strip every tag | Destroys tables and merged-cell structure, the worker's main strength. |
| Wait for upstream pdf-inspector to fix `<u>` | Does not cover the worker's placeholders. Timing is not under our control. |

## How to Recognise / Handle This Again

1. Symptom: search results or chunk text show `<u>`, `<div`, `<img`, `&amp;` or `style=` fragments.
2. Diagnose: count tags in reader output per engine: `grep -ohE '</?[a-z]+\b' output/<engine>/*/*.md | sort | uniq -c`.
3. If the tag is on the closed rule list, the normaliser is off or bypassed. Check the setting and that the call sits after `read_document`.
4. If the tag is new, decide whether it is formatting-only (add it to the list, bump the normaliser version) or structural (pass it through).

## Revisit Triggers

- A new reader or OCR engine joins (for example dots.mocr, Experiment 34 A2). Recount its tags.
- pdf-inspector fixes its underline detection upstream.
- Table handling changes: Markdown tables, or table-aware chunking.

## References

- Experiment 34: `experiments/34-worker-sample-review-2026-09-19/` (outputs per engine, `protocol.md`)
- Experiment 36: `experiments/36-reader-output-normalisation-2026-09-25/` (the before-and-after measurement)
- ADR-070 (the architectural decision and its history); TDR-029, TDR-030 (the two reader faults found on the way)
- OpenSpec change `normalise-reader-markdown`; setting `IngestionSettings.normalise_reader_output`
- `src/omrg/core/ingestion/backends/orchestrator.py` (`BackendRead`, `read_document`), the insertion point
- `src/omrg/core/ingestion/chunker.py` (Markdown routing, ADR-055)
- TDR-027 (the worker page-selection fix that produced these outputs)
