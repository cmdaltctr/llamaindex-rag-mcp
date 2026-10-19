## Context

See proposal.md for the reason. Facts from the code:

- `omrg web` (`transports/cli/web.py`, 311 lines) is one Typer command. It binds the port, takes the workspace lock, prints a one-time link, and runs Uvicorn in the foreground with the access log on.
- The sign-in link is a one-time secret held in memory (`AccessPolicy`, `transports/api/security.py`). Browser sessions are also held in memory. A restart ends every session and needs a new link.
- `security.py` has 497 lines and `lifespan.py` has 500. The limit is 500 (`tests/test_file_size_ceiling.py`).
- `omrg install-login-watcher` already builds LaunchAgents. Its primitives live in `transports/cli/_launchagent.py` (350 lines): label and path layout, absolute command resolution, atomic plist write, `launchctl` argument lists.
- The web server holds an exclusive lock on `<workspace>/.lock`. A second `omrg web` on the same workspace stops with a clear message.
- `GET /v1/health` is public and returns the running `version`.
- OMMS keeps its web app as a macOS login item (`io.github.cmdaltctr.omms.web`). That is the model the user wants.

## Goals / Non-Goals

**Goals**

- One command installs a login item that keeps the web app running on the user's Mac.
- The user can sign in at any time without reading a log file.
- The login item survives deleting a feature worktree.
- No change to the HTTP API.

**Non-Goals**

- A Settings toggle for the login item. It is a follow-up, as in OMMS.
- Linux (`systemd --user`) and Windows (Task Scheduler) login items.
- Log rotation.
- Sessions that survive a restart.
- An update check or self-update. `status` shows when the installed copy is newer; the user runs `restart`.

## Decisions

### D1. `web` becomes a command group with a default action

`omrg web` stays the way to run the server in the foreground. In Typer this is a sub-app whose callback has `invoke_without_command=True` and holds today's options; the subcommands `install`, `uninstall`, `status`, `restart` and `open` sit beside it. The root callback in `cli/__init__.py` already skips the runtime set-up for the subcommand name `web`; nested names do not reach it, so that line stays.

*Alternative:* flat commands (`omrg install-web-login-item`, `omrg web-status`). They match `install-login-watcher` but scatter one topic over five top-level names. Task 1.1 first writes a test that proves `omrg web --port 0 ...` still starts the server through the group. If Click cannot keep the old form, the fallback is the flat names, and this decision and the spec command names change together.

### D2. One LaunchAgent label, `com.omrg.web`

There is one web app per user, so there is one fixed label. This differs from the watcher, which has one label per folder. The plist reuses `compute_paths`, `resolve_command_path`, the atomic write and the `launchctl` argument lists from `_launchagent.py`. The watcher's `LaunchAgentPlan` carries watcher fields, so the web plan is a new small dataclass in `cli/_web_login_item.py`. The atomic write moves out of `write_plist` into `write_plist_atomic(path, content, overwrite)`; `write_plist` calls it and the watcher tests stay green. Reuse is the second use of these primitives, which is enough to share them.

Plist content:

| Key | Value | Why |
|---|---|---|
| `ProgramArguments` | `[omrg, "web", "--login-item", ...user options]` | Argument list, no shell. |
| `RunAtLoad` | true | Starts at login and at load. |
| `KeepAlive` | `{SuccessfulExit: false}` | Restarts after a crash or kill. A clean exit stays stopped. |
| `ThrottleInterval` | 60 | A start that fails at once (port in use, workspace locked) retries once a minute, not once a second. |
| `EnvironmentVariables.PATH` | `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin` | launchd gives a sparse `PATH`; the app starts `llama-server` and similar tools. |
| `WorkingDirectory` | `~/.omrg` (absolute; `install` creates it) | Settings read `.env` from the working folder (D7). Without this key launchd uses `/`. |
| `StandardOutPath`, `StandardErrorPath` | `~/Library/Logs/omrg/com.omrg.web.{out,err}.log` | Same layout as the watcher. |

*Alternative:* `KeepAlive: false`, as OMMS does. Rejected: the point of the login item is that the app stays up, and a crash would go unseen.

### D3. The installed executable must be stable

launchd runs whatever path `install` records. A path inside a feature worktree breaks when the worktree is removed. `install` resolves the executable with `resolve_command_path` and then checks whether the path sits in a `.venv` whose parent holds `.git`. If so, the plan shows a warning, an interactive run asks to confirm, and `--yes` accepts it. The recommended install is `uv tool install` from the main checkout with the `web` extra, not in editable mode: an editable install keeps running the checkout's source files, so it has the same risk while the check cannot see it. No `omrg` is on the `PATH` today. The exact command is a package install, so task 5.1 asks for approval and records the command that works.

*Alternative:* copy the application to a private folder. Rejected: it duplicates `uv tool`.

### D4. Sign-in hand-over: a private link file that renews

The foreground flow prints a one-time link to the terminal. A launchd run has no terminal, and a log file is world-readable by default, grows without limit and keeps the link after use. In `--login-item` mode the server instead:

1. Writes the link to `<workspace>/launch-link` (mode 0600, created with that mode, replaced atomically).
2. Replaces the secret with a new one after each sign-in and after the 20-failure lock.
3. Deletes the file on clean shutdown.

`omrg web open` first checks `GET /v1/health` on the port in the file. A crash or `SIGKILL` leaves an old file behind, and opening its link would show a dead page. When the app answers, the command runs the macOS `open` command with the link. It prints the address without the secret; `--print` prints the full link for a browser that `open` does not reach, such as an embedded preview. Agents on this Mac capture terminal output, so the secret is not printed by default.

A new subclass, `RearmingAccessPolicy`, in the new module `transports/api/launch_link.py`, overrides `exchange_bootstrap` and `for_launch`. The base `for_launch` takes no file path, so the subclass's `for_launch` adds a `link_file` keyword and passes the rest to `cls(...)`. The replacement reads and writes the base class's private secret, counters and lock, which ties the subclass to `security.py` internals; its tests (task 2.1) pin that. `security.py` stays unchanged. A secret changes only after the limit of 20 failures is reached, never on each failure.

*Alternatives considered:*

- **Print the link to the log.** Rejected for the reasons above.
- **Short-lived link minted on demand** (`omrg web open` sends a signal; the server writes a link valid for five minutes). It narrows the window in which a leftover file is useful. Deferred: it adds a signal handler and a clock, and the file has the same trust level as `workspace.db`, which any process of the same user can already read.
- **Sessions that survive a restart** (store session digests in the workspace). Rejected for now: it changes the access model and needs its own spec.

### D5. The login-item mode is one flag

`--login-item` is a hidden option on `omrg web`. It does three things: use `RearmingAccessPolicy` and write the file instead of printing the link, set Uvicorn `access_log=False`, and refuse `--port 0` (a login item needs a stable port). The port is not written into the plist unless the user gave `--port`. At each start the server uses the saved port (Settings > MCP) and then 8765, so a port change in Settings takes effect on `omrg web restart`.

### D6. `status` and `open` find the port from the link file

The link file holds the full URL, so it names the host and port the running server uses. `status` reads the port from the file when it exists, and from the saved-port rule otherwise. It calls `GET /v1/health` on that address with a 2 second timeout. It reads the installed version from `omrg --version` of the plist's executable path, run as a child process.

### D7. launchd has a sparse environment, and `.env` lives in `~/.omrg`

`config/__init__.py` reads `.env` from the working folder (`load_dotenv(find_dotenv(usecwd=True))` and `env_file=".env"`). launchd starts an agent in `/` with no shell variables, so every `.env` setting would silently drop: the embedding backend and model, `LOCAL_BACKEND`, `OLLAMA_HOST`. The app would start with code defaults and could fail or embed with the wrong model.

The plist therefore sets `WorkingDirectory` to `~/.omrg`, and the login item reads `~/.omrg/.env`. `install` checks for that file. When it is missing and the folder where the user runs `install` has a `.env`, the plan says: "The login item reads ~/.omrg/.env. Copy your settings there before you start it." The command never copies, moves or reads the content of `.env` (project rule). Shell variables never reach the agent; the CLI reference says to put them in `~/.omrg/.env`.

Keys that the user saved in Settings > Providers live in the keychain. A LaunchAgent runs inside the user's login session, so it can read them; task 5.4 proves this on the Mac.

*Alternative:* `WorkingDirectory` set to the checkout. Rejected: it brings back the checkout dependency that D3 removes.

### D8. Safe defaults for `install`, and a clean restart

`install` warns, and does not stop, when something already listens on the target port or holds the workspace lock, because the user may be running `omrg web` by hand. The message tells them to stop that process first. `uninstall` asks for confirmation; `launchctl bootout` sends `SIGTERM`, so the app shuts down cleanly.

`restart` does not use `kickstart -k`. The man page does not name the signal it sends, and a forced kill skips the lifespan shutdown: open runs are not drained and the link file stays. `restart` sends `launchctl kill SIGTERM`, waits up to 15 seconds for health to stop answering, then runs `launchctl kickstart`. The kickstart is needed because a clean exit does not trigger `KeepAlive` (D2).

`install` and `restart` wait up to 60 seconds for health, because the first start builds the Engine and can load models. On time-out the command exits non-zero, says the app is still not answering, names the error log and `omrg web status`, and leaves the agent installed.

## Risks / Trade-offs

- **Any process of the same user can read the link file and sign in.** This includes AI agents on the machine. → The file is 0600, renews after each use and disappears at shutdown. The same processes can already read `workspace.db`. The short-lived link in D4 is the next step if the user wants a narrower window.
- **A crash loop when the port or the lock is taken.** → `ThrottleInterval` of 60 seconds. `status` and the error log show the cause.
- **The login item runs an installed copy, not the branch the user is working on.** → `status` shows the running and installed versions. Docs say to run `uv tool install --reinstall` and then `omrg web restart`.
- **Restart signs the browser out.** → Sessions are in memory today. `omrg web open` gives a new link in one command.
- **Log files grow.** → The access log is off, so only start-up and error lines are written. No rotation in this change.
- **The keychain read under launchd is unproved.** → Task 5.4 checks it with a real saved key. If it fails, D7 changes to say keys must come from `~/.omrg/.env`.
- **Settings drift between the terminal and the login item.** A hand-run `omrg web` in a checkout reads that checkout's `.env`; the login item reads `~/.omrg/.env`. → `install` names the file it will read, and the guide says which file each mode reads.
- **Group conversion could change how `omrg web` parses options.** → Task 1.1 is a failing test first, and D1 names the fallback.

## Migration Plan

1. Merge. Nothing runs until the user runs `omrg web install`.
2. The user stops any hand-started `omrg web`, installs with `uv tool install`, copies their settings to `~/.omrg/.env`, then runs `omrg web install`.
3. Rollback: `omrg web uninstall` removes the plist. The workspace, the logs and the data stay.

## Open Questions

- Should a later change add the Settings toggle and the OMMS-style "newer version available" check? It needs a new HTTP route for install state, so it is a separate plan.
