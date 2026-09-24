# Design

## Context

See proposal.md (Why). The current state that shapes the approach:

- `chunk_file_async` in `core/ingestion/chunker.py` is the single path from a document file to nodes. Code and config files return before the document-backend dispatch. `read_document` (`chunker.py:105`) then returns a `BackendRead` with `documents`, `structured` and `text_format`. The structured and unstructured branches both start from `backend_read.documents`.
- `build_index_identity` in `core/ingestion/source_state.py` hashes a payload at `_INDEX_IDENTITY_SCHEMA = 5`. The spec rule is conservative: an input is hashed for every source.
- `IngestionSettings` (`core/ingestion/settings.py`, env prefix `INGESTION__`) is frozen and injected through `EffectiveSettings` (ADR-037).
- The markup to remove comes from the engines, not the pipeline. Experiment 34 outputs give real examples: `output/{pdf_inspector,liteparse,worker}/<doc>/pNNN.md`.

## Goals / Non-Goals

**Goals:**

- One pure function, `normalise_reader_text(text: str) -> str`, plus a module constant `NORMALISER_VERSION`.
- One call site that covers every PDF reader, OCR tier and cloud backend.
- Rules small enough to read in one sitting. Each rule is tested against a real Experiment 34 excerpt.

**Non-Goals:**

- Full HTML-to-Markdown conversion.
- Reading-order repair, header and footer removal, and LaTeX unwrapping (TDR-028 open item).
- Normalising authored files or query text.

## Decisions

### D1 — Call site: in `chunk_file_async`, right after `read_document`

Normalise `backend_read.documents` in place (each document's text) before the `is_markdown` and `structured` branches. Both branches then see clean text, and metadata extraction reads the same text the chunks carry.

- Alternative: inside `read_document`. Rejected: the orchestrator's job is backend dispatch and fallback. Adding content rewriting there mixes concerns, and every backend test would then see rewritten text.
- Alternative: inside each reader adapter. Rejected: rules would be duplicated and drift apart (TDR-028).

### D2 — Scope gate: PDF source only

Normalise when `file_path.suffix.lower() == ".pdf"` or the detected `content_type` is PDF. Authored `.md`, `.txt` and `.html` files often contain intentional HTML (badges, `<details>`, centred logos), so they pass through unchanged.

- Alternative: gate on `text_format == "markdown"`. Rejected: authored `.md` files also resolve to Markdown, and LiteParse emits plain text that can still carry entities.

### D3 — Implementation: protected segments plus closed regex rules, stdlib only

1. Cut out fenced code blocks, inline code spans, `<table>…</table>` blocks and LaTeX maths, and replace them with placeholders. Maths is `$$…$$` (may span lines), `\begin{name}…\end{name}` with a matching name, and `$…$` within one line. Code is cut first, so a `$` inside code never opens maths. An unmatched `$` or `\begin` protects nothing.
2. Apply the `<div>` rules innermost first, repeated until stable: image-bearing block → removed; text-only block → unwrapped.
3. Apply the formatting-tag rules (`u`, `span`, `font`, `center` unwrapped; `b`/`strong` → `**`; `i`/`em` → `*`), `<br>` → newline, bare `<img>` removed.
4. Decode entities with `html.unescape` on the unprotected text only.
5. Clean each protected table: keep structural tags with only `colspan`/`rowspan`, unwrap every other tag inside the table and keep its text (no Markdown bold inside HTML cells). Restore every placeholder.
6. Collapse runs of three or more blank lines that the removals created to one blank line.

- Alternative: `html.parser` or BeautifulSoup. Rejected: the input is Markdown with islands of HTML, not HTML. A tree parser reorders or drops Markdown syntax around the islands. BeautifulSoup would also be a new core dependency (⚠️ Ask).
- Alternative: `markdownify` / `html2text`. Rejected in TDR-028 (new dependency, rewrites tables).

### D4 — Identity: add a `normalisation` block and advance the schema to 6

```python
"normalisation": {
    "enabled": settings.ingestion.normalise_reader_output,
    "version": NORMALISER_VERSION,
},
```

The block is hashed for every source, including non-PDF sources, following the conservative rule. `NORMALISER_VERSION` is an integer that is bumped by hand whenever a rule changes. A test pins the current value to the rule-fixture set, so a rule change without a bump fails the build.

- Alternative: hash the normaliser source code. Rejected: it churns on comments and formatting and forces needless reprocessing.

### D5 — Setting

`IngestionSettings.normalise_reader_output: bool = True`. It is read from the injected `EffectiveSettings` and never from a global (Invariant 9). The conftest default keeps it `True`, so tests exercise production behaviour.

### D6 — Measurement lives in its own experiment

Measure before and after in a new experiment folder, `experiments/36-reader-output-normalisation-<date>/`, created with the s-experiment skill. It reads the Experiment 34 outputs by path and reports, per engine and rule, the tags removed and the visible-character delta. Experiment 34 closes before implementation starts, so the measurement does not reopen it.

## Risks / Trade-offs

- [A text-only `<div>` wraps content that is really part of a figure (chart labels without an `<img>`)] → That text stays; this is the no-text-loss rule working as intended. The measurement reports the count of unwrapped blocks for review.
- [An image block's text is a real caption] → The Experiment 34 sample shows captions in text-only blocks, not image blocks. The measurement lists every removed image-block text for operator spot-checks. Tighten the rule if a real caption appears.
- [Regex rules on malformed HTML (unclosed `<div>`)] → Unbalanced tags are left untouched and not guessed. A test covers an unclosed `<div>`.
- [One-off full re-ingest after upgrade] → Documented in the release notes. It follows the schema 4 and schema 5 precedent.
- [`html.unescape` decodes some entities without a closing semicolon (`&not` → `¬`, `&times` → `×`), and `&` separates LaTeX columns] → Maths is a protected segment (D3 step 1), so entity and tag rules never see it.
- [A currency `$` pairs with another on the same line (`$5 and $10`)] → The span between them is protected and skips the rules. It is kept, not lost, so the no-text-loss rule still holds. Real `<u>` or entities inside such a span stay raw; Experiment 36 counts them.
- [Bold inside a table cell is lost] → Accepted. Markdown `**` does not render inside HTML cells, so the tag is unwrapped and the text kept.

## Migration Plan

1. Ship with the default on and identity schema 6. Every source reprocesses once on its next ingest.
2. Rollback: set `INGESTION__NORMALISE_READER_OUTPUT=false`. That also changes the identity, so sources reprocess to raw text. Reverting the release returns to schema 5 and reprocesses again.

## Open Questions

- Should a removed image block leave a `[figure]` marker? Deferred to the Experiment 36 results: keep it only if the marker improves retrieval or LLM reading on figure-heavy pages. The default is no marker. Adding one later is a rule change and a version bump. It does not change the specs' structure.
