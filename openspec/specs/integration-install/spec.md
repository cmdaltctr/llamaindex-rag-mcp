# integration-install Specification

## Purpose
Let the web server install an allowed optional extra into its own `uv tool` environment, with a fixed list of extras, one install at a time, redacted output and a restart to use it.

## Requirements

### Requirement: The server installs only into itself and only when it can

The server SHALL report its install type as `uv-tool` when a `uv-receipt.toml` file sits in its own Python environment folder, `checkout` when it runs from a project folder with `pyproject.toml` and `uv.lock`, and `other` in all other cases. The install action SHALL be available only for `uv-tool` and only when the `uv` program is found. The action SHALL install into the server's own Python environment and nowhere else.

#### Scenario: Login item installed with uv tool

- **WHEN** the server runs from a `uv tool` environment that holds `uv-receipt.toml` and `uv` is found
- **THEN** `GET /v1/integrations` MUST report the install type `uv-tool` and `installable: true` for each allowed extra that is not installed

#### Scenario: Development checkout

- **WHEN** the server runs with `uv run omrs web` from a project folder
- **THEN** every entry MUST report `installable: false`, and `POST /v1/integrations/{extra}/install` MUST return 409 and start nothing

#### Scenario: uv not found

- **WHEN** the install type is `uv-tool` and no `uv` program is found
- **THEN** every entry MUST report `installable: false` with the reason `uv-not-found`

### Requirement: Only allowed extras can be installed

The install route SHALL accept only an extra from a fixed list held by the server: the extras declared by the installed OMRS package, without `web` and `torch`. The requirements to install SHALL come from the installed OMRS package metadata for that extra. No text from the request SHALL reach the command, other than the choice of a listed extra.

#### Scenario: Unknown extra refused

- **WHEN** a request asks to install `anthropic; rm -rf ~`
- **THEN** the server MUST return 404 and MUST start no process

#### Scenario: Excluded extra refused

- **WHEN** a request asks to install `torch`
- **THEN** the server MUST return 409 naming the reason `not-installable-here`, and MUST start no process

#### Scenario: Requirements come from package metadata

- **WHEN** the user installs `anthropic`
- **THEN** the command MUST install the requirements the installed package declares for `anthropic` (for example `llama-index-llms-anthropic>=0.11.0`), and MUST NOT reinstall OMRS itself

### Requirement: The install action is guarded

`POST /v1/integrations/{extra}/install` SHALL need the browser session with the `manage` scope. A bearer credential SHALL NOT pass. Only one install SHALL run at a time. The route SHALL return 202 when it starts an install, and 409 when another install runs. The install SHALL stop after 10 minutes and SHALL then report failure.

#### Scenario: Bearer token refused

- **WHEN** an MCP bearer token calls the install route
- **THEN** the server MUST return 403 and MUST start no process

#### Scenario: Second install while one runs

- **WHEN** an install of `azure` runs and the user asks to install `chroma`
- **THEN** the server MUST return 409 and the `azure` install MUST continue

#### Scenario: Install takes too long

- **WHEN** an install runs for more than 10 minutes
- **THEN** the server MUST stop the process and report the state `failed` with the reason `timed-out`

### Requirement: Install progress and result can be read

`GET /v1/integrations/install` SHALL return the state of the running or last install: `idle`, `running`, `succeeded` or `failed`, with the extra name, the start time, and at most the last 40 lines of output. The output SHALL NOT contain an API key or any value from the settings secrets. After `succeeded`, the entry SHALL report `restart-needed` until the server restarts.

#### Scenario: Successful install

- **WHEN** the install of `anthropic` ends with exit code 0
- **THEN** the status MUST be `succeeded`, and the `anthropic` entry MUST report `restart-needed`

#### Scenario: Failed install

- **WHEN** the install ends with a non-zero exit code
- **THEN** the status MUST be `failed` with the last output lines, and the entry MUST still report `not-installed`

#### Scenario: Status after restart

- **WHEN** the server restarts after a successful install
- **THEN** the status MUST be `idle` and the entry MUST report `available`
