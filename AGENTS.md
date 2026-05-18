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
  `retrieval.py`, and `reranker.py`.

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

7. **Settings.embed_model executes at import time** in `config.py`. Tests must apply
   `MockEmbedding` before importing any module that imports from `rag_mcp.config`.

## MCP Conventions

- **Transport**: `mcp.run(transport="stdio")`. All logging to stderr.
- **Tool names**: `snake_case`. Function docstring becomes the tool description.
- **Input schemas**: Native Python types (str, int, float, bool, list, dict).
  FastMCP auto-generates JSON Schema. Use `Annotated[type, Field(description="...")]`
  from pydantic for richer descriptions.
- **Tool handlers return `dict` or `list`**, never raise exceptions.

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
