## Why

`omrg web` runs in a terminal window. When the user closes the window, the app stops. The sign-in link works once, so each start needs a new link from the terminal. The user wants the web app to stay running on their Mac and start at login, as the OMMS web app does.

## What Changes

- No breaking change. `omrg web` becomes a command group. `omrg web` with its current options still starts the server in the foreground. Five new subcommands manage a macOS login item:
  - `omrg web install` writes a LaunchAgent (`com.omrg.web`) and starts it.
  - `omrg web uninstall` stops it and removes the file.
  - `omrg web status` shows whether it is installed, running and answering, and which version runs.
  - `omrg web restart` restarts it, for example after the user installs a newer copy.
  - `omrg web open` opens the app in the browser with a fresh sign-in link.
- A new hidden option, `omrg web --login-item`, is what the LaunchAgent runs. It writes the sign-in link to a private file instead of the terminal, issues a new link after each sign-in, and turns off the access log.
- The login item runs a fixed, installed `omrg` executable. The installer warns when that path sits inside a source checkout, because a deleted checkout would stop the app.
- The login item runs in `~/.omrg` and reads its settings from `~/.omrg/.env`. Settings come from the `.env` in the working folder, and launchd would otherwise start the app in `/` with none of the user's settings. The installer tells the user to copy their settings there and never copies `.env` itself.
- New guide section, new ADR-085 and updated CLI reference.

## Capabilities

### New Capabilities

- `web-login-item`: install, remove, inspect, restart and open the web app as a macOS login item.

### Modified Capabilities

- `local-web-workspace`: adds one requirement. A login-item server hands over a private, renewed sign-in link and keeps no terminal output or access log.

## Impact

- **Code:** `src/omrg/transports/cli/web.py` (group and `--login-item`), new `cli/_web_login_item.py` and `cli/web_login_item.py`, new `transports/api/launch_link.py`, small change in `cli/_launchagent.py` (shared atomic write), one line in `cli/__init__.py` (module list).
- **Not touched:** `transports/api/security.py` (497 lines) and `lifespan.py` (500 lines) stay as they are, because both sit at the 500-line ceiling.
- **API:** no route or OpenAPI change.
- **Dependencies:** none.
- **Files outside the repo:** `~/Library/LaunchAgents/com.omrg.web.plist`, `~/Library/Logs/omrg/com.omrg.web.{out,err}.log`, `<workspace>/launch-link`, and the folder `~/.omrg` (the user's own `~/.omrg/.env` is read, never written).
- **Platforms:** macOS only, like `install-login-watcher`. `omrg web install --dry-run` runs on any platform.
- **Tests:** new unit tests with a fake `launchctl` runner and a temporary home folder. No test touches the real `~/Library`.
- **Docs:** `docs/guides/cli-reference.md`, `docs/guides/web-workspace.md`, `docs/adr/085-web-login-item.md`.
- **Out of scope:** a Settings toggle for the login item, Linux and Windows login items, log rotation, and sessions that survive a restart. Design.md lists each.
