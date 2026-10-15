# local-web-workspace delta

## ADDED Requirements

### Requirement: The workspace opens truncated run output

Every preview in the run detail that the server or the browser cut SHALL say that it was cut and SHALL offer one "Open full output" action, unless the server kept no full copy of that output for the run shown. The action SHALL show the full redacted value as plain text, never as markup, up to a stated display limit, and SHALL offer a download of the whole value. A failure to load the value SHALL render as one friendly message with one action.

#### Scenario: Open a cut node summary

- **WHEN** a node summary in the run detail carries `truncated: true` and an `artefact_ref`
- **THEN** the run detail MUST offer "Open full output", and the action MUST show the value that the artefact route returns

#### Scenario: No full copy for this run

- **WHEN** a cut node summary has no `artefact_ref`, or its `artefact_ref` names another run or is not valid
- **THEN** the run detail MUST say that the output was cut and why it cannot be opened, and MUST NOT offer "Open full output"

#### Scenario: Value larger than the display limit

- **WHEN** the full value is larger than the display limit
- **THEN** the view MUST show the first part, MUST state that the rest is not shown, and MUST offer a download of the whole value

#### Scenario: Markup in stored output

- **WHEN** the full value contains text that looks like HTML
- **THEN** the view MUST show it as text and MUST NOT create elements from it

### Requirement: The upload limit is set in Settings

The per-file upload limit SHALL be a workspace setting, saved in the workspace database, in whole MiB from 1 to 2048. With no saved value the limit SHALL be 50 MiB. `GET /v1/settings/upload-limit` (read scope) SHALL return the limit in force, its source, the saved value or `null`, the default, and the allowed range. `PUT /v1/settings/upload-limit` SHALL need a browser session, SHALL take `max_mib` (an integer in range, or `null` to clear the saved value), SHALL save it before it changes the running server, and SHALL apply it to new uploads at once, with no restart. An upload that has already started SHALL keep the limit it started with. Settings › Workspace SHALL show the limit in force, SHALL let the user save a new value or return to the default, and SHALL state that the change applies to new uploads straight away.

#### Scenario: Raise the limit

- **WHEN** the user saves 200 MiB in Settings and then uploads a 120 MiB file
- **THEN** the server MUST accept the file without a restart, and the saved value MUST still apply after a restart

#### Scenario: Return to the default

- **WHEN** the user clears the saved value
- **THEN** the limit in force MUST be 50 MiB, and Settings MUST say that the default applies

#### Scenario: Value out of range

- **WHEN** a request sets `max_mib` to 0, to 4096, or to a value that is not a whole number
- **THEN** the server MUST answer 400 and MUST NOT change the saved or the running limit, and Settings MUST name the allowed range before it sends such a value

#### Scenario: Bearer credential

- **WHEN** a bearer credential sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST refuse it and MUST NOT change the limit

#### Scenario: Limit lowered during an upload

- **WHEN** the limit is lowered while a file upload is in progress
- **THEN** that upload MUST finish against the limit it started with, and the next upload MUST use the new limit

### Requirement: A launch option sets the upload limit without the web workspace

`omrg web` SHALL accept `--max-upload-mib <n>` and SHALL read `WEB_MAX_UPLOAD_MIB` from the environment or `.env` when the flag is absent, so the limit can be set when the web workspace cannot be used. The order SHALL be the flag, then the environment variable, then the value saved in Settings, then 50 MiB. Both SHALL take a whole number from 1 to 2048; any other value SHALL stop the launch with exit code 2 and a message that names the option and the range. While a launch option sets the limit, `GET /v1/settings/upload-limit` SHALL report `source: "launch"`, `PUT` SHALL answer 409 and change nothing, and Settings SHALL show the limit as set at launch with no edit control. `.env.example` and the CLI reference SHALL document both.

#### Scenario: Environment variable in .env

- **WHEN** `.env` holds `WEB_MAX_UPLOAD_MIB=300` and `omrg web` starts without `--max-upload-mib`
- **THEN** the limit in force MUST be 300 MiB, and the response MUST report `source: "launch"`

#### Scenario: Flag beats environment and saved value

- **WHEN** Settings saved 200 MiB, the environment sets 300, and `omrg web --max-upload-mib 400` starts
- **THEN** the limit in force MUST be 400 MiB

#### Scenario: Invalid launch value

- **WHEN** `WEB_MAX_UPLOAD_MIB` is `0`, `5000` or `big`
- **THEN** `omrg web` MUST exit with code 2 before it binds a port and MUST name `WEB_MAX_UPLOAD_MIB` and the range 1 to 2048

#### Scenario: Settings while a launch option is set

- **WHEN** a launch option sets the limit and a browser session sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST answer 409, MUST keep the saved and the running limit, and Settings MUST say the limit was set at launch and how to change it

#### Scenario: No launch option

- **WHEN** neither the flag nor the environment variable is set
- **THEN** the saved value MUST apply, else 50 MiB, and the response MUST report `source: "saved"` or `source: "default"`

### Requirement: The workspace enforces the server's upload limit

The Knowledge Base SHALL read the limit from `GET /v1/settings/upload-limit`, SHALL state it in the upload panel, SHALL refuse a selected file larger than it before any bytes are sent, and SHALL name that value in the refusal. The workspace SHALL keep no limit of its own. A save in Settings SHALL update the upload panel without a page reload. When the limit cannot be read, the workspace SHALL leave the size check to the server, which still refuses an oversized file.

#### Scenario: Server with another limit

- **WHEN** the server reports a limit of 100 MiB and the user selects a 60 MiB file
- **THEN** the workspace MUST send the file, and the upload panel MUST state the 100 MiB limit

#### Scenario: File above the reported limit

- **WHEN** the server reports a limit of 10 MiB and the user selects a 12 MiB file
- **THEN** the workspace MUST refuse the file locally, MUST name the 10 MiB limit, and MUST NOT send the file

#### Scenario: Limit changed in Settings

- **WHEN** the user saves a new limit in Settings and then opens the Knowledge Base
- **THEN** the upload panel MUST state the new limit without a page reload

#### Scenario: Limit unknown

- **WHEN** the limit request fails
- **THEN** the workspace MUST NOT refuse the file locally, and a 413 from the server MUST render as one friendly message that does not name a number the server did not report
