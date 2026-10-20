# Spec Delta

## MODIFIED Requirements

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

#### Scenario: Restart keeps open tabs signed in

- **WHEN** the app restarts with the same workspace and port
- **THEN** earlier browser sessions MUST stop working
- **AND** an open tab MUST sign in again with the workspace sign-in secret, with no user action
- **AND** `omrg web open` MUST still give a sign-in link

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
- **AND** the open tab MUST sign in again with the workspace sign-in secret once the app answers

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

