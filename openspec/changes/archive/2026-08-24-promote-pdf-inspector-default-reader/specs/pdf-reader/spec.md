## MODIFIED Requirements

### Requirement: PDF reader SHALL be selectable via environment variable

The system SHALL read `PDF_READER` at config-load time into frozen
`Settings.pdf_reader`. Accepted values SHALL be `auto`, `pdf_inspector`,
`liteparse`, `pypdfium2`, and `pypdf`. Any other value SHALL log a warning
naming the value and fall back to `auto`. The composition root SHALL resolve
`auto` once at startup and bake a concrete backend name into injected
`EffectiveSettings.pdf_reader`; no module-level resolved constant exists.

#### Scenario: Explicit pdf-inspector selection via env var

- **WHEN** `PDF_READER=pdf_inspector` is set and the package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"pdf_inspector"` and its adapter SHALL ingest all `.pdf` files

#### Scenario: Explicit override selection via env var

- **WHEN** `PDF_READER=liteparse` is set and the package is importable
- **THEN** the injected `EffectiveSettings.pdf_reader` SHALL equal `"liteparse"` and the LiteParse adapter SHALL ingest all `.pdf` files

#### Scenario: Unknown value falls back to auto with warning

- **WHEN** `PDF_READER=fastparser` is set
- **THEN** the system SHALL log a warning naming the value and the fallback, and SHALL resolve as if `PDF_READER=auto` had been set

#### Scenario: Resolution happens once at the composition root

- **WHEN** the server or CLI entry point starts
- **THEN** `compose.resolve_pdf_reader` SHALL run once over frozen settings
- **AND** every operation below the entry point SHALL read the concrete name from injected settings, with no repeated probing

### Requirement: LiteParse SHALL be a core dependency

Both `liteparse` and `pdf-inspector` SHALL be declared in the main
`[project.dependencies]` list in `pyproject.toml`. The base `uv sync` SHALL
install both packages. The configured default SHALL be available without an
optional dependency extra.

#### Scenario: Baseline install includes pdf-inspector

- **WHEN** a user runs `uv sync` without extras
- **THEN** `pdf_inspector` and `liteparse` SHALL be importable

#### Scenario: Explicit override to LiteParse

- **WHEN** a user sets `PDF_READER=liteparse` in `.env`
- **THEN** the system SHALL use LiteParse regardless of pdf-inspector availability

### Requirement: PDF reader default SHALL be configuration-owned after Experiment 14 validation

The packaged `PDF_READER` default SHALL be `pdf_inspector`. The selected
backend SHALL remain configurable through `PDF_READER`; `auto` SHALL retain
its existing capability-resolution and graceful-fallback behaviour. Experiment
14 validated this promotion with zero parser failures, a 346.7-second ingest
run, and the highest reranked Hit@5 result (0.6250).

#### Scenario: Packaged default selects pdf-inspector

- **WHEN** no `PDF_READER` environment variable is set
- **THEN** the resolved reader SHALL be `"pdf_inspector"`

#### Scenario: Environment override takes precedence

- **WHEN** `PDF_READER=pypdf` is set
- **THEN** the system SHALL use pypdf regardless of the packaged default

#### Scenario: Missing configured backend falls back safely

- **WHEN** `PDF_READER=pdf_inspector` is configured but the package is not importable
- **THEN** the system SHALL log an error naming the missing package and fall back to pypdf rather than raising
