## MODIFIED Requirements

### Requirement: Availability comes from the running server

The status of each entry SHALL come from `GET /v1/integrations`, resolved through the runtime probes the server already owns (PDF reader and sparse backend resolution, vector-store and community registries, import checks for the optional providers). The page SHALL state that availability reflects the running launch. When the server can install, the page SHALL say that Install adds the packages and that a restart makes them available. When it cannot, the page SHALL say that installing requires running the command outside the app and restarting the server.

#### Scenario: Installed versus absent

- **WHEN** the pdf-inspector backend is installed and the chroma extra is not
- **THEN** the pdf entries MUST show an available status and the chroma entry MUST show a not-installed status, each stated in text

#### Scenario: Server unreachable

- **WHEN** the integrations request fails
- **THEN** the page MUST show the friendly failure line with a Retry action

#### Scenario: Installed, restart needed

- **WHEN** an install of `anthropic` succeeded in this launch
- **THEN** the `anthropic` entry MUST show the status "Installed, restart to use" and a Restart action

### Requirement: Install commands copy from the page

Each entry's install command SHALL be copyable with one action. The command SHALL match how the server is installed: `uv tool install --reinstall "omrs[<extras>] @ <source>"` for a `uv tool` install, with the current extras plus the entry's extra and the source from the install receipt; `uv sync --extra <extra>` for a development checkout; and `pip install "omrs[<extra>]"` otherwise. For a `uv tool` install, the page SHALL say that this command keeps the extra after a later reinstall.

#### Scenario: Copy the command

- **WHEN** the server runs from a checkout and the user copies the azure entry's install command
- **THEN** the clipboard MUST hold `uv sync --extra azure`

#### Scenario: Copy the command for a uv tool install

- **WHEN** the receipt lists the extras `web` and `hybrid` and the source folder `~/src/omrs`, and the user copies the anthropic entry's command
- **THEN** the clipboard MUST hold `uv tool install --reinstall "omrs[web,hybrid,anthropic] @ ~/src/omrs"`

## ADDED Requirements

### Requirement: An entry can be installed from the page

When an entry reports `installable: true`, the entry SHALL show an Install button. Pressing it SHALL open a confirm dialog that names the extra and the packages it adds, and says that the server needs a restart afterwards. Confirming SHALL call the install route. While the install runs, the entry SHALL show a progress line, and the other Install buttons SHALL be disabled. A failure SHALL show the last output lines and a Retry action. When `installable` is false, the entry SHALL show the copy command only.

#### Scenario: Install the Anthropic extra

- **WHEN** the user presses Install on the Anthropic entry and confirms
- **THEN** the page MUST call `POST /v1/integrations/anthropic/install`, show the progress line, and on success show "Installed, restart to use" with a Restart action

#### Scenario: Cancel the dialog

- **WHEN** the user presses Install and then Cancel
- **THEN** the page MUST NOT call the install route

#### Scenario: Not installable here

- **WHEN** the server runs from a development checkout
- **THEN** no entry MUST show an Install button, and each MUST show its copy command

#### Scenario: Phone width

- **WHEN** the page is 390 px wide
- **THEN** the Install button, the progress line and the output lines MUST fit without sideways page scroll
