## MODIFIED Requirements

### Requirement: Install progress and result can be read

`GET /v1/integrations/install` SHALL return the state of the running or last install: `idle`, `running`, `succeeded` or `failed`, with the extra name, the start time, and at most the last 40 lines of output. The output SHALL NOT contain an API key or any value from the settings secrets. An install SHALL be `succeeded` only when `uv pip install` and the check after it both end with exit code 0. After `succeeded`, the entry SHALL report `restart-needed` until the server restarts.

#### Scenario: Successful install

- **WHEN** the install of `anthropic` ends with exit code 0 and the check after it ends with exit code 0
- **THEN** the status MUST be `succeeded`, and the `anthropic` entry MUST report `restart-needed`

#### Scenario: Failed install

- **WHEN** the install ends with a non-zero exit code
- **THEN** the status MUST be `failed` with the last output lines, and the entry MUST still report `not-installed`

#### Scenario: Status after restart

- **WHEN** the server restarts after a successful install
- **THEN** the status MUST be `idle` and the entry MUST report `available`

## ADDED Requirements

### Requirement: The server checks its packages after an install

After `uv pip install` ends with exit code 0, the server SHALL run `uv pip check --python <its own Python>` as an argument list with no shell, the same environment and the same time limit. When the check ends with a non-zero exit code, the install SHALL be `failed` with the reason `check-failed` and the check's exit code, its output SHALL be kept with the install output, and the entry SHALL NOT report `restart-needed`.

#### Scenario: Packages conflict after the install

- **WHEN** the install ends with exit code 0 and `uv pip check` reports a conflict with exit code 1
- **THEN** the status MUST be `failed` with the reason `check-failed`, the output MUST hold the check lines, and the entry MUST NOT report `restart-needed`

#### Scenario: The check is skipped after a failed install

- **WHEN** the install ends with a non-zero exit code
- **THEN** the server MUST NOT run `uv pip check`

### Requirement: An entry with unknown status cannot be installed

When an entry's probe fails and its availability is `unknown`, the entry SHALL report `installable: false` with the reason `status-unknown`. The install route SHALL return 409 with that reason and start no process.

#### Scenario: Probe failed

- **WHEN** the probe of the `azure` entry raises an error
- **THEN** the entry MUST report `installable: false` with the reason `status-unknown`, and `POST /v1/integrations/azure/install` MUST return 409 and start no process

### Requirement: Extra requirements stay readable

Each requirement line that the installed OMRS package declares for an allowed extra SHALL name that extra with a plain `extra == "<name>"` clause, joined to any other marker part with `and` only. No such line SHALL name the `omrs` distribution. A test SHALL read the installed metadata and fail when a line breaks this rule.

#### Scenario: A line uses or

- **WHEN** a requirement line for `anthropic` has the marker `extra == "anthropic" or extra == "all"`
- **THEN** the metadata guard test MUST fail

#### Scenario: A line names omrs

- **WHEN** a requirement line for `anthropic` is `omrs[hybrid]; extra == "anthropic"`
- **THEN** the metadata guard test MUST fail
