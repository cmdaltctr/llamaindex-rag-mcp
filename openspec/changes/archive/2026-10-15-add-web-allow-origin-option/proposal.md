# Proposal

## Why

The web workspace refuses every login that does not come from its own loopback address. Orca's embedded browser preview serves the workspace page from its own address (for example `http://<worktree>.orca.localhost:<port>`). The login request carries that address as its `Origin`, so the server returns 403 and the page reports "The workspace session was not accepted". Users who work inside Orca cannot use the preview. The only workaround today is to open a separate browser and paste the link by hand.

## Changes

- Add a repeatable `omrg web --allow-origin <origin>` launch option. Each value approves one extra browser origin for this run only.
- Accept only an exact origin: scheme (`http` or `https`), host and optional port. Refuse a value with a path, query, fragment, user information or wildcard.
- Accept only a loopback host: `localhost`, a name ending in `.localhost`, `127.0.0.1` or `[::1]`. Refuse any other host with a message that names the rule. Exit code 2, as for a bad `--root`.
- Print each approved extra origin at launch, so the user can see what the server accepts.
- Keep the default unchanged. With no flag, the server accepts the same origins as today.
- Keep the `Host` check and the `Sec-Fetch-Site` check unchanged (see `design.md` for the evidence).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-web-workspace`: adds one requirement. The operator can approve extra loopback origins at launch. The approval is explicit, exact, per run and applies to every origin check (login, state-changing requests, MCP over HTTP).

## Impact

- Code: `src/omrg/transports/cli/web.py` (new option), `src/omrg/transports/api/security.py` (`AccessPolicy` takes the extra origins), new `src/omrg/transports/api/origins.py` (validation; `security.py` is at 455 of 500 lines).
- Consumers of `AccessPolicy.origin_allowed` and `allowed_origins` need no edit: `middleware.py`, `routes.py`, `mcp_http.py` and `security.py:require_scope`.
- Docs: `docs/guides/web-workspace.md` and `docs/guides/cli-reference.md` (option table and request checks).
- Tests: `tests/unit/test_web_security.py` and `tests/unit/test_web_launch.py`.
- No new dependency. No change to the OpenAPI contract, the stored workspace data or the default behaviour.
