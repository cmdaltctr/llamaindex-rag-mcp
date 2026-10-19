# ADR-079: Approve Extra Loopback Origins at Launch

- **Date:** 2026-10-15
- **Status:** Accepted (2026-10-15; evidence: `tests/unit/test_web_origins.py` (23) and the new cases in `tests/unit/test_web_security.py`, `tests/unit/test_web_launch.py` and `tests/unit/test_web_mcp_http.py` pass; `./scripts/local_ci.sh` exits 0; live server with seven `--allow-origin` values: a probe with a wrong secret got 401 from an approved origin and 403 from an unapproved Orca host name and from `http://evil.example`; in the Orca preview at `http://llamaindex-rag-mcp-v3-integration-core-web-4.orca.localhost:57977` the sign-in returned 200, `GET /v1/collections` returned 200 and the Knowledge Base listed the `documents` collection. An earlier 403 came from approving host name `-2` while the preview used `-3`.)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (local web runtime), [ADR-076](076-serve-mcp-from-the-web-server-with-a-lifespan-provided-engine.md) (MCP over HTTP)
- **Change:** `openspec/changes/add-web-allow-origin-option/` (design D1 to D6)

## Context

The web server accepts an API request only when its `Origin` is one of the
server's own loopback addresses. An embedded preview pane, for example the
Orca browser preview, serves the workspace page from its own address
(`http://<worktree>.orca.localhost:<port>`). Every sign-in from that page
carries a foreign `Origin`, so the server returns 403 and the page shows
"The workspace session was not accepted". A logging proxy recorded the real
`Origin` on 2026-10-15. The `Host` check passed, and the client uses
relative URLs, so the browser marks the requests `same-origin`. Only the
`Origin` rule rejects them.

## Decision

1. **A repeatable launch option approves extra origins.**
   `omrg web --allow-origin <origin>` adds one exact origin per value to the
   origin set of `AccessPolicy`. Every reader of that set follows: the
   request guard, `require_scope`, the session route and MCP over HTTP
   (including the allowed-origin list that goes to the MCP SDK).
2. **Match exactly.** A value is `scheme://host[:port]`. `parse_extra_origin`
   lower-cases it and drops the default port of the scheme. It refuses a
   wildcard, path, query, fragment, user information, a scheme other than
   `http` or `https`, and an invalid port.
3. **Loopback hosts only.** The host must be `localhost`, a `.localhost`
   name, or a loopback IP address. Any other host stops the command with
   exit code 2 before a port is bound.
4. **Leave `Host` and `Sec-Fetch-Site` unchanged.** The evidence shows
   neither blocks the Orca preview. A request from an approved origin still
   fails on a foreign `Host` (400) or cross-site fetch metadata (403).
5. **Per run, command line only.** The server prints each approved origin
   before the launch link. There is no setting, no environment variable and
   no saved state.

## Consequences

### Positive

- The Orca preview can sign in without a second browser.
- The default is unchanged. With no flag, the same origins pass as before.
- One source of truth. No consumer of the origin set needed an edit.

### Negative

- The operator passes the origin on every launch. Orca can change its port,
  or the number at the end of the preview host name (seen moving from `-2`
  to `-3` to `-4`), and then the approved origin is stale. The option is
  repeatable, so several host names can be approved at once. A suffix
  pattern is a possible follow-up.
- A page at an approved origin shares the session with the operator's
  browser tab. The operator chose that origin.

### Neutral

- The new parser sits in `origins.py` because `security.py` is near the
  500-line ceiling.
- Rollback removes the option. No stored data refers to it.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Wildcard such as `*.orca.localhost`** | It approves every local page under the suffix, which is more than the operator can see in the address bar. |
| **Allow any `.localhost` origin by default** | It widens the default for every user to fix one preview tool. |
| **Relax `Sec-Fetch-Site` for approved origins** | The evidence shows it does not block the preview. Relaxing it would also admit real cross-site requests from the approved origin. |
| **Saved setting or environment variable** | A setting sits behind the check it relaxes. A variable lets a shell profile approve origins without the operator noticing. |
| **Proxy that rewrites `Origin`** | It hides the origin from the server and needs a second program to run. |

## References

- `src/omrg/transports/api/origins.py`, `src/omrg/transports/api/security.py`, `src/omrg/transports/api/middleware.py`, `src/omrg/transports/api/mcp_http.py`
- `src/omrg/transports/cli/web.py`
- `docs/guides/web-workspace.md`, `docs/guides/cli-reference.md`, `docs/guides/mcp-tools.md`
