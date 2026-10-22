# src/omrs/core (business logic)

All domain logic: ingestion, retrieval, pipelines, vector stores, providers, profiles, settings models and graphs.

## What belongs here

- One folder per domain. Strategies register through a registry.
- Pure settings data models in `settings.py` and the `*/settings.py` files.

## What it must not import

- `omrs.transports`, any top-level `omrs` module (one sanctioned edge), `mcp`, `typer` or `click`.

## Rules

1. Take `EffectiveSettings` as a parameter. There is no settings singleton.
2. A new strategy is one new file plus one `register()` line in the domain `registry.py`.
3. `core/ingestion/` and `core/retrieval/` never import each other.
4. Graph construction stays deterministic. Do not call an LLM in the code graph, the document graph or community detection.
5. When you fix an import-linter violation, delete its `ignore_imports` entry. A stale entry fails the build.

## Links

- [Root AGENTS.md](../../../AGENTS.md)
- [Architecture guide](../../../docs/guides/architecture.md)
