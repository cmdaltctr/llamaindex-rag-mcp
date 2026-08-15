## 1. Baseline and Contract Tests

- [x] 1.1 Add regression tests that run existing codebase and document Louvain detection repeatedly and demonstrate the current unseeded determinism gap.
- [x] 1.2 Add shared partition-contract tests for complete, disjoint, non-empty node coverage and the existing fewer-than-five-node bypass.
- [x] 1.3 Record current codebase and document community output shapes so strategy extraction cannot alter labels, categories, edge counts, hubs, bridges, or cross-links.

## 2. Community Strategy Core

- [x] 2.1 Create `core/community/` with the flat partition protocol and a lazy strategy registry modelled on the existing chunking and provider registries.
- [x] 2.2 Implement and register the built-in NetworkX Louvain strategy with injected seed support and a default seed of `0`.
- [x] 2.3 Add immutable community algorithm and seed fields to the settings models and propagate them into `EffectiveSettings`.
- [x] 2.4 Thread `EffectiveSettings` from the codebase-map boundary into codebase and document community detection without adding a global settings lookup.
- [x] 2.5 Replace both direct Louvain calls with registry resolution while preserving their existing small-graph and error-handling behaviour.
- [x] 2.6 Add startup validation for unknown community strategy names and list available names in the error.

## 3. Optional Leiden Integration

- [x] 3.1 Verify `leidenalg` and `igraph` wheel support, Python compatibility, locked size, and dependency-floor impact on every supported platform before declaring version floors.
- [x] 3.2 Add a `community-leiden` optional dependency extra without changing the base installation.
- [x] 3.3 Create an acyclic lazy `integrations/leidenalg.py` adapter that preserves stable node identifiers, isolated nodes, edge weights, resolution semantics, and the injected seed during NetworkX-to-igraph conversion.
- [x] 3.4 Implement and register the flat Leiden strategy against the shared partition contract.
- [x] 3.5 Make explicit Leiden selection fail at startup with an installation instruction when the optional dependency is unavailable; do not silently fall back to Louvain.
- [x] 3.6 Compare Louvain and Leiden runtime, partition coverage, connectivity, and determinism on representative codebase and document graph fixtures; record results for the architectural decision.

## 4. Complete Integrations and Registry Eligibility Audit

- [x] 4.1 Recursively inventory every Python module under `src/rag_mcp/integrations/`, including package facades, Azure, Magika, the PDF factory, all three PDF adapters, and the new Leiden adapter; record a baseline module count.
- [x] 4.2 Record each integration module's native or optional availability, configuration selector, shared contract, fallback owner, callers, and disposition as registry strategy, capability integration, factory, facade, or direct implementation.
- [x] 4.3 Audit community detection, chunking, metadata extraction, embedding providers, LLM providers, sparse retrieval, and reranking using the same classification criteria.
- [x] 4.4 Verify Magika against the criteria and document whether it remains a single capability integration or has interchangeable configured implementations requiring registration.
- [x] 4.5 Verify whether concrete `pypdf`, `pypdfium2`, and `liteparse` implementations must register behind the existing `auto` factory; preserve the factory's capability-resolution role and ADR-020 semantics.
- [x] 4.6 Verify whether `document_backend=local|azure` forms one interchangeable strategy contract; retain current credential degradation until a dedicated migration is approved.
- [x] 4.7 Register confirmed missing strategy implementations whose migration preserves behaviour, dependency boundaries, factory APIs, and persisted-data compatibility.
- [x] 4.8 Create separate OpenSpec follow-up proposals for audit findings that would change defaults, public behaviour, fallback semantics, dependencies, or stored data.
- [x] 4.9 Add contract tests that compare documented configurable strategy names with live registries and fail when any `integrations/**/*.py` module is absent from the maintained inventory.

## 5. Architecture and Behaviour Verification

- [x] 5.1 Extend import-linter coverage to include `core.community` and enforce the acyclic `core → integrations` dependency direction.
- [x] 5.2 Test both strategies through codebase and document graph consumers, including deterministic membership, unknown-name failure, missing-extra failure, weighted edges, and isolated nodes.
- [x] 5.3 Confirm community detection makes no LLM call and that no algorithm-specific object escapes the shared strategy boundary.
- [x] 5.4 Confirm a base-only lowest-direct dependency installation runs Louvain and the fast test suite without importing Leiden packages.
- [x] 5.5 Confirm an installation with the Leiden extra passes targeted graph tests on every supported Python version.

## 6. Documentation and Decision Record

- [x] 6.1 Document the community algorithm and seed settings in `.env.example`, configuration guidance, and graph documentation.
- [x] 6.2 Document installation and startup-error behaviour for the optional Leiden extra.
- [x] 6.3 Create an ADR recording the registry placement, flat partition contract, deterministic seed policy, and selection of `leidenalg` over NetworkX backends, graspologic, and a local algorithm port.
- [x] 6.4 Add the strategy-registration inventory and eligibility rule to the architecture guide, including the Magika classification.

## 7. Final Validation

- [x] 7.1 Run `openspec validate add-pluggable-community-detection --strict` and correct every validation error.
- [x] 7.2 Run targeted community, codebase-map, document-graph, settings, composition-root, dependency-floor, and import-contract tests.
- [x] 7.3 Run `uv run ruff check`, `uv run pyright`, and `uv run lint-imports` for affected modules.
- [x] 7.4 Ask for approval, then run the full fast suite with branch coverage and confirm all project coverage floors remain satisfied.
