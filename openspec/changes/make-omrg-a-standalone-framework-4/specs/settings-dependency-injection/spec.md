## MODIFIED Requirements

### Requirement: No settings singleton outside the composition root

The resolved `Settings` singleton SHALL NOT be instantiated at module import
time. `config` SHALL expose `get_settings()` and SHALL NOT expose a
module-level `settings` object.

`get_settings()` SHALL remain the environment-and-file resolution path, and
its production call sites SHALL remain limited to the composition root.
`Engine.from_environment()` SHALL delegate to that root rather than calling
`get_settings()` itself. An engine constructed from caller-supplied settings
SHALL NOT call it at all.

This preserves the existing sole-caller rule while adding an explicit Engine
factory over it; direct Engine construction accepts already-resolved
`EffectiveSettings` and never reads config.

#### Scenario: Import does not resolve settings

- **WHEN** the config module is imported
- **THEN** no `Settings()` instance MUST be constructed as a side effect
- **AND** no environment or YAML resolution MUST occur until `get_settings()`
  is called

#### Scenario: Single call site

- **WHEN** the codebase is searched for `get_settings()`
- **THEN** the composition root MUST remain the sole production call site
- **AND** no module under `core/` or `integrations/` MUST call it

#### Scenario: Explicit settings bypass resolution entirely

- **WHEN** an engine is constructed from a caller-supplied settings object
- **THEN** `get_settings()` MUST NOT be called
- **AND** no environment variable or configuration file MUST be read
