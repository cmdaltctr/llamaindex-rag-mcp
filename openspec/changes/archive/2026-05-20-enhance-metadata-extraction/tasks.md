## 1. Stage 1 — Enrich ollama mode with hybrid category taxonomy

- [x] 1.1 Implement `_gather_existing_categories(collection_name: str) -> list[str]` in `metadata_extractor.py` — queries ChromaDB across all collections for unique `category` metadata values, deduplicates, normalises to lowercase
- [x] 1.2 Merge existing ChromaDB categories with seed categories from keyword mode rules; handle empty ChromaDB (first run) gracefully
- [x] 1.3 Update `_extract_ollama()` prompt to include the merged category list as "EXISTING CATEGORIES" with instructions: prefer existing labels, propose new concise label (1-3 words) if nothing fits, reply with JSON (`category`, `keywords`, `summary`)
- [x] 1.4 Add JSON response parsing with safe fallback: parse `json.loads()` → if invalid JSON, use raw response as `category` with empty `keywords`/`summary`
- [x] 1.5 Add category normalisation: lowercase, underscores for spaces, max 3 words, reject >4 words → `"uncategorised"`; truncate `keywords` to max 10, `summary` to max 300 chars
- [x] 1.6 Ensure ChromaDB query failure falls back gracefully: log WARNING, use seed categories only, continue classification
- [x] 1.7 Ensure fallback on Ollama error (`{"category": "uncategorised", "keywords": [], "summary": ""}`) and WARNING log preserves existing behaviour
- [x] 1.8 Add tests in `tests/test_metadata_extractor.py`: ChromaDB lookup with existing categories, ChromaDB lookup empty (first run), ChromaDB query failure, category reuse vs new proposal, valid JSON response, missing-keys JSON, invalid JSON (plain text), category normalisation (spaces→underscores, length), truncated keywords/summary, Ollama unreachable fallback, backward-compat (category key always present)

## 2. Stage 2 — Implement real llamaindex mode

- [x] 2.1 Add `llama-index-llms-ollama` as optional dependency in `pyproject.toml` under a `[metadata]` extras group
- [x] 2.2 Implement lazy `Settings.llm` initialisation in `_extract_llamaindex()` — import `Ollama` from `llama-index-llms-ollama` inside a try/except, initialise once via module-level singleton
- [x] 2.3 Build `IngestionPipeline` with `TitleExtractor(nodes=5)`, `KeywordExtractor(keywords=10)`, `SummaryExtractor(summaries=["self"])` transformations
- [x] 2.4 Implement chunk capping: process at most 10 chunks (configurable via `LLAMANDEX_EXTRACTOR_MAX_CHUNKS` env var)
- [x] 2.5 Implement metadata aggregation: collect per-node metadata from the pipeline and merge into a single dict (first non-empty value per key across all nodes)
- [x] 2.6 Add fallback: on `ImportError` (missing package) → log WARNING, fall back to keyword mode; on extraction failure → log WARNING, fall back to keyword mode
- [x] 2.7 Add tests: mock `IngestionPipeline` output, mock `Settings.llm`, ImportError fallback, successful extraction, chunk capping, metadata aggregation

## 3. Update configuration and docs

- [x] 3.1 Add `LLAMANDEX_EXTRACTOR_MAX_CHUNKS` env var to `config.py` with default value of `10`
- [x] 3.2 Add new env var to `.env.example` with an explanatory comment
- [x] 3.3 Update metadata extraction table in `README.md`: change `ollama` row to reflect richer output (`{"category": "AI", "keywords": [...], "summary": "..."}`); change `llamaindex` row from "Stub — not yet implemented" to "Ready — per-chunk enrichment via LlamaIndex pipeline"
- [x] 3.4 Update the ASCII pipeline diagram in `README.md` (line ~571) to remove `"(not yet impl.)"` from llamaindex branch

## 4. Verification

- [x] 4.1 Run `uv run pytest -m "not slow" -v` — all existing 288 tests pass with no regressions
- [x] 4.2 Run `uv run pytest tests/test_metadata_extractor.py -v` — new Stage 1 and Stage 2 tests all pass (40 total, 27 new)
- [x] 4.3 Run `uv run pytest -m "not slow" --cov=rag_mcp --cov-report=term-missing` — coverage for metadata_extractor.py at 93%, total at 82%
- [x] 4.4 Manual smoke test: `METADATA_EXTRACTION_MODE=ollama uv run rag-mcp ingest ./docs` → verify richer metadata in ChromaDB (requires Ollama running)
- [x] 4.5 Manual smoke test: `METADATA_EXTRACTION_MODE=llamaindex uv run rag-mcp ingest ./docs` → verify LlamaIndex pipeline metadata (requires Ollama + `uv sync --extra metadata`)
