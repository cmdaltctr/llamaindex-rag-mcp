# Proposal: organise backend folders

## Why

`src/omrg/core/vectordb/` holds 22 files in one flat folder. Ten of them are LanceDB code (`lancedb.py`, `lance_*.py`) and three are Chroma code (`chroma.py`, `chroma_cloud.py`, `paged.py`), next to nine shared contract files. A reader cannot see which file belongs to which database. `src/omrg/transports/api/` has the same problem: 14 route files sit beside 19 support files. Agents that work in these folders also have no local guidance: the only `AGENTS.md` is at the repository root, and its Architecture Invariant 2 is wrong (it says `src/omrg/` holds only `__init__.py` and `compose.py`; it holds 13 modules).

The user asked for one folder per database ("a lancedb folder with all lancedb stuff, a chroma folder with all chroma stuff"), a look at other folders, and short `AGENTS.md` files that tell future agents how to use each folder.

## What Changes

- Move the LanceDB modules into `core/vectordb/lancedb/` and the Chroma modules into `core/vectordb/chroma/`. Drop the backend prefix from file names inside each folder (`lancedb.py` becomes `lancedb/store.py`, `lance_filter.py` becomes `lancedb/filter.py`, `chroma_cloud.py` becomes `chroma/cloud.py`). The shared contract files stay at `core/vectordb/`.
- Move the 14 HTTP route modules into `transports/api/routes/` (`routes_documents.py` becomes `routes/documents.py`; `routes.py` becomes `routes/foundation.py`).
- Update every importer in the same change: source, tests, `experiments/_lib/storage.py`, `scripts/chroma_cloud_smoke.py`, the lazy vector-store registry strings, the import-linter ignore entries, docs and main specs. No re-export shims (ADR-037).
- Add executable guards so the layout stays: a vector-store backend file at the `core/vectordb/` root fails a test, a route file at the `transports/api/` root fails a test, every relative import in the moved folders must resolve, and SDK imports are confined to their backend folder.
- Extend the documentation path check so short citations such as `core/vectordb/lancedb.py` (written without `src/omrg/`) must also resolve.
- Add a short `AGENTS.md` and a `CLAUDE.md -> AGENTS.md` symlink to 10 folders: `src/omrg/`, `src/omrg/core/`, `core/vectordb/`, `core/retrieval/`, `core/ingestion/`, `core/pipelines/`, `src/omrg/transports/`, `src/omrg/integrations/`, `web/src/`, `tests/`. Keep them out of the wheel.
- Fix root `AGENTS.md` Invariant 2 and add a list of the folder guides.
- No behaviour change: settings, environment variables, stored data, HTTP paths, MCP tools and CLI output stay the same.
- **BREAKING (internal imports only):** code that imports `omrg.core.vectordb.lancedb`, `omrg.core.vectordb.chroma`, `omrg.core.vectordb.lance_*`, `omrg.core.vectordb.paged` or `omrg.transports.api.routes_*` must use the new paths. None of these names is in `omrg.__all__`. `docs/guides/library-usage.md` shows `from omrg.core.vectordb.lancedb import LanceVectorStore`; the guide changes to the new path and says that backend classes are internal and can move. The public API is `omrg.Engine`.

### Out of scope (follow-ups, not planned here)

| Candidate | Reason to wait | Size |
| --- | --- | --- |
| `src/omrg/` top level: 7 `compose_*.py`, `engine.py`, `engine_answer.py`, `compose.py` into packages | 114 string patch targets of the form `"omrg.compose*.X"` in tests; `tests/test_core_import_contracts.py:95` and `tests/unit/test_verification_gaps_boundaries.py` pin the top-level module set | 10 modules, 243 test references |
| `graph_adapters*.py` in `core/ingestion/` (3) and `core/retrieval/` (4) into subpackages | Named one by one in three import-linter contracts (`pyproject.toml:315-347`) and in `tests/test_no_global_settings_reads.py:192-224` | 7 modules |
| `web/src/studio/` | Active uncommitted work on `feat/studio-canvas-layout` | n/a |
| Shared route helpers (`ok`, `validation_failure` in `routes_graphs.py`; `ManageScope`, `TRUST_NOTICE` in `routes_experiments.py`; stream helpers in `routes_runs.py`) | 7 route files import helpers from sibling route files; moving them is a design change, not a move | 3 modules |
| `codecov.yml` cites `src/omrg/transports/mcp.py`, which is now a package | Unrelated stale path found during the survey | 1 line |

Folders reviewed and left as they are: `core/pipelines/`, `core/metadata/`, `integrations/`, `web/src/experiments/`, `web/src/api/`.

Known stale after the move (left unrepaired by policy, ADR-037 "Negative"): archived experiment scripts that import the old paths inside functions that tests do not run: `experiments/18-*/harness.py`, `19-native-fts-*/build_index.py` and `run_eval.py`, `21-*/probe.py`, `22-*/build_index.py` and `run_eval.py`, `25-*/build_index.py` and `run_eval.py`, `26-*/run_eval.py`, `27-*/run_eval.py`, and the scripts under `experiments/example/`. Their recorded results do not change.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `vectordb-abstraction`: Chroma requirements name the `core/vectordb/chroma/` folder instead of `chroma.py`; new requirements for one folder per backend and for registry import strings that resolve.
- `lancedb-vector-store`: requirements that cite `lancedb.py`, `lance_meta.py`, `lance_filter.py` and `lance_paged.py` name the new paths; the single import site becomes `core/vectordb/lancedb/`.
- `architecture-boundary-enforcement`: the Chroma confinement requirement names the folder; new requirement that HTTP route groups live in `transports/api/routes/`.
- `internal-maintainability`: the documentation path check also resolves short citations and folder guidance files; new requirements for folder guidance files and for keeping them out of the wheel.

## Impact

- Source: `src/omrg/core/vectordb/` (13 files move, `registry.py` strings), `src/omrg/core/documents/doc_graph.py` (docstring), `src/omrg/transports/api/` (14 files move, `app.py` imports, `README.md`).
- Configuration: `pyproject.toml` (two import-linter ignore lists; Hatch wheel `exclude`).
- Tests: 46 test files import the vector-store backend modules; 3 test files import or scan the route modules; `tests/test_clean_base_tripwire.py` executed-count re-baseline.
- Scripts and experiments: `scripts/chroma_cloud_smoke.py`, `scripts/check_web_wheel.py`, `experiments/_lib/storage.py`.
- Docs: `docs/guides/architecture.md`, `configuration.md`, `reranker.md`, `library-usage.md`; root `AGENTS.md`; 10 new folder guides; comment paths in 5 `web/src/api/*.ts` files.
- Other active changes: this change lands first. `unify-profiles-and-pipelines`, `add-profile-embedding-model`, `clarify-canvas-steps`, `add-pdf-reader-step-setting` and `studio-profiles-gallery` already cite the new paths and land after it (design.md D16).
- Runtime, APIs, data and dependencies: no change.
