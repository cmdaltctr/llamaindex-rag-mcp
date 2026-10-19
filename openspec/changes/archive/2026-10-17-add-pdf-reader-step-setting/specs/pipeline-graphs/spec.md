## ADDED Requirements

### Requirement: Read document step selects its PDF reader

The `read.document` operation SHALL accept an optional `pdf_reader` setting. Its choices SHALL be the registered concrete readers. `null` SHALL inherit the host reader. A set value SHALL make that node read PDF sources with the selected reader through the shared reader factory. A graph-wide override of `pdf_reader` SHALL remain a host-owned setting.

#### Scenario: Inherit uses the host reader

- **WHEN** a Read document node leaves `pdf_reader` empty
- **THEN** the node SHALL read PDF sources with the host reader

#### Scenario: Step reader reads PDF sources

- **WHEN** the host reader is `pypdf` and a Read document node sets `pdf_reader` to `pdf_inspector`
- **THEN** the node SHALL read PDF sources with `pdf_inspector`
- **AND** the reader's declared `markdown` text format SHALL reach the chunking step

#### Scenario: Uninstalled reader is refused

- **WHEN** a Read document node selects a registered reader that the host reports as not installed
- **THEN** validation SHALL fail with issue code `option_unavailable`
- **AND** the issue SHALL name the node, the reader and the missing package
- **AND** no node SHALL run

#### Scenario: Unknown reader is refused

- **WHEN** a Read document node sets `pdf_reader` to `auto` or to a name the registry does not hold
- **THEN** validation SHALL fail with issue code `invalid_parameter` before any node runs

#### Scenario: Graph-wide reader override stays host-owned

- **WHEN** a graph sets `overrides.pdf_reader`
- **THEN** validation SHALL fail with issue code `host_owned_setting`
- **AND** the message SHALL tell the user to set the reader on the Read document step

### Requirement: OCR routing follows the step reader under host OCR settings

A Read document node SHALL apply the OCR routing that its effective reader supports, under the host OCR settings and with the Engine OCR client. A step reader SHALL NOT add an OCR route, start a worker the host has not configured, or change an OCR setting.

#### Scenario: Step selects a reader without OCR routing

- **WHEN** the host reader is `pdf_inspector` with OCR fallback enabled and a Read document node selects `pypdf`
- **THEN** the node SHALL read PDF sources without OCR routing

#### Scenario: Step selects pdf-inspector on a host with another default

- **WHEN** the host reader is `pypdf`, the host enables OCR fallback, and a Read document node selects `pdf_inspector`
- **THEN** OCR-required PDF sources SHALL route through the host OCR routes and the Engine OCR client
- **AND** when the host has no OCR route, the node SHALL keep the partial text and report the degradation, as the standard path does

### Requirement: Ingestion identity records the step reader

Before the reuse check, graph ingestion SHALL compute each source's index identity with the reader of the Read document node in the commit node's ancestor slice. The stored identity SHALL name the same reader and text format as the read.

#### Scenario: Reader change forces reprocessing

- **WHEN** a source was indexed through a graph whose Read document node inherits the host reader `pypdf`, and the node then selects `pdf_inspector`
- **THEN** the next explicit ingest SHALL process the source again
- **AND** SHALL NOT report it as unchanged

#### Scenario: Stored identity names the step reader

- **WHEN** graph ingestion commits a PDF source read with a step reader that differs from the host reader
- **THEN** the stored source identity SHALL equal the identity computed with the step reader
- **AND** SHALL differ from the identity computed with the host reader

#### Scenario: Unchanged step reader reuses the source

- **WHEN** the same graph ingests the same unchanged source again
- **THEN** the source SHALL be reported as unchanged and expensive work SHALL be skipped

#### Scenario: Inheriting the reader keeps the standard identity

- **WHEN** the canonical ingestion template runs with an empty `pdf_reader`
- **THEN** its sources SHALL keep the same identity as the standard ingest path

### Requirement: Catalogue reports unavailable choices per setting

The operation catalogue SHALL report, for each operation setting whose choices depend on the host, the choices the host cannot run with a reason, and the value the setting inherits. Operations without such settings SHALL report empty maps. Operation availability SHALL remain per operation.

#### Scenario: Uninstalled reader is listed with its reason

- **WHEN** a client requests the catalogue on a host where `pypdfium2` is not installed
- **THEN** `read.document` SHALL stay available
- **AND** its unavailable choices SHALL list `pypdfium2` with a reason that names the missing package
- **AND** a client SHALL have enough information to show the choice as disabled with that reason

#### Scenario: Inherited reader is reported

- **WHEN** a client requests the catalogue on a host whose reader is `pdf_inspector`
- **THEN** the catalogue SHALL report `pdf_inspector` as the value that the Read document `pdf_reader` setting inherits
