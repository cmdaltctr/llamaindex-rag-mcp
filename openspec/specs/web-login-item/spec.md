# web-login-item Specification

## Purpose
Define the `omrg web install`, `uninstall`, `status`, `restart` and `open` commands. Together they keep the OMRG web app running on a Mac from login, without a terminal window, and give the user a way to sign in to it.

## Requirements

### Requirement: Web login item install

On macOS, `omrg web install` SHALL write a per-user LaunchAgent with the label `com.omrg.web` and load it, so the web app starts at every login and now. The agent SHALL run the absolute path of the `omrg` executable with the arguments `web --login-item`, plus `--workspace`, `--port`, `--root` and `--experiment-root` only when the user gave them to `install`. The command SHALL show a plan before it writes and SHALL write the file atomically.

#### Scenario: Install and start

- **WHEN** the user runs `omrg web install --yes` on macOS and no login item exists
- **THEN** the plist MUST exist at `~/Library/LaunchAgents/com.omrg.web.plist`
- **AND** the agent MUST be loaded and the app MUST answer `GET /v1/health` within 60 seconds

#### Scenario: Slow or failed first start

- **WHEN** the app does not answer `GET /v1/health` within 60 seconds of install
- **THEN** the command MUST exit non-zero, MUST name the error log and `omrg web status`, and MUST leave the plist installed

#### Scenario: Another process holds the port

- **WHEN** a server that is not the login item answers `GET /v1/health` on the target port and no link file names that port
- **THEN** the command MUST NOT report that the app is running, MUST exit non-zero, MUST say that another process may hold the port, and MUST leave the plist installed

#### Scenario: Options reach the agent

- **WHEN** the user runs `omrg web install --root ~/papers --port 9000 --yes`
- **THEN** the plist arguments MUST include `--root` with the absolute path and `--port 9000`
- **AND** the plist MUST NOT include `--workspace` when the user did not give it

#### Scenario: Existing login item

- **WHEN** a `com.omrg.web` plist already exists and the user runs `omrg web install` without `--force`
- **THEN** the command MUST leave the file unchanged, MUST say how to replace it, and MUST exit non-zero

#### Scenario: Dry run

- **WHEN** the user runs `omrg web install --dry-run` on any platform
- **THEN** the command MUST print the label, the full argument list, the plist path and the log paths
- **AND** it MUST write no file and MUST NOT call `launchctl`

#### Scenario: Not macOS

- **WHEN** the user runs `omrg web install` without `--dry-run` on a platform other than macOS
- **THEN** the command MUST say that login items are macOS-only and MUST exit non-zero

### Requirement: Stable executable for the login item

The login item SHALL run an `omrg` executable path that the command resolved to an absolute path at install time. When that path is inside a source checkout (a `.venv` folder whose parent holds a `.git` entry), the command SHALL warn that deleting the checkout stops the app, SHALL name `uv tool install` as the alternative, and SHALL continue only after the user confirms or passes `--yes`. A `--command-path` option SHALL set the executable and SHALL be absolute.

#### Scenario: Checkout install is flagged

- **WHEN** the resolved executable is `<checkout>/.venv/bin/omrg` and `<checkout>/.git` exists
- **THEN** the plan MUST show the warning
- **AND** an interactive run MUST ask for confirmation before it writes

#### Scenario: Relative command path

- **WHEN** the user passes `--command-path omrg`
- **THEN** the command MUST refuse and MUST say the path must be absolute

### Requirement: The login item keeps the app running

The agent SHALL start at load, SHALL restart the app after a crash or kill, and SHALL NOT restart it after an exit with status 0. The agent SHALL also start the app again after a stop signal, because the signal ends the process and launchd treats that as a crash. `omrg web uninstall` and the Turn off action (see "Power control from the page") stop the app. Uninstall removes the agent for good. Turn off unloads the agent and keeps the plist, so the app starts again at the next login or when `omrg web start` runs. The agent SHALL wait at least 60 seconds between starts. The agent SHALL write standard output and standard error to `~/Library/Logs/omrg/com.omrg.web.out.log` and `com.omrg.web.err.log`. The agent SHALL give the app a fixed `PATH` that includes `/opt/homebrew/bin`, `/usr/local/bin`, `/usr/bin` and `/bin`.

#### Scenario: Crash restarts

- **WHEN** the app process ends with a non-zero status
- **THEN** launchd MUST start it again after the wait

#### Scenario: A stop signal restarts the app

- **WHEN** the app receives SIGTERM
- **THEN** it MUST shut down in the normal way
- **AND** launchd MUST start it again

#### Scenario: Exit with status 0 stays stopped

- **WHEN** the app exits with status 0
- **THEN** launchd MUST NOT start it again

#### Scenario: Turn off keeps the plist

- **WHEN** the Turn off action has unloaded the agent
- **THEN** launchd MUST NOT start the app again in this login session
- **AND** the plist file MUST still exist, so the agent loads at the next login

### Requirement: The login item reads settings from ~/.omrg/.env

The agent SHALL run with the working folder `~/.omrg`, so the app reads `~/.omrg/.env` and no other `.env`. `install` SHALL create `~/.omrg` when it is missing. When `~/.omrg/.env` does not exist, the plan SHALL say that the login item reads that file. When the folder where `install` runs also has a `.env`, the plan SHALL tell the user to copy their settings to `~/.omrg/.env`. The command SHALL NOT read, copy or move any `.env` file.

#### Scenario: Settings file named in the plan

- **WHEN** the user runs `omrg web install --dry-run` in a checkout that has a `.env` and `~/.omrg/.env` does not exist
- **THEN** the plan MUST name `~/.omrg/.env` as the settings file and MUST tell the user to copy their settings there
- **AND** `~/.omrg/.env` MUST still not exist after the command

#### Scenario: Settings reach the app

- **WHEN** `~/.omrg/.env` sets `EMBED_MODEL` and the login item starts
- **THEN** the running app MUST use that embedding model

### Requirement: Web login item status

`omrg web status` SHALL report whether the plist exists, whether the agent is loaded, whether the app answers `GET /v1/health`, the version the running app reports, the version of the installed `omrg` executable, the workspace folder, the port and the log paths. With `--json` the command SHALL print one JSON object with the same facts. It SHALL exit 0 when the app answers and 1 otherwise. When the two versions differ, the report SHALL say that a restart picks up the installed version.

#### Scenario: Running and current

- **WHEN** the login item is loaded and answers health with the same version as the installed executable
- **THEN** the report MUST show "running" and the command MUST exit 0

#### Scenario: Running an older version

- **WHEN** the running app reports a lower version than the installed executable
- **THEN** the report MUST say that `omrg web restart` starts the installed version

#### Scenario: Not installed

- **WHEN** no plist exists
- **THEN** the report MUST say the login item is not installed and name `omrg web install`, and the command MUST exit 1

### Requirement: Web login item restart

`omrg web restart` SHALL send `SIGTERM` to the app, so it shuts down cleanly. It SHALL wait until the old process has ended, for up to 15 seconds. It SHALL then wait up to 5 seconds for launchd to start a new process. Only if none starts SHALL the command start one with `launchctl kickstart`, and it SHALL NOT use the `-k` option. It SHALL then wait until the app answers `GET /v1/health` or 60 seconds pass, and it SHALL exit 0 only when the app answers. When no login item is installed it SHALL say so and exit non-zero.

#### Scenario: Restart shuts down cleanly

- **WHEN** the user runs `omrg web restart`
- **THEN** the old process MUST end through its normal shutdown, which removes its `launch-link` file
- **AND** a new process MUST start

#### Scenario: launchd restarts the app itself

- **WHEN** launchd starts a new process within 5 seconds after the old one ended
- **THEN** the command MUST NOT run `launchctl kickstart`
- **AND** the command MUST exit 0 once the app answers `GET /v1/health`

#### Scenario: No restart by launchd

- **WHEN** no new process starts within 5 seconds after the old one ended
- **THEN** the command MUST run `launchctl kickstart`

#### Scenario: The old process does not end

- **WHEN** the old process is still there after 15 seconds
- **THEN** the command MUST exit non-zero, MUST NOT run `launchctl kickstart`, and MUST name `omrg web status`

#### Scenario: Restart picks up a new install

- **WHEN** the user installs a newer `omrg` and runs `omrg web restart`
- **THEN** `omrg web status` MUST report the new version as running

#### Scenario: Restart signs the browser out

- **WHEN** the app restarts
- **THEN** earlier browser sessions MUST stop working and `omrg web open` MUST give a new sign-in link

### Requirement: Web login item removal

`omrg web uninstall` SHALL unload the agent and delete its plist. It SHALL keep the workspace folder, the logs and the user's data. It SHALL ask for confirmation unless `--yes` is given, and it SHALL succeed with a message when nothing is installed.

#### Scenario: Remove keeps data

- **WHEN** the user runs `omrg web uninstall --yes`
- **THEN** the plist MUST be gone and the agent MUST be unloaded
- **AND** `~/.omrg/workspace` MUST be unchanged

#### Scenario: Nothing to remove

- **WHEN** no plist exists
- **THEN** the command MUST say nothing is installed and MUST exit 0

### Requirement: Open the app with a fresh sign-in link

`omrg web open` SHALL read the sign-in link that the running login-item server wrote, check that the server answers `GET /v1/health` on that address, and open the link in the default browser. It SHALL print the address without the secret. With `--print` it SHALL print the full link to standard error instead of opening a browser. When the file is missing or the server does not answer, the command SHALL say that the login item is not running, name `omrg web status`, and exit non-zero. It SHALL NOT start a server.

#### Scenario: Open signs in

- **WHEN** the login item runs and the user runs `omrg web open`
- **THEN** the default browser MUST open the app and the page MUST sign in without a prompt
- **AND** the terminal output MUST NOT contain the secret

#### Scenario: Print for another browser

- **WHEN** the user runs `omrg web open --print`
- **THEN** the full one-time link MUST be printed to standard error and no browser MUST open

#### Scenario: Old link file after a crash

- **WHEN** the link file exists but nothing answers on its port
- **THEN** the command MUST say the login item is not running, MUST NOT open a browser, and MUST exit non-zero

#### Scenario: Link used twice

- **WHEN** the user runs `omrg web open` twice
- **THEN** each run MUST sign in, because the server issues a new link after each sign-in

#### Scenario: Server not running

- **WHEN** no launch-link file exists
- **THEN** the command MUST say the login item is not running and MUST exit non-zero

### Requirement: Power control from the page

The app SHALL offer `GET /v1/server/power` and `POST /v1/server/power`. Both routes SHALL need the browser session with the `manage` scope. A bearer credential SHALL receive 403.

`GET /v1/server/power` SHALL answer `{"status": "ok", "managed": true}` when the running app is the login item and `{"status": "ok", "managed": false}` otherwise.

`POST /v1/server/power` SHALL take the body `{"action": "restart"}` or `{"action": "off"}`. A body with any other action SHALL receive 422. A body that is not that shape (a missing or extra field) SHALL receive 400, as every other route does. Neither SHALL signal any process. When the app is not the login item, the route SHALL answer 409 and change nothing. When a run, an ingestion or a map call is in progress, the route SHALL answer 409 and change nothing. In every other case the route SHALL answer 202 and SHALL then act after the response has been sent.

The `restart` action SHALL ask launchd to send `SIGTERM` to the app, so launchd starts it again. The `off` action SHALL ask launchd to unload the agent. After `off` the app SHALL stay stopped until the next login or until `omrg web start` runs. The plist file SHALL stay in place.

#### Scenario: A bearer credential is refused

- **WHEN** a request with a bearer credential posts to `/v1/server/power`
- **THEN** the route MUST answer 403 and MUST NOT stop or restart the app

#### Scenario: A foreground server is not managed

- **WHEN** the app runs in a terminal through `omrg web` and `GET /v1/server/power` is called
- **THEN** the answer MUST be `{"status": "ok", "managed": false}`
- **AND** a `POST` with either action MUST answer 409 and MUST NOT signal any process

#### Scenario: Work in progress blocks the action

- **WHEN** an ingestion is running and the session posts `{"action": "off"}`
- **THEN** the route MUST answer 409 with a one-line reason
- **AND** the app MUST keep running

#### Scenario: Restart

- **WHEN** the login item is idle and the session posts `{"action": "restart"}`
- **THEN** the route MUST answer 202
- **AND** the app MUST shut down in the normal way and launchd MUST start it again
- **AND** the browser session MUST end, because sessions stay in memory

#### Scenario: Turn off

- **WHEN** the login item is idle and the session posts `{"action": "off"}`
- **THEN** the route MUST answer 202
- **AND** the app MUST end and MUST NOT start again until the next login or `omrg web start`
- **AND** the plist file MUST still exist

#### Scenario: Unknown action

- **WHEN** the session posts `{"action": "sleep"}`
- **THEN** the route MUST answer 422 and MUST NOT signal any process

#### Scenario: Malformed body

- **WHEN** the session posts `{"verb": "off"}` or `{"action": "off", "force": true}`
- **THEN** the route MUST answer 400 and MUST NOT signal any process

### Requirement: Start the login item

`omrg web start` SHALL load the installed agent into launchd and SHALL wait up to 60 seconds for the app to answer. It SHALL exit 0 only when the app answers. When the agent is already loaded and the app answers, the command SHALL say so and exit 0. When the login item is not installed, the command SHALL name `omrg web install` and exit 1. On a platform other than macOS the command SHALL print a message and exit 1.

#### Scenario: Start after Turn off

- **WHEN** the agent is installed but unloaded and the user runs `omrg web start`
- **THEN** the command MUST load the agent and MUST exit 0 once the app answers

#### Scenario: Start when already running

- **WHEN** the app answers and the user runs `omrg web start`
- **THEN** the command MUST say that the app is running and MUST exit 0 without a second load

#### Scenario: Start when not installed

- **WHEN** no plist exists and the user runs `omrg web start`
- **THEN** the command MUST tell the user to run `omrg web install` and MUST exit 1
