## Context

See `proposal.md` for the problem. Current behaviour:

- `GuardMiddleware` (`src/omrg/transports/api/middleware.py`) checks `Host` on every request. On `/v1` paths it then checks `Sec-Fetch-Site` and `Origin`.
- `AccessPolicy` (`src/omrg/transports/api/security.py`) builds one fixed origin set from the loopback names and the bound port. Four places read it: the guard, `require_scope`, the session route and the MCP-over-HTTP transport (which also passes the set to the MCP SDK as `allowed_origins`).
- The web client calls the API with relative URLs and `credentials: "same-origin"` (`web/src/api/client.ts`, `bootstrap.ts`).

Observed on 2026-10-15: `POST /v1/session` returned 403, not 400. The `Host` check runs first, so Orca's proxy already sends an acceptable `Host`. The `Origin` recorded earlier by a logging proxy was `http://llamaindex-rag-mcp-feat-redesign-web-workspace-3.orca.localhost:57977`. The page comes from that origin and the client uses relative URLs, so the browser marks the requests `same-origin`. Only the `Origin` rule rejects them.

## Goals / Non-Goals

**Goals:**

- One launch option approves extra exact origins for one run.
- Every origin check honours the approval through a single source of truth.
- The default (no flag) behaves exactly as today.

**Non-Goals:**

- Wildcard hosts or wildcard ports (for example `*.orca.localhost:*`).
- Saving approved origins in Settings, the workspace or an environment variable.
- Any change to the `Host` check, the `Sec-Fetch-Site` check, cookies, scopes or the bootstrap flow.
- Non-loopback origins.

## Decisions

**1. Exact origin match.** Each value is one `scheme://host[:port]`. The policy compares the lower-cased `Origin` header with the stored set, as it does today.
Alternatives: a `*.orca.localhost` wildcard approves every local page under that suffix, which is more than the operator can see in the address bar. A regex is harder to explain and to test. Both are rejected. The cost is that the operator passes the origin from the preview address bar for each launch.

**2. Loopback hosts only.** The host must be `localhost`, a name ending in `.localhost`, or a loopback IP (`127.0.0.1`, `[::1]`). A `.localhost` name is reserved (RFC 6761) and browsers resolve it to the local machine. A public origin would let a remote page submit work to a local server, which the existing spec forbids.

**3. Normalise once, in a new module.** `parse_extra_origin(value) -> str` in `src/omrg/transports/api/origins.py` lower-cases the value, rejects a path (other than a lone `/`), query, fragment, user information, wildcard and non-`http(s)` scheme, and drops the default port (80 or 443) because browsers omit it from `Origin`. It raises `ValueError` with a message that names the rule, the same pattern as `validate_bind_host`. `security.py` is at 455 of the 500-line ceiling (`tests/test_file_size_ceiling.py`), so the logic does not go there.

**4. `AccessPolicy` owns the merge.** `AccessPolicy.__init__` and `for_launch` take `extra_origins: Iterable[str] = ()`, call `parse_extra_origin` on each and add the result to the origin set. `origin_allowed` and `allowed_origins` need no change, so the guard, `require_scope`, the session route and MCP over HTTP all follow. `allowed_hosts` stays as it is. The CLI also calls `parse_extra_origin` early, with the other argument checks, so a bad value stops the command before the socket is bound. The second call in the policy is idempotent.

**5. Leave `Host` and `Sec-Fetch-Site` alone.** The evidence above shows neither blocks the Orca preview. Relaxing `Sec-Fetch-Site` for approved origins would open a path for genuine cross-site requests from the approved origin, with no gain. If the manual check in task 4.3 shows that `Sec-Fetch-Site` blocks the preview, stop and revise this design. Do not relax the check inside the apply phase.

**6. Per-run only, command line only.** Approving an origin is a security decision for whoever starts the server. A Settings entry would put that decision behind the very check it relaxes. An environment variable would let a stray shell profile approve origins without the operator noticing. The server prints each approved origin at launch, to stderr like the rest of the CLI output.

## Risks / Trade-offs

- [A page at the approved origin shares the session cookie with the Orca preview] → The operator chose that origin. Only the exact origin passes. Session scopes and the one-time bootstrap are unchanged.
- [DNS rebinding] → The `Host` check is unchanged and still demands a loopback name with the bound port.
- [Orca's port, or the number at the end of its preview host name, changes when Orca reopens the preview, so the approved origin goes stale] → Observed on 2026-10-15: the host name moved from `...core-web-2` to `...core-web-3` between two openings. The preview fails with the same 403 and the operator relaunches with the new origin, or passes several suffixes at once (the option is repeatable). The operator accepted exact matching for now (2026-10-15). A suffix pattern is a possible follow-up if this proves common.
- [The preview still fails because of proxy behaviour that is not visible from here (for example `Set-Cookie` handling)] → Task 4.3 checks the real preview. If it fails, record the finding and revise before archive.
- [`--allow-origin` is mistaken for a CORS setting] → The docs say it approves one origin for this run only and does not change `Host` or cookie rules.

## Migration Plan

No data change. Existing launches behave as before. Roll back by removing the option; no stored state refers to it.
