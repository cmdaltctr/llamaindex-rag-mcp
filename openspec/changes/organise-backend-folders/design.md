# Design: organise backend folders

## Context

See proposal.md for the reason. This section records the facts that shape the approach. All were checked on `integration/core-web` at `739c7a1`.

- `src/omrg/core/vectordb/` has 22 modules. Ten serve LanceDB, three serve Chroma, nine are shared.
- `registry.py:180-210` names backend code as lazy `"module:attr"` strings: two factories, one native sparse probe (`lance_fts:probe_native_fts`) and two storage summaries. `capabilities.py:227-232` and `summary.py:52-56` resolve them with `importlib`. A wrong string fails only at run time, and `capabilities.py:231-234` turns an import failure of the probe into "native sparse unavailable" with a debug log. A stale probe string therefore degrades search without an error.
- `pyproject.toml:519-546` confines `chromadb` and `lancedb` with import-linter contracts. Their `ignore_imports` entries name exact modules, and `unmatched_ignore_imports_alerting = "error"` fails the build when an entry matches nothing.
- `lancedb.py` has exactly 500 lines. `tests/test_file_size_ceiling.py` fails at 501.
- 46 test files import the backend modules. String patch targets: `tests/test_compose.py:745,1122`, `tests/test_chroma_cloud.py:975,1038`, `tests/test_lance_filter_security.py:408,602,692`. Path lists: `tests/test_chroma_cloud.py:1144-1160`, `tests/test_lancedb_import_site.py:42,79`, `tests/test_vectordb_registry.py:29-33,223-245`, `tests/test_vectordb_registry_availability.py:55`.
- `tests/test_vectordb_registry.py:147-178` checks that `compose.py` imports no concrete store module at module level. It compares against an exact set (`omrg.core.vectordb.chroma`, `omrg.core.vectordb.lancedb`). After the move, `from omrg.core.vectordb.chroma.store import X` has base `omrg.core.vectordb.chroma.store`, which is not in the set. The guard would pass while it checks nothing.
- `tests/unit/test_workspace_cleanup_guide.py:95` reads `src/omrg/transports/api/*.py` with a non-recursive `glob`. After the route move, it would stop reading the route files and keep passing.
- Relative imports: the moved modules contain 92 level-1 and 29 level-2+ relative imports. 14 of them sit inside functions (`chroma.py:402`, `routes_admin.py:101-213`, `routes_documents.py:93-120`, `routes_inspect.py:58`, `routes_jobs.py:173`, `routes_templates.py:40`). Python resolves a function-level import only when the function runs, so a wrong level is not caught at import time.
- Chroma tests skip in the base install (`chromadb` is absent here). `tests/test_clean_base_tripwire.py:314-322` lists the Chroma-gated files. CI runs them in a separate chroma-extra job (`.github/workflows/ci.yml:558`).
- `tests/test_clean_base_tripwire.py:72` pins the executed count of the fast suite (`_BASE_EXECUTED = 5165`) and `:309` pins the deselected count (`_BASE_DESELECTED = 20`). Every new fast test changes the first; every new slow test changes the second.
- `tests/test_docs_references.py:27` matches only paths that start with `src/omrg/`. The guides cite the backend files without that prefix (`docs/guides/architecture.md:245-433,663,676-677`, `configuration.md:199`, `reranker.md:131`). Today exactly one short citation does not resolve: `architecture.md:400` (`core/chunking/mystrategy.py`, an example name).
- Hatch ships every file under `src/omrg` (`pyproject.toml:147-148`). A folder guide under `src/omrg/` would go into the wheel. `scripts/check_web_wheel.py` already runs on a built wheel in `scripts/local_ci.sh:81-82` and `.github/workflows/release.yml:65-67`.
- The public API is `omrg.__all__` (`src/omrg/__init__.py:1-6`). "Names absent from `__all__` are internal." `docs/guides/library-usage.md:49,184` still shows `from omrg.core.vectordb.lancedb import LanceVectorStore`.

## Goals / Non-Goals

**Goals:**

- One folder per vector-store backend, and one folder for HTTP route groups.
- Each move lands with every caller, in one commit per move, with no shim.
- Guards that fail loudly when the layout drifts or a guard goes blind.
- Short folder guides that point to the root `AGENTS.md` and `docs/guides/` instead of repeating them.

**Non-Goals:**

- No change to runtime behaviour, settings, stored data, HTTP paths, MCP tools or CLI output.
- No change to import-linter contract names or to what each contract permits.
- No repair of archived experiment scripts (ADR-037).
- No moves listed under "Out of scope" in proposal.md.

## Decisions

### D1. New file names inside the backend folders

Drop the backend prefix inside each folder, because the folder name already says it.

| Old path (`core/vectordb/`) | New path (`core/vectordb/`) |
| --- | --- |
| `lancedb.py` | `lancedb/store.py` |
| `lance_epoch.py` | `lancedb/epoch.py` |
| `lance_filter.py` | `lancedb/filter.py` |
| `lance_fts.py` | `lancedb/fts.py` |
| `lance_literal.py` | `lancedb/literal.py` |
| `lance_meta.py` | `lancedb/meta.py` |
| `lance_node_schema.py` | `lancedb/node_schema.py` |
| `lance_paged.py` | `lancedb/paged.py` |
| `lance_rows.py` | `lancedb/rows.py` |
| `lance_table_name.py` | `lancedb/table_name.py` |
| `chroma.py` | `chroma/store.py` |
| `chroma_cloud.py` | `chroma/cloud.py` |
| `paged.py` | `chroma/paged.py` |

`paged.py` serves only Chroma: its docstring says so, and only `chroma.py:34` imports it.

Alternative: keep the old names (`lancedb/lancedb.py`, `lancedb/lance_filter.py`). Rejected: the path `omrg.core.vectordb.lancedb.lancedb` repeats itself, and every import line changes anyway because the folder changes. No new name matches a standard-library module.

### D2. The folder names `lancedb` and `chroma`

Use the registry names `lancedb` and `chroma`, as the user asked. The folder `omrg.core.vectordb.lancedb` has the same last name as the LanceDB SDK `lancedb`. Python 3 imports are absolute (PEP 328), so `import lancedb` inside `lancedb/store.py` finds the SDK through `sys.path`, not the folder. The folder is never on `sys.path`. A test imports `omrg.core.vectordb.lancedb.store` and checks that its `lancedb` attribute is the installed SDK (module name `lancedb`, file outside `src/omrg`). The import-linter ignore entries give a second check: `store -> lancedb` must match a real external import, or `unmatched_ignore_imports_alerting = "error"` fails the build.

Alternative: name the folder `lance`. Rejected: it does not match the registry name or the user's wording. `chroma` does not clash with the SDK name `chromadb`.

### D3. What stays at the `core/vectordb/` root

Shared modules stay: `__init__`, `base`, `identity`, `legacy`, `naming`, `registry`, `score`, `summary`, `validation`.

- `legacy.py` detects old Chroma data on disk without importing `chromadb`. `compose_engine.py:110` calls it in every install, also without the `chroma` extra. It is a decision about which backend to use, not Chroma code.
- `summary.py` holds the registry dispatch (`storage_summary`) and two SDK-free one-line formatters. Splitting it would create two files of about 10 lines and change two registry strings for no import-boundary gain.

Alternative: move the two formatters into `chroma/summary.py` and `lancedb/summary.py`. Not chosen now; the layout check allows it later with one allow-list edit.

### D4. Backend and routes package files import nothing

`lancedb/__init__.py`, `chroma/__init__.py` and `api/routes/__init__.py` hold a one-line docstring and no import. This keeps the rule "no re-export shims" (ADR-037, gotcha 8b: patching a re-export is a no-op). It also keeps imports cheap: importing `chroma/paged.py` in the base install must not load `chromadb`.

Alternative: re-export `LanceVectorStore` from `lancedb/__init__.py`, so the documented path `from omrg.core.vectordb.lancedb import LanceVectorStore` keeps working. Rejected: it is a shim and it loads the SDK for every module in the folder. See D15 for the guide.

### D5. Import-linter entries stay exact

Replace each `ignore_imports` entry one for one:

- `omrg.core.vectordb.chroma.store -> chromadb`, `omrg.core.vectordb.chroma.cloud -> chromadb`
- `omrg.core.vectordb.lancedb.store -> lancedb`, `omrg.core.vectordb.lancedb.literal -> lancedb`, `omrg.core.vectordb.lancedb.fts -> lancedb`

Alternative: a wildcard (`omrg.core.vectordb.lancedb.** -> lancedb`). Rejected: it widens what the contract permits, and a new SDK import site should be a reviewed edit. Contract names do not change, so `docs/guides/architecture.md:676-677` keeps its contract column.

### D6. Relative imports keep the house style

The moved modules keep relative imports with one more level for shared targets (`from .base` becomes `from ..base`; `from ...core` becomes `from ....core`). Sibling imports stay at one level with the new names (`from .lance_filter` becomes `from .filter`; `from .routes_graphs` becomes `from .graphs`). `lance_filter.py:60` is the only absolute self-import; it becomes `from .literal import _literal_sql`. The layout test parses every module under `core/vectordb/` and `transports/api/` and resolves each relative import, at module level and inside functions, to an existing module or package. This catches the 14 function-level imports that a normal import would miss.

Alternative: switch to absolute `omrg.` imports. Rejected: the transports and vectordb code use relative imports today, and the change must stay a move.

### D7. Route module names

Drop the `routes_` prefix inside `transports/api/routes/`. `routes.py` becomes `routes/foundation.py` (its docstring says "Foundation routes"). `routes_inspect.py` becomes `routes/inspection.py`, because `inspect` is a standard-library module. The other 12 keep their name without the prefix: `admin`, `connections`, `documents`, `experiments`, `graphs`, `integrations`, `jobs`, `logs`, `mcp`, `plugins`, `runs`, `templates`. `app.py` keeps the `API_ROUTERS` order unchanged, because FastAPI matches routes in registration order.

Shared helpers that route files import from each other (`ok`, `validation_failure`, `ManageScope`, `TRUST_NOTICE`, stream helpers) move with their files and are not redesigned (proposal.md, Out of scope).

### D8. Layout guards live in one new test file

Add `tests/unit/test_folder_layout.py`. It reads files and syntax trees only, so it needs no `web` or `chroma` extra and runs in every CI job:

1. The `core/vectordb/` root modules equal the D3 allow-list; the subfolders equal `{"chroma", "lancedb"}`.
2. Each backend `__init__.py` and `api/routes/__init__.py` has no `Import` or `ImportFrom` node.
3. No module at the `transports/api/` root calls `APIRouter(`.
4. `app.py` imports the `router` of every module in `api/routes/` that calls `APIRouter(`.
5. Every relative import under `core/vectordb/` and `transports/api/` resolves (D6).
6. `omrg.core.vectordb.lancedb.store.lancedb` is the installed SDK (D2).
7. In a fresh subprocess, importing `omrg.core.vectordb.chroma.paged` loads no `chromadb` module. A subprocess is needed because the chroma-extra job may already hold `chromadb` in `sys.modules`.

Alternative: extend `tests/unit/test_verification_gaps_boundaries.py`, which pins the top-level module list. Rejected: that file is about the top level; one file for folder shape is easier for agents to find, and the folder guides cite it.

### D9. Repair the guards that would go blind

- `tests/test_vectordb_registry.py`: treat a module as concrete when it equals or starts with `omrg.core.vectordb.chroma.` or `omrg.core.vectordb.lancedb.`. Add cases for `from omrg.core.vectordb.chroma.store import ...` and `from .core.vectordb.lancedb import store`. These cases fail against the exact-set code first.
- `tests/unit/test_workspace_cleanup_guide.py`: read the API folder with `rglob`, and assert that at least one file under `routes/` was read.
- `tests/test_lancedb_import_site.py`: tighten the allowed prefix from `core/vectordb/` to `core/vectordb/lancedb/`.
- `tests/test_chroma_cloud.py:1136-1162`: allow `core/vectordb/chroma/store.py` and `core/vectordb/chroma/cloud.py`.

### D10. Registry strings get a resolution test

Add a test that, for every name in `registry.available()`, splits each `module:attr` string (factory, native sparse probe, summary), finds the module file with `importlib.util.find_spec`, parses it, and checks that `attr` is a top-level function, class or assignment. It imports no backend module, so it runs without the `chroma` extra. Negative cases feed a missing module and a missing attribute to the same helper and expect a failure that names the string.

Alternative: import each module. Rejected: the Chroma factory module must stay importable only with the extra, and the test must run in the base install.

### D11. Documentation check also reads short citations and guides

Extend `tests/test_docs_references.py`:

- Add a second pattern for paths that start at `core/`, `transports/`, `integrations/`, `config/` or `daemon/`, end in `.py`, and are not part of a longer path. Resolve them below `src/omrg/`.
- Scan the root `AGENTS.md` and the ten folder guides as well as `docs/guides/` and `tests/TEST_README.md`.
- Change the example in `architecture.md:400` to `core/chunking/<name>.py`. The angle brackets stop the pattern from matching, so no suppression list is needed.

### D12. Folder guides

Each of the ten folders gets `AGENTS.md` and `CLAUDE.md -> AGENTS.md` (relative symbolic link, the same pattern as the repository root). Claude Code reads a nested `CLAUDE.md`; Codex and OpenCode read `AGENTS.md`. Each guide has at most 40 lines in this order: purpose (one or two lines), what belongs here, what must not be imported, 3 to 6 rules, links. Each guide links to the root `AGENTS.md` by a relative link. `tests/unit/test_agent_guides.py` checks presence, the link target, the line limit and the link back.

Rule drafts (each rule is verified against the cited file):

**`src/omrg/` (composition root)**
- Belongs: `__init__.py` (lazy public exports), `engine*.py`, `compose*.py`, `capabilities.py`, `pipeline_templates.py`. Business logic goes in `core/`.
- Not imported by `core/` (contract `core-never-imports-top-level-modules`; one sanctioned edge to `omrg.capabilities`).
- `compose.py` is the only production caller of `get_settings()`. Resolve settings once and inject them.
- `compose.build_engine()` is the single construction path for an Engine. Only `omrg.compose` imports a concrete provider module (contract `providers-constructed-only-in-compose`).
- Resolve strategies through registries. Do not branch `if/elif` over strategy names.
- Public names are in `omrg.__all__` only.
- A new top-level module needs an entry in `tests/unit/test_verification_gaps_boundaries.py` and in the contract above. Prefer a module under `core/`.

**`src/omrg/core/`**
- Must not import `omrg.transports`, top-level `omrg` modules (except the sanctioned edge), or `mcp`, `typer`, `click`.
- Take `EffectiveSettings` as a parameter. There is no settings singleton.
- A new strategy is one new file plus one `register()` line in the domain `registry.py`.
- `core/ingestion/` and `core/retrieval/` never import each other.
- Graph construction stays deterministic: no LLM call in code graph, document graph or community detection.
- When you fix an import-linter violation, delete its `ignore_imports` entry.

**`src/omrg/core/vectordb/`**
- Belongs: the shared contract at the root (D3 list); LanceDB code in `lancedb/`; Chroma code in `chroma/` (optional `chroma` extra).
- `lancedb` is imported only in `lancedb/` and `chromadb` only in `chroma/` (contracts `lancedb-confined-to-vectordb`, `chromadb-confined-to-vectordb`). `legacy.py` never imports `chromadb`.
- Put backend code in its backend folder. `tests/unit/test_folder_layout.py` fails otherwise.
- Keep each backend `__init__.py` free of imports.
- Add a backend with one folder and one `register()` call in `registry.py`, using `module:attr` strings.
- A new SDK import site needs an exact `ignore_imports` entry in `pyproject.toml`.
- Every backend passes `tests/test_vectordb_contract.py`. Chroma tests skip without the extra; CI runs them in the chroma-extra job.

**`src/omrg/core/retrieval/`**
- Must not import `omrg.core.ingestion` (contract `retrieval-stays-independent-of-ingestion`).
- Read `top_k`, thresholds and reranker flags from the injected settings (ADR-018). Do not hardcode them.
- Do not change the ÷30 rerank threshold scaling without re-running `experiments/1-reranker-threshold-calibration-2026-05-12/`.
- Reranker tests call `reset_model_cache()` (`_reranker_cache.py`) in setup and teardown.
- A sparse backend is one file plus one `register()` line in `sparse_registry.py`.
- PyTorch stays off the default path; `reranker_torch.py` needs the `torch` extra (ADR-073).

**`src/omrg/core/ingestion/`**
- Must not import `omrg.core.retrieval` (contract `ingestion-and-retrieval-stay-independent`).
- `ingest_path_async` in `pipeline.py` is the only entry point. All ingestion is async.
- `content_type` metadata wins over the file extension when the chunker picks a strategy.
- Use markdown chunking when the suffix is `.md` or the reader set `text_format == "markdown"` (ADR-055). A PDF that emits markdown keeps its headings only through `text_format`.
- PDF readers come from `integrations/pdf/factory.py`; tests run with `PDF_READER=pypdf`.
- Document backends register in `backends/registry.py`.

**`src/omrg/core/pipelines/`**
- Must not import `omrg.core.ingestion`, `omrg.core.retrieval`, `omrg.core.answer`, `omrg.core.providers`, `omrg.transports`, `subprocess`, `sqlite3`, `fastapi`, `starlette`, `uvicorn` or `marimo` (contract `pipeline-runner-independent-of-domains`).
- Adapters receive every resource and setting through `NodeContext` (`adapters.py`). Never read a process default.
- A new operation is one adapter in its domain package plus one `catalogue.register()` line. Never branch on operation names.
- Validate the whole graph before any side effect.
- A graph cannot override host-owned settings (`levers.py`).

**`src/omrg/transports/`**
- No business logic. Validate input, delegate to `core/` or the Engine, format output. `core/` never imports this package.
- MCP: never raise from a tool handler; return `{"status": "error", "message": ...}` (helpers in `mcp/errors.py`). Put `ToolAnnotations` (`readOnlyHint`, `destructiveHint`) on every tool.
- CLI: print with `Console(stderr=True)`. Stdout is the MCP protocol channel.
- API: route groups live in `api/routes/`. Keep `api/openapi.yaml` in step; the OpenAPI conformance tests compare it with the running routes. `api/__init__.py` imports nothing, so the `web` extra stays optional.

**`src/omrg/integrations/`**
- Must not import `omrg.core`, `omrg.transports` or `omrg.daemon` (contract `integrations-are-leaves`). The sanctioned exceptions read `omrg.core.settings` only.
- Import optional SDKs inside functions, never at module top (ADR-024; `azure.py` `_get_client()`).
- Degrade gracefully when an optional dependency or cloud service is missing.
- A test patches an availability probe at its own module, for example `omrg.integrations.magika`.
- A new module needs a row in the integration inventory in `docs/guides/architecture.md` (`tests/test_strategy_registration_inventory.py`).

**`web/src/`**
- Belongs: one folder per area; primitives in `components/ui/`; API clients in `api/`; helpers in `lib/`.
- Read `web/DESIGN.md` first. `styles/tokens.css` is the only source of colour, type, spacing and radius. No literal colour in a component; no hand-written CSS file.
- Use the primitives in `components/ui/`. Do not copy their classes or wrap them to change height, radius or colour.
- Show a failure as one friendly line plus one action through `describeError` (`lib/errors.ts`). Send the raw message to the console.
- Keep `api/*.ts` types in step with `src/omrg/transports/api/routes/` and `openapi.yaml`.
- Keep files under 500 lines. Run `npm run lint`, `npm run typecheck` and `npm test` in `web/`.

**`tests/`**
- Front door: `TEST_README.md`.
- Build settings with the `effective_settings(**overrides)` fixture or `set_default_effective_settings(...)`. Do not undo the conftest defaults (`PDF_READER=pypdf`, `extraction_mode="disabled"`).
- Patch a name at the module that defines it, not at a re-export.
- Reranker tests call `reset_model_cache()`. Restore any logging handler or level that a module changes.
- A new fast test changes `_BASE_EXECUTED` in `test_clean_base_tripwire.py`; a new slow test changes `_BASE_DESELECTED`. Update the count with a dated comment.
- Parallel runs use `--dist loadfile`. Do not pass `--dist load`.

The `transports/` guide must not contain an HTML embed tag: `tests/unit/test_notebooks_guide.py:121` scans `.md` files under `transports/` for `<iframe`, `<embed` and `<object`.

### D13. Guides stay out of the wheel

Add `exclude = ["AGENTS.md", "CLAUDE.md"]` to `[tool.hatch.build.targets.wheel]`. A pattern without a slash matches at any depth, and `exclude` wins over `packages` (Hatch build docs). Extend `scripts/check_web_wheel.py` to report every wheel entry whose last path part is `AGENTS.md` or `CLAUDE.md`, so the existing local CI and release steps check a real wheel. `tests/unit/test_agent_guides.py` checks the `exclude` entry in `pyproject.toml`.

Alternative: a slow pytest that builds a wheel, as in `tests/unit/test_plugin_marimo_manifest.py:79-91`. Rejected: it changes `_BASE_DESELECTED` and duplicates the wheel build that local CI and release already run.

### D14. Spec ownership

This change owns `vectordb-abstraction`, `internal-maintainability` and `architecture-boundary-enforcement`. It also modifies `lancedb-vector-store`, because 7 of its requirement texts cite moved files. No other active change has a delta for `lancedb-vector-store` (checked `openspec/changes/*/specs/` on 2026-10-16).

### D15. Backend classes are internal; the guide says so

`LanceVectorStore` is not in `omrg.__all__`, so it is internal. `docs/guides/library-usage.md:49,184` changes to `from omrg.core.vectordb.lancedb.store import LanceVectorStore`. The guide adds one sentence: "Backend classes such as `LanceVectorStore` are internal and can move in any release. The public API is `omrg.Engine`." The commit type is `refactor:`, with a note in the body that names the old and new import path.

- Alternative: a lazy PEP 562 `__getattr__` in `lancedb/__init__.py` that keeps the old import line working. Rejected: it breaks D4 (no re-export shims, ADR-037).
- Alternative: export `LanceVectorStore` from `omrg.__all__`. Rejected: it makes a backend class public API, a `feat:` change that nobody asked for.

### D16. This change lands first

This change lands before `unify-profiles-and-pipelines`, `add-profile-embedding-model`, `clarify-canvas-steps`, `add-pdf-reader-step-setting` and `studio-profiles-gallery` start their apply step. The move is mechanical and short, and it gives them the final paths. Those five changes already cite the new paths (updated on 2026-10-16) and say in their proposals that they land after this change. They plan two new route files at the new paths: `transports/api/routes/profiles.py` (`unify-profiles-and-pipelines`) and `transports/api/routes/embedding.py` (`add-profile-embedding-model`).

- Alternative: land this change last and move the new route files with it. Rejected: two more files to move, and the D8 layout check would fail on the new files at the API root.

## Risks / Trade-offs

- [A function-level relative import has the wrong level and fails only when the function runs] → D6 layout test resolves every relative import from the syntax tree.
- [A guard keeps passing but checks nothing after the move] → D9 repairs the two known cases, and each repaired guard gets a case that fails first.
- [A stale registry string silently turns native sparse search off] → D10 test fails on the string, without importing the SDK.
- [Chroma-gated tests do not run in the base install] → Ask the user before the chroma extra is installed; with approval, run the gated files in a throwaway environment. Otherwise the CI chroma-extra job carries them.
- [Library users who copied `from omrg.core.vectordb.lancedb import LanceVectorStore` break] → The name is internal by `omrg.__all__`. The guide changes to the new path, lists it under "Advanced imports", and says that backend classes are internal and can move (D15). The commit body names the old and new path.
- [Import rewrites push `lancedb/store.py` past 500 lines] → The new import lines are no longer than the old ones. Run the file-size test after `ruff format`.
- [Other active changes cite old paths, and two of them add new route files] → They now cite the new paths (D16). The D8 layout check rejects a new route file at the API root.
- [A Windows checkout without symbolic links turns `CLAUDE.md` into a text file] → The root already uses this pattern. The guide test runs on the CI platforms (Linux and macOS).
- [`git mv` with edits in the same commit can hide history] → Move first and edit second inside each group, or check `git log --follow` on one moved file before you commit.
- [The tripwire executed count drifts] → Measure it once at the end and update `_BASE_EXECUTED` with a dated comment.

## Migration Plan

1. Land this change before the five other changes in D16 start their apply step.
2. Before each of those changes starts apply, check that it cites no old path: run the task 5.7 search on its change folder.
3. Rollback: revert the commits. No data, setting or stored artefact changes, so no data step is needed.

## Open Questions

None. The library import is decided in D15, and the order in D16.
