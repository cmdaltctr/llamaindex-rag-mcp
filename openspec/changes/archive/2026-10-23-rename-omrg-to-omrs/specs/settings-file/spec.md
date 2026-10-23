## MODIFIED Requirements

### Requirement: The user config folder location

The web server, the CLI and the stdio MCP server SHALL read the user config folder: `$OMRS_CONFIG_DIR` when set, else `$XDG_CONFIG_HOME/omrs` when set, else `~/.config/omrs`. The folder MAY hold `omrs.jsonc` and `secrets/<name>.key`. A missing folder or file SHALL give no values and no warning. The folder `~/.config/omrg` and the variable `OMRG_CONFIG_DIR` SHALL NOT be read.

#### Scenario: Folder from OMRS_CONFIG_DIR

- **WHEN** `OMRS_CONFIG_DIR` names a folder that holds `omrs.jsonc` and `XDG_CONFIG_HOME` is also set
- **THEN** every process MUST read `omrs.jsonc` from the `OMRS_CONFIG_DIR` folder

#### Scenario: Folder from OMRG_CONFIG_DIR

- **WHEN** `OMRG_CONFIG_DIR` names a folder that holds `omrg.jsonc` and `OMRS_CONFIG_DIR` is not set
- **THEN** no process MUST read that folder

#### Scenario: Folder from XDG_CONFIG_HOME

- **WHEN** `OMRS_CONFIG_DIR` is not set and `XDG_CONFIG_HOME` names a folder
- **THEN** every process MUST read the `omrs` subfolder of it

#### Scenario: Default folder

- **WHEN** neither variable is set
- **THEN** every process MUST read `~/.config/omrs`

#### Scenario: Missing folder

- **WHEN** the folder does not exist and `omrs web` starts
- **THEN** the server MUST start with defaults and MUST log no warning

#### Scenario: The old folder is not a fallback

- **GIVEN** `~/.config/omrg/omrg.jsonc` exists and `~/.config/omrs` does not
- **WHEN** a process resolves the config folder
- **THEN** the process MUST NOT read `~/.config/omrg`
