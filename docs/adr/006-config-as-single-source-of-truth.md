# ADR-006: Config as Single Source of Truth

**Date:** 2026-05-12
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Git Commits:** `9a1b310`

## Context

During initial development, both `ingestion.py` and `retrieval.py` independently
set `Settings.embed_model = OllamaEmbedding(...)` at import time. This caused
configuration drift: changes to the embedding model URL or batch size in one
module were not reflected in the other. It also made testing harder because
each module's import triggered a real Ollama connection attempt.

The project needed a single place where all configuration constants and the
LlamaIndex global settings are initialised, ensuring that both ingestion and
retrieval use identical parameters.

## Decision

Create **`config.py`** as the single source of truth for all configuration.

- All environment variables loaded and exposed as module-level constants
- `Settings.embed_model` set exactly once in `config.py`
- Both `ingestion.py` and `retrieval.py` import from `config.py`
- **No cross-imports** between `ingestion.py` and `retrieval.py`
- `server.py` and `cli.py` are thin wrappers — all logic lives in the
  three core modules (`ingestion.py`, `retrieval.py`, `reranker.py`)
- `reranker.py` independently imports `dotenv` (intentional, to avoid
  circular import risk with `config.py` which runs `OllamaEmbedding(...)`
  at import time)

## Consequences

### Positive
- Zero configuration drift between ingestion and retrieval
- Single place to change embedding model, batch size, chunk parameters, etc.
- Tests can mock one module (`config.py`) instead of patching each consumer
- Clear dependency graph: `config.py` ← `ingestion.py` / `retrieval.py` / `reranker.py`

### Negative
- `Settings.embed_model` executes at import time in `config.py`, meaning tests
  must apply `MockEmbedding` before importing any module that imports from
  `rag_mcp.config`
- Adding a new config variable requires updating `config.py` and potentially
  the test isolation fixtures in `conftest.py`

### Neutral
- `reranker.py` maintains its own `dotenv` import — a deliberate exception
  to avoid circular import risks

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Duplicate config in each module** | Led to the drift that prompted this ADR |
| **YAML/TOML config file** | Adds a file to manage; `.env` already serves this purpose |
| **Pydantic Settings model** | Over-engineered for a project with ~12 environment variables |
| **Pass config as function parameters** | Verbose; every function call would need 5+ parameters |

## References

- `src/rag_mcp/config.py` — centralised configuration module
- `tests/conftest.py` — `_patch_embed_model`, `_isolate_env` fixtures
- `AGENTS.md` — "Architecture (3 lines)" section documenting this decision
