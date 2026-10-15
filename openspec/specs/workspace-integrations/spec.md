# workspace-integrations Specification

## Purpose
An Integrations page listing the installable integration extras with live availability and copy-ready install commands, so the optional capabilities of the engine are visible and reachable from the workspace.

## Requirements

### Requirement: The Integrations page lists every installable integration

The Integrations view SHALL list one entry for each installable pip extra the project declares (chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web) and for the always-on magika integration. Each entry SHALL show its name, a one-line purpose, its availability status as text with a badge, and its install command.

#### Scenario: Full catalogue

- **WHEN** the user opens Integrations
- **THEN** every declared extra and magika MUST be listed with a name, purpose, status and install command

### Requirement: Availability comes from the running server

The status of each entry SHALL come from `GET /v1/integrations`, resolved through the runtime probes the server already owns (PDF reader and sparse backend resolution, vector-store and community registries, import checks for the optional providers). The page SHALL state that availability reflects the running launch and that installing requires running the command outside the app and restarting the server.

#### Scenario: Installed versus absent

- **WHEN** the pdf-inspector backend is installed and the chroma extra is not
- **THEN** the pdf entries MUST show an available status and the chroma entry MUST show a not-installed status, each stated in text

#### Scenario: Server unreachable

- **WHEN** the integrations request fails
- **THEN** the page MUST show the friendly failure line with a Retry action

### Requirement: Install commands copy from the page

Each entry's install command SHALL be copyable with one action, and the page SHALL NOT install, download or modify packages itself.

#### Scenario: Copy the command

- **WHEN** the user copies the azure entry's install command
- **THEN** the clipboard MUST hold the exact `uv sync --extra azure` command form for that entry
