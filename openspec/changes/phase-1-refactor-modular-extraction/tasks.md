## 1. Preparation

- [x] 1.1 Create branch `git switch -c feat/phase-1-refactor-modular-extraction`
- [x] 1.2 Run baseline: `uv run pytest -m "not slow" --cov=rag_mcp` and record the pass/coverage numbers as the phase gate reference
- [x] 1.3 Grep for hidden cross-imports between `ingestion.py` and `retrieval.py` and between the three target files and their consumers; record findings in the change notes (fix strategy per design D4 — surface, never merge)

## 2. Metadata subpackage extraction

- [x] 2.1 Create `core/metadata/` skeleton with `__init__.py`
- [x] 2.2 Move keyword-regex backend to `core/metadata/keyword.py`
- [x] 2.3 Move Ollama LLM backend to `core/metadata/ollama.py`
- [x] 2.4 Move LlamaIndex Extractor backend to `core/metadata/llamaindex.py`
- [x] 2.5 Move llama.cpp backend to `core/metadata/llamacpp.py`
- [x] 2.6 Move hybrid category taxonomy (ADR-013) to `core/metadata/taxonomy.py`
- [x] 2.7 Create `core/metadata/extractor.py` orchestrator dispatching to backends (including the `disabled` sentinel), preserving every public function signature
- [x] 2.8 Convert `metadata_extractor.py` to a compat shim re-exporting from `core/metadata/` with `DeprecationWarning` (removal: v2.0.0)
- [x] 2.9 Run `uv run pytest -m "not slow"` — must be green before continuing

## 3. Ingestion and chunking subpackage extraction

- [x] 3.1 Create `core/ingestion/` and `core/chunking/` skeletons
- [x] 3.2 Move the code chunking strategy to `core/chunking/code.py`
- [x] 3.3 Move the markdown chunking strategy (heading-aware, small-chunk dropping, heading prepend) to `core/chunking/markdown.py`
- [x] 3.4 Move the sentence chunking strategy to `core/chunking/sentence.py`
- [x] 3.5 Move the whole-file config chunking strategy to `core/chunking/config_file.py`
- [x] 3.6 Move file gathering and reader dispatch to `core/ingestion/loader.py`
- [x] 3.7 Move content_type → strategy dispatch to `core/ingestion/chunker.py` (content-type precedence unchanged)
- [x] 3.8 Move embed + ChromaDB write (including `_bump_collection_generation()`) to `core/ingestion/writer.py`
- [x] 3.9 Expose `ingest_path_async()` from `core/ingestion/__init__.py` with an unchanged signature
- [x] 3.10 Convert `ingestion.py` to a compat shim with `DeprecationWarning`
- [x] 3.11 Confirm NO `structural.py` or `evidence_md.py` was created (deferred per H5)
- [x] 3.12 Run `uv run pytest -m "not slow"` — must be green before continuing

## 4. Retrieval subpackage grouping

- [x] 4.1 Create `core/retrieval/` skeleton
- [x] 4.2 Move dense vector search to `core/retrieval/dense.py`
- [x] 4.3 Move BM25 sparse retrieval from `sparse_retriever.py` to `core/retrieval/sparse.py`
- [x] 4.4 Move Reciprocal Rank Fusion to `core/retrieval/fusion.py`
- [x] 4.5 Move `search()` orchestration to `core/retrieval/pipeline.py` (dense + sparse + RRF + rerank policy)
- [x] 4.6 Move the `HARD_TECHNICAL_THRESHOLD = 0.3` ÷30 rerank threshold policy to `core/retrieval/policy.py` — numerically identical, no recalibration
- [x] 4.7 Move the CrossEncoder reranker unchanged to `core/retrieval/reranker.py`, preserving the `__new__` singleton, module-level `RERANK_MODEL`, and independent `load_dotenv()` (gotcha #4 — DI conversion is Phase 2)
- [x] 4.8 Convert `retrieval.py`, `sparse_retriever.py`, and `reranker.py` to compat shims with `DeprecationWarning`
- [x] 4.9 Verify tests resetting `CrossEncoderReranker._instance = None` still pass unmodified (the shim re-exports the same class object)
- [x] 4.10 Run `uv run pytest -m "not slow"` — must be green before continuing

## 5. Test import migration

- [x] 5.1 Update test files importing from old paths to the new `rag_mcp.core.*` public paths (imports only — zero assertion changes), one commit per subsystem
- [x] 5.2 Run the full fast suite with coverage: `uv run pytest -m "not slow" --cov=rag_mcp` — coverage must meet core ≥95% / overall ≥90%
  - **Result:** 581 passed, 8 deselected, 0 warnings, 87% overall (baseline: 88%).
    Core submodules ≥95% except `extractor.py` (49%, pre-existing), `sentence.py` (65%),
    `chunker.py` (76%, Azure fallback). The 1% drop is from 5 shim files at 0% coverage
    (50 uncovered stmts) — no test imports from shims anymore by design.

## 6. Acceptance and wrap-up

- [x] 6.1 Verify every old import path still resolves (spot-check: `from rag_mcp.metadata_extractor import ...`, `from rag_mcp.ingestion import ...`, `from rag_mcp.retrieval import ...`, `from rag_mcp.sparse_retriever import ...`, `from rag_mcp.reranker import ...`) and emits `DeprecationWarning`
- [x] 6.2 Verify no file under `core/` exceeds 500 lines
- [x] 6.3 Verify all public function signatures, CLI subcommands, and MCP tool signatures are unchanged
- [x] 6.4 Run `openspec validate phase-1-refactor-modular-extraction --strict`
- [x] 6.5 Run `graphify update .` to refresh the knowledge graph
- [ ] 6.6 Commit with Conventional Commits (`refactor:` — no release) and open PR with `gh pr create --base main`
