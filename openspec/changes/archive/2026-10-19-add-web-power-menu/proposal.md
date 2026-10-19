# Proposal

## Why

The power icon in the navigation foot only shows a status light and names two terminal commands. The user pressed it expecting an off switch and nothing happened. The web app runs as a login item (change `add-web-login-item`), so the user needs a way to turn it off or restart it from the page.

## What Changes

- The power panel gains two buttons: **Turn off** and **Restart**. Each opens a confirmation dialog first.
- New route `POST /v1/server/power` with the body `{"action": "restart" | "off"}`. New route `GET /v1/server/power` reports whether the running app is the login item, so the page knows if the buttons can work. Both routes need the browser session with the `manage` scope. A bearer credential never passes.
- **Restart** asks launchd to send `SIGTERM` to the app (the same step as `omrg web restart`). launchd starts the app again.
- **Turn off** asks launchd to unload the agent (`launchctl bootout`). The app ends and stays off. The plist stays in place, so the app starts again at the next login.
- New command `omrg web start` loads the agent again after Turn off. It is the way back on from a terminal.
- The server refuses both actions with `409` while a run, ingestion or map call is in progress, so launchd does not kill work at its exit timeout.
- When the app was not started as the login item (a foreground `omrg web`), the buttons stay disabled and the panel keeps the terminal commands.
- The foreground panel text and the spec line "no Restart button and no Stop button" are replaced.
- A new ADR (ADR-086) records the decision. ADR-085 gets one line in its addendum: Turn off is a second way to stop the app.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `web-login-item`: the app can be restarted or turned off from the page; the `omrg web start` command; `omrg web uninstall` is no longer the only way to stop the app.
- `workspace-presentation`: the power control offers Turn off and Restart in place of "no button that acts on the server".

## Impact

- Code: new `src/omrg/transports/api/routes/power.py`, new `src/omrg/transports/api/power_control.py`, new `src/omrg/transports/cli/web_login_item_start.py`, a read-only counter on the admission object (moved to its own module because `lifespan.py` sits at the 500-line ceiling), `web/src/components/NavFoot.tsx` and a new `PowerMenu` component.
- API: two routes added to `openapi.yaml`.
- Docs: `docs/guides/cli-reference.md`, `docs/guides/web-workspace.md`, ADR-086, ADR-085 addendum.
- No new dependency. macOS only for the working buttons; other platforms see the buttons disabled.
- Security: the new POST route can end the server. It is session-only, needs the `manage` scope, and sits behind the existing Host and Origin checks.
