# Spec Delta

## MODIFIED Requirements

### Requirement: The web server listens on a stable port

`omrg web` SHALL choose its port in this order: the `--port` option, then `web_port` in `omrg.jsonc`, then 8765. `--port 0` SHALL pick a free port for that launch. When the chosen port is taken, the command SHALL exit with an error that names the port and tells the user to pass `--port <n>`. `PUT /v1/settings/web-port` with `{ port }` (browser session only, 1024 to 65535, or `null` to clear) SHALL write `web_port` to `omrg.jsonc` for later launches and SHALL NOT rebind the running server. `GET /v1/settings/web-port` (read scope) SHALL return the file port, the bound port and whether they differ. The login item SHALL read the same value.

#### Scenario: Default port

- **WHEN** `omrg web` starts with no `--port` and no `web_port` in `omrg.jsonc`
- **THEN** it MUST listen on port 8765 of the loopback host

#### Scenario: Port taken

- **WHEN** port 8765 is in use and no other port is given
- **THEN** the command MUST exit with a message naming 8765 and the `--port` option

#### Scenario: Saved port applies next launch

- **WHEN** the browser session saves port 9100 and the server restarts without `--port`
- **THEN** `omrg.jsonc` MUST hold `"web_port": 9100`, the server MUST listen on 9100, and the running server MUST NOT have moved before the restart

#### Scenario: Port edited by hand

- **WHEN** the user sets `web_port` to 9200 in `omrg.jsonc` while the server runs on 8765
- **THEN** `GET /v1/settings/web-port` MUST report that the ports differ, and the next launch MUST listen on 9200

#### Scenario: Option wins

- **WHEN** `omrg.jsonc` sets a port and `--port 9200` is given
- **THEN** the server MUST listen on 9200

#### Scenario: Invalid port in the file

- **WHEN** `web_port` holds a value outside 1024 to 65535
- **THEN** the launch MUST ignore it, use 8765, and list the problem in Settings

### Requirement: The upload limit is set in Settings

The per-file upload limit SHALL be the `web_max_upload_mib` value of `omrg.jsonc`, in whole MiB from 1 to 2048. With no value the limit SHALL be 50 MiB. `GET /v1/settings/upload-limit` (read scope) SHALL return the limit in force, its source, the file value or `null`, the default, and the allowed range. `PUT /v1/settings/upload-limit` SHALL need a browser session, SHALL take `max_mib` (an integer in range, or `null` to clear the file value), SHALL write it to `omrg.jsonc` before it changes the running server, and SHALL apply it to new uploads at once, with no restart. A hand edit of the file SHALL also apply to new uploads at once. An upload that has already started SHALL keep the limit it started with. Settings › Workspace SHALL show the limit in force and its source, SHALL let the user edit it or return to the default, and SHALL state that the change applies to new uploads straight away.

#### Scenario: Raise the limit

- **WHEN** the user saves 200 MiB in Settings and then uploads a 120 MiB file
- **THEN** the server MUST accept the file without a restart, `omrg.jsonc` MUST hold `"web_max_upload_mib": 200`, and the value MUST still apply after a restart

#### Scenario: Return to the default

- **WHEN** the user clears the value
- **THEN** `omrg.jsonc` MUST no longer hold `web_max_upload_mib`, the limit in force MUST be 50 MiB, and Settings MUST say that the default applies

#### Scenario: Value out of range

- **WHEN** a request sets `max_mib` to 0, to 4096, or to a value that is not a whole number
- **THEN** the server MUST answer 400 with the allowed range and MUST NOT change the file or the running limit, and Settings MUST name the allowed range before it sends such a value

#### Scenario: Bearer credential

- **WHEN** a bearer credential sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST refuse it and MUST NOT change the limit

#### Scenario: Limit lowered during an upload

- **WHEN** the limit is lowered while a file upload is in progress
- **THEN** that upload MUST finish against the limit it started with, and the next upload MUST use the new limit

### Requirement: A launch option sets the upload limit without the web workspace

`omrg web` SHALL accept `--max-upload-mib <n>` and SHALL read `WEB_MAX_UPLOAD_MIB` from the environment or `.env` when the flag is absent, so the limit can be set when the web workspace cannot be used. The order SHALL be the flag, then the environment variable, then `web_max_upload_mib` in `omrg.jsonc`, then 50 MiB. Both launch forms SHALL take a whole number from 1 to 2048; any other value SHALL stop the launch with exit code 2 and a message that names the option and the range. While a launch option sets the limit, `GET /v1/settings/upload-limit` SHALL report `source: "launch"`, `PUT` SHALL answer 409 and change nothing, and Settings SHALL show the limit as set at launch with no edit control. `.env.example` and the CLI reference SHALL document both.

#### Scenario: Environment variable in .env

- **WHEN** `.env` holds `WEB_MAX_UPLOAD_MIB=300` and `omrg web` starts without `--max-upload-mib`
- **THEN** the limit in force MUST be 300 MiB, and the response MUST report `source: "launch"`

#### Scenario: Flag beats environment and saved value

- **WHEN** `omrg.jsonc` sets 200 MiB, the environment sets 300, and `omrg web --max-upload-mib 400` starts
- **THEN** the limit in force MUST be 400 MiB

#### Scenario: Invalid launch value

- **WHEN** `WEB_MAX_UPLOAD_MIB` is `0`, `5000` or `big`
- **THEN** `omrg web` MUST exit with code 2 before it binds a port and MUST name `WEB_MAX_UPLOAD_MIB` and the range 1 to 2048

#### Scenario: Settings while a launch option is set

- **WHEN** a launch option sets the limit and a browser session sends `PUT /v1/settings/upload-limit`
- **THEN** the server MUST answer 409, MUST keep the file and the running limit, and Settings MUST say the limit was set at launch and how to change it

#### Scenario: No launch option

- **WHEN** neither the flag nor the environment variable is set
- **THEN** the file value MUST apply, else 50 MiB, and the response MUST report `source: "config-file"` or `source: "default"`

## REMOVED Requirements

### Requirement: Workspace settings live in the workspace database

**Reason**: Settings now live in `omrg.jsonc` (ADR-087). Two stores made it unclear which value was in force.
**Migration**: `omrg web` moves existing rows into `omrg.jsonc` once on start, see `settings-file` "Saved settings move out of the workspace database". API keys stay in the system keychain behind a `keychain://` reference.
