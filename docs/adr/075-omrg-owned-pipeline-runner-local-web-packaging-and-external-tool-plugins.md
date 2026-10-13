# ADR-075: OMRG-Owned Pipeline Runner, Local Web Packaging, and External-Tool Plugins

**Date:** 2026-10-13
**Status:** Proposed
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Related:** [ADR-031](031-three-layer-config-compose-di.md) (config, compose, DI), [ADR-036](036-phase-5-refactor-transport-separation.md) (transport separation), [ADR-037](037-architecture-v2-conformance.md) (architecture v2 conformance), [ADR-042](042-dependency-floor-integrity.md) (dependency floors), [ADR-073](073-make-the-torch-extra-a-normal-choice.md) (optional extras)
**Change:** `openspec/changes/add-local-web-pipeline-workspace/` (design D1, D4, D6, D7, D10, D11)

## Context

OMRG runs its RAG operations through fixed paths: `Engine.ingest`, `Engine.search` and `Engine.answer` in `src/omrg/engine.py`. Users want to connect stages on a canvas, run the resulting graph, and inspect the evidence. Experiment notebooks need the same operations.

Three questions need a decision:

1. Who owns graph execution, and who owns the expensive resources (embedder, store, reranker, LLM, OCR routes)?
2. How does a local web application ship and store its records without new services or a Node runtime?
3. How does an optional notebook editor (marimo) connect without becoming an OMRG dependency?

Constraints:

- Settings are injected, never global (ADR-031, ADR-037). `compose_engine.py` builds the resources.
- `core/` never imports `transports/` (ADR-036).
- PyTorch stays out of the base install (ADR-073). Dependency floors are tested (ADR-042).
- The HTTP transport has an OpenAPI contract in `src/omrg/transports/api/openapi.yaml` but no runtime.
- Source lineage and replacement safeguards (`core/ingestion/source_state.py`, `core/ingestion/replacement.py`) must not be bypassed.

## Decision

### 1. OMRG owns a small graph runner in `core/pipelines/` (design D1, D4)

1. Graph validation and scheduling live in a new `core/pipelines/` package. The runner handles finite acyclic graphs, typed ports, joins, and a bounded number of ready branches.
2. The runner receives an operation catalogue and adapters by injection from the composition root. It does not import `core/ingestion`, `core/retrieval`, `core/answer`, `core/providers`, `transports`, `subprocess`, FastAPI, Starlette, Uvicorn, or marimo.
3. Domain adapters stay in their owning packages and use the existing strategy registries. A new operation is one adapter plus one registration. The runner has no name-specific branches.
4. Adapters pass `store` and `settings` explicitly. They reuse the existing ranking, threshold, chunking, citation, and replacement code. The runner contains no second implementation of these algorithms.
5. Application services for revisions, runs, and events live in a new `core/workspace/` package. It does not import ingestion, retrieval, answering, transports, or FastAPI.
6. Import-linter contracts in `pyproject.toml` enforce items 2 and 5.

### 2. The Engine owns resources; jobs borrow them (design D6)

1. `Engine` gains `validate_pipeline(...)` and async `run_pipeline(...)`. Graph types are exported lazily next to the existing public names.
2. A graph run leases the Engine's existing embedder, store, reranker, answer resources, and OCR routes. A run never constructs a provider, changes `.env`, or downloads a model.
3. Validation errors occur before any side effect. Cancellation is cooperative: it stops scheduling and checks before a commit. A commit that has started is allowed to finish.
4. `close()` during an active run fails clearly and leaves the Engine usable.

### 3. One local process with SQLite records and packaged assets (design D7, D11)

1. `omrg web` starts one Uvicorn process with reload disabled and one supervised run consumer. It binds to loopback only. There is no Redis, Celery, or multi-process model copy.
2. Application records (graph revisions, layouts, runs, events, plugin registrations) go in a separate SQLite file in the selected workspace. Vector data stays in its current store. A standard-library SQLite adapter sits behind an injected repository interface and stays an integration leaf.
3. The React/Vite frontend is built with npm during release preparation. Hatchling force-includes the built assets in the wheel. End users need no npm and no Node server.
4. FastAPI and Uvicorn are in an optional `web` extra. Imports, `omrg --help`, and existing commands work without it. Only `omrg web` reports the missing extra.

### 4. marimo connects through an external declarative manifest (design D10)

1. OMRG defines a minimal external-tool manifest: schema and plugin versions, capability identifiers, tested tool-version range, executable reference, and structured argument templates.
2. The marimo manifest, documentation, and starter notebook are distributed separately from the base wheel. The manifest contains no shell commands, import hooks, credentials, or install actions.
3. Operators install and update marimo outside OMRG, for example in an isolated `uv tool` environment. OMRG probes the registered executable. It never runs `uvx`, installs packages, or upgrades tools.
4. Neither marimo nor uv becomes an OMRG runtime dependency or enters the lock file. No graph or domain code imports marimo or uv. A generic process adapter owns process creation and cleanup.
5. Registering and enabling a plugin is an explicit trust decision.

## Consequences

### Positive

- The browser, notebooks, and Python callers share one implementation of each RAG operation and one owner for each resource.
- Boundary tests catch a runner or workspace import of a domain, transport, or web framework module.
- The base install keeps its current dependency set. The web extra and the notebook plugin stay optional.
- A marimo update normally needs no OMRG release.

### Negative

- Stage extraction can change ranking or citations if done wrongly. Parity fixtures against the existing operations are required.
- A single process limits throughput. Blocking inference can finish after cancellation is requested.
- Two stores (SQLite and the vector store) can disagree after a crash. A crashed run is marked interrupted and needs inspection before retry.
- The release process gains an npm build step and a check that the wheel contains the built assets.
- An incompatible marimo CLI change disables the plugin until the manifest or host capability is updated.

### Neutral

- Existing Engine methods, MCP signatures, CLI commands, and RAG defaults do not change.
- Device-aware optimisation is deferred to a later change. That change can offer **Quick**, **Standard** and **Full** modes
  (design D12 of `add-local-web-pipeline-workspace`). This change adds no optimiser code, endpoint, control or dependency for it.

## Alternatives Considered

1. **Django (ORM and admin).** Rejected for this release. It suits a larger database-driven application. The first local workspace needs finite typed graphs and existing Pydantic models, so Django adds little.
2. **A standalone workflow framework** for scheduling. Rejected. The runner needs finite typed graphs, bounded scheduling, and the existing OMRG operations and safeguards. A general framework adds a dependency and a second execution model.
3. **A companion Python entry-point plugin package** for marimo. Rejected. It must be installed into OMRG's environment for discovery and adds a separate publishing lifecycle.
4. **A pinned optional `marimo` extra.** Rejected. It couples marimo dependency resolution and update cadence to OMRG's lock file.

## References

- `openspec/changes/add-local-web-pipeline-workspace/proposal.md`
- `openspec/changes/add-local-web-pipeline-workspace/design.md` (D1, D4, D6, D7, D10, D11)
- `openspec/changes/add-local-web-pipeline-workspace/specs/architecture-boundary-enforcement/spec.md`
- `openspec/changes/add-local-web-pipeline-workspace/specs/notebook-plugins/spec.md`
- `openspec/changes/add-local-web-pipeline-workspace/specs/local-web-workspace/spec.md`
- `openspec/changes/add-local-web-pipeline-workspace/specs/pipeline-graphs/spec.md`
- `src/omrg/engine.py`, `src/omrg/compose_engine.py`
- `src/omrg/transports/api/openapi.yaml`
- `pyproject.toml` (`[tool.importlinter]`)
- `tests/test_contract_coverage.py`, `tests/test_no_global_settings_reads.py`, `tests/test_no_torch_at_runtime.py`, `tests/test_dependency_floors.py`

Accept this ADR only after the change's verification evidence passes (task 9.3).
