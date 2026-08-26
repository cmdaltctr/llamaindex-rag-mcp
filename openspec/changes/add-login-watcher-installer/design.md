## Context

The current `rag-mcp watch` command is already the right long-running process for automatic collection updates: it recursively monitors a directory, filters supported document types, debounces writes, routes ingestion/deletion to a selected collection, and handles graceful shutdown. The missing piece is lifecycle management on macOS. Users want a friendly `rag-mcp install-login-watcher --help` flow that can ask for the folder and collection, optionally catch up existing documents, and install a per-user Login Item so the watcher starts after login.

macOS supports this without a GUI dependency through per-user LaunchAgents in `~/Library/LaunchAgents`. A LaunchAgent plist can run `rag-mcp watch ...` at login with stdout/stderr redirected to log files. The command should be safe for local/offline usage, avoid privileged writes, and not alter the watcher process semantics.

## Goals / Non-Goals

**Goals:**
- Provide an interactive wizard for non-expert users and a non-interactive mode for scripts/automation.
- Generate a deterministic per-user LaunchAgent that starts `rag-mcp watch` for one folder and collection at login.
- Support optional initial catch-up ingestion before installing or starting the watcher.
- Make install/update safe through validation, preview/dry-run, atomic plist writes, and explicit overwrite confirmation.
- Keep the generated watcher observable via a stable label, plist path, and log paths displayed to the user.

**Non-Goals:**
- Replacing `rag-mcp watch` with a background service inside the MCP server.
- Implementing Windows Task Scheduler or Linux systemd support in this change.
- Creating a macOS GUI application, System Settings Login Item entry, or privileged LaunchDaemon.
- Supporting multiple watch folders inside one LaunchAgent. Users can install multiple generated agents by label if needed.

## Decisions

1. **Use a per-user LaunchAgent plist, not a GUI Login Item.**
   - Rationale: LaunchAgents are scriptable, reversible, and do not require packaging an app bundle or requesting administrator privileges.
   - Alternative considered: AppleScript/System Events Login Items. Rejected because modern macOS login item APIs are app-centric, less reliable for raw CLI commands, and harder to test headlessly.

2. **Add a new Typer subcommand: `install-login-watcher`.**
   - Rationale: The command is discoverable through `rag-mcp --help`, can have rich option help, and mirrors the user's desired `rag-mcp install-login-watcher --help` experience.
   - Alternative considered: A separate script. Rejected because package entry-point discovery and testing are simpler when it is part of the existing CLI.
3. **Represent installation logic in a small dedicated module.**
   - Rationale: The CLI command module (a new file under `src/rag_mcp/transports/cli/`, registered on the shared command-group import line) should own prompts/output while a dedicated installer module owns plist rendering, label sanitisation, path calculation, atomic writes, and launchctl command construction.
   - Alternative considered: Inline all code in the command module. Rejected to keep unit tests focused and avoid enlarging CLI modules.

4. **Resolve and persist the absolute installed `rag-mcp` console executable, with an explicit override.**
   - Rationale: LaunchAgents run in a sparse environment, so relying on the user's interactive shell PATH is fragile. The plist should use an absolute executable path and explicit arguments.
   - Preferred approach: resolve the absolute path of the installed `rag-mcp` console executable (the `project.scripts` entry point `rag_mcp.transports.cli:run_cli`) at install time and persist it as `ProgramArguments[0]`. Do not use `sys.executable -m rag_mcp.cli` — `rag_mcp.cli` is a deleted v1 module and that invocation fails on v2+ layouts.
   - Provide `--command-path` as an explicit override for environments where executable resolution is ambiguous (multiple installs, managed Python, packaged distributions).
   - Alternative considered: `ProgramArguments = ["rag-mcp", ...]`. Rejected as default because launchd may not inherit PATH entries such as `~/.local/bin` or Homebrew paths.

5. **Optional catch-up ingest runs before loading the agent, mirroring the ingest CLI.**
   - Rationale: The watcher only sees events after it starts. A guided prompt can run one catch-up ingest to avoid a cold-start gap.
   - The catch-up must follow the current `rag-mcp ingest` flow: resolve the collection's profile once via the composition root's profile resolver, obtain the resulting `EffectiveSettings`, and inject them into `ingest_path_async(path, collection_name=collection, effective_settings=...)`. Do not read global settings repeatedly inside the catch-up loop.
   - Alternative considered: Make the LaunchAgent run `ingest` then `watch` every login. Rejected because repeated full-folder ingestion at each login is slower and makes the long-running command more complex.
6. **Use explicit generated labels and log paths.**
   - Rationale: A deterministic label such as `com.rag-mcp.watch.<slug>` lets users update/remove a watcher safely. Logs in `~/Library/Logs/rag-mcp/` make troubleshooting possible after login.
   - Alternative considered: Random labels. Rejected because they make update/remove workflows harder.

7. **Treat launchctl load/start as best-effort and test via mocked subprocess.**
   - Rationale: CI may not run on macOS or may lack a GUI launchd domain. Plist generation and command construction are the portable contract; actual `launchctl` execution is platform-gated.

## Risks / Trade-offs

- **LaunchAgent environment lacks user shell variables** → Use absolute paths in `ProgramArguments`, avoid shell wrappers by default, and document `OLLAMA_HOST`/environment limitations if needed.
- **Duplicate watchers can contend for the same vector-store collection** → Detect an existing generated plist label and require overwrite/update confirmation unless `--force` is provided. Any contention warning the installer displays SHALL be conditional on the selected vector-store adapter: cross-process write isolation differs between the Chroma and LanceDB adapters, so the installer must not emit an unconditional ChromaDB-specific warning.
- **User chooses a folder that does not exist or is not a directory** → Validate before writing and fail early in non-interactive mode; re-prompt in interactive mode.
- **User changes Python environments after installation** → Show the exact command embedded in the plist and provide an update/overwrite path.
- **Non-macOS usage** → Fail with a clear message unless `--dry-run` is used for preview/testing.
- **Shared CLI registration files** → This change and the migration CLI contemplated by `add-per-collection-persist-dirs` both modify the command-group registration import in `src/rag_mcp/transports/cli/__init__.py`. The two implementations must not modify that file concurrently; land them on sequenced branches.
