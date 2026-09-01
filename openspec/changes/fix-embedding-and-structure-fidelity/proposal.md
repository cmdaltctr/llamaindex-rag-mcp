# Fix embedding-text and document-structure fidelity

## Why

The 2026-09-01 RAG audit found two ingest-side defects that silently degrade
every vector this project has ever written. Both are invisible at runtime:
no error, no warning, no failing test.

**1. Reader diagnostics are embedded into the vectors.** Only the eight
lineage keys are excluded from embedding text. Every other metadata key a
reader attaches is prepended to the chunk before it reaches the embedding
model. Verified at runtime for the default PDF path:

```
pdf_reader: pdf_inspector
pdf_type: text_based
pdf_confidence: 0.98
page_count: 12
file_path: /Users/someone/corpus/report.pdf
file_name: report.pdf
category: ai
...
<the actual chunk text>
```

Four lines of parser telemetry and a machine-specific absolute path sit in
front of every PDF chunk vector. `pdf_confidence: 0.98` carries no
retrievable meaning; it is constant across the document and dilutes the
chunk's own signal uniformly.

**2. Parser-produced document structure is discarded one step later.** The
default reader, `pdf_inspector`, extracts markdown correctly — measured on a
real 106,000-character paper it produced 38 properly nested headings and 24
markdown table rows. `chunker.py` then decides whether to use the
heading-aware path with `file_path.suffix.lower() == ".md"`, which is false
for a `.pdf`, so all of that structure is thrown away:

| Path | Chunks | Chunks carrying `header_path` |
| --- | --- | --- |
| Today (suffix check fails → plain sentence split) | 99 | **0** |
| Routed through `MarkdownNodeParser` | 60 | **60** |

The project already wrote the recovery hooks. `ensure_heading_metadata` and
`apply_heading_prepend` look for exactly the `header_path` key
`MarkdownNodeParser` emits — built during Experiment 6c, tested, and never
once executed for a PDF.

Two smaller defects share the same root (structure produced then dropped) and
are fixed here because they touch the same files and the same re-index:

**3. `page_label` is structurally unreachable.** Only `pypdf` emits it.
`liteparse` emits `page`; `pdf_inspector` emits neither. The default
configuration therefore returns `page_label: null` for every PDF, while
`openapi.yaml` lists it as a **required** field and the CLI renders a Page
column for it. The contract promises what no default path can deliver.

**4. AST code chunking is unreachable through ingestion.** `codebase.yaml`
sets `chunking.strategy_fallback: code`, but `SUPPORTED_EXTENSIONS` excludes
every source-code extension, so a `.py` file is never gathered. The only
ingest-level test that exercises it patches `gather_supported_files` to force
the file past the gate, so the suite reports coverage that production does not
have.

Now, because every fix here changes stored vectors. Doing this before a large
corpus is built costs one re-ingest; doing it after costs a full rebuild.

## What Changes

- The set of metadata keys excluded from embedding text becomes an explicit,
  centrally-owned contract rather than an accident of which reader ran.
- That exclusion set is folded into `source_index_identity`, so changing it
  correctly invalidates existing chunks instead of leaving a corpus half
  embedded under the old rule.
- PDF reader adapters declare the text format they emit. The chunker routes
  on that declaration instead of the file suffix, so parser-produced markdown
  reaches the heading-aware pipeline regardless of the source file's
  extension.
- `liteparse` emits `page_label` alongside `page`, giving two of four readers
  real page provenance.
- The OpenAPI contract and the CLI stop promising a page number that the
  configured reader cannot produce.
- Source-code extensions become admissible for ingestion under the `codebase`
  profile only, making the profile's existing `strategy_fallback: code`
  setting genuinely reachable without changing what a `documents`-profile ingest
  picks up.

Not in scope: retrieval-side behaviour (separate change), answer synthesis
(separate change), OCR for scanned PDFs, table-aware chunking
(`MarkdownElementNodeParser` needs an LLM call per element — an experiment,
not a fix).

## Capabilities

### New Capabilities

- `embedding-text-composition`: the contract governing exactly which text and
  which metadata keys reach the embedding model, and how a change to that set
  invalidates previously-written vectors.

### Modified Capabilities

- `pdf-reader`: readers declare their emitted text format; `liteparse` emits
  `page_label`; the page-provenance matrix per reader becomes explicit.
- `markdown-aware-chunking`: the heading-aware path is selected by declared
  text format, not by file suffix.
- `type-aware-ingestion`: the ingestible extension set is profile-scoped so
  the `codebase` profile can admit source files.

`async-ingestion` needs no requirement change: its existing
"complete index identity" requirement already mandates covering *every*
index-shaping input. The exclusion set and the declared text format are two
more such inputs, so this is an implementation obligation under an unchanged
requirement, tracked by the new `embedding-text-composition` capability.

## Impact

- **Requires a full re-ingest.** Vectors written before this change were
  embedded under a different text composition. `source_index_identity`
  changes, so existing collections re-process on next ingest rather than
  silently serving stale chunks — the mechanism already built for this.
- Code: `core/ingestion/source_state.py`, `core/ingestion/chunker.py`,
  `core/ingestion/loader.py`, `core/ingestion/backends/`,
  `integrations/pdf/{registry,liteparse,pdf_inspector,pypdf,pypdfium}.py`,
  `core/profiles/`, `transports/api/openapi.yaml`, `transports/cli/search.py`.
- Retrieval-quality gate: the Tier-2 floors are measured against the current
  embedding text. They must be re-measured and re-committed as part of this
  change, not adjusted to fit.
- No new dependencies. No API-shape change to `search()` results beyond
  `page_label` becoming honestly optional.
