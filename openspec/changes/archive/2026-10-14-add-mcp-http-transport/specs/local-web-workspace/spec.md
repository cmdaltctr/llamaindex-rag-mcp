# local-web-workspace delta

## ADDED Requirements

### Requirement: The web server listens on a stable port

`omrg web` SHALL choose its port in this order: the `--port` option, then the port saved in the workspace, then 8765. `--port 0` SHALL pick a free port for that launch. When the chosen port is taken, the command SHALL exit with an error that names the port and tells the user to pass `--port <n>`. `PUT /v1/settings/web-port` with `{ port }` (browser session only, 1024 to 65535, or `null` to clear) SHALL save the port for later launches and SHALL NOT rebind the running server. `GET /v1/settings/web-port` (read scope) SHALL return the saved port and the bound port.

#### Scenario: Default port

- **WHEN** `omrg web` starts with no `--port` and no saved port
- **THEN** it MUST listen on port 8765 of the loopback host

#### Scenario: Port taken

- **WHEN** port 8765 is in use and no other port is given
- **THEN** the command MUST exit with a message naming 8765 and the `--port` option

#### Scenario: Saved port applies next launch

- **WHEN** the browser session saves port 9100 and the server restarts without `--port`
- **THEN** the server MUST listen on 9100, and the running server MUST NOT have moved before the restart

#### Scenario: Option wins

- **WHEN** a port is saved and `--port 9200` is given
- **THEN** the server MUST listen on 9200

### Requirement: Workspace settings live in the workspace database

Settings that the web workspace changes at run time SHALL be stored in a `workspace_settings` key-value table of the workspace database, added by a schema migration. Only the keys `mcp_http_enabled` and `web_port` SHALL exist, each validated on read; a value that fails validation SHALL be treated as unset. Provider and engine settings SHALL NOT be stored there.

#### Scenario: Invalid stored value

- **WHEN** `web_port` holds a value outside 1024 to 65535
- **THEN** the launch MUST ignore it and use the next source in the port order
