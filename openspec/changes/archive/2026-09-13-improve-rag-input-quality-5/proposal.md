# Improve RAG input quality before retrieval

## Why

The current retrieval stack can only rank the evidence that ingestion gives it. Three input-quality gaps remain before dense retrieval, BM25, RRF, reranking, or grounded answer synthesis can help.

First, `pdf-inspector` is the current fast structured-PDF path and **does not perform OCR**. It already classifies PDFs as text-based, scanned, image-based, or mixed, exposes confidence and `pages_needing_ocr`, and emits structured Markdown for extractable PDFs. Today, when it identifies a PDF that may need OCR, the adapter logs that the Markdown may be partial and continues. There is no intelligent OCR fallback.

Second, Markdown ultimately passes through LlamaIndex's `MarkdownNodeParser` plus `SentenceSplitter`. This preserves useful heading boundaries, but size enforcement is still sentence-splitter driven. The Markdown recovery path also still contains a four-characters-per-token estimate. That is weaker than using the tokenizer that the embedding model will actually use, especially for tables, lists, multilingual text, symbols, and model-specific tokenisation.

Third, the dense query path currently sends the raw query directly to `get_query_embedding()`. Qwen3-Embedding recommends an instruction on the **query** while leaving retrieval documents un-instructed. The current code has no model-agnostic query-preparation seam for that asymmetry.

The purpose of this change is therefore not to add another retrieval algorithm. It is to improve the evidence before retrieval sees it:

```text
PDF understanding -> structured Markdown -> structure-aware chunks
-> model-matched token budgeting -> document embeddings

User query -> optional query-only instruction -> query embedding  (dense branch)
User query -> raw query                                            (BM25 and reranker)
```

The existing Qwen3-Embedding-4B model, vector store, dense retrieval, BM25, RRF, reranking policy, and grounded-answer work remain separate concerns.

## What Changes

### 1. Keep `pdf-inspector` as the fast PDF front door

For the normal PDF path, `pdf-inspector` remains the cheap Rust-based classifier and extractor. A clean text-based PDF, including a well-formed multi-column academic PDF or a PDF containing ordinary tables, stays on this fast path.

The system SHALL NOT equate "complex layout" with "needs OCR". OCR is selected only when the inspection result says visual/OCR understanding is materially required, such as scanned, image-based, or mixed content, significant `pages_needing_ocr`, or a separately calibrated extraction-quality failure.

### 2. Add PaddleOCR-VL through an isolated local worker

When the fast path determines that OCR is required and the worker capability is available, route the **whole PDF** through the full PaddleOCR-VL document pipeline. The pipeline includes layout analysis, region handling, reading order, recognition, and result assembly. It does not reduce PaddleOCR to a bare image-to-text model call.

PaddleOCR runs in a separate local Python environment owned by the worker. That environment has its own lockfile and declares Python `>=3.11,<3.14`. PaddleOCR, PaddleX, PaddlePaddle, and accelerator packages SHALL NOT enter OMRG's main environment, main lockfile, or import graph. OMRG contains only the worker client, lifecycle control, routing, and protocol contracts.

The OCR process is lazy and long-lived. It starts only after routing selects an OCR-required PDF, loads its model inside the isolated process, and remains available for later OCR requests. A clean PDF never starts the worker. Normal owner shutdown closes the process. A crash or timeout discards the process handle; a later eligible file may start a fresh process, but the failed request is not replayed automatically.

OMRG and the worker communicate through UTF-8 JSON Lines over standard input and standard output. Each request is exactly one JSON object on one line. A healthy worker returns exactly one terminal response object on one line for each accepted request. Standard output is reserved for protocol messages. Worker diagnostics and logs go only to standard error.

The composition boundary resolves a capability fingerprint without loading the OCR model. The fingerprint records worker availability, protocol version, package versions, document-pipeline identity, model identity, and output-schema version. A metadata-only probe must not start the long-lived worker or import model code.

If the worker is unavailable before dispatch, preserve today's useful degraded behaviour: retain the `pdf-inspector` output, surface an explicit diagnostic that OCR was required but unavailable, and do not fabricate missing content. Once OMRG dispatches an OCR request, a worker crash, timeout, or protocol failure produces a structured per-file ingestion error. That failed source is not marked current, and the existing failure-safe replacement path preserves any prior current version.

### 3. Converge both PDF paths on structured Markdown

Both the `pdf-inspector` fast path and a successful PaddleOCR worker response SHALL converge on the same downstream contract: structured Markdown plus honest metadata.

The Markdown should preserve useful document structure when available:

```text
heading
paragraph
table
list
figure/caption
equation
```

Existing provenance and reader metadata must remain available. OCR-specific diagnostics may be added, but this change does **not** introduce a new `CanonicalDocument` class or a parallel document hierarchy. Structured Markdown is the canonical interoperability boundary for this change.

### 4. Use `semantic-text-splitter` for model-token-aware Markdown chunking

Add the Rust-backed `semantic-text-splitter` Markdown splitter for the structured Markdown path. It should prefer complete structural boundaries such as headings, paragraphs, tables, lists, and sentences while respecting the configured token budget.

Token counting SHALL use a Hugging Face tokenizer matching the embedding model, not a generic tokenizer and not a four-characters-per-token estimate. For the current Qwen3-Embedding-4B deployment, the intended tokenizer identity is:

```text
Qwen/Qwen3-Embedding-4B
```

The tokenizer is loaded through Hugging Face `tokenizers` and cached. Embedding inference may still run through Ollama, llama.cpp, OpenRouter, or another configured provider; the chunker must not depend on a live inference server merely to count tokens.

The tokenizer identity is explicit configuration owned by embedding settings. Do not guess an HF repository from an Ollama alias and do not add model-name `if/elif` dispatch.

Non-Markdown paths, including code and configuration chunking, remain unchanged.

The existing `CHUNKING__MARKDOWN_CHUNK_SIZE` remains the initial budget. This proposal does not promote a new chunk-size default without an experiment.

### 5. Keep index identity and embedding text honest about the new inputs

The additions above change the chunk text that gets stored, so they belong in the existing `source_index_identity` that decides whether a source is `skipped_unchanged`. The identity SHALL gain the embedding-tokenizer identity and revision, the resolved active Markdown splitter, the OCR routing configuration, and the resolved worker capability fingerprint. It stays one identity: no parallel mechanism and no second change-detection path.

The worker fingerprint SHALL include availability, protocol version, exact worker package versions, document-pipeline identity, model identity, and output-schema version. These values are available before model loading. A stable unavailable value represents a missing, invalid, protocol-incompatible, or output-schema-incompatible worker. Transient process data, including process identifiers and timestamps, stays out of the fingerprint.

The resolved values matter as much as the configured ones. A source indexed while the tokenizer could not load, or while the OCR worker was unavailable, must not stay `skipped_unchanged` after that capability arrives. Changes to the worker protocol, packages, pipeline, model, or output schema must also produce a new identity because any of them can change emitted Markdown.

The new OCR diagnostics are additive metadata, and they are parser telemetry: constant across every chunk of a document, carrying nothing a user query could match. `ocr_required`, `ocr_used`, `ocr_backend`, and `pages_needing_ocr` SHALL join the centrally owned embedding-text exclusion set, so they stay out of embedding vectors and LLM-visible text while remaining in stored metadata and retrieval results.

### 6. Add optional query-only embedding instructions

Add an embedding-query preparation seam that can prepend an instruction to **queries only**. Indexed document text remains unchanged.

For Qwen3-Embedding-4B, the first candidate to evaluate is:

```text
Instruct: Given a user query, retrieve passages that provide relevant and accurate evidence for answering the query.
Query: <original user query>
```

The exact wording is an experimental candidate, not an unmeasured permanent default. The baseline is the current raw query.

Retrieval code SHALL remain model-agnostic. In particular, do not add code such as:

```python
if "qwen3" in model_name:
    ...
```

Query/document asymmetry is driven by injected embedding configuration or its adapter seam. The prepared query is what is embedded and what participates in query-embedding cache identity. Changing an instruction must not return a vector cached for another instruction.

Because Qwen retrieval documents remain un-instructed, enabling only the query instruction does not require re-ingesting stored documents.

## Implementation Stages

### Stage 1 — Pin baselines and quality gates

Create representative clean, multi-column/table, scanned, image-based, and mixed PDF fixtures, split into a **calibration** set and a disjoint **evaluation** set. Record current `pdf-inspector` classification, confidence, `pages_needing_ocr`, emitted Markdown, chunk behaviour, retrieval evidence metrics, and latency. Add a raw-query Qwen retrieval baseline before introducing instructions.

This stage also freezes the promotion gates. Each experiment's quality, regression, and latency limits are written into its machine-readable plan and committed **before** any candidate is measured, because a limit chosen after the numbers are visible describes the winner rather than gating it. This proposal records no values for those limits; producing and freezing them is Stage 1 work and a precondition for Stage 5.

The OCR routing threshold is calibrated in its own step, on the calibration fixtures only. Calibrating on the same PDFs that later measure whether OCR helped would fit the threshold to the evaluation set and report the fit as a gain.

OCR routing thresholds, a new Markdown chunk-size default, and a default Qwen instruction SHALL NOT be guessed.

### Stage 2 — PDF routing and isolated PaddleOCR worker

Keep `pdf-inspector` as the classifier/extractor for the fast path. Add an OMRG-side worker client and a small routing seam that sends OCR-required PDFs to the full Paddle document pipeline when available. The worker uses its own locked Python environment and communicates through the versioned JSON Lines protocol. Both successful branches return structured Markdown and compatible metadata. An unavailable worker degrades to the existing `pdf-inspector` result with a clear diagnostic.

Start the long-lived process only on the first OCR dispatch, then reuse it. Keep standard output protocol-only, drain logs from standard error, and close the process with its owner. Treat a post-dispatch crash, timeout, malformed response, or worker error as a structured per-file failure. Do not mark that source current.

Do not implement page-level stitching in this stage. Whole-document Paddle processing is simpler and avoids corrupting reading order at merge boundaries.

### Stage 3 — Structure-aware, model-token-aware Markdown chunking

Introduce `semantic-text-splitter` and Hugging Face `tokenizers`. Add explicit embedding-tokenizer identity and revision to injected settings. When the model-matched tokenizer is configured, structured Markdown uses `MarkdownSplitter` with the real tokenizer budget, truncation disabled, the configured overlap in tokenizer units, and heading paths derived from the source Markdown. Preserve current heading metadata and recovery behaviour, but replace the Markdown four-character token approximation with actual token counts. Other chunking strategies are unchanged.

### Stage 4 — Query-only Qwen instruction support

Add an optional query instruction in embedding settings and apply it immediately before query embedding. Documents remain untouched, and so do the sparse and reranking branches: `search()` hands the same raw query string to the sparse runner and to the cross-encoder, so an instruction prefix reaching either would have BM25 score the instruction's own tokens and the reranker rank against a prompt. Keep `dense.py` free from Qwen-specific dispatch, and make the query-embedding cache key reflect the prepared query plus embedding model identity.

Evaluate raw queries against the candidate Qwen instruction before promoting any default.

### Stage 5 — Evaluate the complete input-quality path

Run separate ablations so improvements are attributable:

1. `pdf-inspector` only vs the routed isolated-worker candidate on OCR-required PDFs.
2. Current Markdown splitter vs `semantic-text-splitter` with the Qwen tokenizer.
3. Raw Qwen queries vs query-instructed Qwen queries.
4. The combined candidate pipeline vs the current baseline.

Measure parsing/structure fidelity, evidence-level retrieval quality, latency, failures, and resource cost. A gain must not be attributed to retrieval knobs when it came from input preparation.

### Stage 6 — Promote only proven behaviour

Only after the experiments pass their gates should a threshold, query instruction, or other default change be proposed as production behaviour. Document the accepted configuration, update `.env.example` and guides, run strict OpenSpec validation and the required test/coverage suites, and record the confirmed decision in an ADR.

## Capabilities

### New Capabilities

- `query-embedding-preparation`: optional query-only embedding instructions with document/query asymmetry and model-agnostic configuration.

### Modified Capabilities

- `pdf-reader`: add `pdf-inspector`-driven routing to an isolated PaddleOCR-VL worker while preserving the fast text-based path and pre-dispatch graceful degradation.
- `markdown-aware-chunking`: add Rust structure-aware Markdown splitting using the configured embedding-model tokenizer and remove approximate Markdown token counting where the real tokenizer is available.
- `query-embedding-cache`: cache the actual prepared query embedding input, not a raw query that may hide different instructions.
- `async-ingestion`: extend `source_index_identity` with the tokenizer identity, resolved active splitter, OCR routing configuration, and resolved worker capability fingerprint. The fingerprint covers availability, protocol, packages, pipeline, model, and output schema, so degraded or changed ingestion does not stay `skipped_unchanged`.
- `embedding-text-composition`: add the new OCR diagnostics to the centrally owned embedding-text exclusion set.

## Out of Scope

- Replacing Qwen3-Embedding-4B.
- OCRing every PDF.
- Treating every multi-column or table-heavy PDF as an OCR document.
- Page-by-page merging between `pdf-inspector` and PaddleOCR.
- Multimodal image/table embeddings.
- A new canonical document object model.
- Changes to BM25, RRF, reranking thresholds, authority resolution, or grounded-answer semantics.
- Profile-specific query instructions unless the experiment demonstrates that they are required.
- Changing `CHUNKING__MARKDOWN_CHUNK_SIZE` without evidence.

## Impact

- **Quality:** fixes information loss before retrieval, where later ranking stages cannot reconstruct damaged reading order, tables, or omitted scanned content.
- **Performance:** clean PDFs remain on the fast `pdf-inspector` path and never start the OCR worker. Only OCR-required PDFs pay process-start and model costs. The process then stays alive for later OCR requests. Rust-backed Markdown splitting and tokenisation keep the CPU-side preparation path efficient.
- **Dependencies:** `semantic-text-splitter` and Hugging Face `tokenizers` are proposed as OMRG chunking dependencies. PaddleOCR, PaddleX, PaddlePaddle, and accelerator packages exist only in the worker-owned lockfile and isolated Python `>=3.11,<3.14` environment. OMRG's main environment contains no Paddle package or import.
- **Storage:** OCR or chunking changes alter chunk text or boundaries and therefore require re-ingestion to affect existing documents. Because the new inputs join `source_index_identity`, re-ingestion is triggered on the next run rather than requiring a manual rebuild. This includes worker availability and any protocol, package, pipeline, model, or output-schema change. Inclusion remains unconditional, so provisioning or changing the OCR worker also invalidates non-PDF sources. Query-instruction-only changes do not require re-ingestion.
- **Compatibility:** explicit non-`pdf_inspector` readers remain explicit overrides. Non-Markdown and code chunking remain unchanged. Existing public retrieval and transport contracts remain unchanged.
- **Architecture:** settings stay injected, metadata-only capability probing stays at the composition boundary, and registries remain the dispatch mechanism. The JSON Lines worker boundary keeps Paddle code outside OMRG. No `core/ingestion` ↔ `core/retrieval` import is introduced.
