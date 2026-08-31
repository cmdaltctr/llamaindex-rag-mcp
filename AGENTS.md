# AGENTS.md — LlamaIndex RAG MCP Server

Conventions, constraints, and workflow for AI agents. Only what you **cannot infer** from reading the code — details live in `docs/guides/`.

## Quick Reference

```bash
uv sync                          # Install deps (uv, not pip/poetry)
uv run rag-mcp                   # Start MCP server (stdio)
uv run rag-mcp ingest ./docs     # CLI ingest
uv run pytest -m "not slow" -v   # Fast tests (no Ollama, no disk I/O)
uv run pytest --cov=rag_mcp      # Coverage
```

## WHEN YOU WRITE

### Explaining problems and errors

**MUST ADHERE**
When you hit a bug, error, or design problem, structure the response as:

1. What's wrong — one or two plain English sentences. No jargon without a plain translation in the same sentence.
2. What to do — a numbered list of concrete actions. Not a bullet mentioning the problem exists; an instruction I can follow.
3. Never describe a problem without action points attached. Never make me ask "what's next" — give it upfront. If there's more than one valid fix, list the options as numbered choices, not a single buried recommendation.
4. Assume I'm not going to ask for a plain English version. Write it that way the first time.
5. Use British English in all except code: documentation, comments, commit messages, agent outputs, proposals, papers, and user-facing text.

### IMPORTANT: TECHNICAL WRITING (STE Rules)

Write technical documentation in ASD-STE100 Simplified Technical English where practical: use clear active voice, one action per instruction, short sentences (maximum 20 words for procedures), unambiguous terms, and avoid idiom, filler, and unexplained abbreviations; use the official ASD-STE100 approved dictionary when available.

## Architecture Invariants

→ Full detail: [`docs/guides/architecture.md`](docs/guides/architecture.md)

1. **`config/` is the single source of truth for settings data; `compose.py` constructs everything.** `config/` is a LEAF: it must not import `core/` business logic (only the pure-data `core/*/settings.py` models). There is **no** `config.settings` singleton and no `RESOLVED_*` constants — importing `config` resolves nothing. `compose.py` is the only production caller of `get_settings()`, and it owns the runtime capability probes (sparse backend, PDF reader).
2. **No cross-imports** between `core/ingestion/` and `core/retrieval/` — they share only settings. The v1 top-level shims (`ingestion.py`, `retrieval.py`, `server.py`, `cli.py`, `readers/`, …) were **deleted in v2.0.0**; `src/rag_mcp/` holds only `__init__.py` and `compose.py` at the top level.
3. **Transports are thin wrappers** — `transports/mcp/` (MCP server, split by tool), `transports/cli/` (CLI split by command group), and `transports/api/` (OpenAPI contract only) all delegate to `core/`. No transport contains business logic. The `core/` layer never imports from `transports/`.
4. **All ingestion is async** — `ingest_path_async` is the sole entry point.
5. **Balanced retrieval defaults are intentional** (ADR-018): `retrieval.top_k=10`, `chunking.chunk_overlap=100`. Read from the injected `EffectiveSettings`, never hardcode. Env vars are nested: `RETRIEVAL__TOP_K`, `CHUNKING__CHUNK_OVERLAP` (ADR-037). **Note:** the code default is `RERANK_ENABLED=false` (flipped off after Experiment 10, which showed the reranker degrades technical-workload retrieval by 19–27%). Phase 4 profiles restore ADR-018's balanced intent per use case: the `documents` profile sets `reranker_enabled: true` (semantic workloads benefit from the reranker), while the `codebase` profile keeps it `false` (speed-first for coding agents). The profile-level value takes precedence over the global default at operation time.
6. **Codebase/document graph modules live under `core/`** — `core/codebase/{codebase_map,code_graph,ast_extract,communities,cache,format}.py` and `core/documents/{doc_graph,similarity}.py` (ADR-037). They have no cross-imports with `core/ingestion/` or `core/retrieval/`. Magika detection lives in `integrations/magika.py` and does **not** import back into the codebase map.
7. **Azure SDK import is lazy** (ADR-024) — `integrations/azure.py` never imports `azure-ai-documentintelligence` at module top-level. Import happens inside `_get_client()`.
8. **Graph construction is deterministic** — no LLM involvement in code graph, document graph, or community detection.
9. **Settings are injected, never global** (ADR-037). `core/` and `integrations/` MUST NOT import a settings singleton. Entry points (`search`, `ingest_path_async`) resolve `EffectiveSettings` **once at the boundary**; everything below takes it as a parameter. `EffectiveSettings` and all four of its blocks are frozen.
10. **Registries are the dispatch mechanism** (PROPOSAL §4.4). A new strategy = one new file + one `register()` line. Dispatch modules MUST NOT import concrete strategy modules at module level, and MUST NOT branch `if/elif` over strategy names.
11. **No file exceeds 500 lines.** Enforced by `tests/test_file_size_ceiling.py`.

## Critical Gotchas (silent breakage if violated)

1. **Never raise from MCP tool handlers.** Return `{"status": "error", "message": "..."}`. Every handler in `transports/mcp/` wraps its body in try/except — keep this uniform when adding new tools.
2. **The reranker is a DI plain class with a process-wide model cache** (ADR-031, Phase 2). Tests MUST call `reset_model_cache()` in setup/teardown — it replaced the old `CrossEncoderReranker._instance = None` hook.
3. **The ÷30 threshold scaling is empirically calibrated.** Don't change without re-running `experiments/1-reranker-threshold-calibration-2026-05-12/`.
4. **The reranker no longer imports `dotenv` independently** — settings are injected via the composition root (Phase 2, ADR-031). The old circular-import workaround (gotcha #4 pre-Phase-2) is gone; don't reintroduce it.
5. **CLI output goes to stderr.** stdout is the MCP protocol channel. The `transports/cli/` package uses `Console(stderr=True)`.
6. **PDF reader is a factory** (ADR-020, amended Phase 5). Located at `integrations/pdf/factory.py`. Default `auto` (LiteParse if installed, else pypdf). Tests MUST set `PDF_READER=pypdf` to stay deterministic.
7. **MCP tool annotations are mandatory.** Use `ToolAnnotations` (`readOnlyHint`, `destructiveHint`) on every tool.
8. **`content_type` metadata takes precedence** over file extension for chunking strategy selection (implemented in `core/ingestion/chunker.py`; no dedicated ADR — ADR-022 is "Code Graph via Tree-Sitter AST", not content-type dispatch).
   8a. **Tests inject settings; they do not patch a singleton.** There is nothing to patch. Use the `effective_settings(**overrides)` conftest factory, or `set_default_effective_settings(...)` for code that reads the composition-root default. The conftest default deliberately sets `extraction_mode="disabled"` and `pdf_reader="pypdf"` — the class defaults would make ingestion tests perform real LLM calls and hang on network timeouts.
   8b. **Patch targets follow the function, not the re-export.** After the ADR-037 splits, `_get_git_commit_hash`/`_load_cache`/`_save_cache` live in `core/codebase/cache.py`, `format_codebase_map` in `core/codebase/format.py`, `Observer` in `daemon/runner.py`, and `_is_magika_available` in `integrations/magika.py`. Patching the re-exporting module is a no-op.
   8c. **A stale `ignore_imports` entry fails the build.** All contracts set `unmatched_ignore_imports_alerting = "error"`. When you fix a violation, delete its ignore — that failure is the signal, not a nuisance.
9. **Codebase map cache is keyed by git commit hash.** If not a git repo, caching is disabled — map is rebuilt every call.
10. **`DOC_SIMILARITY_THRESHOLD` default (0.85) needs calibration.** Don't change without running experiment 10.1.
11. **Pre-v2 flat env vars raise at startup.** `TOP_K`, `CHUNK_SIZE`, `METADATA_EXTRACTION_MODE` … are no longer read; a startup tripwire fails with the nested replacement named. Retirement lifetime is **shape-aware** (see `config/legacy.py` docstring): nested entries expire one major after the rename; flat entries persist while an upgrade path exists because pydantic cannot detect them.
12. **OpenSpec validation is a guardrail, not a constitution.** If a spec has factually wrong content (wrong default value, wrong scenario name, stale accepted-set), fix it. When `openspec validate --strict` then complains that a MODIFIED block "drops" scenarios from the baseline, the baseline spec itself is wrong — fix the baseline in `openspec/specs/` too. Do not work around the validator by keeping incorrect content and adding explanatory notes. The tool serves the spec, not the other way around.
13. **Dependency floors are enforced by `tests/test_dependency_floors.py` and the `floors` CI job.** The test fails when a declared floor drifts more than one minor below its locked version (or sits above it). The `floors` job installs with `--resolution lowest-direct` and runs the fast suite. When raising a floor, update the exemption dict in the test if the gap is intentional (with a comment naming the reason). See ADR-042.

## Hard Boundaries

| Type      | Rule                                                                                                                                                |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| ⚠️ Ask    | Cloud dependencies & API keys — local-first by default, cloud allowed as opt-in (see ADR-024). All cloud features must degrade gracefully to local. |
| 🚫 Never  | PyTorch in the base install or on the default retrieval path. ONNX Runtime only. PyTorch behind the optional `torch` extra is ⚠️ Ask.               |
| 🚫 Never  | Hardcoded paths or secrets. Everything via `.env`.                                                                                                  |
| 🚫 Never  | Modifying `config.py` to depend on `ingestion.py` or `retrieval.py`.                                                                                |
| ⚠️ Ask    | Adding new core dependencies. Mixing embedding models (ChromaDB locks dims).                                                                        |
| ✅ Always | Type annotations + `from __future__ import annotations` in new modules.                                                                             |
| ✅ Always | Google-style docstrings on public functions and classes.                                                                                            |
| ✅ Always | `uv sync` + `uv run pytest -m "not slow" --cov=rag_mcp` before committing.                                                                          |

## Change Workflow

```
OpenSpec (propose → implement → archive)
  └── Experiment (if empirical validation needed) → ADR (record the decision)
```

1. **Propose** (`openspec-propose` skill) → `openspec/changes/<id>/` (proposal.md, specs/, tasks.md)
2. **Experiment** (if needed, `s-experiment`) → `experiments/<slug>-<date>/`
3. **Implement** (`openspec-apply-change`) → work through `tasks.md` checkboxes
4. **ADR** → `docs/adr/` once confirmed · **Archive** (`openspec-archive-change`) → `openspec/changes/archive/`

**Documentation drift check**: when a default value changes, grep `docs/guides/` for the old value. This is a procedural partial, not automation — it depends on discipline and will sometimes be skipped, but it is strictly better than the previous state (nothing).

**Branch/PR**: `git switch -c feat/<change-id>` → `openspec validate --all --strict` + targeted tests → Conventional Commits → `gh pr create --base main` → merge when green.

## Release Automation

Releases via `python-semantic-release` on every push to `main`. `feat:` → minor, `fix:`/`perf:` → patch, `feat!:` → major, `chore:`/`docs:`/`test:`/`refactor:` → no release. Never manually edit `version` in `pyproject.toml`.

## Coverage Thresholds

| Tier          | Floor    | Modules                                                                                                                                                 |
| ------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core + MCP    | ≥95%     | `core/ingestion`, `core/retrieval`, `core/metadata`, `core/chunking`, `core/vectordb`, `core/profiles`, `core/settings.py`, `config/`, `transports/mcp` |
| Orchestration | ≥85%     | `daemon/watcher`, `transports/cli`                                                                                                                      |
| **Overall**   | **≥90%** | all (excluding deprecated compat shims — see below)                                                                                                     |

> All modules under `src/rag_mcp/` are in the gate. The v1 compat-shim
> `omit` list was removed with the shims themselves in v2.0.0 (ADR-037).
>
> Coverage is measured with branch coverage (`--cov-branch`), which scores
> 2-3 points lower than the line-only coverage these floors were originally
> based on. The Codecov project checks are currently **informational** (not
> CI-blocking) while the targets are recalibrated for branch measurement.
> The `patch` check (new code coverage) remains blocking. See TDR-007.

## Detailed Documentation

| Topic                         | Where                                                                      |
| ----------------------------- | -------------------------------------------------------------------------- |
| Architecture deep-dive        | [`docs/guides/architecture.md`](docs/guides/architecture.md)               |
| MCP tools reference           | [`docs/guides/mcp-tools.md`](docs/guides/mcp-tools.md)                     |
| Ingestion pipeline            | [`docs/guides/ingestion.md`](docs/guides/ingestion.md)                     |
| Retrieval + reranker          | [`docs/guides/reranker.md`](docs/guides/reranker.md)                       |
| Metadata extraction           | [`docs/guides/metadata-extraction.md`](docs/guides/metadata-extraction.md) |
| CLI reference                 | [`docs/guides/cli-reference.md`](docs/guides/cli-reference.md)             |
| Configuration                 | [`docs/guides/configuration.md`](docs/guides/configuration.md)             |
| Testing                       | [`docs/guides/testing.md`](docs/guides/testing.md)                         |
| ADRs (27 decisions)           | [`docs/adr/`](docs/adr/)                                                   |
| Config vars                   | `.env.example` + defaults in `config.py`                                   |
| OpenSpec specs                | `openspec/specs/` + `openspec/changes/`                                    |
| NiftyPM local source of truth | `niftypm/llamaindex-rag-mcp.json`                                          |

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

**Truncated results.** The `query_graph` MCP tool defaults to `token_budget: 2000`, which silently drops nodes on anything broad — the output says `TRUNCATED: showing N of M nodes`. When you see that, **re-run with `token_budget: 8000`** before concluding the graph lacks the answer. Narrow instead with `context_filter` (e.g. `['call']`) or `depth` when even 8000 truncates, and use `get_node` when you already know the symbol.

**Symbol lookups are the exception to graphify-first.** This graph is prose-heavy: "where is X defined" tends to return `docs/guides/*.md` nodes rather than the source symbol. For pure location questions (find a class, function, or file), grep/glob directly. Use graphify for relationships, call paths, and architecture — that is where it beats grep.
