# Design: improve RAG input quality before retrieval

## Context

The current document path already contains the right extension points:

- `integrations/pdf/pdf_inspector.py` exposes `pdf_type`, confidence, `pages_needing_ocr`, page count, and structured Markdown.
- `integrations/pdf/registry.py` and `factory.py` provide reader registration and construction.
- `core/chunking/sentence.py` currently sends Markdown through `MarkdownNodeParser` and `SentenceSplitter`.
- `core/chunking/markdown.py` preserves heading metadata and recovery knobs, but small-chunk sizing still uses a four-characters-per-token estimate.
- `core/retrieval/dense.py` calls `Settings.embed_model.get_query_embedding(query)` and caches query embeddings.
- embedding inference is already provider-selected through `core/providers/embeddings/` and the composition root.

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

```text
                     USER QUERY
                         │
                         ▼
             optional query instruction
                         +
                    original query
                         │
                         ▼
               QUERY EMBEDDING
             Qwen3-Embedding-4B
                         │
                  ┌──────┴──────┐
                  ▼             ▼
                Dense          BM25
                  └──────┬──────┘
                         ▼
                        RRF
                         │
                         ▼
                 retrieval policy
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

This also means filtered and unfiltered retrieval still share a cache entry when their actual query embedding input is identical.

### D7. Defaults and thresholds are empirical decisions

Do not guess:

- a confidence threshold for OCR fallback;
- a percentage of `pages_needing_ocr` that should trigger fallback;
- a replacement for the current Markdown chunk-size default;
- a default Qwen query instruction.

Build red-first fixtures, run the isolated experiments, then promote only values that pass the project's retrieval-quality and latency gates. The initial implementation can expose the new capabilities without changing unvalidated defaults.

## Configuration shape

Keep the new configuration minimal and nested with the existing settings model. Proposed fields:

```text
EMBEDDING__TOKENIZER_MODEL
EMBEDDING__QUERY_INSTRUCTION
```

`EMBEDDING__TOKENIZER_MODEL` identifies the Hugging Face tokenizer repository used for exact chunk token counts. For the current Qwen deployment it is `Qwen/Qwen3-Embedding-4B`.

`EMBEDDING__QUERY_INSTRUCTION` is empty by default until the experiment justifies a production default. It affects query embeddings only.

No new flat compatibility variables are added.

OCR availability is a runtime capability, not a secret or model-choice setting. The heavy OCR stack lives in an optional extra and is resolved at the composition boundary.

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
5. Model tokenizer cannot be loaded: do not claim exact model-token chunking. Use the existing splitter path with a clear diagnostic unless the operator explicitly selected a fail-closed experimental mode later.
6. Query instruction is empty: preserve current query embedding behaviour exactly.

## Evaluation

Keep attribution clean by changing one stage at a time.

### PDF experiment

Use clean text, two-column/table, scanned, image-based, and mixed PDFs. Compare extracted structure, table fidelity, reading order, missing text, latency, and downstream Evidence Recall@K.

### Chunking experiment

Index the same canonical Markdown twice: current MarkdownNodeParser/SentenceSplitter versus `semantic-text-splitter` using the Qwen tokenizer. Compare Evidence Recall@1/@3/@5, Evidence MRR, section/hierarchy match, nDCG, chunk-size distribution, and ingestion time.

### Query instruction experiment

Hold index and retrieval settings fixed. Compare raw query versus the candidate Qwen instruction. The instruction is promoted only if it improves retrieval quality without an unacceptable regression on identifier-heavy or technical queries.

### Combined experiment

After individual stages qualify, evaluate the complete candidate pipeline against the current baseline. Record both quality and latency so an improvement is not hidden behind an impractical ingestion cost.

## External basis

- PaddleOCR/PaddleX documentation: full PaddleOCR-VL document pipelines include document layout/region processing and result assembly, not only OCR model inference.
- `benbrandt/text-splitter`: Rust `MarkdownSplitter` with Hugging Face tokenizer support via the `semantic-text-splitter` Python package.
- Qwen3-Embedding model documentation: retrieval queries support task instructions while retrieval documents are left without an instruction.

These references justify the experiment candidates; repository experiments remain the authority for production defaults.
