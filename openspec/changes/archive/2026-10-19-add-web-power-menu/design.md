# Design

## Context

- The login item (ADR-085, change `add-web-login-item`) is one LaunchAgent, label `com.omrg.web`. Its plist uses `KeepAlive` with `SuccessfulExit: false` and a 60-second `ThrottleInterval`.
- Uvicorn re-raises the stop signal after a clean shutdown, so the process ends by signal and launchd starts it again. A stop signal therefore restarts the app. `omrg web restart` uses this: it sends `SIGTERM` with `launchctl kill`.
- Today only `omrg web uninstall` stops the app, and it removes the plist.
- The power panel (`web/src/components/NavFoot.tsx`) shows a light and two commands. The spec for it says the panel has no Restart button and no Stop button.
- Destructive routes already follow one pattern: browser session, `manage` scope, bearer refused (`routes/admin.py`).
- Three files sit at the 500-line ceiling: `lifespan.py` (500), `security.py` (497), `cli/web_login_item.py` (497). New behaviour goes into new files.
- Sessions live in memory. Any restart ends the browser session.

## Goals / Non-Goals

**Goals:**

- Turn off and Restart from the power panel, each behind a confirmation.
- Turn off keeps the app off until the next login or `omrg web start`.
- A way back on from a terminal: `omrg web start`.
- No action while work is running.

**Non-Goals:**

- Sessions that survive a restart. ADR-085 defers this.
- Starting the app from the page after Turn off. The page is gone when the app is off.
- Controlling a foreground `omrg web` server. The buttons stay disabled for it.
- Linux or Windows service managers.
- A scheduled or timed Turn off.

## Decisions

### D1. Two actions, mapped to two launchd steps

`restart` sends `SIGTERM` with `launchctl kill SIGTERM gui/<uid>/com.omrg.web`. This is the step `omrg web restart` already uses and tests. launchd starts the app again by itself.

`off` runs `launchctl bootout gui/<uid>/com.omrg.web`. launchd sends `SIGTERM`, then unloads the agent, so `KeepAlive` has nothing to restart. The plist stays on disk and `RunAtLoad` loads it at the next login.

Alternatives:

| Option | Rejected because |
|--------|------------------|
| Exit with status 0 for Turn off | Uvicorn re-raises the signal, so the exit status is not under our control (ADR-085 addendum). |
| Run `omrg web uninstall` for Turn off | It removes the plist, so the app would not return at the next login. |
| `kickstart -k` for Restart | Rejected in ADR-085: it can skip the clean shutdown and leave the link file. |

### D2. The server acts after it answers

The route answers 202 and then runs the launchctl argv in a background task after a short delay (0.5 seconds), so the response and the browser's next poll leave before the process ends. The route runs the argv with no shell, a fixed argument list and a timeout. A launchctl failure is logged and nothing else happens, because the caller has gone.

### D3. A route can only act when the app is the login item

`web.py` sets `application.state.power_control` only when `--login-item` is given. The object holds the label and the user id. `GET /v1/server/power` answers `managed` from its presence. Without it, `POST` answers 409. This keeps `lifespan.py` and `WebConfig` unchanged, and it stops a foreground server from signalling an unrelated launchd job.

### D4. No action while work runs

`POST` answers 409 when the admission object counts active work. `Admission` lives in `lifespan.py`, which is at the ceiling, so the first task moves `Admission` and `AdmissionClosed` to `admission.py` and re-exports both names from `lifespan.py`, which keeps every existing import and patch target. It adds a read-only `active` property. The launchd exit timeout is 20 seconds by default. A long ingestion would be killed at that point, so the guard is needed, not a courtesy.

A race remains: work can start between the check and the signal. The window is the 0.5-second delay. The shutdown path already waits for admitted work, so the risk is the exit timeout only. It is accepted and listed under Risks.

### D5. `omrg web start`

A new command in `cli/web_login_item_start.py`, registered on the `web` group. It checks that the plist exists, runs `launchctl bootstrap` when the agent is not loaded, and waits for health with the helpers that `install` uses. It prints the same "run `omrg web open`" line as `restart`. A new file is needed because `web_login_item.py` is at the ceiling.

### D6. Shared launchctl argv, no cross-transport import

The API must not import from `transports/cli`. `power_control.py` builds its two argv lists itself. A test compares them with the output of `_launchagent.kill_command` and `_launchagent.bootout_command`, so the two copies cannot drift apart.

### D7. The page

A new `PowerMenu` component replaces the body of `PowerControl` in `NavFoot.tsx`:

- It reads `GET /v1/server/power` with the health poll.
- Turn off and Restart are `Button` primitives. Each opens the existing `Dialog` primitive with the text from the spec. Use the `omrg-design` skill before any UI work.
- After 202 the page stops polling health for 5 seconds, then shows a plain state: "Restarting. Run `omrg web open` to sign in." or "Turned off. Run `omrg web start` to turn it on." The page cannot sign itself in again, because the sign-in link is private to the Mac.
- A 409 shows the reason in one line through `describeError`.
- Disabled buttons carry the reason as text, not as a tooltip alone.

### D8. Security

- The route needs the `manage` scope and a session. A bearer credential receives 403.
- The Host and Origin checks already cover the route. A cross-site page cannot post to it.
- The body is a closed enum. There is no free text in any argv.
- The route needs no confirmation token. The action loses no data, and the dialog is the confirmation.

## Risks / Trade-offs

- **Restart delay.** `ThrottleInterval` is 60 seconds. If launchd applies it after a signal exit, Restart can take up to a minute. Task 5.2 measures it on the real Mac. If it is long, the dialog says so.
- **Sign-out.** Every action ends the browser session. The dialog says so first.
- **Off cannot be undone from the page.** The user needs a terminal. The dialog names the command.
- **Race with new work.** See D4. Accepted.
- **Duplicate argv code.** See D6. The test guards it.
- **macOS only.** Elsewhere `managed` is false and the buttons stay disabled.
- **Another process can post to the route** if it holds a browser session. That is the same trust level as every other `manage` route.
