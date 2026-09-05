# Tasks: improve-rag-input-quality-5

Implement in stages. Do not promote OCR thresholds, chunk-size defaults, or query-instruction defaults until the corresponding experiment passes.

## 1. Pin baselines and fixtures

- [ ] 1.1 Add representative PDF fixtures for clean single-column text, clean two-column/table content, scanned content, image-based content, and mixed content. Keep fixtures small and licence-safe.
- [ ] 1.2 Add baseline assertions for `pdf-inspector` output: `pdf_type`, confidence, `pages_needing_ocr`, page count, emitted Markdown, and current degraded behaviour when OCR may be required.
- [ ] 1.3 Add a Markdown fixture containing headings, paragraphs, a table, and a list. Record current MarkdownNodeParser/SentenceSplitter chunk boundaries and token-size behaviour.
- [ ] 1.4 Add a regression fixture that demonstrates why the current four-characters-per-token small-chunk estimate can disagree with the Qwen tokenizer.
- [ ] 1.5 Add a Qwen retrieval baseline using the current raw query path. Record Evidence Recall@1/@3/@5, MRR/nDCG where available, latency, and representative identifier-heavy queries.
- [ ] 1.6 Write the experiment promotion gates before changing any production default.

## 2. Add PDF routing and PaddleOCR fallback

- [ ] 2.1 Add an optional OCR dependency group for the tested PaddleOCR/PaddleX/PaddlePaddle stack. Keep all heavy imports lazy and add dependency-floor coverage for the selected versions.
- [ ] 2.2 Add a PaddleOCR-VL PDF adapter under `integrations/pdf/`. Use the full document pipeline and emit structured Markdown plus honest reader/OCR metadata.
- [ ] 2.3 Add the smallest routing seam around the existing `pdf-inspector` result. Clean extractable text-based PDFs MUST stay on `pdf-inspector`; scanned/image-based/mixed or otherwise qualified OCR-required PDFs use Paddle when available.
- [ ] 2.4 Route the whole PDF through Paddle in the OCR branch. Do NOT add page-level `pdf-inspector`/Paddle stitching in this change.
- [ ] 2.5 Keep multi-column or table-heavy **text-based** PDFs on `pdf-inspector` when its inspection/extraction quality is acceptable. Layout complexity alone MUST NOT select OCR.
- [ ] 2.6 Resolve OCR capability availability at the composition boundary and inject the result. Do not probe optional dependencies from `config/` or introduce a settings singleton.
- [ ] 2.7 When OCR is required but the optional OCR stack is absent, preserve `pdf-inspector`'s partial Markdown, mark the result as degraded, and emit an actionable diagnostic rather than fabricating content or failing the whole batch.
- [ ] 2.8 Add tests proving the clean path never invokes Paddle, the OCR path does invoke Paddle when available, and the unavailable path degrades deterministically.
- [ ] 2.9 Preserve the existing per-file reader error boundary so a Paddle failure cannot raise through an MCP handler or stop subsequent files in the ingestion batch.

## 3. Add structure-aware model-token Markdown chunking

- [ ] 3.1 Add `semantic-text-splitter` and Hugging Face `tokenizers` as explicit dependencies and record tested dependency floors.
- [ ] 3.2 Add `embedding.tokenizer_model` to the pure settings model and frozen `EmbeddingBlock`; expose it as `EMBEDDING__TOKENIZER_MODEL`. Keep it empty/unset until explicitly configured or promoted by evidence.
- [ ] 3.3 Add a cached Hugging Face tokenizer loader keyed by tokenizer identity. For the Qwen experiment use `Qwen/Qwen3-Embedding-4B`.
- [ ] 3.4 Add the Rust-backed `MarkdownSplitter` path for structured Markdown when a model-matched tokenizer is configured. Prefer complete headings, paragraphs, tables, lists, and sentences that fit before splitting at smaller boundaries.
- [ ] 3.5 Preserve current Markdown heading metadata propagation, optional heading prepend, and other supported recovery hooks around the new splitter.
- [ ] 3.6 Replace the Markdown small-chunk four-character token estimate with the real configured tokenizer count on the model-token-aware path.
- [ ] 3.7 Keep `CHUNKING__MARKDOWN_CHUNK_SIZE` as the initial token budget. Do not change its packaged default in this stage.
- [ ] 3.8 Keep plain-text, code, config, AST, and other non-Markdown strategies unchanged.
- [ ] 3.9 Add tests proving a table or other complete Markdown unit stays together when it fits, oversized structures split without exceeding the configured Qwen-token budget, and non-Markdown output is unchanged.
- [ ] 3.10 When the configured tokenizer cannot be loaded, do not claim model-token-aware chunking. Preserve the current Markdown splitter path with a clear diagnostic.

## 4. Add query-only embedding instructions

- [ ] 4.1 Add `embedding.query_instruction` to the pure settings model and frozen `EmbeddingBlock`; expose it as `EMBEDDING__QUERY_INSTRUCTION`. Empty means current raw-query behaviour.
- [ ] 4.2 Add a generic embedding-query preparation seam that produces `Instruct: <instruction>\nQuery: <query>` only when an instruction is configured.
- [ ] 4.3 Apply query preparation immediately before query embedding. Indexed/document embedding text MUST remain unchanged.
- [ ] 4.4 Keep dense retrieval model-agnostic. Do NOT add Qwen/provider/model-substring `if/elif` dispatch in `dense.py`.
- [ ] 4.5 Change query-embedding cache identity to `(prepared_query, embedding_model_name)` so equal raw queries with different instructions cannot collide.
- [ ] 4.6 Add tests for empty-instruction backward compatibility, instructed query formatting, unchanged document embeddings, cache reuse for identical prepared queries, and cache separation when the instruction changes.
- [ ] 4.7 Use the first experiment candidate: `Given a user query, retrieve passages that provide relevant and accurate evidence for answering the query.` Do not make it a packaged default yet.

## 5. Run isolated and combined evaluations

- [ ] 5.1 PDF ablation: compare current `pdf-inspector` output with the routed Paddle candidate on OCR-required fixtures. Record reading order, table/structure fidelity, missing content, failure rate, latency, and downstream evidence retrieval.
- [ ] 5.2 Chunking ablation: build comparable indexes from the same canonical Markdown using the current splitter and `semantic-text-splitter` + Qwen tokenizer. Record Evidence Recall@1/@3/@5, Evidence MRR, section/hierarchy Match@1, nDCG, chunk-size distribution, and ingestion time.
- [ ] 5.3 Query-instruction ablation: hold the index fixed and compare raw Qwen queries with the candidate instruction, including semantic and identifier-heavy technical queries.
- [ ] 5.4 Combined run: compare the full candidate path against the current production-shaped baseline and record both quality and cost/latency.
- [ ] 5.5 Promote only values that pass the predeclared gates. If a threshold, chunk size, or instruction does not qualify, leave it opt-in and record the negative result rather than tuning around the gate.

## 6. Documentation, validation, and decision record

- [ ] 6.1 Update the ingestion/PDF guide with the `pdf-inspector` fast path, OCR fallback rules, optional OCR installation, graceful degradation, and emitted diagnostics.
- [ ] 6.2 Update the chunking/configuration guides with `EMBEDDING__TOKENIZER_MODEL`, model-token-aware Markdown behaviour, and the fact that the embedding inference provider is independent from the tokenizer used for token budgeting.
- [ ] 6.3 Document `EMBEDDING__QUERY_INSTRUCTION`, including that it applies to queries only and may change query-vector semantics without requiring document re-ingestion.
- [ ] 6.4 Update `.env.example` with commented examples for `Qwen/Qwen3-Embedding-4B` tokenizer identity and the evaluated query instruction. Do not add pre-v2 flat aliases.
- [ ] 6.5 Run `uv sync` and targeted PDF/chunking/retrieval tests.
- [ ] 6.6 Run `uv run pytest -m "not slow" --cov=omrg` and confirm the existing coverage floors hold.
- [ ] 6.7 Run the dependency-floor job/test after adding the new dependencies.
- [ ] 6.8 Run `openspec validate improve-rag-input-quality-5 --strict` and fix any stale baseline requirement rather than working around the validator.
- [ ] 6.9 After the empirical decisions are confirmed, write an ADR recording the accepted OCR routing gate, tokenizer/chunking choice, query-instruction policy, fallback behaviour, and any defaults that were actually promoted.
