# Testing

## Running tests

```bash
# Fast tests — no Ollama, no ONNX download, no disk I/O (run these routinely)
uv run pytest -m "not slow" -v

# With coverage report
uv run pytest -m "not slow" --cov=rag_mcp --cov-report=term-missing

# E2E stdio smoke test (requires uv run rag-mcp to work)
uv run pytest -m slow -v

# Single test file
uv run pytest tests/test_reranker.py -v
```

The fast suite (261 tests) uses mock embeddings and an in-memory ChromaDB client — no external services needed.

## Test files

| File | Tests | Coverage area |
|------|-------|---------------|
| `tests/test_watcher.py` | 39 | File watcher: debounce, hash dedup, throttling, shutdown, error handling, on_deleted |
| `tests/test_reranker.py` | 23 | Sigmoid, ONNX variant, singleton, fallback, mock inference, model loading |
| `tests/test_cli.py` | 93 | CLI validation, formatting, edge cases, delete subcommand |
| `tests/test_metadata_extractor.py` | 40 | Keyword, disabled, custom rules, ollama (JSON parsing, normalisation, hybrid taxonomy), llamaindex (pipeline, fallback, aggregation), unknown mode fallback |
| `tests/test_ingestion.py` | 20 | Path validation, empty dir, list empty, collection routing, metadata attachment, delete functions, upsert |
| `tests/test_retrieval.py` | 17 | Empty store, threshold, rerank flag, threshold scaling, collection search, metadata filter, list collections |
| `tests/test_mcp_tools.py` | 19 | Tool discovery, ingest, search, list, list_collections, collection params, backward compat, delete_documents |
| `tests/test_signal_handling.py` | 13 | SIGINT, shutdown flag, lock recheck |
| `tests/test_ingestion_parallel.py` | 21 | Concurrent ingestion, all-or-nothing semantics |
| `tests/test_e2e_stdio.py` | 1 | JSON-RPC handshake over stdio subprocess (`@pytest.mark.slow`) |

## Coverage thresholds

Coverage is enforced per-module rather than as a single flat number.

| Module type | Floor | Modules |
|-------------|-------|---------|
| Core logic | ≥95% | `ingestion.py`, `retrieval.py`, `reranker.py`, `metadata_extractor.py`, `config.py` |
| MCP wrappers | ≥95% | `server.py` |
| Orchestration | ≥85% | `watcher.py` |
| CLI | ≥85% | `cli.py` |
| **Overall** | **≥90%** | all |

## Gotchas

- **EphemeralClient leaks state between tests.** `conftest.py` clears collections before each test, but if you bypass the fixture or create a new `PersistentClient`, data can leak.
- **Reranker singleton must be reset** in `setup_method`/`teardown_method`: `CrossEncoderReranker._instance = None`.
- **`@pytest.mark.slow`** marks the E2E stdio test. Excluded by default with `-m "not slow"`.
- **`METADATA_EXTRACTION_MODE`** must be patched on the `rag_mcp.metadata_extractor` module (not just `config.py`) because the extractor copies values at import time.
