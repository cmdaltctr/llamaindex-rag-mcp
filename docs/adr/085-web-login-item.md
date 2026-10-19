# ADR-085: Web Login Item

- **Date:** 2026-10-19
- **Status:** Proposed (2026-10-19; the unit tests pass. The checks on the real Mac, tasks 5.1 to 5.6 of the change, are still open.)
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-075](075-omrg-owned-pipeline-runner-local-web-packaging-and-external-tool-plugins.md) (local web runtime), [ADR-079](079-approve-extra-loopback-origins-at-launch.md) (sign-in and origins), [ADR-083](083-llm-provider-settings-in-the-web-workspace.md) (keys in the keychain)
- **Change:** `openspec/changes/add-web-login-item/` (design D1 to D8)

## Context

`omrg web` runs in a terminal window. When the user closes the window, the app
stops. The sign-in link works once, and the server holds the link and the
browser sessions in memory. Each start needs a new link from the terminal.

The user wants the web app to stay running on their Mac and start at login, as
the OMMS web app does. A login item has no terminal. Three facts shape the
design:

- launchd starts an agent in `/` with no shell variables, and the app reads
  `.env` from its working folder.
- launchd runs one fixed executable path. A path in a feature worktree breaks
  when the worktree is removed.
- `security.py` (497 lines) and `lifespan.py` (500 lines) sit at the 500-line
  ceiling.

## Decision

1. **`web` becomes a command group** (D1). `omrg web` with its old options
   still starts the server in the foreground. The subcommands `install`,
   `uninstall`, `status`, `restart` and `open` sit beside it. The test
   `tests/unit/test_web_group.py` pins the old form.
2. **One LaunchAgent, label `com.omrg.web`** (D2). There is one web app per
   user. The plist uses `RunAtLoad`, `KeepAlive` with `SuccessfulExit: false`
   (restart after a crash, stay stopped after a clean exit), a
   `ThrottleInterval` of 60 seconds, a fixed `PATH`, and the working folder
   `~/.omrg`. It reuses the path, command and `launchctl` helpers of
   `install-login-watcher`.
3. **The executable must be stable** (D3). `install` resolves the absolute path
   of `omrg` and warns when it sits in a `.venv` of a source checkout. The
   user confirms or passes `--yes`. The recommended install is `uv tool
   install` from the main checkout with the `web` extra, not in editable mode.
4. **A private link file replaces the printed link** (D4). In login-item mode
   the server writes the sign-in link to `<workspace>/launch-link` (mode 0600,
   atomic replace). It writes a new link after each sign-in and after the
   failed-attempt limit. It removes the file at a clean shutdown. `omrg web
   open` reads the file, checks that the app answers, and opens the link. It
   prints the address without the secret; `--print` prints the full link.
   The new class `RearmingAccessPolicy` lives in `transports/api/launch_link.py`
   and leaves `security.py` unchanged.
5. **One hidden flag selects the mode** (D5). `omrg web --login-item` uses the
   renewing policy, turns the access log off, and refuses `--port 0`.
6. **Settings come from `~/.omrg/.env`** (D7). The login item runs in `~/.omrg`.
   `install` names the file and never reads, copies or moves a `.env` file.
7. **Restart is clean** (D8). `restart` sends `SIGTERM` with `launchctl kill`,
   waits up to 15 seconds for the app to stop, then runs `launchctl kickstart`
   without `-k`. `install` and `restart` wait up to 60 seconds for health.

## Consequences

### Positive

- The web app stays up across terminal windows and starts at login.
- The user signs in with one command. The secret does not reach a log, the
  terminal or the process list.
- No change to the HTTP API or to `security.py`.
- Deleting a feature worktree cannot stop the app once `omrg` is installed
  outside the checkout.

### Negative

- Any process that runs as the same user can read the link file and sign in,
  including AI agents on the machine. The same processes can already read
  `workspace.db`. A link that expires after five minutes is a possible
  follow-up.
- `RearmingAccessPolicy` reads and writes private fields of `AccessPolicy`.
  Its tests pin that tie.
- A restart signs the browser out, because sessions stay in memory.
- The login item runs an installed copy, not the branch under work. The user
  runs `omrg web restart` after each reinstall.
- The log files have no rotation.

### Neutral

- macOS only. `install --dry-run` runs on any platform.
- `install` warns about a busy port but does not probe the workspace lock.
- Rollback is `omrg web uninstall`. The workspace, logs and data stay.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Flat commands such as `omrg install-web-login-item`** | They scatter one topic over five top-level names. They stay the fallback if Click cannot keep the old `omrg web` form. |
| **`KeepAlive: false`, as OMMS does** | The point of the login item is that the app stays up, and a crash would go unseen. |
| **Copy the application to a private folder** | It duplicates what `uv tool install` does. |
| **Print the link to the log file** | A log file grows without limit and keeps the link after use. |
| **Short-lived link minted on demand** | It needs a signal handler and a clock. The file has the same trust level as `workspace.db`. Deferred. |
| **Sessions that survive a restart** | It changes the access model and needs its own spec. |
| **`kickstart -k` for restart** | The man page does not name the signal. A forced kill skips the lifespan shutdown and leaves the link file. |
| **Working folder set to the checkout** | It brings back the checkout dependency that decision 3 removes. |

## References

- `src/omrg/transports/cli/web.py`, `src/omrg/transports/cli/web_login_item.py`, `src/omrg/transports/cli/_web_login_item.py`, `src/omrg/transports/cli/_launchagent.py`
- `src/omrg/transports/api/launch_link.py`
- `docs/guides/cli-reference.md`, `docs/guides/web-workspace.md`
