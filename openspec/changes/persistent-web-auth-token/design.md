# Design

## Context

Observed in the code:

- `AccessPolicy` (`transports/api/security.py`, 497 lines) holds a one-time bootstrap secret, the session digests and the bearer credentials, all in memory. `POST /v1/session` checks the `Origin`, calls `exchange_bootstrap` and sets the cookie `omrg_session_<port>` (HttpOnly, SameSite=Strict).
- `RearmingAccessPolicy` (`launch_link.py`) overrides `exchange_bootstrap`. After each successful exchange it writes a new link to `<workspace>/launch-link`. `omrg web open` reads that file.
- `GuardMiddleware` checks `Host` on every request, static or API. On `/v1` it also checks `Origin`, fetch metadata and the query string.
- `FrontendFallback` (`static.py`) serves `index.html` for `/` and for every front-end route, with `Cache-Control: no-cache`.
- The page (`web/src/main.tsx`) calls `exchangeBootstrap()` once, then renders. `createApiClient` throws `ApiError` on 401, and `describeError` shows "The workspace session was not accepted".
- The redaction pattern `omrg_(bs|ss|bt|mcp)_…` removes a bootstrap-shaped value from every log line. `looks_like_credential` refuses such a value in a query string.
- The OMMS reference: `src/services/auth-token.ts` keeps a 32-byte token in `~/.omms/.auth-token` (0600). `web-server.ts` puts the token into the served page; `cors.ts` refuses foreign browser origins.

## Goals / Non-Goals

**Goals:**

- An open tab keeps working after a server restart with the same workspace, with no user action.
- The secret reaches only a page load of the server's own origin.
- The cookie, scopes, bearer credentials and request checks stay as they are.

**Non-Goals:**

- Sessions that survive a restart. Each restart still ends every session; the page gets a new one.
- Secret rotation from the page.

## Decisions

### D1. One secret file per workspace, in the bootstrap format

The secret is `omrg_bs_` plus `secrets.token_urlsafe(32)` (256 bits). It lives in `<workspace>/.auth-token`, because the workspace is the unit that one server owns (`WorkspaceLock`), and the user already trusts its folder with `workspace.db` and `launch-link`. A second workspace has its own secret.

The `omrg_bs_` prefix is deliberate. The existing redaction pattern and the query-string guard then cover the secret with no new code, and the value fits the existing `bootstrap` field of `POST /v1/session`.

`PageSecret.load_or_create` uses `make_private_dirs`, so a new workspace folder gets mode 0700. An existing folder keeps its mode, as the workspace rules already say (the operator can choose a shared parent). The file itself is always 0600:

- It is written to a `mkstemp` file (mode 0600) and renamed into place, so no reader sees a partial secret.
- It is opened with `O_NOFOLLOW`, so a symbolic link is refused.
- A mode looser than 0600 gets a warning. When the current user owns the file, the mode is set to 0600. The server does not stop.
- A file whose content is not a valid secret gets a warning and is replaced. A crash cannot cause this (the write is atomic), so it means a hand edit.

The warnings name the path and the mode, never the value.

### D2. The page carries the secret only to its own origin

`FrontendFallback` adds `<meta name="omrg-page-secret" content="…">` before `</head>` when `page_may_carry_secret` allows it:

1. `Host` is one of the server's own loopback names with the bound port. The guard has already refused any other `Host` with 400. The rule checks it again, so it stands alone. This is the DNS-rebinding guard: a foreign name that resolves to 127.0.0.1 never gets the page.
2. An `Origin` header, when present, is the server's own origin or one approved with `--allow-origin`. A top-level navigation sends no `Origin`.
3. `Sec-Fetch-Site` is absent, `none` or `same-origin`, or `Sec-Fetch-Mode` is `navigate`. A cross-site or same-site `fetch` gets the page without the secret.

A foreign page cannot read a cross-origin response, and the server sends no CORS headers. A navigation from another site therefore gets the secret but cannot read it. `X-Frame-Options: DENY` and `frame-ancestors 'none'` stop a frame. The page with the secret is sent with `Cache-Control: no-store`. `/index.html` takes the same path as `/`.

A meta tag needs no inline script, so a later `script-src` policy does not break it.

### D3. Sign-in goes through the existing session route

`POST /v1/session` keeps its body `{"bootstrap": "…"}` and its `Origin` check. The route now checks the page secret first, with a constant-time compare. On a match it calls the new `AccessPolicy.open_session()`, which mints a session exactly as the bootstrap exchange does. Otherwise it calls `exchange_bootstrap` as before, so a wrong guess still counts toward the 20-failure limit of the one-time link.

The page-secret check is in the route and not in `exchange_bootstrap`. `RearmingAccessPolicy.exchange_bootstrap` renews the login-item link after each successful exchange. A silent re-sign-in would then renew the link and break a link that the user printed with `omrg web open --print` a moment before. The failure limit also does not apply to the page secret, so 20 wrong guesses from another local program cannot lock out the page. A guess of a 256-bit value is not a practical attack.

`security.py` was at 497 lines. `open_session` needs four more lines, so `validate_bind_host` moves to `bind_address.py`, the same way `SecretSet` moved to `secret_set.py`. `app.py`, `cli/web.py` and the test import it from the new module.

### D4. The page signs in again on 401, once

`main.tsx` reads the tag with `takePageSecret` (which removes the tag) and builds one renewer with `createSessionRenewer`. `startSession` signs in on load: with the launch-link secret when the address has one, else, or when that fails, with the page secret. `ApiProvider` passes the renewer to `createApiClient`.

When a response is 401 and a renewer exists, the client awaits the renewer and, when it succeeds, sends the request once more with the same method, headers and body. A second 401 is reported as before. The renewer shares one in-flight `POST /v1/session` between all callers, so ten queries that fail together after a restart cause one sign-in. A 403 never triggers a sign-in: it means a foreign origin or a missing scope, which a new session does not fix.

Event streams (`EventSource`) are not changed. They already fall back to polling through the client, and the poll signs in again.

### D5. Messages after a restart

`omrg web restart`, the power menu and the restart dialog said that the browser is signed out. They now say that the page signs in again by itself. They still name `omrg web open`, because a restart that changes the port moves the app to a new origin, and an open tab cannot follow it. The 401 message of `describeError` now says to reload the page or run `omrg web open`.

### D6. What stays

- `omrg web open` still opens the one-time link from `launch-link` and prints the address without the secret. The page uses the link first. If the link was already used, the page falls back to the page secret, so the sign-in still works.
- The foreground `omrg web` still prints the one-time link.
- Bearer credentials, MCP tokens, scopes and the `Origin` check on state-changing requests do not change.

## Risks / Trade-offs

- **Local programs can sign in.** Any program that runs as the user can read `.auth-token` and get a session. The login-item `launch-link` file and `workspace.db` already accept this trust level. OMMS accepts it too. The secret does not widen access beyond what the user's own account can already reach. ADR-088 records this.
- **The secret does not expire.** It lasts until the file is deleted. To rotate it, stop the server, delete `<workspace>/.auth-token` and start the server again. Open tabs then get 401 and must be reloaded.
- **Session digests grow with page loads.** Each load or re-sign-in adds one 32-byte digest to the in-memory set until the server stops. A thousand reloads cost about 32 KB. No limit is added.
- **A first start race.** Two `omrg web` processes that start at the same moment on a new workspace can both write the file. The last write wins, and the other process then fails to take the workspace lock and stops.

## Migration Plan

No data migration. The first start after the upgrade creates `.auth-token`. Tabs that were open before the upgrade have no secret; they need one reload.
