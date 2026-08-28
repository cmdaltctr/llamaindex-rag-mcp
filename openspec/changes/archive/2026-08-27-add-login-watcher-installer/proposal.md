## Why

`rag-mcp watch <path> --collection <name>` already keeps a collection current while a terminal process is running, but users still need to remember to start that watcher after login and to run an initial catch-up ingest. This change adds a guided installer for macOS Login Items / LaunchAgents so a chosen folder can be automatically ingested once and then watched across user logins.

## What Changes

- Add a new `rag-mcp install-login-watcher` CLI command that can run as a guided, step-by-step wizard or in non-interactive/scriptable mode.
- The command collects a watch folder, target collection, debounce interval, optional initial catch-up ingest choice, and LaunchAgent label/location preferences.
- On macOS, it writes a per-user LaunchAgent plist that runs `rag-mcp watch <folder> --collection <collection>` at login and can optionally load/start it immediately.
- Provide safe overwrite/update behaviour for an existing generated watcher, including previewing the planned plist before writing.
- Keep the existing `rag-mcp watch` runtime semantics unchanged; this change installs and manages how the watcher is started.
- No breaking changes.

## Capabilities

### New Capabilities
- `login-watcher-installer`: Guided and scriptable installation of a macOS per-user LaunchAgent that starts a `rag-mcp watch` process for a chosen folder and collection at login.

### Modified Capabilities
- `watch-command`: Clarify that installed login watchers invoke the existing `rag-mcp watch` command and must preserve its collection routing, debounce, deletion, logging, and shutdown semantics.

## Impact

- CLI: new Typer subcommand, help text, prompts, validation, dry-run/yes/options.
- New module: LaunchAgent plist generation, atomic writes, load/unload/start helpers, and path/label sanitisation.
- macOS integration: writes to `~/Library/LaunchAgents/` and uses `launchctl bootstrap/gui/$UID`, `bootout`, and/or `kickstart` where appropriate.
- Ingestion: optional initial catch-up mirrors the `rag-mcp ingest` flow — resolve the collection profile once via the composition root, inject the resulting `EffectiveSettings` into `ingest_path_async(path, collection_name=..., effective_settings=...)` — before watcher installation/start.
- Tests: CLI wizard and non-interactive coverage plus plist generation and macOS command invocation tests with subprocess calls mocked.
- Documentation: usage examples and operational notes for install/update/remove/startup behaviour.
