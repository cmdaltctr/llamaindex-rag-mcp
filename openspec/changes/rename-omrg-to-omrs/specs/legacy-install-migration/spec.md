## ADDED Requirements

### Requirement: An old OMRG install is detected and refused

At startup, every transport (web server, CLI, stdio MCP server, watcher) SHALL check for an old OMRG install. The signs are: an environment variable that starts with `OMRG_`, the folder `~/.omrg`, the folder `~/.config/omrg`, and a launchd plist whose label starts with `com.omrg.` in `~/Library/LaunchAgents`. Every sign is a read-only file or environment check. The check SHALL NOT read the keychain, because a keychain read can show a system prompt on every start and the old entry stays in place after `omrs migrate`. When a sign is present, the transport SHALL stop and name each sign found, its `omrs` replacement and the command `omrs migrate`. The check SHALL read only. It SHALL NOT use the old value as a fallback.

The commands `omrs migrate` and `omrs --help` SHALL run without the check.

#### Scenario: An old variable stops the server

- **GIVEN** `OMRG_CONFIG_DIR` is set in the environment
- **WHEN** a user runs `omrs web start`
- **THEN** the command SHALL exit with a non-zero status
- **AND** the message SHALL name `OMRG_CONFIG_DIR`, its replacement `OMRS_CONFIG_DIR` and the command `omrs migrate`
- **AND** the server SHALL NOT start

#### Scenario: An old data folder stops the stdio MCP server

- **GIVEN** `~/.omrg` exists and `~/.omrs` does not
- **WHEN** an MCP client starts `omrs`
- **THEN** the process SHALL write the message to stderr and exit
- **AND** the process SHALL NOT write to stdout, because stdout is the protocol channel

#### Scenario: An old keychain entry alone does not stop startup

- **GIVEN** a keychain entry under the service `omrg` and no other sign of an old install
- **WHEN** a user runs `omrs web start`
- **THEN** the check SHALL pass
- **AND** the check SHALL NOT call the keychain

#### Scenario: A clean install passes

- **GIVEN** no sign of an old install
- **WHEN** a user runs `omrs web start`
- **THEN** the check SHALL pass without output

#### Scenario: The migrate command is not blocked

- **GIVEN** `~/.omrg` exists
- **WHEN** a user runs `omrs migrate --dry-run`
- **THEN** the command SHALL run and report its plan

### Requirement: The migrate command moves an old install

`omrs migrate` SHALL move an old OMRG install to the `omrs` names. The command SHALL:

1. rename `~/.omrg` to `~/.omrs`;
2. rename `~/.config/omrg` to `~/.config/omrs`, rename `omrg.jsonc` to `omrs.jsonc` and rewrite each `file://~/.config/omrg/secrets/` reference to the new path;
3. copy each keychain entry from the service `omrg` to the service `omrs` for each provider that the old workspace records as saved, leave the old entry in place, and say so in the report;
4. unload each `com.omrg.*` launchd job, remove its plist and install the `com.omrs.*` replacement;
5. print the `OMRG_*` variables that remain set, with the `OMRS_*` names to use, because a process cannot change its parent's environment;
6. leave the LanceDB data unchanged;
7. rewrite each absolute path into the old data folder that `workspace.db` stores in the `runs.inputs_json` column, so saved runs still find their uploads.

The command SHALL accept `--dry-run`, which prints the plan and changes nothing. The command SHALL refuse to overwrite an existing `omrs` target and SHALL name the conflict. The command SHALL print a report of each step and its result. Running it a second time SHALL change nothing and SHALL report that the install is already migrated.

#### Scenario: Dry run changes nothing

- **GIVEN** an old install
- **WHEN** a user runs `omrs migrate --dry-run`
- **THEN** the command SHALL list every step it would take
- **AND** no file, keychain entry or launchd job SHALL change

#### Scenario: A full migration

- **GIVEN** `~/.omrg`, `~/.config/omrg/omrg.jsonc` with a `file://~/.config/omrg/secrets/deepseek.key` reference, a keychain entry under `omrg` and a `com.omrg.web` login item
- **WHEN** a user runs `omrs migrate` and confirms
- **THEN** `~/.omrs`, `~/.config/omrs/omrs.jsonc` and `~/.config/omrs/secrets/deepseek.key` SHALL exist
- **AND** the reference in `omrs.jsonc` SHALL read `file://~/.config/omrs/secrets/deepseek.key`
- **AND** the keychain SHALL hold the entry under `omrs`
- **AND** `com.omrg.web` SHALL be unloaded and `com.omrs.web` SHALL be installed
- **AND** the collections in `~/.omrs/lancedb` SHALL open with unchanged contents

#### Scenario: An existing target blocks the move

- **GIVEN** both `~/.omrg` and `~/.omrs` exist
- **WHEN** a user runs `omrs migrate`
- **THEN** the command SHALL exit with a non-zero status
- **AND** the message SHALL name both folders
- **AND** no step SHALL run

#### Scenario: A second run is a no-op

- **GIVEN** a completed migration
- **WHEN** a user runs `omrs migrate` again
- **THEN** the command SHALL report that nothing is left to migrate
- **AND** no file SHALL change

#### Scenario: Remaining old variables are reported

- **GIVEN** `OMRG_CONFIG_DIR` is set in the shell
- **WHEN** a user runs `omrs migrate`
- **THEN** the report SHALL list `OMRG_CONFIG_DIR` and name `OMRS_CONFIG_DIR`
- **AND** the command SHALL NOT edit shell profiles
