## MODIFIED Requirements

### Requirement: No settings singleton outside the composition root

The resolved `Settings` singleton SHALL NOT be instantiated at module import
time. `config` SHALL expose `get_settings()` and SHALL NOT expose a
module-level `settings` object.

`get_settings()` SHALL remain the environment-and-file resolution path, and
its production call sites SHALL remain limited to the composition root:
`compose.py` and its sanctioned sibling modules that `compose.py`
re-exports (currently `compose_answer.py`). No module under `core/`,
`integrations/` or `transports/` SHALL call it; the watcher installer's
current direct call SHALL be removed by this change.
`Engine.from_environment()` SHALL delegate to the composition-root builder
rather than calling `get_settings()` itself. An engine constructed from
caller-supplied settings SHALL NOT call it at all.

This preserves the existing sole-caller rule while adding an explicit Engine
factory over it; direct Engine construction accepts already-composed
dependencies and resolved `EffectiveSettings`, and never reads config.

#### Scenario: Import does not resolve settings

- **WHEN** the config module is imported
- **THEN** no `Settings()` instance MUST be constructed as a side effect
- **AND** no environment or YAML resolution MUST occur until `get_settings()`
  is called

#### Scenario: Single call site

- **WHEN** the production package is searched for `get_settings()` call sites
- **THEN** the only permitted production callers MUST be the composition root
  (`compose.py` and its sanctioned re-export siblings)
- **AND** no module under `core/`, `integrations/` or `transports/` MUST call
  it
- **AND** the enforcement guard MUST scan the full production package, not
  only `core/` and `integrations/`

#### Scenario: Explicit settings bypass resolution entirely

- **WHEN** an engine is constructed from caller-supplied dependencies and
  settings
- **THEN** `get_settings()` MUST NOT be called
- **AND** no environment variable or configuration file MUST be read
