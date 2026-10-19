# Spec Delta

## MODIFIED Requirements

### Requirement: The on/off state persists and changes only from the browser session

`GET /v1/mcp` (read scope) SHALL return `{ enabled, source, url, token }`, where `url` is the full `/mcp` address on the bound host and port and `token` describes the MCP token without its value (`{ exists, created_at }`). `PUT /v1/mcp` with `{ enabled }` SHALL require the browser session, SHALL write `mcp_http_enabled` to `omrg.jsonc`, SHALL take effect without a restart, and SHALL return the new state. The file value SHALL apply on every later launch, and a hand edit of it SHALL apply without a restart.

#### Scenario: Enable survives a restart

- **WHEN** the browser session enables MCP over HTTP and the server restarts
- **THEN** `omrg.jsonc` MUST hold `"mcp_http_enabled": true`, `GET /v1/mcp` MUST report `enabled: true` and `/mcp` MUST accept a valid token

#### Scenario: Turned off by hand

- **WHEN** the server serves `/mcp` and the user sets `mcp_http_enabled` to `false` in `omrg.jsonc`
- **THEN** the next request to `/mcp` MUST receive 404

#### Scenario: Bearer credential cannot toggle

- **WHEN** a bearer credential, including the MCP token, calls `PUT /v1/mcp`
- **THEN** the server MUST refuse it and the file MUST NOT change
