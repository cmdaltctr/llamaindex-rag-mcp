## Context

Codebase and document graph modules currently call NetworkX Louvain directly. Both calls omit `seed`, despite the codebase community module claiming reproducibility. The modules then convert the returned node sets into different domain outputs, so only the partition operation is shared.

NetworkX 3.6 exposes a Leiden dispatch API but provides no default implementation. It requires an external backend such as cuGraph. The project supports NetworkX 3.2 and is local-first, so the NetworkX dispatch API is not a portable integration path. The official LlamaIndex GraphRAG cookbooks call `graspologic.partition.hierarchical_leiden`, but that code exists only in notebooks and brings substantial scientific-computing dependencies.

The architecture requires injected frozen settings, registry dispatch for named strategies, acyclic integration leaves, deterministic graph construction, and no cross-import between codebase and document graph subsystems.

## Goals / Non-Goals

**Goals:**

- Provide one flat partition contract shared by codebase and document graphs.
- Preserve Louvain as a base-install strategy and default behaviour.
- Offer deterministic Leiden through an optional dependency.
- Keep external-library conversion outside core business logic.
- Make registry eligibility consistent and auditable across the project.

**Non-Goals:**

- Port LlamaIndex cookbook `GraphRAGStore` or `GraphRAGQueryEngine` classes.
- Add hierarchical communities, community summaries, or global-query LLM calls.
- Replace existing `Community` or `DocCommunity` output models.
- Add cuGraph, GPU requirements, or a pure-Python Leiden implementation.
- Convert capability adapters such as Magika into registries without interchangeable configured implementations.

## Decisions

### 1. Add a shared community strategy package under core

Create `core/community/` as a sibling of `core/codebase/` and `core/documents/`. It owns the flat partition protocol, strategy registry, availability reporting, and strategy contract tests. Both graph consumers depend on this package and retain their domain-specific formatting.

This avoids a cross-import between graph subsystems. Duplicating dispatch in both consumers was rejected because strategy validation, seeding, and error handling would drift.

### 2. Use registry dispatch for community algorithms

The configured algorithm name resolves through a community registry. Concrete strategies live in separate modules and register against a callable contract returning `list[set[Hashable]]`. Consumer modules do not branch over `louvain` and `leiden`.

A single dispatch function was considered. The registry is preferred because the project already mandates registry dispatch for named strategies, and an optional Leiden strategy introduces independent availability and dependency behaviour.

The registry must follow the lazy-loading pattern used by existing chunking and provider registries. It must not import every concrete strategy at module import time.

### 3. Keep Louvain native and make Leiden optional

The Louvain strategy calls NetworkX directly with the injected seed. It remains available in the base installation and remains the default.

The Leiden strategy delegates to `integrations/leidenalg.py`. That adapter lazily imports `leidenalg` and `igraph`, converts NetworkX node identifiers to stable igraph indices, runs a flat partition with the injected seed, and maps memberships back to original nodes.

`leidenalg` is preferred over `graspologic` because this change needs a flat partition, not a hierarchy, and should avoid SciPy and scikit-learn as new transitive dependencies. NetworkX's Leiden API was rejected because it has no built-in implementation and its documented backend is unsuitable for the project's CPU-first baseline. A local algorithm port was rejected because algorithm maintenance and correctness exceed this project's responsibility.

The packages belong to an optional extra. They are not added to base dependencies.

### 4. Make algorithm selection explicit

Add cross-cutting immutable settings for the community algorithm and seed. The default algorithm is `louvain`; the default seed is `0`. `auto` selection is excluded because optional-package installation must not change graph output silently.

`compose.py` validates the selected registered name and probes optional strategy availability once. Selecting unavailable Leiden fails startup with an installation instruction. Runtime fallback to Louvain is rejected because an explicit algorithm setting is an operator contract.

The resolved settings instance flows from the codebase-map boundary into codebase and document community functions. Neither detector performs a global settings lookup.

### 5. Preserve the existing consumer contract

The shared strategy boundary returns only flat node sets. Codebase and document modules continue to handle small graphs before dispatch and continue formatting labels, categories, edge counts, hubs, bridges, and cross-links after dispatch.

The strategy contract validates complete, disjoint, non-empty coverage. It prevents igraph or Leiden-specific objects from leaking into core consumers.

### 6. Audit registry eligibility using a fixed taxonomy

The implementation produces an inventory with four classifications:

| Classification | Rule | Expected examples |
|---|---|---|
| Strategy registry | Configuration selects by name between interchangeable implementations | chunking, providers, community detection |
| Capability integration | One optional external capability or executable adapter | Magika, Azure SDK adapter |
| Factory | Ordered capability probing or fallback construction | PDF reader factory |
| Direct implementation | No configured alternative exists | single-purpose helpers |

The audit covers all current name dispatch and integration modules. Low-risk missing registrations are corrected in this change. Findings that alter defaults, public behaviour, dependencies, or persisted data become separate OpenSpec changes.

Magika is not assumed to require registration. It must be evaluated against the same rule. With one configured capability adapter and no interchangeable file-detector strategy family, it remains an integration.

`Native` is an availability property, not a dispatch category. A native implementation uses only base dependencies. It still registers when it belongs to a configured interchangeable family. An optional adapter can remain outside a registry when it supplies one capability and has no named peer contract.

The audit starts with this complete integration inventory:

| Current module | Availability | Preliminary classification | Required audit question |
|---|---|---|---|
| `integrations/__init__.py` | Native | Package facade | Does it export only stable integration APIs? |
| `integrations/azure.py` | Optional cloud dependency | Capability adapter; registry candidate with local document backend | Do `local` and `azure` satisfy one document-backend strategy contract, and can registration preserve graceful fallback? |
| `integrations/magika.py` | Optional executable | Capability adapter with suffix fallback | Is Magika selected by a strategy name or only used as an availability-enhanced detector? |
| `integrations/pdf/__init__.py` | Native | Public package facade | Does it expose only the factory contract? |
| `integrations/pdf/factory.py` | Native | Capability-resolution factory | Can `auto` remain in the factory while concrete names resolve through a registry? |
| `integrations/pdf/pypdf.py` | Base dependency | Native PDF strategy candidate | Must it register with optional PDF readers because `pdf_reader` selects it by name? |
| `integrations/pdf/pypdfium.py` | Optional dependency | Optional PDF strategy candidate | Can it register lazily behind the existing factory API? |
| `integrations/pdf/liteparse.py` | Optional dependency | Optional PDF strategy candidate | Can it register lazily behind the existing factory API? |
| `integrations/leidenalg.py` | Optional dependency, new | External capability adapter | The adapter does not self-register; `core/community` registers the Leiden strategy that delegates to it. |

The likely PDF disposition is a registry-backed factory: `auto` remains composition and capability probing, while concrete `pypdf`, `pypdfium2`, and `liteparse` readers resolve through a registry. The implementation task must confirm this against ADR-020 and create a separate change if migration affects fallback semantics.

The Azure disposition remains deliberately unresolved until the audit compares the local and cloud document-backend contracts. Existing credential degradation makes this more likely to need a separate proposal than an in-place refactor.

## Risks / Trade-offs

- **Optional native wheels may be unavailable for a supported platform** → Keep Leiden outside the base install, test installation on supported Python and macOS versions, and fail with a clear message.
- **NetworkX-to-igraph conversion can lose node or weight data** → Preserve stable node identifiers and edge weights explicitly; test weighted and isolated-node graphs.
- **Seeded Louvain can differ from a previously cached random partition** → Document the change and rely on the existing git-commit cache key to rebuild after implementation.
- **A broad registry audit can expand scope** → Apply only behaviour-preserving corrections; create follow-up changes for larger findings.
- **A registry adds more files than a binary branch** → Accept the small structural cost to satisfy the project's strategy-dispatch invariant and future extension model.
- **Flat Leiden omits GraphRAG hierarchy** → Keep hierarchy and LLM summaries as separate capabilities with separate cost and data contracts.

## Migration Plan

1. Add deterministic seeding to the existing Louvain path and lock its behaviour with tests.
2. Introduce the shared registry while registering Louvain only; confirm both graph consumers retain output contracts.
3. Add the optional Leiden adapter, strategy registration, and installation extra.
4. Add startup validation and settings documentation.
5. Run the registry eligibility audit and make only behaviour-preserving corrections.
6. Run strict OpenSpec validation, import-linter, dependency-floor tests, targeted graph tests, and the fast test suite.

Rollback removes the Leiden extra and strategy registration, then restores direct seeded Louvain through the shared contract. Existing stored vectors and documents need no migration.
