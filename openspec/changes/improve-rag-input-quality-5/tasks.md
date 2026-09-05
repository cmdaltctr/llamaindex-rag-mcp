# Tasks: improve-rag-input-quality-5

Implement in stages. Do not promote OCR thresholds, chunk-size defaults, or query-instruction defaults until the corresponding experiment passes.

## 1. Pin baselines and fixtures

- [ ] 1.1 Add representative PDF fixtures for clean single-column text, clean two-column/table content, scanned content, image-based content, and mixed content. Keep fixtures small and licence-safe. Split them into a committed **calibration** set and a disjoint committed **evaluation** set, and record which files belong to which.
- [ ] 1.2 Add baseline assertions for `pdf-inspector` output: `pdf_type`, confidence, `pages_needing_ocr`, page count, emitted Markdown, and current degraded behaviour when OCR may be required.
- [ ] 1.3 Add a Markdown fixture containing headings, paragraphs, a table, and a list. Record current MarkdownNodeParser/SentenceSplitter chunk boundaries and token-size behaviour.
- [ ] 1.4 Add a regression fixture that demonstrates why the current four-characters-per-token small-chunk estimate can disagree with the Qwen tokenizer.
- [ ] 1.5 Add a Qwen retrieval baseline using the current raw query path. Record Evidence Recall@1/@3/@5, MRR/nDCG where available, latency, and representative identifier-heavy queries.
- [ ] 1.6 Freeze the promotion gates **before any candidate is evaluated**, not merely before a default changes. For each of the three experiments, write into its machine-readable plan (per `experiment-validity-gates`) a numeric quality limit, a numeric regression limit on the workload the candidate is most likely to damage, and a numeric latency/cost limit at a stated percentile. Commit them in their own commit so the record shows they preceded the measurements. Do not invent the values here; produce them from the Stage 1 baselines.
- [ ] 1.7 Calibrate the OCR routing gate on the calibration fixtures only. Sweep the confidence threshold and the `pages_needing_ocr` proportion, and report for each candidate gate how many text-based PDFs it would route to OCR and how many OCR-required PDFs it would leave on the fast path. Report routing behaviour only — retrieval quality belongs to the held-out evaluation set in stage 5.
- [ ] 1.8 Define the routing gate's configuration shape before implementation: top-level fields on `EffectiveSettings` beside `pdf_reader` and `liteparse_ocr_enabled`, resolved once at the composition root and injected. Confirm the chosen names do not collide with the retired-variable tripwire in `config/legacy.py`.
- [ ] 1.9 Record the baseline `source_index_identity` payload shape and the current `_INDEX_IDENTITY_SCHEMA` value, so the stage 2/3 identity extension is a visible, reviewable diff rather than an incidental change.

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
- [ ] 2.10 Emit the additive OCR diagnostics `ocr_required`, `ocr_used`, `ocr_backend`, and `pages_needing_ocr` on both PDF branches. Store `pages_needing_ocr` as a store-compatible scalar count, not the list `pdf-inspector` returns — nothing sanitises metadata values before the vector store.
- [ ] 2.11 Add those four keys to `EXCLUDED_EMBED_METADATA_KEYS` in `core/ingestion/source_state.py` — the single central set `stamp_source_lineage` applies on every ingest path. Do not add a second exclusion list in the PDF reader.
- [ ] 2.12 Add tests proving the four keys are absent from `MetadataMode.EMBED` and `MetadataMode.LLM` text, present in stored metadata and in retrieval result rows, and that an operator can tell fast path from OCR fallback from degraded extraction by reading them.
- [ ] 2.13 Extend `build_index_identity` with the OCR routing configuration and the **resolved** OCR capability, passed as explicit keyword arguments alongside `text_format` and `embed_model`. Bump `_INDEX_IDENTITY_SCHEMA` once for the new payload shape. Do not add a second identity mechanism.
- [ ] 2.14 Add a test proving degraded-extraction recovery: a byte-identical PDF indexed while the OCR capability was absent MUST NOT be reported `skipped_unchanged` once the capability resolves, and MUST be re-extracted through the routing seam.

## 3. Add structure-aware model-token Markdown chunking

- [ ] 3.1 Add `semantic-text-splitter` and Hugging Face `tokenizers` as explicit dependencies and record tested dependency floors.
- [ ] 3.2 Add `embedding.tokenizer_model` and `embedding.tokenizer_revision` to the pure settings model and frozen `EmbeddingBlock`; expose them as `EMBEDDING__TOKENIZER_MODEL` and `EMBEDDING__TOKENIZER_REVISION`. Keep them empty/unset until explicitly configured or promoted by evidence.
- [ ] 3.3 Add a cached Hugging Face tokenizer loader keyed by tokenizer identity **and revision**. For the Qwen experiment use `Qwen/Qwen3-Embedding-4B`. Call `no_truncation()` on the resolved tokenizer before it is used as a size calculator: a tokenizer loaded with truncation enabled caps every long count and would silently under-measure chunks.
- [ ] 3.3a Make the loader work from the local Hugging Face cache with no network access, and add a test that resolves offline. Ingestion must not acquire a hidden runtime dependency on a remote hub.
- [ ] 3.4 Add the Rust-backed `MarkdownSplitter` path for structured Markdown when a model-matched tokenizer is configured. Prefer complete headings, paragraphs, tables, lists, and sentences that fit before splitting at smaller boundaries.
- [ ] 3.5 Derive `header_path` on the new path from the source Markdown itself: use the splitter's chunk-offset API to locate each chunk and resolve the enclosing heading chain, then write the path before the recovery hooks run. `ensure_heading_metadata` only copies metadata a parent node already carries, and the Rust splitter emits text with no parent node, so it cannot be the source of heading ancestry here. Keep it in the pipeline as the idempotent guard it already is, and keep optional heading prepend and the other recovery hooks around the new splitter.
- [ ] 3.5a Pass the configured `CHUNKING__CHUNK_OVERLAP` to the splitter as its own overlap in tokenizer units. Validate `chunk_overlap < markdown_chunk_size` at the composition boundary and fail naming both settings, because the splitter rejects an overlap at or above the capacity.
- [ ] 3.5b Enforce the token cap over the chunk text **as finalised for embedding**, prepended heading included. When heading prepend is enabled, reduce the splitter capacity by the token length of the prefix that chunk will receive, so a prepended chunk cannot exceed the budget. Do not define the cap over the complete LlamaIndex embedding payload: retained metadata is added after chunking and is not known when the splitter runs.
- [ ] 3.6 Replace the Markdown small-chunk four-character token estimate with the real configured tokenizer count on the model-token-aware path.
- [ ] 3.7 Keep `CHUNKING__MARKDOWN_CHUNK_SIZE` as the initial token budget. Do not change its packaged default in this stage.
- [ ] 3.8 Keep plain-text, code, config, AST, and other non-Markdown strategies unchanged.
- [ ] 3.9 Add tests proving a table or other complete Markdown unit stays together when it fits, oversized structures split without exceeding the configured Qwen-token budget, and non-Markdown output is unchanged.
- [ ] 3.9a Add a heading-derivation test: nested headings in, correct `header_path` on every emitted chunk out, derived without a parent node.
- [ ] 3.9b Add a heading-prepend-at-the-limit test: a section sized to fill the cap exactly, prepend enabled, and the finalised chunk still within `CHUNKING__MARKDOWN_CHUNK_SIZE` tokenizer units.
- [ ] 3.9c Add an overlap test in tokenizer units, and a rejection test for `chunk_overlap >= markdown_chunk_size` failing at the composition boundary.
- [ ] 3.9d Add a truncation test: a text longer than the tokenizer's truncation limit reports its full token count, proving `no_truncation()` took effect.
- [ ] 3.10 When the configured tokenizer cannot be loaded, do not claim model-token-aware chunking. Preserve the current Markdown splitter path with a clear diagnostic.
- [ ] 3.11 Extend `build_index_identity` with the tokenizer identity and revision and the **resolved** active splitter (model-token-aware or legacy fallback), using the same explicit keyword-argument path as task 2.13 and the same schema bump. The resolved value is required: recording only the configuration would leave a corpus chunked under the fallback matching forever once the tokenizer became loadable.
- [ ] 3.12 Add a test proving degraded-chunking recovery: a byte-identical Markdown source indexed while the tokenizer could not be resolved MUST NOT be reported `skipped_unchanged` once it resolves.

## 4. Add query-only embedding instructions

- [ ] 4.1 Add `embedding.query_instruction` to the pure settings model and frozen `EmbeddingBlock`; expose it as `EMBEDDING__QUERY_INSTRUCTION`. Empty means current raw-query behaviour.
- [ ] 4.2 Add a generic embedding-query preparation seam that produces `Instruct: <instruction>\nQuery: <query>` only when an instruction is configured.
- [ ] 4.3 Apply query preparation immediately before query embedding. Indexed/document embedding text MUST remain unchanged.
- [ ] 4.4 Keep dense retrieval model-agnostic. Do NOT add Qwen/provider/model-substring `if/elif` dispatch in `dense.py`. Preserve the injected embedder/engine-owned cache path; the legacy `Settings.embed_model` fallback in `dense.py` is out of scope for this change and must be left as it is, not removed or extended.
- [ ] 4.4a Confine preparation to the dense branch. `search()` passes the same raw query to the sparse runner and to the reranker, so add a test proving the sparse backend and the cross-encoder receive the raw query, never the instructed one.
- [ ] 4.5 Change query-embedding cache identity to `(prepared_query, embedding_model_name)` so equal raw queries with different instructions cannot collide.
- [ ] 4.6 Add tests for empty-instruction backward compatibility, instructed query formatting, unchanged document embeddings, cache reuse for identical prepared queries, and cache separation when the instruction changes, isolation between engines with the same model name, and cache release on engine close.
- [ ] 4.7 Use the first experiment candidate: `Given a user query, retrieve passages that provide relevant and accurate evidence for answering the query.` Do not make it a packaged default yet.
- [ ] 4.8 Keep `embedding.query_instruction` **out** of `build_index_identity`. Add a test proving that changing it alone leaves the stored index identity unchanged and a byte-identical source still reports `skipped_unchanged`.

## 5. Run isolated and combined evaluations

- [ ] 5.0 Before running any candidate cell, confirm the frozen gates from tasks 1.6 and 1.7 are committed and unchanged. If a gate is missing, stop and produce it — a gate written after the candidate numbers exist is not a gate.
- [ ] 5.1 PDF ablation: compare current `pdf-inspector` output with the routed Paddle candidate on the **held-out evaluation fixtures**, using the gate calibrated in task 1.7. Record reading order, table/structure fidelity, missing content, failure rate, latency, and downstream evidence retrieval.
- [ ] 5.2 Chunking ablation: build comparable indexes from the same canonical Markdown using the current splitter and `semantic-text-splitter` + Qwen tokenizer. Record Evidence Recall@1/@3/@5, Evidence MRR, section/hierarchy Match@1, nDCG, chunk-size distribution, and ingestion time. Record in the runtime manifest the resolved tokenizer identity **and revision**, the proportion of chunks carrying a derived `header_path` on each path, and the worst-case gap between chunk-text tokens and full embedding-payload tokens.
- [ ] 5.3 Query-instruction ablation: hold the index fixed and compare raw Qwen queries with the candidate instruction, including semantic and identifier-heavy technical queries.
- [ ] 5.4 Combined run: compare the full candidate path against the current production-shaped baseline and record both quality and cost/latency.
- [ ] 5.5 Promote only values that pass the frozen gates. If a threshold, chunk size, or instruction does not qualify, leave it opt-in, keep the packaged default unchanged, and commit the negative result alongside the positive ones rather than tuning around the gate or deleting the run.

## 6. Documentation, validation, and decision record

- [ ] 6.1 Update the ingestion/PDF guide with the `pdf-inspector` fast path, OCR fallback rules, optional OCR installation, graceful degradation, and emitted diagnostics.
- [ ] 6.2 Update the chunking/configuration guides with `EMBEDDING__TOKENIZER_MODEL` and `EMBEDDING__TOKENIZER_REVISION`, model-token-aware Markdown behaviour, the token-cap and heading-prepend contract, and the fact that the embedding inference provider is independent from the tokenizer used for token budgeting.
- [ ] 6.3 Document `EMBEDDING__QUERY_INSTRUCTION`, including that it applies to queries only and may change query-vector semantics without requiring document re-ingestion.
- [ ] 6.4 Update `.env.example` with commented examples for the `Qwen/Qwen3-Embedding-4B` tokenizer identity and revision, the OCR routing gate fields, and the evaluated query instruction. Do not add pre-v2 flat aliases.
- [ ] 6.4a Document the re-ingestion consequence: the tokenizer identity, the resolved splitter, and the OCR routing configuration and capability all participate in the index identity, so changing any of them — or merely installing the optional OCR extra — invalidates previously indexed sources, including non-PDF ones. State that the query instruction deliberately does not.
- [ ] 6.5 Run `uv sync` and targeted PDF/chunking/retrieval tests.
- [ ] 6.6 Run `uv run pytest -m "not slow" --cov=omrg --cov-branch` and confirm the existing coverage floors hold.
- [ ] 6.7 Run the dependency-floor job/test after adding the new dependencies.
- [ ] 6.8 Run `openspec validate improve-rag-input-quality-5 --strict` and fix any stale baseline requirement rather than working around the validator.
- [ ] 6.9 After the empirical decisions are confirmed, write an ADR recording the accepted OCR routing gate, tokenizer/chunking choice, query-instruction policy, fallback behaviour, the frozen gates and whether each candidate met them, and any defaults that were actually promoted. Record rejected candidates and their negative results in the same ADR.
