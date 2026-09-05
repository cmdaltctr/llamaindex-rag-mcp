# Design: improve RAG input quality before retrieval

## Context

The current document path already contains the right extension points:

- `integrations/pdf/pdf_inspector.py` exposes `pdf_type`, confidence, `pages_needing_ocr`, page count, and structured Markdown.
- `integrations/pdf/registry.py` and `factory.py` provide reader registration and construction.
- `core/chunking/sentence.py` currently sends Markdown through `MarkdownNodeParser` and `SentenceSplitter`.
- `core/chunking/markdown.py` preserves heading metadata and recovery knobs, but small-chunk sizing still uses a four-characters-per-token estimate.
- `core/retrieval/dense.py::_embed_query()` accepts an injected embedder and engine-owned cache. Its legacy fallback still uses `Settings.embed_model`; the new preparation seam must preserve the engine-owned path.
- embedding inference is already provider-selected through `core/providers/embeddings/` and the composition root.
- `core/ingestion/source_state.py` owns both the index-shaping identity (`build_index_identity`) that decides `skipped_unchanged` and the central embedding-text exclusion set (`EXCLUDED_EMBED_METADATA_KEYS`) that `stamp_source_lineage` applies on every ingest path.

The change should use those seams rather than create a second ingestion or retrieval architecture.

## Goals

1. Preserve clean PDF speed while adding document understanding where OCR is genuinely required.
2. Give all structured PDF paths one Markdown contract before chunking.
3. Chunk Markdown on semantic structure while enforcing the embedding model's real token budget.
4. Support Qwen-style query instructions without changing document embedding text.
5. Keep the implementation registry-driven, settings-injected, and easy to benchmark stage by stage.

## Non-goals

- A universal document AST or `CanonicalDocument` hierarchy.
- OCR for every PDF.
- A new embedding model.
- New retrieval/fusion/reranking algorithms.
- Page-level hybrid OCR stitching.
- Model-name branching in retrieval.

## Target flow

### Ingestion

```text
                                      SOURCE
                                         │
                      ┌──────────────────┴─────────────────┐
                      │                                    │
                    PDF                              other formats
                      │                                    │
                      ▼                                    ▼
              pdf-inspector probe                existing readers
                  [Rust / fast]
                      │
            ┌─────────┴─────────┐
            │                   │
       extractable          OCR required
       text-based         scanned/image/mixed/
       PDF                  failed-quality gate
            │                   │
            ▼                   ▼
     pdf-inspector          PaddleOCR-VL
            │              full document pipeline
            │                   │
            └─────────┬─────────┘
                      ▼
              STRUCTURED MARKDOWN
                      │
             metadata + structure
                      │
                      ▼
            semantic-text-splitter
             MarkdownSplitter [Rust]
                      │
                      ▼
        embedding-model HF tokenizer
          Hugging Face Tokenizers [Rust]
                      │
                      ▼
              token-aware chunks
                      │
                      ▼
             DOCUMENT EMBEDDING
             Qwen3-Embedding-4B
                      │
                      ▼
                 vector store
```

### Retrieval

Instruction preparation belongs to the dense branch alone. `search()` hands the
same raw query string to the sparse runner and to the reranker, so an
instruction prefix must never reach either: BM25 would score the instruction's
own tokens, and the cross-encoder would rerank against a prompt rather than the
user's question.

```text
                        USER QUERY [raw]
                               │
              ┌────────────────┴────────────────┐
              │                                 │
        dense branch                      sparse branch
              │                                 │
              ▼                                 │
   optional query instruction                   │
              +                                 │
        original query                          │
              │                                 │
              ▼                                 ▼
      QUERY EMBEDDING                   BM25 / native sparse
     Qwen3-Embedding-4B                  [raw query tokens]
              │                                 │
              └────────────────┬────────────────┘
                               ▼
                              RRF
                               │
                               ▼
                       retrieval policy
                               │
                               ▼
                    reranker [raw query]
                               │
                               ▼
                    grounded-answer stage
```

## Decisions

### D1. `pdf-inspector` supplies the routing evidence and remains the clean-PDF extractor

`pdf-inspector` already distinguishes text-based, scanned, image-based, and mixed PDFs and exposes `pages_needing_ocr`. Re-running a second classifier would duplicate work and add another disagreement point.

A text-based document is not sent to Paddle merely because it is visually sophisticated. `pdf-inspector` already targets reading order, headings, lists, tables, and multi-column layouts without OCR.

The OCR branch is entered only from explicit inspection evidence or a calibrated extraction-quality gate.

### D2. OCR-required PDFs use the full PaddleOCR-VL document pipeline

The fallback uses PaddleOCR/PaddleX as a document parser, not merely the VLM checkpoint as a raw OCR function. The adapter must retain layout/reading-order/table information that can be represented downstream.

For the first implementation, route the whole PDF when OCR is required. Page-level stitching looks attractive but creates difficult ordering, metadata, and boundary rules and is not required to solve the current failure mode.

Paddle is optional and lazy. The composition root owns the runtime availability probe and injects the resolved capability. `config/` remains pure settings data.

If Paddle is unavailable, the system keeps `pdf-inspector`'s existing partial Markdown and marks the degraded result honestly.

### D3. Structured Markdown is the canonical boundary

Both PDF branches emit Markdown suitable for the same chunking path. Preserve headings, paragraphs, tables, lists, figures/captions, and equations where the source parser provides them.

Do not add a new document class hierarchy. The existing LlamaIndex `Document` plus structured Markdown and metadata is sufficient for this change.

Recommended additive diagnostics are deliberately small:

```text
pdf_reader
pdf_type
pdf_confidence
page_count
pages_needing_ocr     (when available)
ocr_required
ocr_used
ocr_backend           (when used)
```

Existing metadata remains authoritative when already present.

### D4. Markdown structure decides boundaries; the embedding tokenizer decides size

`semantic-text-splitter` supplies the structural splitter. Its Markdown splitter should keep the largest meaningful structure that fits the configured budget before recursively using smaller boundaries.

The token budget is measured by the tokenizer that belongs to the embedding model. For the present Qwen deployment:

```text
embedding inference model: Qwen3-Embedding-4B
HF tokenizer identity:     Qwen/Qwen3-Embedding-4B
```

Inference and token counting are separate concerns. Qwen inference may run through Ollama or another provider while the tokenizer is loaded locally through Hugging Face `tokenizers`.

Add an explicit embedding tokenizer-model setting rather than guessing from an inference-server alias. The resolved tokenizer is cached once per tokenizer identity.

When no model-matched tokenizer is configured, preserve the current Markdown splitter path rather than silently pretending an approximate tokenizer is exact. Promotion to a new shipped default belongs after Stage 5 evidence.

Non-Markdown chunking is unchanged.

#### D4.1 Heading paths are derived, not recovered

`MarkdownNodeParser` emits LlamaIndex nodes that already carry `header_path`,
and `SentenceSplitter` children inherit it through `source_node`. That is what
`ensure_heading_metadata` copies. `semantic_text_splitter.MarkdownSplitter`
emits plain strings from raw Markdown: there is no parent node, so there is
nothing for `ensure_heading_metadata` to copy, and it would leave every chunk
without a heading path.

The replacement splitter therefore derives heading ancestry itself. It uses the
splitter's chunk-offset API (`chunk_indices`) to locate each chunk in the
source Markdown, walks the ATX heading chain that encloses that offset, and
writes the resulting path to `header_path` before the recovery hooks run.
`ensure_heading_metadata` stays in the pipeline unchanged as the idempotent
guard it already is; it is not the source of heading ancestry on this path.

#### D4.2 Overlap is the splitter's own overlap

`MarkdownSplitter` accepts an `overlap` argument measured in the same units as
the capacity, so the configured `CHUNKING__CHUNK_OVERLAP` is passed straight
through in tokenizer units. The library rejects an overlap greater than or
equal to the capacity, so the composition boundary validates
`chunk_overlap < markdown_chunk_size` and fails with a named setting rather
than surfacing a library error mid-ingest.

#### D4.3 The cap governs the finalised chunk text

The token cap is the size of the text the chunk carries after
`apply_heading_prepend` has run — not the size of the LlamaIndex embedding
payload, which additionally contains the retained metadata keys
(`file_name`, `header_path`, `category`, `keywords`, `summary`,
`document_title`, `content_type`).

Two consequences follow.

First, heading prepend cannot be applied after a chunk has been filled to the
cap. When `CHUNKING__MARKDOWN_HEADING_PREPEND` is enabled, the splitter is
given a reduced capacity: `markdown_chunk_size` minus the token length of the
prefix that will be prepended to that chunk. A chunk that would otherwise sit
exactly on the cap must still be within the cap once its heading prefix is
attached.

Second, the metadata overhead is measured rather than budgeted. The chunking
experiment records the worst-case token count of the embedding payload against
the chunk-text count, so the headroom between the configured budget and the
embedding model's context limit is visible evidence rather than an assumption.
Folding metadata into the cap is deliberately out of scope: it would couple the
chunker to the extraction pipeline's output, which is not known when the
splitter runs.

#### D4.4 Tokenizer resolution is exact, pinned, and offline-capable

A Hugging Face tokenizer loaded with truncation enabled reports capped token
counts, which would silently under-count every long chunk. The loader calls
`no_truncation()` on the resolved tokenizer before handing it to the splitter,
and a test asserts a known long string counts above any plausible truncation
limit.

The loader resolves an explicit revision and works from the local Hugging Face
cache without network access, so ingestion is reproducible and does not acquire
a hidden runtime dependency on the Hub. The resolved tokenizer identity and
revision are recorded in the experiment runtime manifest alongside the other
index-shaping inputs.

### D5. Query instructions are query-only and configuration-driven

The retrieval document text stored at ingestion remains un-instructed. The query path may prepare:

```text
Instruct: <configured instruction>
Query: <raw query>
```

before calling `get_query_embedding()`.

The first Qwen experiment candidate is:

```text
Given a user query, retrieve passages that provide relevant and accurate evidence for answering the query.
```

The implementation must not test for `qwen`, `qwen3`, provider names, or model substrings inside dense retrieval. A generic embedding-query preparation seam reads injected embedding settings. Empty instruction means current raw-query behaviour.

### D6. Query cache identity uses the actual embedding input

Today the cache identity is conceptually `(raw_query, embedding_model_name)`. With optional preparation, two equal raw queries can intentionally produce different embedding inputs.

The cache therefore keys on:

```text
(prepared_query, embedding_model_name)
```

This changes the key, not cache ownership. Each engine retains its own bounded cache, which is released when that engine closes. Separate engines never share entries, even when model names match.

Filtered and unfiltered retrieval within the same engine still share a cache entry when their actual query embedding input is identical.

### D7. Defaults and thresholds are empirical decisions

Do not guess:

- a confidence threshold for OCR fallback;
- a percentage of `pages_needing_ocr` that should trigger fallback;
- a replacement for the current Markdown chunk-size default;
- a default Qwen query instruction.

Build red-first fixtures, run the isolated experiments, then promote only values that pass the project's retrieval-quality and latency gates. The initial implementation can expose the new capabilities without changing unvalidated defaults.

#### D7.1 Gates are frozen before any candidate is measured

"Do not guess a default" is not the same rule as "do not guess a gate". A gate
written after the candidate numbers are visible is not a gate; it is a
description of the winner. The numeric limits therefore land in the
machine-readable experiment plan required by `experiment-validity-gates`
before the first candidate cell runs, and the commit that records them is the
evidence that they preceded the measurement.

Each experiment freezes three numbers before execution:

- a **quality** limit: the primary evidence-retrieval metric and the minimum
  improvement that counts as a real effect;
- a **regression** limit: the largest acceptable loss on the secondary
  workload the candidate is most likely to damage — identifier-heavy technical
  queries for the query instruction, table and reading-order fidelity for OCR
  routing, small-chunk survival for the splitter;
- a **latency/cost** limit: the largest acceptable increase in ingestion or
  query time at the measured percentile.

This proposal deliberately records no values for those limits. Producing and
freezing them is Stage 1 work and a precondition for Stage 5, not an output of
it.

#### D7.2 OCR routing is calibrated on its own fixture set

The routing gate decides *which* documents reach Paddle. Choosing its threshold
on the same PDFs that later measure whether Paddle helped would fit the
threshold to the evaluation set and report the fit as a win.

The PDF fixtures are therefore split into two disjoint sets, both committed:

- a **calibration set**, used to choose the confidence threshold and the
  `pages_needing_ocr` proportion that select OCR;
- an **evaluation set**, untouched during calibration, used for the Stage 5
  ablation.

Calibration reports classifier behaviour — how many text-based PDFs the gate
would wrongly route to OCR, and how many OCR-required PDFs it would wrongly
leave on the fast path — not downstream retrieval quality. Retrieval quality is
the evaluation set's job.

#### D7.3 The selected gate is injected configuration

Once calibrated, the threshold is not a constant in the routing module. It
follows the shape the existing PDF knobs already use: top-level fields on
`EffectiveSettings` next to `pdf_reader` and `liteparse_ocr_enabled`, resolved
once at the composition root and injected downstream. `config/` never probes
for the OCR stack, no module reads a settings singleton, and the packaged
default keeps the fallback off until Stage 6 promotes it. New names must not
collide with an entry in the retired-variable tripwire.

### D8. New index-shaping inputs join the existing source index identity

`build_index_identity` in `core/ingestion/source_state.py` already hashes every
input that can change stored chunks or vectors, and `is_complete_current_version`
uses that hash to decide `skipped_unchanged`. This change adds four inputs that
change emitted chunks, so all four join that payload. No second identity
mechanism is introduced and `_INDEX_IDENTITY_SCHEMA` is bumped once for the new
payload shape.

The identity is computed **before** the file is read, from settings plus the
values already resolved at the composition boundary (`text_format`,
`embed_model`). The new inputs follow the same rule and arrive as explicit
keyword arguments:

```text
embedding tokenizer identity   configured tokenizer repository + revision
active Markdown splitter       resolved: model-token-aware or legacy fallback
OCR routing configuration      the calibrated gate's settings values
OCR capability                 resolved: fallback available or absent
```

Two of those are *resolved* rather than *configured*, and that distinction is
the point. A configured-but-unresolvable tokenizer runs the legacy splitter; a
configured-but-uninstalled OCR stack runs `pdf-inspector` alone. If identity
recorded only the configuration, a corpus indexed while degraded would keep
matching after the capability arrived, and every one of those files would stay
`skipped_unchanged` forever — with no signal that its chunks came from the path
the operator has since replaced. Recording what actually resolved makes the
capability transition an identity change, and the existing failure-safe
replacement path then re-ingests the affected sources on the next run.

Inclusion is unconditional, matching the doctrine already stated in
`build_index_identity`: parser selectors are hashed even for file types that
cannot use them, because unnecessary reprocessing is safer than reusing stale
vectors. Installing the OCR extra will therefore invalidate non-PDF sources
too. That cost is accepted rather than engineered around; a conditional
identity would have to know which selectors a file will use before the file is
read.

`EMBEDDING__QUERY_INSTRUCTION` is the deliberate exception. It changes query
vectors only, never stored chunk text, so it stays out of the document identity
payload — as §6 of the proposal states, enabling it must not re-ingest a
corpus. Its effect on the query side is carried entirely by the query-embedding
cache key (D6).

### D9. OCR diagnostics are parser telemetry, not embedding text

The four additive OCR keys — `ocr_required`, `ocr_used`, `ocr_backend`,
`pages_needing_ocr` — meet the exclusion test in `embedding-text-composition`
exactly: they are parser telemetry, constant across every chunk of a document,
and carry no signal a user query could match. `"ocr_used: true"` appended to
every chunk of a scanned PDF is noise that shifts the vector without adding
retrievable meaning.

They join `EXCLUDED_EMBED_METADATA_KEYS` in `source_state.py`, the single
central set that `stamp_source_lineage` applies on every ingest path. Nothing
else is needed: exclusion removes them from embedding and LLM-visible text
while leaving them in stored metadata and in retrieval result rows, and that
module-global set is already hashed into the index identity, so extending it
invalidates prior chunks through the existing mechanism rather than a new one.

`pages_needing_ocr` reaches metadata as a scalar count, not the list
`pdf-inspector` returns. Vector-store metadata values are scalars in both
backends, and nothing sanitises them on the way in.

## Configuration shape

Keep the new configuration minimal and nested with the existing settings model. Proposed fields:

```text
EMBEDDING__TOKENIZER_MODEL
EMBEDDING__TOKENIZER_REVISION
EMBEDDING__QUERY_INSTRUCTION
```

`EMBEDDING__TOKENIZER_MODEL` identifies the Hugging Face tokenizer repository used for exact chunk token counts. For the current Qwen deployment it is `Qwen/Qwen3-Embedding-4B`.

`EMBEDDING__TOKENIZER_REVISION` pins the resolved revision so a repository update cannot silently change chunk boundaries. It participates in the index identity (D8) and is recorded in experiment evidence.

`EMBEDDING__QUERY_INSTRUCTION` is empty by default until the experiment justifies a production default. It affects query embeddings only and stays out of the document index identity (D8).

The OCR routing gate adds top-level fields beside the existing `PDF_READER` and `LITEPARSE_OCR_ENABLED` knobs rather than a new block, because that is the shape the PDF settings already have. Their names and calibrated values are Stage 1 output (D7.2, D7.3), so this proposal fixes only their shape:

```text
one enable/mode field  packaged default keeps the fallback off
the calibrated gate    threshold values, no hardcoded constant in the router
```

No new flat compatibility variables are added, and no new name may collide with an entry in the retired-variable tripwire.

OCR availability is a runtime capability, not a secret or model-choice setting. The heavy OCR stack lives in an optional extra and is resolved at the composition boundary. The resolved capability is injected, and it is part of the index identity precisely because it decides which extraction path actually ran (D8).

## Dependencies

### Core chunking

- `semantic-text-splitter`
- `tokenizers`

Both need dependency-floor entries once the implementation experiment selects tested versions.

### Optional OCR

A new optional OCR extra contains the tested PaddleOCR/PaddleX/PaddlePaddle combination. The exact package floors should be recorded from the implementation environment rather than guessed in this proposal.

No new cloud API or API key is required.

## Failure behaviour

1. `pdf-inspector` fails: preserve the existing per-file ingestion error boundary.
2. OCR is required and Paddle is installed: use Paddle and emit structured Markdown.
3. OCR is required and Paddle is absent: keep the partial `pdf-inspector` result, set a clear degraded diagnostic, and continue.
4. Paddle fails for one file: return a structured per-file failure or the explicitly defined safe fallback; never crash the MCP boundary.
5. Model tokenizer cannot be loaded: do not claim exact model-token chunking. Use the existing splitter path with a clear diagnostic unless the operator explicitly selected a fail-closed experimental mode later. The fallback is the *resolved* splitter state, so it enters the index identity and a source indexed under it is re-ingested once the tokenizer resolves (D8).
6. Configured overlap is greater than or equal to the Markdown chunk size: fail at the composition boundary naming both settings, rather than letting the splitter raise part-way through a batch.
7. Query instruction is empty: preserve current query embedding behaviour exactly.

## Evaluation

Keep attribution clean by changing one stage at a time.

Every gate below is a number frozen in the machine-readable plan before the
first candidate cell runs (D7.1). None of them is set in this proposal.

### OCR routing calibration

Run before the PDF experiment and on the disjoint calibration fixtures only
(D7.2). Sweep the confidence threshold and the `pages_needing_ocr` proportion,
and report, for each candidate gate, how many text-based PDFs it routes to OCR
and how many OCR-required PDFs it leaves on the fast path. The output is one
selected gate, expressed in the injected configuration shape of D7.3.

### PDF experiment

Use the evaluation fixtures — clean text, two-column/table, scanned,
image-based, and mixed PDFs — held out of calibration. Compare extracted
structure, table fidelity, reading order, missing text, latency, and downstream
Evidence Recall@K.

### Chunking experiment

Index the same canonical Markdown twice: current MarkdownNodeParser/SentenceSplitter versus `semantic-text-splitter` using the Qwen tokenizer. Compare Evidence Recall@1/@3/@5, Evidence MRR, section/hierarchy match, nDCG, chunk-size distribution, and ingestion time.

Record alongside those metrics, because the chunking contract of D4 depends on
them: the resolved tokenizer identity and revision; the proportion of chunks
carrying a derived `header_path` on each path; and the worst-case gap between
chunk-text tokens and full embedding-payload tokens, which is the measured
headroom D4.3 refuses to budget for.

### Query instruction experiment

Hold index and retrieval settings fixed. Compare raw query versus the candidate Qwen instruction. The instruction is promoted only if it improves retrieval quality without an unacceptable regression on identifier-heavy or technical queries.

### Combined experiment

After individual stages qualify, evaluate the complete candidate pipeline against the current baseline. Record both quality and latency so an improvement is not hidden behind an impractical ingestion cost.

## External basis

- PaddleOCR/PaddleX documentation: full PaddleOCR-VL document pipelines include document layout/region processing and result assembly, not only OCR model inference.
- `benbrandt/text-splitter`: Rust `MarkdownSplitter` with Hugging Face tokenizer support via the `semantic-text-splitter` Python package. Its documentation states that a tokenizer with truncation enabled caps the measured chunk size, and its `overlap` argument must be strictly less than the capacity — the two constraints behind D4.2 and D4.4.
- Qwen3-Embedding model documentation: retrieval queries support task instructions while retrieval documents are left without an instruction.

These references justify the experiment candidates; repository experiments remain the authority for production defaults.
