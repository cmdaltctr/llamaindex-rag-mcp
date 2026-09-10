# Ingestion Guide

## How ingestion works

Each file passes through a four-stage pipeline:

```
Source file (PDF, DOCX, TXT, ...)
      |
      v
[1] Load & parse  -----> Metadata extraction (optional)
      |                      |
      |                      +-- keyword:    regex (instant, no model)
      |                      +-- local:      chat model via METADATA_LLM_PROVIDER (~2s/file)
      |                      +-- llamaindex: per-chunk pipeline (~5–30s/file)
      |
      v
[2] Split into chunks (SentenceSplitter)
      |  chunk_size = 512 chars (default)
      |  chunk_overlap = 100 chars
      |
      v
[3] Embed each chunk --> Ollama embedding model (EMBED_MODEL)
      |                     Produces a fixed-dimension vector (768, 1024, etc.)
      |
      v
[4] Store in the selected vector store
      |  LanceDB is the base-install default
      |  collection = "documents" (or --collection value)
      |  Each record: vector + text + metadata + file_path
      v
[Done] Collection ready for search
```

Re-ingesting a file is an **upsert** — old chunks are removed before new ones are written. There is no duplication.

## Embedding write contract

Stage 4 is fail-closed
([ADR-051](../adr/051-fail-closed-embedding-write-contract.md)): the store
adapter validates the complete embedding batch before any backend
mutation. The shared validator rejects a batch that contains:

- no identifiers or no vectors (empty batch)
- a count of identifiers that differs from the count of vectors
- a value that is not a sized vector, or an empty vector
- a non-numeric element (booleans are rejected)
- a non-finite element (NaN or infinity)
- mixed vector dimensions within one batch
- a dimension that conflicts with the existing collection

A rejected batch writes nothing: no rows, no collection recreation, and no
generation change. The error names the collection, the embedding
provider/model, and each affected node or row identifier. Vectors are
never normalised, truncated, or repaired — the validator reports the
fault and stops the write. Norm policy is enforced separately by the
embedding norm guard ([ADR-053](../adr/053-embedding-norm-guard.md)): a
vector outside the unit-norm tolerance aborts the file replacement at the
embed stage, before the store validator runs.

## Source and chunk lineage

Every production-ingested chunk carries stable identity metadata
([ADR-052](../adr/052-stable-source-chunk-lineage.md)). The identifiers are
deterministic hashes: the same inputs always produce the same value.
`core/ingestion/source_state.py` owns the formulas and stamps them after
parsing, chunking, and metadata extraction but before embedding, so no
identifier ever changes a vector or the text an LLM sees.

### The identity hierarchy

| Field                 | Formula                                                                                            | Stability                                                                                        |
| --------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| `file_path`           | canonical absolute path                                                                            | Human-readable locator for display and diagnostics                                               |
| `source_id`           | `"src_" + SHA-256("file\0" + canonical path)`                                                      | Stable while the file is edited in place; new after a move or copy; identical across collections |
| `source_content_hash` | SHA-256 of the original file bytes                                                                 | New when bytes change; shared by equal bytes at two paths                                        |
| `source_version`      | SHA-256 of `source_content_hash` + NUL + `source_index_identity`                                   | New when bytes or any index-shaping setting (parser, chunker, metadata, embedding) changes       |
| `source_chunk_index`  | zero-based ordinal within the version                                                              | Orders membership in the chunk set                                                               |
| `source_chunk_count`  | N, the chunk total for the version                                                                 | Declares the size of the complete set                                                            |
| `chunk_id`            | `"chk_" + SHA-256(source_id + NUL + source_version + NUL + decimal index + NUL + chunk text hash)` | Stable for the same text at the same ordinal in one version                                      |
| vector row ID         | SHA-256 of `source_id` + NUL + `source_attempt` + NUL + `chunk_id`                                 | Attempt-specific; never a store primary key                                                      |

All digests are lower-case hexadecimal over UTF-8 input joined with NUL
separators. `source_id` excludes the collection name, so one file indexed
into two collections carries one identity. The vector row ID stays internal:
a forced re-ingestion reproduces the same `chunk_id` values but writes fresh
row IDs, so candidate and durable attempts coexist until verification
([ADR-048](../adr/048-bounded-failure-safe-ingestion.md)). Ordinary public
results never expose the row ID.

### Ordered reconstruction

One `source_id` plus one `source_version` is a complete ordered chunk set:

```text
rows    = all rows with source_id = "src_…" and source_version = "…"
assert  every row has source_chunk_count == N and N == len(rows)
ordered = rows sorted by source_chunk_index   # indices are 0, 1, …, N-1
```

Sorting by `source_chunk_index` rebuilds the indexed chunk sequence. This
reconstructs the INDEXED representation only. It does not recover the
original file bytes, PDF layout, or parser input. The source file and
`source_content_hash` remain authoritative for the original content.

### Moving or copying a file

Identity follows the path. A new canonical path is a new logical source, so:

1. Delete the old path from the collection.
2. Ingest the destination path.

The watcher applies both steps automatically for a rename inside the watch
tree (`on_moved`: delete the old path first, then ingest the destination). A
failed cleanup is retried and reported; the destination is never ingested
while the old path still holds rows. Manual moves outside a watch tree still
need the two steps above. Equal bytes at two paths share
`source_content_hash` but keep different `source_id` values; content is never
deduplicated.

### Pre-lineage rows fail before mutation

If a collection holds rows for a canonical path that lack, or disagree on,
the derived `source_id`, ingestion stops before any parse, embedding, or
store write. The error names the path and instructs you to rebuild the
affected data by deleting the source or collection and re-ingesting it. The
stored rows are never migrated, upgraded, or deleted. This is a deliberate
clean boundary: no production documents predate this change.

## Upgrading to this release

This release changes two things every stored vector depends on:

1. The embedding-text contract
   ([ADR-055](../adr/055-embedding-text-is-a-declared-contract.md)). Parser
   telemetry and filesystem bookkeeping no longer enter embedding text.
2. Index identity schema 3. The identity now records the exclusion set and
   the reader's declared text format.

Both changes alter `source_index_identity`. The result is one full re-ingest.

### What you will see

- Every previously ingested source re-processes on the next corpus ingest.
- `files_skipped_unchanged` drops to zero on the first run after upgrade.
  Later runs resume normal incremental skipping.
- Search results are unchanged in shape. No tool or CLI call changes.

### Interrupted re-ingests resume

The re-ingest is per source, not one atomic collection rebuild. An
interrupted run may leave old-era and new-era sources in one collection.
This is safe. The next run re-processes each old-era source; it does not
skip it. Each replacement stays failure-safe per source
([ADR-048](../adr/048-bounded-failure-safe-ingestion.md)).

### Rows the lineage guard rejects

Pre-lineage rows, or rows from an incompatible mixed state, still fail
`assert_source_lineage_compatible()` before any mutation. Those rows keep
the explicit delete-and-rebuild path described above. This release neither
weakens nor replaces that guard.

## PDF reader configuration

The PDF parser is a pluggable factory controlled by the `PDF_READER`
environment variable. Accepted values:

| Value           | Description                                                         | Install                      |
| --------------- | ------------------------------------------------------------------- | ---------------------------- |
| `pdf_inspector` | Default. Rust markdown extractor. Emits one document per PDF.       | Base dependency              |
| `pypdf`         | Always available via `llama-index-readers-file`. Terminal fallback. | Base (transitive)            |
| `liteparse`     | Column-aware reading order + bounding-box metadata.                 | Base dependency              |
| `pypdfium2`     | Same PDFium engine as LiteParse, no bbox. Fallback tier.            | `[pdf-pypdfium2]` extra      |
| `auto`          | Probes in order: liteparse → pypdfium2 → pypdf.                     | Depends on what is installed |

The packaged default is `pdf_inspector`, a base dependency selected through
configuration after Experiment 14
([ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)).
`auto` keeps the LiteParse-first capability policy. Set `PDF_READER` to any
registered name to override the default. A configured reader that is not
importable logs an error and falls back to pypdf.

`pdf_inspector` emits one document per PDF, where pypdf and LiteParse emit
per-page documents. Markdown chunking then splits that single document, so
source-document boundaries change with this reader.

LiteParse captures bounding-box metadata (`page`, `column`,
`section_bbox`, `bbox_schema_version`) on every emitted Document for
future spatial RAG capabilities. OCR is disabled by default
(`LITEPARSE_OCR_ENABLED=false`) — enable it only for scanned PDFs.

See [ADR-020](../adr/020-use-liteparse-as-pdf-reader.md) for the factory
adoption rationale and [ADR-050](../adr/050-configure-pdf-inspector-as-default-reader.md)
for the default-selection decision and Experiment 14 results.

## OCR fallback for scanned PDFs

`pdf-inspector` reads text out of a PDF. It cannot read text that is only
an image. A scanned page therefore comes back empty or nearly empty, and
that content never reaches the index. The OCR fallback sends those PDFs
to an isolated PaddleOCR-VL worker instead.

**This is opt-in and stays off by default.** Two reasons, both measured.

First, OCR is expensive: 34–106 seconds per page against roughly one
second per file on the fast path. A 20-page scanned document costs
twenty minutes.

Second, how much a corpus benefits is unresolved. On a library of 79 real
academic PDFs, only 2 documents genuinely lacked a text layer — but with
79 documents the 95% interval on that rate still runs from 0.7% to 8.8%,
so "rare" is supported and "negligible" is not. See
[ADR-064](../adr/064-input-quality-promotion-decisions.md) and experiment 28.

The same measurement identified a limitation in the original policy: it
sent a 991-page `mixed` document to OCR in full, despite extracting 1,127
characters per page with only 10 of 991 pages flagged. That defect was
fixed on 2026-09-10: `mixed` is no longer in the unconditional routing
set and now routes by the calibrated thresholds.

The worker is a separate project in `ocr-worker/` with its own lockfile.
It owns every Paddle package. The OMRG main install has none of them, and
a normal `uv sync` never pulls them in.

### Routing policy

Every PDF starts on `pdf-inspector`. The routing seam only looks at the
evidence `pdf-inspector` already produced: `pdf_type`, `pdf_confidence`,
the count of pages flagged for OCR, and the page count.

A PDF routes to the OCR worker when either rule fires:

1. `pdf_type` is `scanned` or `image_based`. This is unconditional and
   ignores the thresholds, because both labels mean the whole document
   is pictures and no threshold can change that.
2. Anything else — including `mixed` and `text_based` — routes only if
   `pdf_confidence` falls below `OCR_FALLBACK_MIN_CONFIDENCE`, or the
   flagged-page proportion reaches `OCR_FALLBACK_PAGE_FRACTION`.

`mixed` sits in the second group. It means "some pages carry text and
some do not", which the page-fraction threshold can evaluate. The whole
file is dispatched together, with no page-level stitching. The 991-page
document from experiment 28 motivated this fix; see
[ADR-064](../adr/064-input-quality-promotion-decisions.md).

OCR remains off by default. Keep `OCR_FALLBACK_ENABLED=false` with both
thresholds at `0.0` until the operator explicitly enables OCR.

Layout complexity is not a rule. Multi-column and table-heavy PDFs stay
on the fast path when their text extracts cleanly. Experiment 24
confirmed the fast-path Markdown is byte-identical with the fallback
enabled and disabled.

The whole PDF goes to the worker, not individual pages. There is no
page-level stitching between the two readers.

### Configuration

| Variable                      | Default | Meaning                                                          |
| ----------------------------- | ------- | ---------------------------------------------------------------- |
| `OCR_FALLBACK_ENABLED`        | `false` | Master switch. Off means no PDF ever reaches the worker.         |
| `OCR_FALLBACK_MIN_CONFIDENCE` | `0.0`   | Confidence floor for text-based PDFs. `0.0` never triggers.      |
| `OCR_FALLBACK_PAGE_FRACTION`  | `0.0`   | Flagged-page proportion that triggers OCR. `0.0` never triggers. |
| `OCR_WORKER_COMMAND`          | empty   | Command that starts the worker. Empty means unavailable.         |
| `OCR_WORKER_ENV_DIR`          | empty   | Worker virtual-environment directory.                            |
| `OCR_WORKER_REQUEST_TIMEOUT`  | `300.0` | Seconds to wait for one parse response.                          |

In the proposed local variant, both `0.0` thresholds are "never triggered"
sentinels, not "always triggered". Enabling the fallback without calibrated
thresholds gives classification-only routing in that variant.

The first three fields form the calibrated gate in the proposed local variant.
The last three are operational: how to reach the worker. Keep them separate.
`0.5` / `0.5` are the values Experiment 23 calibrated on the committed
calibration fixtures.

### Provision the worker

```bash
cd ocr-worker
python3 provision.py                # Python 3.12
python3 provision.py --python 3.11  # or 3.13
python3 provision.py --dry-run      # resolve only, install nothing
```

The script syncs from the worker's own `uv.lock` with `uv sync --locked`
and never touches the OMRG environment. It rejects any interpreter
outside 3.11 to 3.13 before installing anything. Do not run `uv sync`
from the repository root to provision the worker: that installs OMRG.

Then point OMRG at it:

```bash
OCR_FALLBACK_ENABLED=true
OCR_FALLBACK_MIN_CONFIDENCE=0.5
OCR_FALLBACK_PAGE_FRACTION=0.5
OCR_WORKER_COMMAND="uv run python -m omrg_ocr_worker"
OCR_WORKER_ENV_DIR=/absolute/path/to/ocr-worker
```

### Worker lifecycle

The worker is lazy and long-lived, and the engine owns it.

1. Building an engine starts nothing. A metadata-only capability probe
   runs at the composition boundary. It reads versions and identities
   only: it does not initialise Paddle, import model code, or load
   weights.
2. A clean PDF never starts the worker.
3. The first PDF that actually dispatches starts one subprocess.
4. Later OCR requests reuse that subprocess. One request is in flight at
   a time.
5. Engine shutdown closes it.
6. A timeout, crash, closed output stream, or protocol violation
   discards the handle. The next OCR request starts a fresh process. The
   failed request is never replayed automatically.

### Protocol and diagnostics

The two processes speak UTF-8 JSON Lines. OMRG writes one request per
line to the worker's standard input; the worker writes one terminal
response per line to standard output. Nothing else goes to standard
output. All worker logs go to standard error, which OMRG drains
separately and forwards through its own logging, so a noisy worker can
never corrupt the protocol stream or block on a full pipe.

Protocol version is `1.0`. Successful parse responses declare the output
schema `omrg.ocr.parse_output` version `1`. A version or schema mismatch
is a protocol failure, not a silent downgrade.

The capability probe reports availability, protocol version, every
worker package with its exact version, pipeline identity and revision,
model identity and revision, and output-schema identity and version.
Missing, unusable, malformed, and incompatible workers all collapse to
ONE stable unavailable fingerprint. The reason lives in the log, never
in the fingerprint.

### When the worker is not there

If a PDF needs OCR but no usable worker exists **before dispatch**,
ingestion keeps `pdf-inspector`'s partial Markdown, marks the result
degraded through the OCR metadata, logs an actionable warning naming
`OCR_WORKER_COMMAND`, and continues the batch. Nothing is fabricated and
no other file fails.

If the worker fails **after** a complete request was written and
flushed, that file returns a structured error instead. The partial
Markdown is not substituted for a success, the failed source version is
not marked current, any prior current version survives, and the batch
continues with the next file.

### OCR metadata on every PDF

Four keys are stamped on both branches, so an operator can tell what
happened by reading a retrieval result:

| Key                 | Meaning                                   |
| ------------------- | ----------------------------------------- |
| `ocr_required`      | The routing gate said this PDF needs OCR. |
| `ocr_used`          | The worker actually parsed it.            |
| `ocr_backend`       | `pdf_inspector` or `paddleocr_vl`.        |
| `pages_needing_ocr` | Scalar count of flagged pages.            |

Read them together:

| `ocr_required` | `ocr_used` | `ocr_backend`   | What happened                                    |
| -------------- | ---------- | --------------- | ------------------------------------------------ |
| `false`        | `false`    | `pdf_inspector` | Fast path. Clean text extraction.                |
| `true`         | `true`     | `paddleocr_vl`  | OCR fallback. Worker output.                     |
| `true`         | `false`    | `pdf_inspector` | Degraded. Worker unavailable; partial text only. |

`pages_needing_ocr` is stored as a count, never as the page list
`pdf-inspector` returns internally: no vector store accepts a list-valued
metadata field. All four keys are in `EXCLUDED_EMBED_METADATA_KEYS`, so
they are stored and returned but never embedded and never sent to an LLM.

### Re-ingestion consequence

The OCR routing configuration and the resolved worker fingerprint both
participate in the index identity. See
[Index identity and re-ingestion](configuration.md#index-identity-and-re-ingestion).

## Document backends

Document reading dispatches through a registry selected by `DOCUMENT_BACKEND`.

| Value   | Reads                            | Install                 |
| ------- | -------------------------------- | ----------------------- |
| `local` | All supported formats (default)  | Base dependency         |
| `azure` | `.pdf`, `.docx`, and `.doc` only | `uv sync --extra azure` |

Files outside azure's list read through the local backend even when
`DOCUMENT_BACKEND=azure`. An unknown value fails server start-up and
lists the registered names.

Azure needs credentials (`AZURE_DOC_INTELLIGENCE_ENDPOINT`,
`AZURE_DOC_INTELLIGENCE_KEY`) and the optional package. Either piece
missing degrades azure to local before any file is read; each warning
names what is missing. At read time a failed azure attempt retries once
after a 5-second delay, then falls back to local exactly once. Every
step logs a diagnostic naming what happened, so a local-served file is
never silent.

Both backends run their blocking parser work in worker threads, so a
long parse never blocks the MCP event loop.

## Supported file formats

`.pdf` `.docx` `.pptx` `.txt` `.md` `.html` `.csv`

For directories, the server recursively finds all supported files.

The set is the **documents-profile default**. It is profile-scoped, not a
global constant: the `codebase` profile collects the seven above plus
source extensions for the languages the AST extractor maps to tree-sitter
grammars (`.py`, `.ts`, `.go`, and more — see `config/profiles/codebase.yaml`),
so those files reach the AST-aware code chunker. Override per machine with
`INGESTION__INGEST_EXTENSIONS` (comma-separated). Binary files are skipped
under every profile — content-type detection rejects them even when the
extension is admitted.

## Embedding models

Set `EMBED_MODEL` in `.env` to any Ollama embedding model:

| Model                    | Params | Dims  | Context | MTEB | Pull command                       | Notes                                                                    |
| ------------------------ | ------ | ----- | ------- | ---- | ---------------------------------- | ------------------------------------------------------------------------ |
| **qwen3-embedding:0.6b** | ~600M  | 1,024 | 32,768  | —    | `ollama pull qwen3-embedding:0.6b` | **Default** — 100% Hit@1 in experiments, practical ingest times          |
| nomic-embed-text         | 137M   | 768   | 8,192   | 62.4 | `ollama pull nomic-embed-text`     | Fastest query latency (~36ms), but lower retrieval quality (94.1% Hit@1) |
| mxbai-embed-large        | 334M   | 1,024 | 512     | 64.7 | `ollama pull mxbai-embed-large`    | Highest MTEB score for short chunks                                      |
| all-minilm               | 23M    | 384   | 256     | ~58  | `ollama pull all-minilm`           | Blazing fast, tiny footprint                                             |

See [ADR-009](../adr/009-switch-to-qwen3-embedding-0-6b.md) for the full evidence behind the default model choice.

> **llama.cpp provider:** When `EMBED_PROVIDER=local` and `LOCAL_BACKEND=llamacpp`, set `LLAMACPP_EMBED_MODEL` to the GGUF filename instead of `EMBED_MODEL`. The same models are available in GGUF format from HuggingFace. When `EMBED_PROVIDER=cloud` and `CLOUD_BACKEND=openrouter`, set `OPENROUTER_EMBED_MODEL` to a cloud embedding model (e.g., `text-embedding-3-small`). See [Providers](providers.md) for setup.

### How long will ingestion take?

Practical timings on Apple Silicon (M-series) with `qwen3-embedding:0.6b`, default settings (`INGESTION__EMBED_CONCURRENCY=2`, `INGESTION__EMBED_BATCH_SIZE=100`, `CHUNKING__CHUNK_SIZE=512`):

| Scenario                                     | Time        |
| -------------------------------------------- | ----------- |
| 1 PDF (~117 chunks)                          | ~14 seconds |
| 5 PDFs (~585 chunks)                         | ~70 seconds |
| 20 PDFs (~2,340 chunks)                      | ~5 minutes  |
| Full Zotero library (57 PDFs, ~6,600 chunks) | ~13 minutes |

For comparison, the larger `qwen3-embedding:8b` model (4,096-dim vectors) takes ~3 hours for the same Zotero library — the 0.6b model is **13× faster** with identical retrieval quality in our tests.

> **Apple Silicon note:** Ollama serialises `/api/embed` requests internally on Apple Silicon, so `INGESTION__EMBED_CONCURRENCY > 2` yields diminishing returns. Setting it to 2 overlaps network round-trips with embedding computation; beyond that, requests queue up in Ollama's internal pipeline.

File reading is sequential. Tune throughput with `INGESTION__EMBED_BATCH_SIZE` and `INGESTION__EMBED_CONCURRENCY` rather than file-reader worker settings.

Run `uv run omrg benchmark` to measure throughput on your own hardware.

### Switching models

```bash
# 1. Pull the new model
ollama pull mxbai-embed-large

# 2. Update .env
EMBED_MODEL=mxbai-embed-large

# 3. Re-index your documents into a fresh collection
omrg ingest /path/to/docs/
```

> **Why re-index?** The selected vector store locks the vector dimension at collection creation time. Each model produces a different dimension (nomic=768, mxbai=1024, minilm=384). Switching models requires a fresh collection.

## Chunk size guide

Two budgets apply, depending on the source.

### Non-Markdown sources: character budget

`--chunk-size` controls how many **characters** go into each chunk for plain text and other
non-Markdown sources. The embedding model has a **context length** in **tokens**. A rough guide:
~4 characters ≈ 1 token for English.

| Model                | Context (tokens) | Max safe chunk-size | Default 512 safe? |
| -------------------- | ---------------- | ------------------- | ----------------- |
| qwen3-embedding:0.6b | 32,768           | ~130,000 chars      | Yes               |
| nomic-embed-text     | 8,192            | ~32,000 chars       | Yes               |
| mxbai-embed-large    | 512              | ~1,500 chars        | Yes               |
| all-minilm           | 256              | ~1,000 chars        | Yes               |

The default 512-character chunk size is safe for all models. For models with large context windows:

```bash
# 2048-char chunks are fine (2048 × 0.25 = 512 tokens)
omrg ingest /path/to/docs/ --chunk-size 2048
```

### Markdown sources: token budget (default since ADR-063 promotion)

Markdown files (`.md`, or any reader that declares its output as Markdown, such as the PDF
text path) are chunked by the Rust-backed `semantic-text-splitter` using the configured
embedding tokenizer — real token units, not a characters-per-token guess
([ADR-063](../adr/063-model-token-aware-markdown-chunking.md); promoted to the packaged
default after [experiment 25](../../experiments/25-token-chunking-ablation-2026-09-08/results.md)
passed all four frozen gates: retrieval neutral, embedded tokens −2.5%, largest chunk
halved).

| Setting                                 | Default                                    | Meaning                                                                                          |
| --------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `EMBEDDING__TOKENIZER_MODEL`            | `Qwen/Qwen3-Embedding-4B`                  | Tokenizer identity for the budget                                                                |
| `EMBEDDING__TOKENIZER_REVISION`         | `5cf2132abc99cad020ac570b19d031efec650f2b` | Pinned revision; must be in the local Hugging Face cache                                         |
| `CHUNKING__MARKDOWN_CHUNK_SIZE`         | `1024`                                     | Maximum chunk size in tokenizer units                                                            |
| `CHUNKING__MARKDOWN_HEADING_PREPEND`    | `false`                                    | Prepend the heading path to each chunk. When on, the prepended text counts against the token cap |
| `CHUNKING__MARKDOWN_MIN_CHUNK_FRACTION` | `0.0`                                      | Filter chunks below this fraction of the cap (measured in real tokens on this path)              |

The contract, in short:

- The splitter prefers structural boundaries — headings, sections, tables, lists, paragraphs —
  and only then splits smaller. Nothing is emitted over the cap.
- The cap governs the finalised chunk text. A heading prefix that would push a chunk over the
  cap reduces the space for content instead of being dropped or overflowing; a Markdown
  structure that cannot fit at all fails that one file (`status="failed"`), never the batch.
- The tokenizer is a **local cache artefact** and is independent of the embedding inference
  provider: whether embeddings run through Ollama, llama.cpp, or OpenRouter, the budget uses
  the pinned Hugging Face tokenizer, never an inference-server alias.

Cache the tokenizer once (offline thereafter):

```bash
hf download Qwen/Qwen3-Embedding-4B tokenizer.json \
  --revision 5cf2132abc99cad020ac570b19d031efec650f2b
```

If the revision is not cached, ingestion logs a warning naming the failure and falls back to
the legacy character-budgeted splitter for that run. Setting both `EMBEDDING__TOKENIZER_*`
fields empty makes the legacy path permanent (explicit opt-out).

The resolved tokenizer identity and splitter participate in the source index identity, so
changing the identity, revision, or cache availability re-chunks every Markdown source on
the next ingest — by design, so one collection never mixes chunking strategies.

## Progress and interruption

Progress bars appear automatically in TTY terminals (Rich). In non-TTY contexts (pipes, CI) plain text is emitted to stderr. Press Ctrl+C once for graceful shutdown (finishes the current file, skips the rest). Press again to force quit.

## Which model runs when

| Stage                              | Model type                                  | What it does                 | Speed impact            |
| ---------------------------------- | ------------------------------------------- | ---------------------------- | ----------------------- |
| Metadata extraction (local mode)   | Chat/LLM (e.g. qwen3:0.6b)                  | Classifies document category | ~2s per file            |
| Metadata extraction (keyword mode) | None (regex)                                | Pattern matching             | Instant                 |
| Embedding                          | Embedding model (e.g. qwen3-embedding:0.6b) | Converts text to vectors     | ~50–500ms per chunk     |
| Search (rerank)                    | Cross-encoder (ms-marco-MiniLM-L-6-v2)      | Re-scores top results        | ~10–50ms per query pair |

The embedding model and chat/classification model are **separate** — each pulled independently via Ollama.
