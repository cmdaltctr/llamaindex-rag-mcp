# Audit findings that motivate this change

**Audit target:** `v3` production code and active calibration harnesses as inspected before this change.  
**Purpose:** preserve the concrete defect list so implementation does not drift into a generic refactor.

> Stage 0 SHALL turn each confirmed item into an executable regression before fixing production code. This document records the audit observation, not a completed test result.

| ID | Severity | Area | Confirmed observation | Why it matters | Stage |
|---|---|---|---|---|---|
| A01 | P0 | Code chunking | `chunk_code_file_async()` supplies `chunk_size=` / `chunk_overlap=` to LlamaIndex CodeSplitter, while LlamaIndex v0.14.5 CodeSplitter accepts `chunk_lines`, `chunk_lines_overlap`, `max_chars`; broad exception handling falls back to SentenceSplitter | AST-aware code chunking can appear green while never running | 0/1 |
| A02 | P0 | Code chunking tests | existing success test asserts nodes/content_type, not that CodeSplitter actually executed | fallback masks the regression | 0/1 |
| A03 | P1 | Hybrid filtering | dense branch receives `metadata_filter`; BM25 branch currently does not | RRF can re-introduce forbidden rows | 0/2 |
| A04 | P1 | BM25 cache | process-wide cache keyed by `collection_name` only | same collection name across stores can reuse wrong rows at equal generation | 0/2 |
| A05 | P1 | Dense store abstraction | core dense layer converts generic `distance` with a Chroma-shaped `1/(1+d)` transform while ABC does not define metric semantics | interface swappability is not semantic swappability | 0/2 |
| A06 | P1 | Threshold maths | RRF fused score is assigned to `score`; final `similarity_threshold` is then applied to it in non-reranked hybrid mode | dense and RRF score scales are incomparable (`2/61 ~= 0.0328` for rank 1 in both at k=60) | 0/2 |
| A07 | P1 | Generation ownership | VectorStore contract says mutations own generation, but writer also bumps; Lance methods already bump some mutations while Chroma relies more on caller | backend behaviour is asymmetric and may double-bump | 0/2 |
| A08 | P1 | Metadata units | metadata path slices `text[: max_chunks * chunk_size]` even though chunk_size is token-oriented | `max_chunks` can cap much earlier than intended | 0/1 |
| A09 | P2 | Metadata semantics | LlamaIndex temporary per-chunk enrichments are aggregated to one file metadata dict then copied to final chunks | docs/experiments must not assume persisted per-chunk LLM metadata | 1/7 |
| A10 | P1 | Ingestion memory | directory ingest accumulates all emitted nodes in `all_nodes` before one final embed/write | peak memory grows with corpus and failures occur late | 0/3 |
| A11 | P1 | Ingestion durability | old chunks are deleted before replacement parse/embed/write succeeds | a failed update can remove the last good searchable version | 0/3 |
| A12 | P1 | Ingestion concurrency | global write lock encloses embedding + store write; embed semaphore is inside the lock | configured concurrency does not imply concurrent file-level embedding | 0/3/6 |
| A13 | P1 | Re-ingestion | current production path still reprocesses unchanged files; archived change-detection tasks were not reflected in inspected code | wastes local embedding compute and increases failure exposure | 3 |
| A14 | P0 | Experiment 10b | protocol declares dense+hybrid, rerank-off controls and hybrid primary contrasts; current runner only sweeps dense/rerank-on fetch_k | runner cannot answer its stated H1/H2/H3 | 0/4/8 |
| A15 | P0 | Experiment 13 | current runner calls `search(..., rerank=True)` while threshold policy is only consulted when rerank is `None` | manipulated threshold has zero causal effect on rerank decision | 0/4/9 |
| A16 | P1 | Experiment 13 | one RNG advances while constructing different threshold/fraction samples | thresholds are confounded with changing query membership | 0/4/9 |
| A17 | P0 | Experiment 14 | preparation exports Qasper `full_text.paragraphs` to `.md`; builder reads those Markdown files directly and merely sets `PDF_READER` | pypdf/LiteParse never parse the treatment corpus | 0/4/10 |
| A18 | P1 | Experiment observability | runners record intended configuration but not a complete effective backend/device/provider/parser manifest | silent fallback can invalidate latency/quality labels | 4/5 |
| A19 | Boundary | Embedding provider | provider registry is real, but query embedding and store-mediated embedding use process-global LlamaIndex `Settings.embed_model` | current system is deployment-swappable, not safely concurrent per-collection provider-swappable | 2 |
| A20 | Evidence | Apple acceleration | prior bounded evidence showed Torch MPS can be much faster than ONNX CPU while Torch CPU/MPS rankings matched; ONNX-int8/Torch-fp32 differences remain backend/precision differences | device, backend and precision must be separated as factors | 5 |

## Non-findings / things not to rewrite gratuitously

The audit did **not** identify a reason to discard the whole RAG design:

- BM25 Okapi scoring/fallback formula is structurally reasonable for its current role; state/filtering are the bigger defects.
- RRF formula itself is correct; the error is treating its numeric scale as dense similarity later.
- reranker single-sigmoid handling is deliberate, including Torch `Identity()` to avoid SentenceTransformers' default activation being applied twice.
- `fetch_k` override implementation genuinely bypasses the production formula and is suitable for a repaired sweep once the runner design matches the protocol.
- registry/composition-root architecture is real enough to harden incrementally rather than rewrite wholesale.

## Audit acceptance rule

A finding leaves this list only when its Stage 0 regression exists and the later-stage fix makes that regression pass. Documentation-only closure is not sufficient for A01-A18.
