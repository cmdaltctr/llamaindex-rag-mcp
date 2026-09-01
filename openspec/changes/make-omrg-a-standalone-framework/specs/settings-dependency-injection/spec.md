## MODIFIED Requirements

### Requirement: No settings singleton outside the composition root

The resolved `Settings` singleton SHALL NOT be instantiated at module import
time. `config` SHALL expose `get_settings()` and SHALL NOT expose a
module-level `settings` object.

`get_settings()` SHALL remain the environment-and-file resolution path, and
its production call sites SHALL be limited to the composition root and the
engine's own environment-resolving constructor. An engine constructed from
caller-supplied settings SHALL NOT call it at all.

This narrows the previous rule, which named `compose.py` as the sole caller.
That was correct when the composition root was the only way to build a
runtime; with an engine that can be constructed from explicit settings, the
invariant that matters is that resolution happens in exactly one layer and
never in `core/`.

#### Scenario: Import does not resolve settings

- **WHEN** the config module is imported
- **THEN** no `Settings()` instance MUST be constructed as a side effect
- **AND** no environment or YAML resolution MUST occur until `get_settings()`
  is called

#### Scenario: Single call site

- **WHEN** the codebase is searched for `get_settings()`
- **THEN** production call sites MUST be confined to the composition root and
  the engine's environment-resolving construction path
- **AND** no module under `core/` or `integrations/` MUST call it

#### Scenario: Explicit settings bypass resolution entirely

- **WHEN** an engine is constructed from a caller-supplied settings object
- **THEN** `get_settings()` MUST NOT be called
- **AND** no environment variable or configuration file MUST be read
