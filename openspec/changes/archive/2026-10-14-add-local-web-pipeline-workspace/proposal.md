# Proposal: Local web pipeline workspace

## Why

OMRG's modular operations need a local workspace where users can connect stages, execute the resulting graph, and inspect the evidence. A shared graph runner will let the browser and experiment notebooks use the existing RAG algorithms and safeguards.

## What Changes

- Require `repair-modular-core-boundaries` to be implemented, verified, and integrated into the starting checkout before this change is applied. Its production-dispatch, owning-store taxonomy, injected cache, and fresh-import regressions are the entry gate.
- Add an optional FastAPI web transport, launched with `omrg web`, for individual use on the same machine. Serve a packaged React application without a Node server at runtime.
- Add an OMRG-owned runner for user-defined acyclic graphs. Saved connections determine execution, including compatible branches and joins. Templates are editable starting points.
- Reuse domain registries, algorithms, injected settings, provider ownership, source lineage, and vector-store contracts. Extract stage boundaries only where the current orchestration combines operations.
- Add typed node contracts, graph validation, per-run profile snapshots, bounded execution, cooperative cancellation, and engine-produced events.
- Use SQLite for graph revisions, layouts, run summaries, events, and plugin registrations. Keep documents and vectors in their existing stores.
- Provide Canvas, Library, Search, Ask, Runs, Experiments, and Settings views. Use the warm neutral OMMS design direction, accessible controls, and light/dark themes.
- Add a minimal external-tool plugin contract. Supply marimo as a separately distributed manifest, with its executable installed and updated outside OMRG's environment. Open its editable interface in a separate local browser tab.
- Preserve existing Engine methods, MCP signatures, CLI commands, profile previews, citation guarantees, and ingestion recovery behaviour. Add public graph types and graph validation/execution methods.
- Record device-aware **Quick**, **Standard**, and **Full** optimisation as a later change. Add no optimiser implementation, inactive controls, or speculative tuning framework here.

No existing public API is intentionally broken. Enabling the web transport and registering a notebook plugin are explicit actions.

## Capabilities

### New Capabilities

- `pipeline-graphs`: Versioned executable graphs, typed stage contracts, profile resolution, branch/join execution, and domain safeguards.
- `pipeline-run-records`: Local graph revisions, run snapshots, sequenced events, cancellation, restart interruption, and bounded artefact storage.
- `local-web-workspace`: Packaged local server, protected APIs, document workflows, runtime ownership, and optional web dependencies.
- `pipeline-canvas`: Editable React Flow graphs, node controls, event-driven execution views, evidence inspection, and accessible application navigation.
- `notebook-plugins`: Optional external-tool manifests, independently managed marimo installations, trusted notebook launch, and shared graph execution from notebooks.

### Modified Capabilities

- `public-library-api`: Export stable graph/result/event/error types and add Engine graph validation/execution without import-time setup.
- `engine-scoped-composition`: Lease existing resources to graph runs and preserve ownership, isolation, and lazy answering.
- `modular-core-extraction`: Permit async graph ingestion through shared internal stages while preserving existing operation behaviour.
- `transport-separation`: Implement the previously deferred HTTP transport and retain the reviewed OpenAPI contract and thin-handler boundary.
- `architecture-boundary-enforcement`: Cover the new packages and enforce runner independence from domain implementations and web frameworks.

## Impact

**Core:** Proposed `core/pipelines/` and `core/workspace/`; small adapters in the existing ingestion, retrieval, and answer packages; composition wiring and Engine additions. Existing strategy registries remain the implementation dispatch mechanism.

**Web:** `transports/api/` runtime modules, one CLI command module, a `web/` React/Vite application, and packaged static assets. FastAPI and Uvicorn belong to an optional `web` extra. Frontend dependencies require approval during implementation. Use npm, Vitest, and focused browser checks.

**Persistence and plugins:** A standard-library SQLite adapter stores application records separately from vector data. A generic process adapter launches approved external tools. The first-party marimo manifest, documentation, and starter notebook live outside the base Python package; neither marimo nor uv becomes an OMRG runtime dependency.

**Prerequisite:** The repair change owns the three confirmed correctness fixes. This change verifies their integrated commit and regression results, then reuses the repaired interfaces. Checked boxes or archived planning files alone do not satisfy the gate.

**Verification:** Graph contract tests, parity fixtures against existing operations, import-boundary tests, index/lineage safeguards, API conformance, packaged-wheel smoke tests, and browser evidence. Record architectural choices in a proposed ADR during implementation, then accept it after verification.

**Risks:** Incorrect stage boundaries could weaken score or replacement guarantees. Model calls can outlive cancellation requests. Notebook editors execute trusted Python with the user's permissions. The design includes explicit safeguards and release tests for these risks.

**Deferred:** Automatic optimisation, feedback loops, arbitrary Python canvas nodes, distributed workers, hosted multi-user access, collaboration, plugin marketplaces, automatic plugin installation/updating, and embedding the full marimo editor.
