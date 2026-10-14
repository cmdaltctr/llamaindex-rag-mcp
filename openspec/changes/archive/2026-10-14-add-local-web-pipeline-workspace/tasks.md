# Tasks

Planning only. Every checkbox is implementation work and remains unchecked until approval, implementation, and verification.

Prerequisite: implement, verify, and integrate `repair-modular-core-boundaries` before applying this web change. Another session can implement the repair alone. This checklist reuses its repaired interfaces; it does not duplicate their implementation.

For each new behaviour, observe its test fail without the implementation, then pass after implementation. Record both outcomes. Use injected offline settings, deterministic fixtures, `PDF_READER=pypdf`, and reranker cache reset where required. Installs, model downloads, full test suites, commits, and external actions retain approval gates.

## 1. Scope, dependency and boundary setup

- [x] 1.0 Verify the integrated repair commit and focused regressions on the intended base; stop web implementation if readiness fails.
  - Run `tests/test_document_registry_dispatch.py`, `tests/test_metadata_store_ownership.py`, `tests/unit/test_codebase_context_repair.py`, and `tests/test_no_global_settings_reads.py`.
  - Compare results with the evidence in `openspec/changes/archive/2026-10-13-repair-modular-core-boundaries/evidence/`.
- [x] 1.1 Prepare the approved feature worktree and copy planning artefacts; verify repository root, branch, and unchanged environment files.
- [x] 1.2 Add the optional web dependency group after approval; verify base imports, torch-free resolution, and qualified dependency floors.
- [x] 1.3 Extend executable import boundaries for graph/workspace packages and adapters; prove intentional violations fail the boundary tests.
- [x] 1.4 Record a proposed ADR for runner ownership, local packaging, and external-tool plugins; verify its index entry and source references.

## 2. Graph contracts and admission

- [x] 2.1 Define versioned graph, result, event, and validation-error models; verify round trips, rejected versions, and lazy public exports.
- [x] 2.2 Add the operation catalogue and registration contract; test port schemas, capability reasons, parameter validation, and declared bypasses.
- [x] 2.3 Implement graph preflight; verify incompatible ports, missing inputs, cycles, executable strings, identity mismatches, and conflicting commits cannot execute.
- [x] 2.4 Add inherited/named-profile resolution and allowed overrides; test precedence, unchanged collection metadata, and immutable admission snapshots.
- [x] 2.5 Document graph inputs, profiles, connections, and validation errors in a pipeline guide; verify examples against model fixtures.

## 3. Reusable domain operations

- [x] 3.1 Extract retrieval sizing, policy, filtering, and fallback seams; run existing hybrid/threshold/policy tests and canonical parity fixtures.
- [x] 3.2 Adapt dense, sparse, fusion, reranker, and context operations; test score kinds, empty branches, rank provenance, and lineage preservation.
- [x] 3.3 Extract repaired source/read/normalise/enrich/chunk seams; retain dispatch/store-context regressions and test reader declarations plus bounded per-source processing.
- [x] 3.4 Adapt embedding and protected replacement; verify malformed vectors, invalid lineage, interrupted attempts, and mutation locks retain existing guarantees.
- [x] 3.5 Add ingestion graph fingerprints; test changed shaping operations reprocess sources while layout/query-only changes preserve reuse.
- [x] 3.6 Adapt answer preparation, synthesis, and verification; run no-evidence, citation, failure-attribution, and degraded-verification parity fixtures.
- [x] 3.7 Update ingestion/retrieval guides and architecture ownership; verify described paths, preserved defaults, and existing operation return shapes.
- [x] 3.8 Add each new graph-adapter module to the leaf list in `tests/test_no_global_settings_reads.py`. Add a behavioural test with poisoned process defaults; verify it fails when an adapter drops `store` or `settings`.

## 4. Execution and Engine ownership

- [x] 4.1 Implement bounded ready-node scheduling and joins; test completion-order independence, mutable fan-out isolation, and resource limits.
- [x] 4.2 Add actual node/unit events and failure propagation; verify skipped dependants, domain fallbacks, and directory per-file outcomes.
- [x] 4.3 Add Engine validation/execution methods and resource leases; verify the documented method set, lazy answering, and two-Engine isolation.
- [x] 4.4 Implement run-scoped cancellation; test queued cancellation, pre-commit cancellation, entered-commit completion, and blocking-call safe boundaries.
- [x] 4.5 Publish canonical ingestion/search/answer graph templates; prove parity with existing operations using deterministic recorded fixtures.
- [x] 4.6 Update the library/pipeline guides with execution and cancellation examples; verify examples without web or notebook dependencies.

## 5. Workspace records and local run service

- [x] 5.1 Add repository contracts and the standard-library SQLite adapter; test immutable revisions, separate layouts, backups, and schema migration rollback.
- [x] 5.2 Implement the bounded single-consumer service; test queue overflow, failed-job recovery, immutable snapshots, and ordered status/event transactions.
- [x] 5.3 Persist bounded outputs/events; test private permissions, secret redaction, reconnect sequences, and overlapping versus total timing.
- [x] 5.4 Handle shutdown/restart interruption and explicit retry; test that unfinished writes are never repeated automatically.
- [x] 5.5 Add previewed app-artefact cleanup and workspace documentation; verify source files, vectors, notebooks, and experiment outputs survive cleanup.

## 6. Local HTTP and packaged application

- [x] 6.1 Add `omrg web` and lifespan ownership; test lazy extra checks, unchanged no-argument MCP startup, and graceful resource drain.
- [x] 6.2 Add loopback/session/bearer protection; test remote binding rejection, invalid Host/Origin, bootstrap handling, scoped access, and credential redaction.
- [x] 6.3 Add canonical root grants and managed uploads; test traversal, symlink escape, metadata-path denial, file limits, and partial-upload cleanup.
- [x] 6.4 Implement reviewed document endpoints and protected chunk inspection; verify listing/search/answer shapes and existing profile/lineage semantics.
- [x] 6.5 Add preview-bound destructive actions; test altered selectors, stale validity tokens, backend guarantee warnings, and unchanged data before confirmation.
- [x] 6.6 Expose graph/revision/run/event/cancellation services; test direct invalid submissions, SSE replay, polling fallback, and disconnection without cancellation.
- [x] 6.7 Extend the versioned OpenAPI document and runtime conformance checks; verify fields, defaults, errors, authorisation, and job semantics.
- [x] 6.8 Add React/Vite packaging with approved npm dependencies; verify assets from an installed wheel outside the checkout without Node.
- [x] 6.9 Document launch, file grants, jobs, auth, and optional dependencies; exercise documented commands and verify API fallback never serves HTML errors.

## 7. Canvas and existing document workflows

- [x] 7.1 Build shared semantic styles and application navigation; verify light/dark themes, responsive inspectors, focus, and persisted draft state.
- [x] 7.2 Build catalogue-based nodes, controls, and connection editing; test schema validation, keyboard editing, profile inheritance, and real rewiring.
- [x] 7.3 Add revision saving, validation, execution, and cancellation controls; verify admitted snapshots survive later draft changes.
- [x] 7.4 Render real node/edge events and labelled replay; test no fabricated progress, reduced motion, fallback states, and reconnect deduplication.
- [x] 7.5 Add bounded node/evidence inspectors and Runs; verify rank/score-kind labels, truncation, citations, completed effects, and secret exclusion.
- [x] 7.6 Add Library, Search, Ask, and runtime Settings workflows; test upload, filters, source availability, and profile/deletion confirmation.
- [x] 7.7 Add frontend guide screenshots and attribution; capture browser evidence for affected screens and verify all documented actions.

## 8. Optional marimo plugin and experiments

- [x] 8.1 Implement constrained manifest registration and generic tool probing; test invalid recipes, changed registrations, incompatibility, and no implicit installation.
- [x] 8.2 Publish the separate marimo manifest/docs outside the base wheel; verify independent registration and external-version rechecks.
- [x] 8.3 Add owned editor launch/stop supervision; test loopback authentication, disabled startup execution/install behaviour, unrelated ports, and process cleanup.
- [x] 8.4 Qualify the supported marimo/uv versions after installation approval; record launch flags, configuration precedence, and independent-update results.
- [x] 8.5 Add approved experiment Engine contexts and scoped credentials; verify live-library mutation rejection and experiment-local backend/index identity.
- [x] 8.6 Add Experiments and the explicit-run starter notebook; verify shared graph execution, parameter changes without reruns, checkpoints, and revocation.
- [x] 8.7 Document notebook trust and stop/update/recheck/start; verify the app works without the plugin and never embeds a claimed full editor.

## 9. Integrated qualification and handoff

- [x] 9.1 Run an offline end-to-end rewired graph through browser and notebook clients; compare recorded graph, settings, outputs, and events.
- [x] 9.2 Run approved fast/coverage, frontend, OpenAPI, import, floor, wheel, and torch-free gates; record exact PASS/FAIL/NOT RUN results.
- [x] 9.3 Verify the implementation against all delta scenarios; validate OpenSpec strictly, update Graphify, and accept the ADR only after evidence passes.
- [x] 9.4 Confirm deferred optimisation has no endpoint, button, dependency, or unused scaffolding; retain Quick/Standard/Full in the later-change notes.

Do not archive, commit, push, or release automatically. Present verification evidence and request the next approval.
