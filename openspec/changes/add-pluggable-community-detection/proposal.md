## Why

Codebase and document graphs call NetworkX Louvain directly, without a seed or an extension point. This makes uncached partitions non-deterministic and prevents operators from selecting Leiden without coupling external dependencies to both graph subsystems.

The project also lacks a written rule for deciding when a selectable implementation belongs in a registry and when a module should remain a capability integration, such as Magika. This change adds that rule and audits the current modules against it.

## What Changes

- Add a shared community-detection strategy registry under `core/community/` for codebase and document graphs.
- Keep seeded NetworkX Louvain as the built-in default strategy.
- Add flat Leiden as an optional strategy backed by a lazy `leidenalg` integration and optional dependency extra.
- Inject the configured strategy name and seed through `EffectiveSettings`; explicit Leiden selection fails at startup with an installation instruction when its dependency is unavailable.
- Preserve existing community output models, labels, small-graph handling, hub detection, bridge detection, and the no-LLM graph-construction invariant.
- Add deterministic partition tests and shared strategy-contract tests for both graph consumers.
- Audit every Python module recursively under `src/rag_mcp/integrations/`, including package facades, Azure, Magika, the PDF factory, and every PDF adapter. No current or future integration module may remain unclassified.
- Audit strategy-like modules outside `integrations/`, including sparse retrieval, metadata extraction, providers, chunking, reranking, and other name-dispatched implementations.
- Define registry eligibility: interchangeable implementations selected by configuration use a registry; external capability adapters, single implementations, and ordered capability factories remain integrations or factories.
- Treat `native` and `registered` as independent classifications: a base-install implementation still registers when it belongs to a configured strategy family, while an optional integration adapter does not self-register unless it is the strategy boundary.
- Register confirmed missing strategy implementations when migration preserves behaviour. Record behaviour-changing or dependency-changing findings as follow-up OpenSpec changes.

## Capabilities

### New Capabilities

- `community-detection-strategies`: Configurable, deterministic Louvain and optional Leiden partitioning shared by codebase and document graphs.
- `strategy-registration-governance`: Rules and an auditable inventory for deciding which implementations require registry dispatch.

### Modified Capabilities

- `architecture-boundary-enforcement`: Add `core.community` to the enforced core package set and define the allowed dependency direction between community strategies and external integrations.

## Impact

- **Core**: new `core/community/` registry and strategy modules; settings are threaded into codebase and document community detection.
- **Integrations**: new lazy `integrations/leidenalg.py` adapter with no import back into `core/`; complete classification audit of every existing module under `src/rag_mcp/integrations/`.
- **Configuration**: new community algorithm and seed fields; Louvain remains the default.
- **Dependencies**: optional `leidenalg` and `igraph` installation only for operators selecting Leiden. No new base dependency.
- **Specifications**: new community strategy and registry-governance contracts; architecture boundary contract extended for the new package.
- **Documentation**: configuration guidance, optional-extra installation guidance, an architecture decision record, and a registry eligibility audit.
- **Compatibility**: default behaviour remains Louvain, but its fixed seed can produce a different first partition from a previous unseeded uncached run.
