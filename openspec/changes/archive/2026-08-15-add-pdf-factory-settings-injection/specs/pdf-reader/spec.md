## MODIFIED Requirements

### Requirement: Auto resolution SHALL probe backends in preference order with graceful fallback

When the configured reader is `auto`, the system SHALL probe backend imports
in the order `liteparse → pypdfium2 → pypdf` and SHALL select the first
importable backend. PyMuPDF is structurally excluded from accepted values
entirely (AGPL-3 incompatibility). If no optional backend is installed, the
system SHALL fall back to `pypdf` (always available via
`llama-index-readers-file`).

The composition root resolves `auto` once at startup and injects the concrete
name. Callers that bypass the composition root (direct library use, tests)
SHALL receive the same preference order from the reader factory's local
resolution, so the selected backend is identical on both paths for the same
installed packages.

#### Scenario: LiteParse installed and selected by auto

- **WHEN** the configured reader is `auto` and the `liteparse` package is importable
- **THEN** the resolved reader SHALL be `liteparse`

#### Scenario: LiteParse missing, pypdfium2 installed

- **WHEN** the configured reader is `auto`, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** the resolved reader SHALL be `pypdfium2` and the system SHALL log an informational message that LiteParse was not available

#### Scenario: No optional backend installed

- **WHEN** the configured reader is `auto` and neither `liteparse` nor `pypdfium2` is importable
- **THEN** the resolved reader SHALL be `pypdf` and ingestion SHALL behave identically to the pre-change pipeline

#### Scenario: Explicit backend requested but not installed

- **WHEN** the configured reader is `liteparse` but `liteparse` is not importable
- **THEN** the system SHALL log an error naming the missing package and SHALL fall back to `pypdf` rather than raising

#### Scenario: Factory-local auto resolution matches composition-root order

- **WHEN** the reader factory resolves `auto` for a caller that bypassed the composition root, `liteparse` is not importable, and `pypdfium2` is importable
- **THEN** the factory SHALL return the `pypdfium2` adapter
- **AND** the selection SHALL match what the composition root would have resolved for the same installed packages
