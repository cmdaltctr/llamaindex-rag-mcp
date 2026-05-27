## 1. LaunchAgent Planning and Core Utilities

- [ ] 1.1 Add a dedicated login watcher module for installer data structures, label generation, path resolution, plist rendering, and validation.
- [ ] 1.2 Implement watch directory validation with `~` expansion, absolute resolution, directory checks, and clear error messages.
- [ ] 1.3 Implement deterministic LaunchAgent label generation with a `com.rag-mcp.watch.` prefix and safe slug/hash handling.
- [ ] 1.4 Implement log path calculation under `~/Library/Logs/rag-mcp/` and plist path calculation under `~/Library/LaunchAgents/`.
- [ ] 1.5 Implement absolute command resolution for generated `ProgramArguments`, including a safe default and an explicit override option.

## 2. Plist Write and launchctl Operations

- [ ] 2.1 Render a valid LaunchAgent plist with label, absolute `ProgramArguments`, `RunAtLoad`, log paths, and KeepAlive disabled by default.
- [ ] 2.2 Write plist files atomically, creating parent directories as needed and preserving existing files unless overwrite is explicitly allowed.
- [ ] 2.3 Add dry-run support that returns or prints the planned plist path/content without writing files or calling `launchctl`.
- [ ] 2.4 Implement platform-gated launchctl helpers for bootstrap/load, bootout/update, and optional kickstart/start in the current user's GUI domain.
- [ ] 2.5 Surface launchctl stdout/stderr and failures without swallowing diagnostic output.

## 3. CLI and Interactive Wizard

- [ ] 3.1 Add the `rag-mcp install-login-watcher` Typer command with help text and options for path, collection, debounce, label, dry-run, force, initial ingest, load, start, and command path.
- [ ] 3.2 Implement interactive prompts for omitted values when running in an interactive terminal.
- [ ] 3.3 Implement non-interactive validation so missing required values fail clearly instead of blocking on prompts.
- [ ] 3.4 Implement final summary/confirmation before writing in the wizard flow.
- [ ] 3.5 Implement existing plist detection with interactive overwrite confirmation and non-interactive `--force` behaviour.

## 4. Initial Catch-up Ingestion

- [ ] 4.1 Wire optional initial catch-up ingestion to existing `ingest_path_async(path, collection_name=collection)`.
- [ ] 4.2 Ensure initial ingest runs before LaunchAgent load/start and reports success/error counts to the user.
- [ ] 4.3 Prevent load/start after initial ingest failure unless the user explicitly confirms continuing or the documented continue/force option is provided.

## 5. Tests and Documentation

- [ ] 5.1 Add unit tests for label generation, path validation, plist rendering, dry-run behaviour, and overwrite protection.
- [ ] 5.2 Add CLI tests for `--help`, non-interactive success, non-interactive missing path failure, wizard prompts, invalid folder re-prompt, and force overwrite.
- [ ] 5.3 Add mocked subprocess tests for launchctl command construction, success reporting, and failure reporting.
- [ ] 5.4 Add tests proving initial ingest receives the selected collection and runs before load/start.
- [ ] 5.5 Add documentation or README usage examples for guided install, scriptable install, dry-run preview, updating an existing watcher, log locations, and macOS-only limitations.
- [ ] 5.6 Run targeted tests for the new module and CLI, then run the relevant existing watcher/CLI test suite.
