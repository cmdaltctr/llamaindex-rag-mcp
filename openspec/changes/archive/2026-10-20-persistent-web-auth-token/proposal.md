# Proposal

## Why

A restart of `omrg web` signs every browser out. The sign-in secret and the browser sessions live only in server memory. A restart from the power menu, `omrg web restart`, a reinstall or a reboot therefore ends every session. The open tab then shows "The workspace session was not accepted. Open the workspace again from the link that omrg web prints". The user must run `omrg web open` to get a new one-time `#bootstrap=` link.

OMMS does not have this problem. It keeps one secret in a private file, puts the secret into the page that it serves, and the page sends it with each request. The secret lasts across restarts.

## What Changes

- The server keeps one persistent sign-in secret in `<workspace>/.auth-token`. It creates the file on the first start (folder mode 0700 when it creates the folder, file mode 0600) and reads the same secret on every later start. A file with a looser mode gets a warning and, when the user owns it, mode 0600. A broken file is replaced, with a warning.
- The server puts the secret into `index.html` as a `<meta name="omrg-page-secret">` tag, only when the request is a page load of its own origin: the `Host` check passes, any `Origin` is the server's own or one approved with `--allow-origin`, and the fetch metadata shows a same-origin request or a navigation. That page is sent with `Cache-Control: no-store`. Any other request gets the page without the secret.
- The page reads the tag once and removes it. On load it signs in with the launch-link secret when the address has one, else, or when that fails, with the page secret. It posts to the existing `POST /v1/session`, so the session cookie (`omrg_session_<port>`, HttpOnly, SameSite=Strict) and the scope model do not change.
- When any API request gets 401, the client signs in again with the page secret once, then sends the request again once. Requests that fail together share one sign-in.
- A sign-in with the page secret does not spend or renew the one-time launch link. `omrg web open` and old `#bootstrap=` links keep working, and the output of `omrg web open` does not change.
- The messages that said "the browser is signed out" after a restart change: `omrg web restart`, the power menu and the restart dialog now say that the page signs in again by itself.
- `validate_bind_host` moves from `security.py` to `bind_address.py`, so that `security.py` stays under the 500-line ceiling. The behaviour does not change.
- Docs: the web workspace guide, the CLI reference and the API module table. ADR-088 records the decision and amends ADR-085.

## Non-goals

- Persistent browser sessions. Sessions stay in memory. Only the sign-in secret persists.
- A change to bearer credentials, MCP tokens, scopes, the Origin check on state-changing requests, or the `Host` check.
- A way to rotate the secret from the page. Deleting the file and restarting the server makes a new secret.
- The `npm run dev` server. It serves its own `index.html`, which has no secret, and keeps using the launch link.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `local-web-workspace`: a new requirement for the persistent sign-in secret, and the login-item link requirement no longer says that a browser must sign in again after a restart.
- `web-login-item`: the restart and power-control scenarios say that an open tab signs in again by itself.
- `workspace-presentation`: the power menu copy.
- `workspace-settings`: the restart dialog copy.

## Impact

- Python: `transports/api/page_secret.py` (new), `bind_address.py` (new, moved code), `security.py`, `static.py`, `app.py`, `routes/foundation.py`, `transports/cli/web.py`, `transports/cli/web_login_item.py`, `openapi.yaml` (description only).
- Front end: `api/bootstrap.ts`, `api/client.ts`, `api/ApiProvider.tsx`, `main.tsx`, `lib/errors.ts`, `components/PowerMenu.tsx`, `settings/RestartDialog.tsx`.
- Trust: any program that runs as the user can read `.auth-token` and sign in. That is the trust level that the login-item link file and `workspace.db` already accept.
