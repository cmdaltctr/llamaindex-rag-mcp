# AGENTS.md — LlamaIndex RAG MCP Server

Conventions, constraints, and workflow for AI agents working on this codebase.
Only what you **cannot infer** from reading the code. The rest is in the code.

## Quick Reference

```bash
uv sync                    # Install deps (uv, not pip/poetry)
uv run rag-mcp             # Start MCP server (stdio)
uv run rag-mcp ingest ./docs   # CLI ingest
uv run pytest -m "not slow" -v # Fast tests (no Ollama, no disk I/O)
uv run pytest --cov=rag_mcp    # Coverage (must stay ≥ 95%)
```

## Architecture (3 lines)

- **`config.py`** is the single source of truth for `Settings.embed_model` and all constants.
  Never set `Settings.embed_model` in `ingestion.py`, `retrieval.py`, or `server.py`.
- **No cross-imports between `ingestion.py` and `retrieval.py`** — they share only `config.py`.
- **`server.py` and `cli.py` are thin wrappers** — all logic lives in `ingestion.py`,
  `retrieval.py`, `reranker.py`, and `metadata_extractor.py`.
- **All ingestion is async** — `ingest_path_async` is the sole entry point.

## Non-Obvious Rules (the stuff that'll trip you up)

1. **Never raise from MCP tool handlers.** Always return `{"status": "error", "message": "..."}`.
   Let FastMCP wrap errors as `TextContent` with `isError`.

2. **All new MCP tool parameters must be optional with sensible defaults.**
   Preserves backward compatibility with existing clients.

3. **CLI output goes to stderr** (`Console(stderr=True)`). stdout is the MCP protocol channel.
   `--json` mode is the only exception.

4. **The reranker is a singleton.** `CrossEncoderReranker.__new__()` returns one instance.
   Tests MUST reset `CrossEncoderReranker._instance = None` in setup/teardown.

5. **The ÷30 threshold scaling is empirically calibrated.**
   When `rerank=True`, `similarity_threshold` is divided by 30 because cross-encoder sigmoid
   scores are much lower than cosine similarity (valid reranker results can be as low as 0.015).
   See `experiments/experiment-1/` for the data. Don't change the factor without re-running
   experiments.

6. **`reranker.py` imports `dotenv` independently** of `config.py`. This is intentional —
   it works standalone. Don't "fix" this without checking for circular import risks
   (config.py runs `OllamaEmbedding(...)` at import time).

7. **Deletion functions live in `ingestion.py`** (`remove_document`, `remove_by_metadata`,
   `remove_collection`). They use direct ChromaDB ``collection.delete(where=...)`` API,
   not LlamaIndex abstractions.

8. **Re-ingestion is upsert, not append.** `ingest_path()` calls `remove_document()` for
   each file before reading/chunking. Old chunks are always replaced.

9. **The `delete` CLI subcommand takes exactly one of `--path`, `--metadata`, `--collection`.**
   `--collection` drops the entire collection (requires confirmation unless `--yes`).
   `--dry-run` previews without modifying ChromaDB. JSON output via `--json`.

10. **`delete_documents` MCP tool** — `path` (by file), `metadata_filter` (by filter), or
    `collection` alone (drop collection). All params optional. `dry_run` previews.

11. **Watcher `on_deleted` is immediate** (no debounce). Cancels pending ingest timers,
    clears hash cache, calls `remove_document()`. Deletion is idempotent.

## MCP Conventions

- **Transport**: `mcp.run(transport="stdio")`. All logging to stderr.
- **Tool names**: `snake_case`. Function docstring becomes the tool description.
- **Input schemas**: Native Python types (str, int, float, bool, list, dict).
  FastMCP auto-generates JSON Schema. Use `Annotated[type, Field(description="...")]`
  from pydantic for richer descriptions.
- **Tool handlers return `dict` or `list`**, never raise exceptions.

### Multi-Collection Support

- **Don't use `COLLECTION_NAME` from config.py in retrieval.py.** Use the `collection_name` parameter
  (default `"documents"`) passed to `search()` instead. The same applies to new ingestion code.
- **All collection parameters default to `"documents"`** — backward compatibility with the original
  single-collection design is maintained.
- **`list_collections()` lives in retrieval.py**, not ingestion.py. It uses `PersistentClient` directly.
- **ChromaDB collections share the same embedding dimension** — all use the embed model from `config.py`.
  Never create a collection with a different embedding model without handling dimension mismatch.

### Metadata Extraction

- **`METADATA_EXTRACTION_MODE=keyword` is the default.** It uses regex rules from
  `metadata_extractor.py` — zero additional dependencies.
- **Ollama mode uses `OLLAMA_CLASSIFY_MODEL`** (default `qwen3:0.6b`) via the `/api/generate` endpoint.
  It sends only the first 2000 characters of the document for efficiency.
- **`metadata_extractor.py` imports `config.py`** for its constants, but the module is otherwise
  self-contained. It does NOT import any LlamaIndex modules (the llamaindex mode is a stub).
- **Metadata is attached in `_read_and_chunk_file()`** — one `extract_metadata()` call per file,
  result attached to all chunks. Tests must set `METADATA_EXTRACTION_MODE` on the
  `rag_mcp.metadata_extractor` module (not just `config.py`) because the extractor copies
  values at import time.

## Test Gotchas

All tests inherit three autouse patches from `conftest.py`:
1. **ChromaDB** → shared `EphemeralClient` (no disk I/O)
2. **Settings.embed_model** → `MockEmbedding(384)` (no Ollama)
3. **Module-level constants** → patched via `sys.modules` for consistent collection naming

Watch for:
- **EphemeralClient leaks state between tests.** `conftest.py` clears collections before each
  test, but if you bypass the fixture or create a new `PersistentClient`, data can leak.
- **Reranker singleton must be reset:** `CrossEncoderReranker._instance = None` in
  `setup_method`/`teardown_method`.
- **`@pytest.mark.slow`** on the E2E stdio test. Excluded by default (`-m "not slow"`).
- **`connected_client`** is imported directly from conftest: `from conftest import connected_client`.
  It's an `asynccontextmanager`, not a fixture.

## Hard Boundaries

| Type | Rule |
|------|------|
| 🚫 Never | API keys, cloud services, or any dependency that needs a remote sign-up |
| 🚫 Never | PyTorch at runtime. ONNX Runtime only. The reranker downloads pre-exported ONNX models (~23 MB). |
| 🚫 Never | Hardcoded paths or secrets. Everything via `.env`. |
| 🚫 Never | Modifying `config.py` to depend on `ingestion.py` or `retrieval.py`. |
| ⚠️ Ask | Adding new core dependencies. Prefer no-code solutions first. |
| ⚠️ Ask | Mixing embedding models (ChromaDB locks vector dimension at collection creation). |
| ⚠️ Ask | Big bang refactors. Use OpenSpec: propose → implement → archive. |
| ✅ Always | Type annotations on every function. `from __future__ import annotations` in new modules. |
| ✅ Always | Google-style docstrings on public functions and classes. |
| ✅ Always | `uv sync` + `uv run pytest -m "not slow" --cov=rag_mcp` before committing. |

## Release Automation

Releases are automated via `python-semantic-release` (PSR). The tool runs in CI
(GitHub Actions) on every push to `master` and determines the version bump from
commit prefixes.

| Commit prefix | Version bump | Example |
|---------------|--------------|---------|
| `feat:` | minor | 0.1.0 → 0.2.0 |
| `fix:` / `perf:` | patch | 0.1.0 → 0.1.1 |
| `feat!:` or `BREAKING CHANGE:` | major | 0.1.0 → 1.0.0 |
| `chore:` / `docs:` / `test:` / `refactor:` | no release | — |

**Rules:**
- PSR is NOT a project dependency (conflicts with typer/click). Run via `uvx` locally.
- Never manually edit the `version` in `pyproject.toml` — PSR owns it.
- Never manually create git tags with `v` prefix — PSR owns those too.
- Config lives in `pyproject.toml` under `[tool.semantic_release]`.

**Local preview:**
```bash
uvx --from="python-semantic-release@10.5.3" semantic-release -v --noop version
```

## Coverage Thresholds

Coverage is enforced per-module rather than as a single flat number. This
reflects the reality that CLI formatting branches and OS-level defensive
code yield diminishing returns past ~85%, while core logic benefits from
tight coverage.

| Module type | Floor | Modules | Rationale |
|-------------|-------|---------|-----------|
| Core logic | ≥95% | `ingestion.py`, `retrieval.py`, `reranker.py`, `metadata_extractor.py`, `config.py` | Business logic, data integrity, embedding correctness |
| MCP wrappers | ≥95% | `server.py` | Tool contract correctness — MCP clients depend on exact response shapes |
| Orchestration | ≥85% | `watcher.py` | OS-level edge cases (symlink traversal, shutdown timeout) are low-value to mock |
| CLI | ≥85% | `cli.py` | Rich/Typer formatting branches, subprocess GPU detection, progress-bar callbacks |
| **Overall** | **≥90%** | all | Weighted floor across the full package |

When adding new modules, assign them to the appropriate tier. If a module
straddles tiers (e.g., a new module with both core logic and CLI glue),
default to the stricter floor and document exceptions inline.

Renegotiated 2026-05-20 during the `make-ingest-path-async` OpenSpec change.
Previous rule was a flat ≥95% on the entire package. The modular approach
was adopted because `cli.py` (450 statements of Typer/Rich glue) and
`watcher.py` (defensive OS-error branches) were dragging the overall number
below 95% despite core logic sitting at 92–99%.

## OpenSpec Workflow

For any non-trivial change:

1. **Propose** (`openspec-propose` skill): Creates `proposal.md`, `specs/`, `tasks.md`
2. **Implement** (`openspec-apply-change` skill): Work through `tasks.md` checkboxes
3. **Archive** (`openspec-archive-change` skill): Move to `openspec/changes/archive/`

Changes live in `openspec/changes/<change-id>/`. Active specs are in `openspec/specs/`.

## Where to Find Things

| What | Where |
|------|-------|
| Dependencies | `pyproject.toml` (not duplicated here) |
| Config vars | `.env.example` + defaults in `config.py` |
| Experiment data | `experiments/experiment-1/` |
| OpenSpec specs | `openspec/specs/` and `openspec/changes/` |
| Reranker model | `cross-encoder/ms-marco-MiniLM-L-6-v2` via HuggingFace Hub |
| Metadata extraction | `rag_mcp/metadata_extractor.py` (keyword/Ollama/llamaindex modes) |
| Multi-collection logic | `ingestion.py` (`_get_chroma_collection`), `retrieval.py` (`list_collections`) |
