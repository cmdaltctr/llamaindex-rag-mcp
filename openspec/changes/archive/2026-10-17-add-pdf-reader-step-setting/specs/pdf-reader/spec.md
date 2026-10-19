## MODIFIED Requirements

### Requirement: PDF reader SHALL be selectable via environment variable

The system SHALL read a `PDF_READER` environment variable at config-load
time into the frozen `Settings.pdf_reader` field. Accepted values SHALL be
`auto`, `pdf_inspector`, `liteparse`, `pypdfium2`, and `pypdf`. Any other
value SHALL log a warning naming the offending value and fall back to
`auto`. The composition root SHALL resolve `auto` to a concrete backend
name exactly once at startup and bake the result into the injected
`EffectiveSettings.pdf_reader`; no module-level resolved constant exists.

The resolved value SHALL be the host default reader. A pipeline's Read
document step MAY select another registered concrete reader for that step
only. A step selection SHALL NOT change the environment, the frozen
`Settings.pdf_reader` field or the resolved host default, and SHALL NOT be
`auto`.

#### Scenario: Explicit pdf-inspector selection via env var

- **WHEN** `PDF_READER=pdf_inspector` is set and the package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"pdf_inspector"` and its adapter SHALL ingest all `.pdf` files

#### Scenario: Explicit override selection via env var

- **WHEN** `PDF_READER=liteparse` is set and the `liteparse` package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"liteparse"` and the LiteParse adapter SHALL be used for all `.pdf` ingestion

#### Scenario: Unknown value falls back to auto with warning

- **WHEN** `PDF_READER=fastparser` (an unsupported value) is set
- **THEN** the system SHALL log a warning naming the offending value and the fallback, and SHALL resolve as if `PDF_READER=auto` had been set

#### Scenario: Resolution happens once at the composition root

- **WHEN** the server or CLI entry point starts
- **THEN** `compose.resolve_pdf_reader` SHALL run once over the frozen settings
- **AND** every operation below the entry point SHALL read the concrete name from its injected settings, with no repeated probing

#### Scenario: Step selection leaves the host default unchanged

- **WHEN** the host default reader is `pypdf` and one pipeline's Read document step selects `pdf_inspector`
- **THEN** that step SHALL read PDF files with `pdf_inspector`
- **AND** the standard ingest path, other pipelines and steps that inherit SHALL keep reading with `pypdf`
- **AND** the environment and the injected host settings SHALL remain unchanged

#### Scenario: Step selection cannot be auto

- **WHEN** a Read document step sets its reader to `auto`
- **THEN** validation SHALL reject the value before any node runs
- **AND** the message SHALL tell the user to choose a concrete reader or inherit the host reader

## ADDED Requirements

### Requirement: Reader installation SHALL be reported per reader

The host SHALL probe each registered concrete reader with its registry dependency probe once per Engine, on first use. It SHALL report each reader as installed, or as not installed with a reason that names the missing package.

#### Scenario: A registered reader is not installed

- **WHEN** the `pypdfium2` package is not importable
- **THEN** the host SHALL report `pypdfium2` as not installed
- **AND** the reason SHALL name the package `pypdfium2`

#### Scenario: Probing happens once per Engine

- **WHEN** a client lists the operation catalogue twice and then validates a graph on the same Engine
- **THEN** the host SHALL probe each registered reader once only
