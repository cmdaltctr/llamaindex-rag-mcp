# AGENTS.md — LlamaIndex RAG MCP Server

Conventions, constraints, and workflow for AI agents working on this codebase.
Only what you **cannot infer** from reading the code. The rest is in the code.

## Quick Reference

```bash
uv sync                          # Install deps (uv, not pip/poetry)
uv run rag-mcp                   # Start MCP server (stdio)
uv run rag-mcp ingest ./docs     # CLI ingest
uv run pytest -m "not slow" -v   # Fast tests (no Ollama, no disk I/O)
uv run pytest --cov=rag_mcp      # Coverage
```

## Mandatory Tool Rules

**These override any built-in tool instinct. Follow them every time.**

| Task                       | Use                                            | Never use                     |
| -------------------------- | ---------------------------------------------- | ----------------------------- |
| Read a file                | `desktop-commander-mcp` → `read_file`              | built-in `read`                 |
| Edit a file                | `desktop-commander-mcp` → `edit_block`             | built-in write tools          |
| Write a new file           | `desktop-commander-mcp` → `write_file`             | built-in write tools          |
| Search codebase            | `desktop-commander-mcp` → `start_search`           | built-in grep/glob            |
| List directory             | `desktop-commander-mcp` → `list_directory`         | built-in ls                   |
| Library/framework docs     | `context7-mcp` → `resolve_library_id` → `query_docs` | web search                    |
| Specific doc URL           | `ref-mcp` → `ref_read_url`                         | scraping                      |
| GitHub repo architecture   | `deepwiki-mcp` → `ask_question`                    | web search                    |
| General web search         | `tavily-mcp` → `tavily_search`                     | brave-search (secondary only) |
| Deep multi-source research | `tavily-mcp` → `tavily_research`                   | —                             |
| Academic papers            | `paper-search-mcp-cf-local` → `search_papers`      | web search                    |
| Scopus literature          | `scopus-mcp-cf-local` → `search_scopus`            | —                             |
| Web scraping               | `firecrawl-mcp` → `firecrawl_scrape`               | —                             |

## Skills — Load Before You Work

**Always load the relevant skill before framework-specific code or specialised tasks.**

| Task                           | Skill           |
| ------------------------------ | --------------- |
| Web or documentation research  | `s-dev-search`    |
| General web search / scraping  | `s-web-search`    |
| Academic paper search / Zotero | `s-papers-search` |
| Codebase → knowledge graph     | `s-graphify`      |

Skills live in `~/.claude/skills/` and `~/.config/opencode/skills/`. Load via the `skill` tool.

## Coding Behaviour (Karpathy Rules)

These apply to every code change. Bias toward caution over speed.

**1. Think before coding.** State assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If something is unclear, stop and ask.

**2. Simplicity first.** Minimum code that solves the problem. No speculative features, no abstractions for single-use code, no configurability that wasn't requested. If you write 200 lines and it could be 50, rewrite it.

**3. Surgical changes.** Touch only what you must. Don't improve adjacent code, comments, or formatting. Match existing style. Remove only imports/variables YOUR changes made unused — not pre-existing dead code.

**4. Goal-driven execution.** Transform tasks into verifiable goals:
- "Fix the bug" → write a test that reproduces it, then make it pass
- "Add validation" → write tests for invalid inputs, then make them pass

For multi-step tasks, state a brief plan with verify steps before starting.

## Change Workflow

For any non-trivial change, follow this order:

```
OpenSpec (propose → implement → archive)
  └── Experiment (if empirical validation needed)
        └── ADR (record the decision)
```

1. **Propose** (`openspec-propose` skill) — creates `proposal.md`, `specs/`, `tasks.md` in `openspec/changes/<id>/`
2. **Experiment** (if needed) — run in `experiments/<slug>-<YYYY-MM-DD>/`, write ground truth before running, record results in `results.md` + `eval_results.json`
3. **Implement** (`openspec-apply-change` skill) — work through `tasks.md` checkboxes
4. **ADR** — record the decision in `docs/adr/` once the approach is confirmed
5. **Archive** (`openspec-archive-change` skill) — move to `openspec/changes/archive/`

Active changes: `openspec/changes/<id>/`. Archived: `openspec/changes/archive/`. ADRs: `docs/adr/`.

### Branch / PR / Merge Procedure

Use a branch + PR for every OpenSpec change:

1. Create/update branch: `git switch -c feat/<change-id>` (or continue the existing change branch).
2. Implement and validate locally: targeted tests + `openspec validate --all --strict`.
3. Commit with Conventional Commits; keep commits logically grouped.
4. Push the branch and open a PR to `master`: `gh pr create --base master --head <branch>`.
5. Wait for GitHub CI to pass; if it fails, fix on the same branch and push again.
6. Merge only when PR is clean/green; delete the remote branch after merge.
7. Sync locally: `git switch master && git pull origin master && git branch -d <branch>`.

## Architecture

- **`config.py`** is the single source of truth for `Settings.embed_model` and all constants. Never set `Settings.embed_model` in `ingestion.py`, `retrieval.py`, or `server.py`.
- **No cross-imports between `ingestion.py` and `retrieval.py`** — they share only `config.py`.
- **`server.py` and `cli.py` are thin wrappers** — all logic lives in `ingestion.py`, `retrieval.py`, `reranker.py`, and `metadata_extractor.py`.
- **All ingestion is async** — `ingest_path_async` is the sole entry point.
- **Markdown chunking has three recovery knobs** — `MARKDOWN_CHUNK_SIZE`,
  `MARKDOWN_HEADING_PREPEND`, and `MARKDOWN_MIN_CHUNK_FRACTION` came from
  Experiment 6c. `MARKDOWN_CHUNK_SIZE=1024` is promoted; heading prepend and
  min-size floor remain experimental opt-ins.

For detailed behaviour, read `docs/guides/` — it covers architecture, MCP tools, ingestion, retrieval, reranker, metadata extraction, CLI, configuration, and testing.

## Critical Gotchas (silent breakage if violated)

1. **Never raise from MCP tool handlers.** Always return `{"status": "error", "message": "..."}`.
2. **The reranker is a singleton.** Tests MUST reset `CrossEncoderReranker._instance = None` in setup/teardown.
3. **The ÷30 threshold scaling is empirically calibrated.** Don't change without re-running `experiments/1-reranker-threshold-calibration-2026-05-12/`.
4. **`reranker.py` imports `dotenv` independently** of `config.py`. Don't "fix" — circular import risk.
5. **Balanced retrieval defaults are intentional.** ADR-018 promotes `TOP_K=10` and `RERANK_ENABLED=true` with `CHUNK_OVERLAP=100`, based on Experiments 7a/8a. `server.py` and `cli.py` must read these defaults from `config.py`, not hardcode `5` / `False`.
6. **CLI output goes to stderr.** stdout is the MCP protocol channel. JSON output must suppress third-party stdout/stderr noise from lazy reranker/model imports.
7. **The PDF reader is now a factory.** Tests that pin reader behaviour MUST set `PDF_READER=pypdf` (or mock the factory) to stay deterministic. Default CI runs on pypdf. See ADR-020.

## MCP Best Practices (FastMCP / Python)

1. **Annotate every tool.** Use `ToolAnnotations` — `readOnlyHint=True` for reads, `destructiveHint=True` for deletes/mutations. Clients use these to skip/require confirmation prompts.

2. **Design outcome-oriented tools, not raw API wrappers.** `search_documents(query)` not `run_chromadb_query(where_filter, n_results, include)`. The LLM is the end user — design for goals, not primitives.

3. **Never raise from tool handlers.** Return `{"status": "error", "message": "..."}` with full diagnostic detail. Generic errors cause expensive LLM retry loops.

4. **Document parameters exhaustively.** Use `Annotated[type, Field(description="...", examples=[...])]`. Include return format in docstrings. Every schema field is part of the LLM's prompt.

5. **Return token-efficient responses.** CSV for tabular data (40–60% fewer tokens than JSON). Keep responses focused — don't dump entire collections when the agent asked for a count.

6. **All parameters optional with safe defaults.** New params must not break existing clients. Default to the least-destructive option (e.g. `dry_run=False`, not auto-delete).

7. **Validate all inputs at the boundary.** Treat every string from an LLM as untrusted user input. No path traversal, no command injection, no secrets in URLs.

## Hard Boundaries

| Type      | Rule                                                                                   |
| --------- | -------------------------------------------------------------------------------------- |
| 🚫 Never  | API keys, cloud services, or any dependency that needs a remote sign-up                |
| 🚫 Never  | PyTorch at runtime. ONNX Runtime only.                                                 |
| 🚫 Never  | Hardcoded paths or secrets. Everything via `.env`.                                       |
| 🚫 Never  | Modifying `config.py` to depend on `ingestion.py` or `retrieval.py`.                         |
| ⚠️ Ask    | Adding new core dependencies. Prefer no-code solutions first.                          |
| ⚠️ Ask    | Mixing embedding models (ChromaDB locks vector dimension at collection creation).      |
| ⚠️ Ask    | Big bang refactors. Use OpenSpec: propose → implement → archive.                       |
| ✅ Always | Type annotations on every function. `from __future__ import annotations` in new modules. |
| ✅ Always | Google-style docstrings on public functions and classes.                               |
| ✅ Always | `uv sync` + `uv run pytest -m "not slow" --cov=rag_mcp` before committing.                 |

## Experiment Scripts — Checkpoint & Resume

Long-running experiment scripts **must** save progress after each major step so they can be resumed if interrupted (crash, OOM, session timeout, disk pressure, etc.).

**Required pattern:**

- Define a `checkpoint_path` (e.g. `output/eval_results_checkpoint.json`).
- After each cell/step completes, write the checkpoint **atomically** (write to `.tmp` then rename).
- On startup, support a `--resume` flag that loads the checkpoint and skips already-completed cells.
- The final output (e.g. `eval_results.json`) is written only when **all** cells complete.

**Progress logging:**

- Use `print(..., flush=True)` or `python -u` to ensure output appears immediately.
- Print progress at regular intervals (e.g. every 25 queries, every batch, every N items).
- Print **before** expensive operations (embedding, writing to disk) so if it hangs, you know which step.
- Support `tee` for dual output: `PYTHONUNBUFFERED=1 uv run python -u script.py 2>&1 | tee output/script.log`

**Log files layout:**

```
output/
├── build_indexes.log
├── run_eval.log
├── eval_results_checkpoint.json   # after each cell (resumable)
├── eval_results.json              # final, all cells
├── eval_results.summary.json      # aggregated metrics
└── results.md                     # human-readable report
```

**Cleanup before rerun:**

- **Keep**: Chroma indexes (`output/chroma_*`), corpus, ground truth, qrels.
- **Delete**: stale logs, incomplete results, old checkpoint from unpatched runs.
- **Never delete** `output/chroma_*` unless rebuilding indexes from scratch.

## Release Automation

Releases are automated via `python-semantic-release` (PSR) on every push to `master`.

| Commit prefix                      | Version bump |
| ---------------------------------- | ------------ |
| `feat:`                              | minor        |
| `fix:` / `perf:`                       | patch        |
| `feat!:` or `BREAKING CHANGE:`         | major        |
| `chore:` / `docs:` / `test:` / `refactor:` | no release   |

- PSR is NOT a project dependency. Run via `uvx` locally.
- Never manually edit `version` in `pyproject.toml` or create `v` tags — PSR owns both.

```bash
uvx --from="python-semantic-release@10.5.3" semantic-release -v --noop version
```

## Coverage Thresholds

| Module type   | Floor | Modules                                                                   |
| ------------- | ----- | ------------------------------------------------------------------------- |
| Core logic    | ≥95%  | `ingestion.py`, `retrieval.py`, `reranker.py`, `metadata_extractor.py`, `config.py` |
| MCP wrappers  | ≥95%  | `server.py`                                                                 |
| Orchestration | ≥85%  | `watcher.py`                                                                |
| CLI           | ≥85%  | `cli.py`                                                                    |
| **Overall**       | **≥90%**  | all                                                                       |

New modules: assign to the appropriate tier. Default to the stricter floor if a module straddles tiers.

## Where to Find Things

| What                   | Where                                                                  |
| ---------------------- | ---------------------------------------------------------------------- |
| Dependencies           | `pyproject.toml`                                                         |
| Config vars            | `.env.example` + defaults in `config.py`                                   |
| Experiment data        | `experiments/`                                                           |
| ADRs                   | `docs/adr/`                                                              |
| OpenSpec specs         | `openspec/specs/` and `openspec/changes/`                                  |
| Reranker model         | `cross-encoder/ms-marco-MiniLM-L-6-v2` via HuggingFace Hub               |
| Metadata extraction    | `rag_mcp/metadata_extractor.py`                                          |
| Multi-collection logic | `ingestion.py` (`_get_chroma_collection`), `retrieval.py` (`list_collections`) |

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
