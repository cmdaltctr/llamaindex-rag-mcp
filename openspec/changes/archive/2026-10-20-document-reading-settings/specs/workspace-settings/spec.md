## MODIFIED Requirements

### Requirement: Settings is split into sections

The Settings view SHALL offer the sections Appearance, Providers, Chat, MCP, Server log, Runtime, Workspace, Document reading and Configuration, in that order, switched with chip buttons, with one section shown at a time. Each section SHALL have the address `#/settings/<section>` (`appearance`, `providers`, `chat`, `mcp`, `log`, `runtime`, `workspace`, `document-reading`, `configuration`). Selecting a chip SHALL rewrite the address. `#/settings` SHALL show Appearance.

#### Scenario: Switch section

- **WHEN** the user selects the Server log chip
- **THEN** only the Server log section MUST show, the Server log chip MUST be marked selected, and the address MUST read `#/settings/log`

#### Scenario: Open a section from a link

- **WHEN** the app opens at `#/settings/chat`
- **THEN** only the Chat section MUST show and the Chat chip MUST be marked selected

#### Scenario: Open Document reading from a link

- **WHEN** the app opens at `#/settings/document-reading`
- **THEN** only the Document reading section MUST show, its chip MUST be marked selected, and its chip MUST come directly before the Configuration chip

## ADDED Requirements

### Requirement: Document reading shows the reading settings and their state

The Document reading section SHALL show one row for each of `pdf_reader`, `ocr_fallback_enabled`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_routing_unit`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`. Each row SHALL show the value in force since launch, its source and the default. When the saved file value differs from the value in force, the row SHALL show the saved value and "Restart to apply". A key set in the environment or `.env` SHALL be read-only and SHALL show "Remove <ENV_NAME> from the environment or .env to edit it here." The section SHALL state that the settings apply after a restart, and that they are part of the index identity, so the next ingest after a restart can read existing files again. The PDF reader choice SHALL mark each reader that is not installed and SHALL NOT let the user choose it. The engine choices SHALL list the engines the server reports and SHALL mark each engine that is not provisioned, with the reason. When `OCR_WORKER_COMMAND` is set, the section SHALL say that it replaces the primary engine.

#### Scenario: Value saved but not yet in force

- **WHEN** the server launched with `pdf_reader` `auto` and `omrg.jsonc` now holds `"pdf_reader": "liteparse"`
- **THEN** the PDF reader row MUST show `auto` in force, `liteparse` saved and "Restart to apply"

#### Scenario: Key locked by the environment

- **WHEN** `OCR_ROUTING_UNIT=page` is set in `.env`
- **THEN** the routing unit row MUST offer no Edit and MUST show "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here."

#### Scenario: Reader not installed

- **WHEN** the server reports `pypdfium2` as not installed
- **THEN** the PDF reader choice MUST show `pypdfium2` as not available with the reason and MUST NOT allow it to be selected

#### Scenario: Worker command overrides the primary engine

- **WHEN** `OCR_WORKER_COMMAND` is set
- **THEN** the primary engine row MUST say that `OCR_WORKER_COMMAND` replaces the primary engine

### Requirement: Document reading saves to omrg.jsonc for the next launch

A save in the Document reading section SHALL write the changed keys into `omrg.jsonc` with the file revision the page last read. A save SHALL NOT change the value in force. After a save that leaves a key waiting for a restart, the page SHALL offer the restart dialog and SHALL repeat the index identity note. "Use default" on a row SHALL remove the key from the file. A refused save SHALL show the server message and SHALL leave the row unchanged.

#### Scenario: Save a fraction

- **WHEN** the user sets the OCR page fraction to 0.2 and presses Save
- **THEN** `omrg.jsonc` MUST hold `"ocr_fallback_page_fraction": 0.2`, the row MUST show "Restart to apply", and the restart dialog MUST open

#### Scenario: Return to the default

- **WHEN** the file holds `"ocr_engine_fallback": "my-engine"` and the user presses "Use default" on that row
- **THEN** `omrg.jsonc` MUST no longer hold `ocr_engine_fallback`

#### Scenario: File edited while the page is open

- **WHEN** the user edits `omrg.jsonc` in an editor and then saves a row in Document reading
- **THEN** the page MUST show "omrg.jsonc changed on disk. Reload to see the new values." and MUST offer Reload

### Requirement: Document reading routes

`GET /v1/settings/document-reading` SHALL need the read scope. It SHALL return the file `revision`, one entry for each of the nine keys in a fixed order (with the value in force, the saved value, the source, whether it is locked, the lock reason, whether a restart is pending, and the default), every PDF reader with its availability, the reader in use, and the OCR workers folder, whether `OCR_WORKER_COMMAND` is set, and each known engine with its availability. `PUT /v1/settings/document-reading` SHALL need a browser session with the manage scope. It SHALL take `values` (one to nine of the nine keys, each a value or `null`) and a required `revision`. It SHALL write all values or none. On success it SHALL return the same body as `GET`. It SHALL answer 400 for a key outside the nine, for a value that breaks its rule, for a blank text value and for a PDF reader that is not installed. It SHALL answer 409 for a locked key, for a stale revision and for a file that cannot be parsed. No error message SHALL hold a submitted value.

#### Scenario: Read the section

- **WHEN** a session with the read scope sends `GET /v1/settings/document-reading`
- **THEN** the answer MUST be 200 and MUST hold nine `settings` entries, `pdf_readers` starting with `auto`, and `ocr.engines`

#### Scenario: Key outside the nine

- **WHEN** a `PUT` sets `embed_provider`
- **THEN** the server MUST answer 400 "embed_provider is not a document reading setting." and MUST NOT change the file

#### Scenario: Locked key

- **WHEN** `PDF_READER` is set in the environment and a `PUT` sets `pdf_reader`
- **THEN** the server MUST answer 409 "Remove PDF_READER from the environment or .env to edit it here." and MUST NOT change the file

#### Scenario: Value out of range

- **WHEN** a `PUT` sets `ocr_maths_page_fraction` to 1.5
- **THEN** the server MUST answer 400 with a message that names `ocr_maths_page_fraction` and the range and does not hold 1.5, and MUST NOT change the file

#### Scenario: One bad value stops the whole save

- **WHEN** a `PUT` sets `ocr_routing_unit` to `page` and `ocr_engine_primary` to `../x`
- **THEN** the server MUST answer 400 and the file MUST hold neither value

#### Scenario: Uninstalled reader

- **WHEN** `pypdfium2` is not installed and a `PUT` sets `pdf_reader` to `pypdfium2`
- **THEN** the server MUST answer 400 "pdf_reader: This PDF reader is not installed. Install its package, then save again." and MUST NOT change the file

#### Scenario: Unprovisioned engine is allowed

- **WHEN** a `PUT` sets `ocr_engine_primary` to a valid name that has no folder under the engines folder
- **THEN** the server MUST answer 200, the file MUST hold the name, and the engine entry MUST report `available` false with the reason
