# src/omrs (composition root)

The package marker, the public Engine and the composition root. Business logic lives in `core/`.

## What belongs here

- `__init__.py`: lazy public exports (`omrs.__all__`).
- `engine*.py`, `compose*.py`, `capabilities.py` and `pipeline_templates.py`.

## What must not import this folder

- `core/`. Contract `core-never-imports-top-level-modules` enforces this. One sanctioned edge reaches `omrs.capabilities`.

## Rules

1. `compose.py` is the only production caller of `get_settings()`. Resolve settings once and inject them.
2. `compose.build_engine()` is the single construction path for an Engine.
3. Only `omrs.compose` imports a concrete provider module (contract `providers-constructed-only-in-compose`).
4. Resolve strategies through registries. Do not branch `if/elif` over strategy names.
5. Public names go in `omrs.__all__` only.
6. A new top-level module needs an entry in `tests/unit/test_verification_gaps_boundaries.py` and in the `core-never-imports-top-level-modules` list. Prefer a module under `core/`.
7. Settings come from one source order, highest first: explicit option, `env`, `dotenv`, `omrs.jsonc` (`config-file`), YAML defaults, code default (ADR-087). Only `env` and `dotenv` lock a field.
8. `config/` returns a `keychain://` key reference unresolved. `compose_providers` resolves it. A literal key never goes in `omrs.jsonc` or `.env` from code (root gotcha 18).

## Links

- [Root AGENTS.md](../../AGENTS.md)
- [Architecture guide](../../docs/guides/architecture.md)
