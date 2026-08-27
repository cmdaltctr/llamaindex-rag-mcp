# Specification: login-watcher-installer

## Purpose

Define the `rag-mcp install-login-watcher` CLI command that installs a macOS per-user LaunchAgent which starts `rag-mcp watch` at login, covering guided and scriptable installation, plist generation, overwrite safety, optional catch-up ingest, and launchd loading.

## Requirements

### Requirement: CLI subcommand `rag-mcp install-login-watcher`

The system SHALL provide a `rag-mcp install-login-watcher` CLI subcommand that installs a macOS per-user LaunchAgent for starting `rag-mcp watch` at login. The command SHALL expose help text describing both interactive and non-interactive usage.

#### Scenario: Help describes guided and scriptable usage
- **WHEN** the user runs `rag-mcp install-login-watcher --help`
- **THEN** the CLI SHALL show the purpose of the command
- **THEN** the CLI SHALL list options for watch path, collection, debounce, label, dry-run, force/overwrite, initial ingest, and immediate start/load behaviour

#### Scenario: Non-macOS install is rejected
- **WHEN** the user runs `rag-mcp install-login-watcher` on a non-macOS platform without `--dry-run`
- **THEN** the command SHALL print a clear error that LaunchAgent installation is macOS-only
- **THEN** the command SHALL exit with a non-zero status code

### Requirement: Guided interactive setup

When required options are omitted in an interactive terminal, the installer SHALL guide the user step by step through selecting the watch directory, target collection, debounce interval, initial ingest choice, label, and whether to load/start the agent immediately. The wizard SHALL validate answers before writing any files.

#### Scenario: Wizard collects missing values
- **WHEN** the user runs `rag-mcp install-login-watcher` in an interactive terminal without required options
- **THEN** the CLI SHALL prompt for the folder to watch
- **THEN** the CLI SHALL prompt for the vector-store collection name, defaulting to `documents`
- **THEN** the CLI SHALL prompt for whether to run an initial catch-up ingest
- **THEN** the CLI SHALL display a final summary before installation

#### Scenario: Invalid folder is re-prompted
- **WHEN** the wizard receives a path that does not exist or is not a directory
- **THEN** the CLI SHALL explain the validation failure
- **THEN** the CLI SHALL ask for the folder again rather than writing a plist

### Requirement: Non-interactive installation

The installer SHALL support non-interactive usage when the watch directory and collection are provided as options. In non-interactive mode, missing required values SHALL cause a clear error instead of prompting.

#### Scenario: Scriptable install with explicit options
- **WHEN** the user runs `rag-mcp install-login-watcher --path /docs --collection research --yes`
- **THEN** the command SHALL validate `/docs` as a directory
- **THEN** the command SHALL generate a LaunchAgent configured for collection `research`
- **THEN** the command SHALL not require interactive prompts

#### Scenario: Missing path in non-interactive mode
- **WHEN** standard input is non-interactive and the user omits `--path`
- **THEN** the command SHALL print an error explaining that `--path` is required
- **THEN** the command SHALL exit with a non-zero status code

### Requirement: LaunchAgent plist generation

The installer SHALL generate a valid per-user LaunchAgent plist under `~/Library/LaunchAgents` by default. The plist SHALL use a deterministic label, an absolute path to the resolved `rag-mcp` console executable as `ProgramArguments[0]` (overridable via an explicit command-path option when resolution is ambiguous), the chosen watch path, collection, debounce interval, RunAtLoad behaviour, KeepAlive disabled by default, and log paths under `~/Library/Logs/rag-mcp`.

#### Scenario: Plist contains watcher command
- **WHEN** the installer generates a plist for path `/docs`, collection `research`, and debounce `3`
- **THEN** the plist SHALL contain the resolved absolute executable followed by `watch /docs --collection research --debounce 3`
- **THEN** the plist SHALL not invoke the command through an unescaped shell string

#### Scenario: Command executable is resolved absolutely
- **WHEN** the installer generates a plist without an explicit command-path option
- **THEN** `ProgramArguments[0]` SHALL be the absolute path of the installed `rag-mcp` console executable resolved at install time
- **AND** the resolved path SHALL be persisted in the plist and shown to the user

#### Scenario: Command path override is honoured
- **WHEN** the user provides an explicit command-path option such as `--command-path /opt/homebrew/bin/rag-mcp`
- **THEN** `ProgramArguments[0]` SHALL use that path exactly

#### Scenario: Deterministic label and paths
- **WHEN** the user does not provide a custom label
- **THEN** the installer SHALL derive a stable label using a `com.rag-mcp.watch.` prefix and a safe slug or hash from the watch configuration
- **THEN** the plist path SHALL be shown to the user after generation

#### Scenario: Dry run previews without writing
- **WHEN** the user runs `rag-mcp install-login-watcher --path /docs --collection research --dry-run`
- **THEN** the command SHALL print the planned plist path and plist content or summary
- **THEN** the command SHALL NOT write a plist file
- **THEN** the command SHALL NOT call `launchctl`

### Requirement: Existing watcher safety

If the target generated plist already exists, the installer SHALL protect the existing file from accidental replacement. Overwrite/update SHALL require explicit confirmation in the wizard or an explicit force flag in non-interactive mode.

#### Scenario: Existing plist without force is rejected non-interactively
- **WHEN** a generated plist already exists
- **AND** the user runs the installer non-interactively without `--force`
- **THEN** the command SHALL print an error identifying the existing plist
- **THEN** the command SHALL exit with a non-zero status code without modifying the file

#### Scenario: Existing plist can be updated explicitly
- **WHEN** a generated plist already exists
- **AND** the user confirms overwrite interactively or passes `--force`
- **THEN** the installer SHALL replace the plist atomically
- **THEN** the installer SHALL show the updated label and plist path

### Requirement: Optional initial catch-up ingest

The installer SHALL support running an initial catch-up ingestion of the selected directory into the selected collection before loading or starting the LaunchAgent. This operation SHALL use the existing ingestion pipeline, SHALL route documents to the selected collection, and SHALL mirror the `rag-mcp ingest` flow by resolving the collection's profile once and injecting the resulting effective settings.

#### Scenario: Initial ingest runs before load
- **WHEN** the user enables initial ingest for path `/docs` and collection `research`
- **THEN** the installer SHALL call the existing ingest pipeline for `/docs` with collection `research`
- **AND** the catch-up SHALL resolve the collection's profile once and inject the resulting effective settings into the ingestion call
- **THEN** the installer SHALL complete or report the ingestion result before loading or starting the LaunchAgent

#### Scenario: Initial ingest failure stops installation unless confirmed
- **WHEN** initial ingest returns an error
- **THEN** the installer SHALL display the error
- **THEN** the installer SHALL not load or start the LaunchAgent unless the user explicitly confirms continuing or a documented force/continue option is provided

### Requirement: LaunchAgent loading and immediate start

After writing the plist, the installer SHALL optionally load the LaunchAgent into the current user's GUI launchd domain and optionally start it immediately. The command SHALL display the exact status/result and any log paths needed for troubleshooting.

#### Scenario: Install without immediate start
- **WHEN** the user installs with immediate start disabled
- **THEN** the command SHALL write the plist
- **THEN** the command SHALL explain that the watcher will start on next login or when manually loaded

#### Scenario: Install and start immediately
- **WHEN** the user chooses to load and start the LaunchAgent immediately
- **THEN** the command SHALL invoke the appropriate `launchctl` command for the current user's GUI domain
- **THEN** the command SHALL report success or show the launchctl failure without hiding stderr

#### Scenario: Log paths are reported
- **WHEN** installation completes successfully
- **THEN** the command SHALL print the LaunchAgent label
- **THEN** the command SHALL print stdout and stderr log file paths for the watcher
