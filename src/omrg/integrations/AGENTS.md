# src/omrg/integrations (external services)

Adapters for optional tools and services: PDF readers, Magika, Azure and OCR.

## What belongs here

- One module or folder per external system. Each degrades gracefully when its dependency is missing.

## What it must not import

- `omrg.core`, `omrg.transports` or `omrg.daemon` (contract `integrations-are-leaves`).
- The sanctioned exceptions read `omrg.core.settings` only.

## Rules

1. Import optional SDKs inside functions, never at module top (ADR-024; see `azure.py`).
2. Degrade gracefully when an optional dependency or a cloud service is missing. Cloud use is opt-in.
3. A test patches an availability probe at its own module, for example `omrg.integrations.magika`.
4. A new module needs a row in the integration inventory in `docs/guides/architecture.md`. `tests/test_strategy_registration_inventory.py` checks it.

## Links

- [Root AGENTS.md](../../../AGENTS.md)
- [Architecture guide](../../../docs/guides/architecture.md)
