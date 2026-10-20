# ADR-088: Persistent Workspace Sign-in Secret

- **Date:** 2026-10-20
- **Status:** Accepted (2026-10-20; the user approved the design)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-085](085-web-login-item.md) (web login item; this ADR amends its sign-in consequence), [ADR-086](086-web-power-menu.md) (power menu), [ADR-079](079-approve-extra-loopback-origins-at-launch.md) (approved origins), [ADR-077](077-web-workspace-client-foundation.md) (web client)
- **Change:** `openspec/changes/persistent-web-auth-token/` (design D1 to D6)

## Context

The browser signs in to `omrg web` with a one-time secret in the `#bootstrap=`
fragment of the launch link. The server holds that secret and every browser
session in memory. Each restart therefore signs every browser out: a restart
from the power menu, `omrg web restart`, a reinstall or a reboot. The open tab
then shows "The workspace session was not accepted", and the user must run
`omrg web open` for a new link.

ADR-085 accepted this as a negative consequence of the login item. In daily use
it is the most frequent friction: every restart-only setting change, every
upgrade and every power-menu Restart needs a terminal.

OMMS solves the same problem with one persistent token in `~/.omms/.auth-token`
(mode 0600). Its web server puts the token into the page it serves, and its
CORS rule refuses foreign browser origins. A foreign web page cannot read the
token, because a browser does not let a page read a cross-origin response.

## Decision

1. **One secret per workspace** (D1). The server keeps one secret in
   `<workspace>/.auth-token`: `omrg_bs_` plus `secrets.token_urlsafe(32)`. It
   creates the file on the first start with mode 0600 (written to a temporary
   file and renamed), and creates a missing workspace folder with mode 0700. It
   reads the same secret on every later start. A looser mode gets a warning and
   is set to 0600 when the user owns the file. A broken file is replaced. The
   bootstrap prefix means that the existing log redaction and query-string guard
   cover the secret with no new code.
2. **The page carries the secret to its own origin only** (D2). The server adds
   `<meta name="omrg-page-secret">` to `index.html` only when the `Host` is one
   of its own loopback names with the bound port, any `Origin` is its own or
   approved with `--allow-origin`, and the fetch metadata shows a same-origin
   request or a navigation. That page is sent with `Cache-Control: no-store`.
   The `Host` rule is the DNS-rebinding guard.
3. **The existing session route takes the secret** (D3). `POST /v1/session`
   keeps its body, its `Origin` check and its cookie. It checks the workspace
   secret first and mints a session with `AccessPolicy.open_session()`. That
   path never spends or renews the one-time link, and wrong guesses never
   disable the workspace secret.
4. **The page signs in again on 401, once** (D4). On load the page uses a
   launch link when the address has one, else, or when the link is refused, the
   workspace secret. After any 401 the client signs in again once and repeats
   the request once. Requests that fail together share one sign-in.
5. **The one-time link stays** (D6). `omrg web` still prints it and
   `omrg web open` still opens it. Their output does not change.

## Consequences

### Positive

- An open tab keeps working after a restart with the same workspace and port.
  The power menu Restart, `omrg web restart` and an upgrade need no terminal.
- Sessions, scopes, bearer credentials, MCP tokens and the request checks are
  unchanged. The cookie is still HttpOnly and SameSite=Strict.
- No new route and no change to the OpenAPI schemas; only descriptions changed.

### Negative

- **Any program that runs as the user can sign in.** It can read
  `.auth-token` and post it from a loopback client with the server's own
  `Origin`. This is the trust level that the login-item `launch-link` file
  (ADR-085) and `workspace.db` already accept, and that OMMS accepts. Before
  this ADR, such a program could already read `launch-link` and sign in; now it
  can do so also when no login item runs. The secret gives no access beyond
  what the user's own account can reach.
- The secret does not expire. To rotate it, stop the server, delete
  `<workspace>/.auth-token`, start the server and reload each open tab.
- Each page load or silent re-sign-in adds one 32-byte digest to the in-memory
  session set until the server stops. No limit is added.
- A restart that changes the port moves the app to a new origin. An open tab
  cannot follow it, so the copy still names `omrg web open`.

### Neutral

- `validate_bind_host` moved from `security.py` to `bind_address.py`, so
  `security.py` stays under the 500-line ceiling (ADR-085 noted it at 497).
- The `npm run dev` server serves its own `index.html` without the secret and
  keeps using the launch link.

## Alternatives Considered

- **Persistent sessions** (store session digests in `workspace.db`, or sign the
  cookie with a persistent key). Rejected: the cookie would then outlive the
  server, and a stolen cookie would last as long as the key. The chosen design
  keeps sessions short and only the sign-in secret long.
- **Check the workspace secret inside `exchange_bootstrap`.** Rejected:
  `RearmingAccessPolicy` renews the login-item link after each successful
  exchange, so a silent re-sign-in would break a link that the user printed a
  moment before with `omrg web open --print`.
- **Send the secret as a header on every request, as OMMS does.** Rejected: it
  changes the authentication of every route, the OpenAPI security schemes and
  the bearer and MCP paths. Posting it once to the existing session route keeps
  the security model as it is.
- **An inline script instead of a meta tag.** Rejected: a later `script-src`
  Content-Security-Policy would block it.
- **Make `omrg web open` open the plain address.** Not needed: the page falls
  back to the workspace secret when a link is spent, and keeping the link keeps
  the command's output and spec unchanged.

## References

- `src/omrg/transports/api/page_secret.py`, `static.py`, `routes/foundation.py`
- `web/src/api/bootstrap.ts`, `web/src/api/client.ts`
- `tests/unit/test_web_page_secret.py`, `web/src/api/session.test.ts`
- [Web workspace guide: Browser session](../guides/web-workspace.md#browser-session)
- OMMS reference: `src/services/auth-token.ts`, `src/services/web-server.ts`, `src/services/cors.ts`

## Addendum (2026-10-20): Verification on the Live Login Item

The user reinstalled the login item from `v3` at `fcb4f1c` and checked it on port 8765.

- The plain address signed in with no launch link.
- After `omrg web restart`, an open tab kept working with no reload. The first request got 401, the page signed in again by itself, and the repeated request got 200.
- A tab loaded before the upgrade has the old page code. It needs one reload.
