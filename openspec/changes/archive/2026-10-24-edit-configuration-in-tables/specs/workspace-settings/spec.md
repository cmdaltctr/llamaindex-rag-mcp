## MODIFIED Requirements

### Requirement: The Configuration section lists every setting

Settings SHALL have a Configuration section that lists every setting, grouped by block, with its value in force, its source, and "Restart to apply" when its file value differs from the value the server started with. Keys SHALL show at most the last four characters. The section SHALL show the `omrs.jsonc` path with a copy action, and the problems found in the file. It SHALL take its data from `GET /v1/settings/configuration` (read scope).

Each block SHALL be a card that holds one table with the columns Setting, Value and Source, one row for each setting. A row waiting for a restart SHALL show "Next launch: <value>" under the value. At a phone width the Source SHALL show under the setting name, and the page SHALL NOT scroll sideways.

A block card with at least one editable setting SHALL show Edit at its top right. Edit SHALL put the whole table in edit mode: each setting the server reports as editable SHALL show, in its Value cell, a control for its kind filled with the value the next launch uses. The control SHALL be an on/off switch for a boolean, a number field with its range for a number, a choice list for a setting with fixed choices, and a text field for text. A Value cell SHALL hold only the control and its rule; a row SHALL have no button of its own. In edit mode, Save and Cancel SHALL take the place of Edit.

Save SHALL be disabled until a cell differs from its starting value, and while a cell breaks its rule. Save SHALL send every changed cell of that table in one `PUT /v1/settings/configuration` call with the revision the section read, so the server writes all of them or none. After a good save the table SHALL leave edit mode, and when a saved setting applies at restart the restart dialog SHALL open once for the whole save. A refused save SHALL keep the table in edit mode with the typed values and SHALL show the server's message. Cancel SHALL drop every change in the table and leave edit mode. Only one table SHALL be in edit mode at a time; Edit on another table while the open table has changes SHALL ask whether to discard them.

A setting the server reports as read-only SHALL keep its value as text with a lock mark, also in edit mode, and in edit mode its reason SHALL show on a line under the row. A setting set in the environment or `.env` SHALL be read-only with the reason "Remove <ENV_NAME> from the environment or .env to edit it here." An optional setting SHALL be cleared by emptying its field and saving, which removes the key so the default applies. A chunking block SHALL state that its settings are part of the index identity, so the next ingest after a restart can read existing files again.

#### Scenario: Engine setting edited by hand

- **WHEN** the user changes `retrieval.top_k` in `omrs.jsonc` while the server runs
- **THEN** the section MUST show the launch value, the source `config-file` and "Restart to apply", and MUST offer the restart dialog

#### Scenario: Problems listed

- **WHEN** `omrs.jsonc` holds an unknown key and an invalid value
- **THEN** the section MUST list both by key with one plain line each and MUST NOT show the invalid value

#### Scenario: Database rows not moved

- **WHEN** the server could not move saved settings into `omrs.jsonc`
- **THEN** the section MUST show "Saved settings could not be moved to omrs.jsonc" with the folder path

#### Scenario: Block shown as a table

- **WHEN** the section shows the Retrieval block
- **THEN** the block card MUST hold a table with the columns Setting, Value and Source, one row for each `retrieval.` setting, and no control MUST be visible until the user presses Edit

#### Scenario: Edit a restart-only number

- **WHEN** `retrieval.top_k` comes from the default, and the user presses Edit on the Retrieval table, types 20 and presses Save
- **THEN** the page MUST send `{"revision": <read revision>, "changes": {"retrieval.top_k": 20}}`, the table MUST leave edit mode, the row MUST show "Next launch: 20", "Saved in settings (omrs.jsonc)" and "Restart to apply", and the restart dialog MUST be offered

#### Scenario: Several cells saved together

- **WHEN** the user changes `retrieval.top_k` to 20 and `retrieval.hybrid_enabled` to on in one edit mode and presses Save
- **THEN** the page MUST send one request whose changes hold exactly those two keys, and the restart dialog MUST open once

#### Scenario: Nothing changed

- **WHEN** the user presses Edit and changes no cell
- **THEN** Save MUST be disabled and no request MUST be sent

#### Scenario: Turn a boolean off

- **WHEN** the user switches `answer.enabled` off in edit mode and saves
- **THEN** `omrs.jsonc` MUST hold `answer.enabled` false and the row MUST show "Off"

#### Scenario: Choose from fixed choices

- **WHEN** the user edits `metadata.extraction_mode`
- **THEN** the control MUST be a choice list of the accepted modes, and no free text MUST be possible

#### Scenario: Out of range number refused before the request

- **WHEN** the server reports `answer.max_rounds` with the range 1 to 8 and the user types 12
- **THEN** the cell MUST show the range rule, Save MUST be disabled and no request MUST be sent

#### Scenario: Cancel drops the changes

- **WHEN** the user types 20 for `retrieval.top_k` and presses Cancel
- **THEN** the table MUST leave edit mode, the row MUST show the value it showed before, and no request MUST be sent

#### Scenario: Read-only identity setting

- **WHEN** the user presses Edit on the block that holds `embed_model`
- **THEN** the row MUST keep its value as text with a lock mark and MUST show its reason ("The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest.") under the row

#### Scenario: Block with no editable setting

- **WHEN** every setting in a block is read-only
- **THEN** the block card MUST NOT show Edit

#### Scenario: Clear an optional setting

- **WHEN** `omrs.jsonc` holds `metadata.ollama_classify_timeout_override` 30, and the user empties its field in edit mode and saves
- **THEN** the page MUST send `null` for that key, the key MUST be removed from the file and the row MUST show the default and the source "default"

#### Scenario: Second table while the first has changes

- **WHEN** the Retrieval table has a changed cell and the user presses Edit on the Answer table
- **THEN** the page MUST ask whether to discard the Retrieval changes, and MUST open the Answer table only after the user agrees

#### Scenario: Refused save keeps the typed values

- **WHEN** the server refuses a save with 400 and a message
- **THEN** the table MUST stay in edit mode with the typed values and MUST show the message

#### Scenario: File changed under the page

- **WHEN** someone edits `omrs.jsonc` by hand after the section loaded and the user then saves a table
- **THEN** the page MUST show "omrs.jsonc changed on disk. Reload to see the new values." and MUST NOT write

#### Scenario: Phone width

- **WHEN** the section is shown 390 px wide
- **THEN** each table MUST show the source under the setting name, Edit, Save and Cancel MUST stay at the top right of the card, and the page MUST NOT scroll sideways
