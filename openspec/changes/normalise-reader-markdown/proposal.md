# Proposal: Normalise reader Markdown before chunking

## Why

Nothing cleans the text a PDF reader or OCR engine emits. Tag characters therefore reach stored chunks, embeddings and BM25 unchanged. Experiment 34 counted 112 `<u>` pairs from pdf-inspector, some wrapping running headers or half a sentence. It also counted 104 `<div>` blocks from the PaddleOCR-VL worker: 30 image-only, 52 image-plus-text (badges and chart labels read from inside figures), and 22 text-only figure captions. TDR-028 records the decision. This change implements it.

## What Changes

- Add one pure, deterministic normalisation function for reader-produced text. It runs once per document, after `read_document` and before chunking. It uses no LLM and no new dependency.
- Rules (closed list; unknown tags pass through unchanged):
  - Remove formatting-only tags and keep their text: `<u>`, `<span>`, `<font>`, `<center>`. `<b>`/`<strong>` become `**text**`. `<i>`/`<em>` become `*text*`.
  - Remove a `<div>` block that contains an image, including any text inside it.
  - Unwrap a `<div>` that contains only text, and keep the text (figure captions).
  - Remove bare `<img>` tags.
  - Keep Markdown links and bare URLs unchanged.
  - Keep `<table>` blocks. Keep only structural tags and `colspan`/`rowspan`, and remove presentational attributes (`style`, `border`, …).
  - Convert `<br>` to a newline. Decode HTML entities outside tables and code.
  - Never change fenced code blocks or inline code.
- Scope: text extracted from PDF sources, through every PDF reader, the OCR tiers and cloud backends. Authored text files (`.md`, `.txt`, `.html`) and code and config files pass through unchanged, because their HTML can be intentional.
- New nested setting `ingestion.normalise_reader_output` (`INGESTION__NORMALISE_READER_OUTPUT`), default `true`. It exists for comparison experiments.
- The normaliser version and the resolved on/off value join `source_index_identity`. The identity schema advances from 5 to 6. **Reprocessing:** every existing source re-ingests once on its next ingest, including sources the normaliser would not change. This follows the spec's conservative identity rule.
- Measure before and after on the Experiment 34 outputs: tags removed per engine and rule, and visible text lost (target: zero outside removed image blocks).

## Capabilities

### New Capabilities

- `reader-output-normalisation`: deterministic cleanup of reader-produced Markdown before chunking. Covers the rule set, the PDF-source scope, the setting, and the no-text-loss guarantee.

### Modified Capabilities

- `async-ingestion`: the complete-index-identity requirement gains the normaliser version and the resolved setting, and advances the identity schema to 6.

## Impact

- Code: new `src/omrg/core/ingestion/normalise.py` (pure function). One call in `src/omrg/core/ingestion/chunker.py` after `read_document`. The setting in `src/omrg/core/ingestion/settings.py`. Identity fields in `src/omrg/core/ingestion/source_state.py`.
- Tests: rule unit tests with fixtures cut from the Experiment 34 outputs; a chunker routing test (PDF normalised, `.md` untouched); identity tests (version change forces reprocessing; setting change forces reprocessing).
- Docs: `docs/guides/ingestion.md`, `docs/guides/configuration.md`, `.env.example`, and TDR-028 status.
- Data: existing collections re-ingest once after upgrade (schema 6).
- No new dependencies. No transport or API change.
- Timing: implementation starts after Experiment 34 closes, on this branch (operator decision 2026-09-24).
- Out of scope: LaTeX-wrapped plain text from the worker (`$ ^{1} $`, `$ \underline{\text{Supporting}} $`), recorded in TDR-028 as an open item; converting HTML tables to Markdown tables; reading-order repair.
