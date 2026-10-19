# Spec Delta

## ADDED Requirements

### Requirement: Power control from the page

The app SHALL offer `GET /v1/server/power` and `POST /v1/server/power`. Both routes SHALL need the browser session with the `manage` scope. A bearer credential SHALL receive 403.

`GET /v1/server/power` SHALL answer `{"managed": true}` when the running app is the login item and `{"managed": false}` otherwise.

`POST /v1/server/power` SHALL take the body `{"action": "restart"}` or `{"action": "off"}`. Any other body SHALL receive 422. When the app is not the login item, the route SHALL answer 409 and change nothing. When a run, an ingestion or a map call is in progress, the route SHALL answer 409 and change nothing. In every other case the route SHALL answer 202 and SHALL then act after the response has been sent.

The `restart` action SHALL ask launchd to send `SIGTERM` to the app, so launchd starts it again. The `off` action SHALL ask launchd to unload the agent. After `off` the app SHALL stay stopped until the next login or until `omrg web start` runs. The plist file SHALL stay in place.

#### Scenario: A bearer credential is refused

- **WHEN** a request with a bearer credential posts to `/v1/server/power`
- **THEN** the route MUST answer 403 and MUST NOT stop or restart the app

#### Scenario: A foreground server is not managed

- **WHEN** the app runs in a terminal through `omrg web` and `GET /v1/server/power` is called
- **THEN** the answer MUST be `{"managed": false}`
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

## MODIFIED Requirements

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
