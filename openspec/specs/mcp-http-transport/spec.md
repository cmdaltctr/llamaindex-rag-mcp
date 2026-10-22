# mcp-http-transport Specification

## Purpose
Serve the OMRS MCP tools over streamable HTTP from the local web server, so MCP clients and the browser share one running server and one Engine, with explicit on/off control and token authentication.

## Requirements

### Requirement: The web server serves MCP over streamable HTTP when enabled

The `omrs web` server SHALL serve the same MCP tools as the stdio server over streamable HTTP at `/mcp`, with stateful sessions so sampling and multi-round answers work. The endpoint SHALL be off on a new workspace. While it is off, every request to `/mcp` SHALL receive 404, including requests on sessions opened before it was turned off.

#### Scenario: Same tools as stdio

- **WHEN** an authorised client lists tools on `/mcp`
- **THEN** the list MUST equal the stdio server's tool names, descriptions and annotations

#### Scenario: Off by default

- **WHEN** a new workspace starts and a client sends a valid token to `/mcp`
- **THEN** the server MUST answer 404

#### Scenario: Turning off ends open sessions

- **WHEN** a client holds an open session and the endpoint is turned off
- **THEN** the next request on that session MUST receive 404

### Requirement: The on/off state persists and changes only from the browser session

`GET /v1/mcp` (read scope) SHALL return `{ enabled, source, url, token }`, where `url` is the full `/mcp` address on the bound host and port and `token` describes the MCP token without its value (`{ exists, created_at }`). `PUT /v1/mcp` with `{ enabled }` SHALL require the browser session, SHALL write `mcp_http_enabled` to `omrs.jsonc`, SHALL take effect without a restart, and SHALL return the new state. The file value SHALL apply on every later launch, and a hand edit of it SHALL apply without a restart.

#### Scenario: Enable survives a restart

- **WHEN** the browser session enables MCP over HTTP and the server restarts
- **THEN** `omrs.jsonc` MUST hold `"mcp_http_enabled": true`, `GET /v1/mcp` MUST report `enabled: true` and `/mcp` MUST accept a valid token

#### Scenario: Turned off by hand

- **WHEN** the server serves `/mcp` and the user sets `mcp_http_enabled` to `false` in `omrs.jsonc`
- **THEN** the next request to `/mcp` MUST receive 404

#### Scenario: Bearer credential cannot toggle

- **WHEN** a bearer credential, including the MCP token, calls `PUT /v1/mcp`
- **THEN** the server MUST refuse it and the file MUST NOT change

### Requirement: MCP clients authenticate with a durable, hashed token

One MCP token SHALL exist at most. `POST /v1/mcp/token` (browser session) SHALL create a random token or replace the existing one, SHALL store only its SHA-256 hash and creation time in the workspace database, and SHALL return the token value in that response only. `DELETE /v1/mcp/token` (browser session) SHALL revoke it. Requests to `/mcp` SHALL carry `Authorization: Bearer <token>`; a missing, wrong or revoked token SHALL receive 401 before any MCP processing. The token SHALL grant only the `mcp` scope, and no `/v1` route SHALL accept it. The token value SHALL NOT appear in logs, error responses or `GET /v1/mcp`.

#### Scenario: Shown once

- **WHEN** the browser session creates the token and then reads `GET /v1/mcp`
- **THEN** the create response MUST contain the token and the read response MUST NOT

#### Scenario: Rotation revokes the old token

- **WHEN** the token is replaced
- **THEN** a request to `/mcp` with the old token MUST receive 401

#### Scenario: Token survives a restart

- **WHEN** the server restarts
- **THEN** the existing token MUST still authenticate `/mcp`

#### Scenario: Token cannot reach the REST API

- **WHEN** the MCP token is sent to any `/v1` route
- **THEN** the route MUST refuse it

### Requirement: MCP over HTTP keeps the local host and origin rules

Requests to `/mcp` SHALL pass the same Host check as the rest of the web server and the MCP SDK's DNS-rebinding protection, limited to the bound loopback host and port. A request whose `Origin` header names another origin SHALL be refused. Requests without an `Origin` header SHALL be allowed, because MCP clients are not browsers.

#### Scenario: Foreign origin

- **WHEN** a request to `/mcp` carries a valid token and `Origin: https://example.com`
- **THEN** the server MUST refuse it before any tool runs

#### Scenario: Rebound host name

- **WHEN** a request to `/mcp` carries a `Host` header that is not the bound loopback address and port
- **THEN** the server MUST refuse it

### Requirement: File paths over HTTP stay inside the approved roots

Over HTTP, `ingest_documents` and `get_codebase_map` SHALL accept only paths inside the directories approved with `--root`, resolved the same way as the web API's file grants. A path outside them SHALL return the standard MCP error dict and SHALL NOT be read. Over stdio, path handling SHALL stay unchanged.

#### Scenario: Path outside the roots

- **WHEN** a client calls `ingest_documents` over HTTP with a path outside every approved root
- **THEN** the tool MUST return `{"status": "error", ...}` and MUST NOT read the path

#### Scenario: Symlink escape

- **WHEN** the path is inside an approved root but resolves through a symlink to a place outside it
- **THEN** the tool MUST refuse it

### Requirement: HTTP MCP work uses the web server's Engine and admission

Tool calls over HTTP SHALL run on the web runtime's Engine and SHALL be admitted through the runtime's admission gate, so shutdown waits for them like any other engine work. Server shutdown SHALL close the MCP session manager before the Engine closes.

#### Scenario: Shared index

- **WHEN** a document is ingested through the web API and a client then searches over `/mcp`
- **THEN** the search MUST find it without a restart

#### Scenario: Shutdown order

- **WHEN** the server shuts down while an MCP tool call runs
- **THEN** the call MUST finish or be cancelled before the Engine closes
