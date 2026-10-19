# CLI Reference

The `omrg` command doubles as an MCP server and a CLI tool. With no arguments it starts the MCP stdio server. With subcommands it operates directly from the terminal.

## Subcommands

| Command                         | Description                                                                      |
| ------------------------------- | -------------------------------------------------------------------------------- |
| `omrg`                       | Start the MCP stdio server                                                       |
| `omrg ingest <path>`         | Index a file or directory into the vector store                                  |
| `omrg search <query>`        | Search indexed documents for semantically relevant chunks                        |
| `omrg answer <query>`        | Answer a question from indexed documents with verifiable citations               |
| `omrg list`                  | Show indexed documents with chunk counts                                         |
| `omrg list-collections`      | Show all collections in the selected vector store with document and chunk counts |
| `omrg watch <dir>`           | Watch a directory for new/changed documents and auto-ingest them                 |
| `omrg install-login-watcher` | Install a macOS LaunchAgent that runs the document watcher at login              |
| `omrg delete`                | Delete documents by file path, metadata filter, or drop a collection             |
| `omrg set-profile`           | Bind a built-in profile (`documents` or `codebase`) to a collection              |
| `omrg benchmark`             | Benchmark embedding throughput without vector-store writes                       |
| `omrg config init`           | Write a commented starter `omrg.jsonc` in the user config folder                 |
| `omrg config show`           | Print every setting with its value and source, and the problems in `omrg.jsonc`  |
| `omrg web`                   | Start the local web workspace (needs the `web` extra)                            |
| `omrg web install`           | Keep the web app running as a macOS login item and start it                      |
| `omrg web uninstall`         | Stop the login item and remove its LaunchAgent file                              |
| `omrg web status`            | Show whether the login item is installed, running and answering                  |
| `omrg web restart`           | Restart the login item, for example after you install a newer copy               |
| `omrg web start`             | Load the login item again after Turn off in the power panel                      |
| `omrg web open`              | Open the app in your browser with a fresh sign-in link                           |
| `omrg --version`             | Show version                                                                     |
| `omrg --help`                | Show help                                                                        |
| `omrg --install-completion`  | Install shell tab completion                                                     |

## Common flags

| Flag                 | Applies to                                               | Description                                                          |
| -------------------- | -------------------------------------------------------- | -------------------------------------------------------------------- |
| `--collection`, `-c` | `ingest`, `search`, `list`, `watch`, `delete`, `answer`, `set-profile` | Collection name in the selected vector store (default `"documents"`) |
| `--json`             | `ingest`, `search`, `list`, `list-collections`, `delete`, `answer`, `set-profile` | Output results as JSON (written to stderr like all CLI output; stdout stays the MCP protocol channel) |
| `--chunk-size`       | `ingest`                                                 | Override chunk size (characters)                                     |
| `--chunk-overlap`    | `ingest`                                                 | Override chunk overlap (characters)                                  |
| `--report`, `-r`     | `ingest`                                                 | Write ingestion report to a file                                     |
| `--top-k`, `-k`      | `search`, `answer`                                       | Max results to return; evidence chunks for `answer`                  |
| `--threshold`, `-t`  | `search`                                                 | Minimum similarity score                                             |
| `--rerank`           | `search`, `answer`                                       | Re-score with cross-encoder reranker (`answer` also `--no-rerank`)   |
| `--hybrid`           | `search`, `answer`                                       | Fuse dense vector search with sparse BM25 via RRF (`answer` also `--no-hybrid`) |
| `--expand-window`    | `search`                                                 | Neighbours added per side of each chunk during context assembly      |
| `--diagnostics`      | `search`, `answer`                                       | Include core-produced retrieval diagnostics; `answer` adds generation timings and completion counts. Disabled by default. |
| `--debounce`, `-d`   | `watch`                                                  | Debounce interval in seconds (default: 2)                            |
| `--verbose`, `-v`    | `watch`                                                  | Enable DEBUG-level logging                                           |
| `--dry-run`          | `delete`                                                 | Preview deletion without modifying the selected vector store         |
| `--yes`, `-y`        | `delete`, `set-profile`                                  | Skip the confirmation prompt                                         |
| `--profile`, `-p`    | `set-profile`                                            | Target built-in profile: `documents` or `codebase`                   |

## Examples

### ingest

```bash
# Index a single file
omrg ingest ~/Documents/paper.pdf

# Index a directory
omrg ingest /path/to/docs/

# Index into a named collection
omrg ingest /path/to/papers/ --collection research

# Custom chunking
omrg ingest /path/to/docs/ --chunk-size 1024 --chunk-overlap 128

# JSON output for scripts
omrg ingest /path/to/docs/ --json
```

Collections are created automatically on first ingest — nothing to set up.

File reading is sequential. For ingestion throughput, tune `INGESTION__EMBED_BATCH_SIZE` and `INGESTION__EMBED_CONCURRENCY` in your environment.

A collection can follow a user profile (see [User profiles](configuration.md#user-profiles)).
`omrg ingest` then runs the Ingest pipeline of that profile. The command reads the profile from
the default workspace file, `~/.omrg/workspace/workspace.db`, and opens it read-only. If the file
does not exist, the command exits with code 1 and names the profile and the path. A collection
that follows `documents` or `codebase` ingests as before.

### search

```bash
# Basic semantic search
omrg search "quantum entanglement"

# Search a specific collection
omrg search "transformer architecture" --collection research

# With reranking and threshold
omrg search "machine learning" --rerank --threshold 0.3 --top-k 10

# Hybrid retrieval for rare terms / exact identifiers
omrg search "What fixes MCP-1138?" --hybrid

# JSON output
omrg search "climate change" --json

# JSON output with retrieval diagnostics for debugging
omrg search "climate change" --diagnostics --json
```

The `--diagnostics` flag changes JSON output only. The human-readable table
keeps the existing Score, Source, and Text columns. The Page column appears
only when at least one result row carries a `page_label`; readers without
page boundaries show no column rather than an empty one.

With `--diagnostics --json`, each result row carries a `timings` mapping of
per-stage retrieval wall-clock durations in seconds: `embedding_seconds`,
`dense_seconds`, `sparse_seconds` (hybrid only), `fusion_seconds` (hybrid
only), and `rerank_seconds` (when reranking ran). A stage that did not run is
absent — absence means "did not execute", never "took zero time". No total
duration is emitted. Dense and sparse stages run concurrently in hybrid mode,
so their durations overlap; do not sum them to get wall time.

A collection can follow a user profile. `omrg search` then runs the Search pipeline of that
profile. The command reads the profile from the default workspace file, read-only. Without that
file the command exits with code 1 and names the profile and the path. For such a collection,
`--top-k`, `--threshold`, `--rerank` and `--expand-window` replace the matching step setting of the
pipeline only when you type them. `--hybrid` has no step setting: the wiring of the pipeline
decides whether retrieval is hybrid. A built-in collection uses the defaults of its profile.

> Search-time metadata filtering is available via the `search_documents` MCP tool. The CLI supports metadata filters for deletion via `omrg delete --metadata`.

### answer

```bash
# Answer a question with citations
omrg answer "What thresholds does the reranker use?"

# Scope to a collection and raise the evidence pool
omrg answer "What fixes MCP-1138?" --collection research --top-k 15

# Hybrid retrieval for rare terms and exact identifiers
omrg answer "What fixes MCP-1138?" --hybrid

# Force the reranker off
omrg answer "summarise the norm guard" --no-rerank

# JSON output with retrieval and generation timings
omrg answer "quantum entanglement" --diagnostics --json
```

The command retrieves through the same profile-resolved path as
[`search`](#search), then synthesises one answer from the evidence with one
or more language-model completion calls
([ADR-057](../adr/057-answering-is-additive-and-injected.md)). Human output
prints the answer, then numbered sources:

```
Sources
  1. docs/guides/reranker.md chunk=3f2a91c4 score=0.712
  2. docs/adr/053-embedding-norm-guard.md chunk=9d08e7f1 score=0.655 (+2 merged)
```

A `(+N merged)` note marks a row that merged adjacent chunks; every
constituent `chunk_id` appears in the JSON output.

All output goes to stderr — human and `--json` alike. Stdout stays the
MCP protocol channel. In `--json` mode the result object is the only
output; pipeline chatter is suppressed so the JSON stream stays clean.

The JSON result carries `status`, `query`, `answer`, `citations`, `evidence`,
`failure_stage`, `error`, and `completion_source`. With `--diagnostics`, a
`diagnostics` object adds `retrieval_ms`, `generation_ms`, and
`completion_calls`.

Statuses:

- `ok` — the answer carries at least one verifiable citation.
- `no_evidence` — prints `No supporting evidence was found.` No model call ran.
- `generation_unverified` — prints a warning; the answer carried no
  verifiable citation. Treat it as unverified.
- `unverified_claims` — claim verification was enabled
  (`ANSWER__VERIFY_CLAIMS=true`) and one or more cited claims failed the
  judge. The answer, citations, and evidence are all retained; `--json`
  output lists the failing claims under `unverified_claims`.
- `error` — prints the message and exits 1.

Claim verification is **settings-only**: there is deliberately no
`--verify` flag. Control it with `ANSWER__VERIFY_CLAIMS` (or a profile
bundle's `answer.verify_claims`); when the judge cannot run, `--json`
output carries `verification_skipped` with the reason and the status
stays `ok`. See
[ADR-059](../adr/059-claim-verification-stage.md).

With no answer model configured, a run that finds evidence exits 1 with
an actionable message naming `ANSWER__PROVIDER`. An empty collection
still returns `no_evidence` and exits 0, because no model call was
needed:

```
Error: No answer model is configured for grounded answering. Set ANSWER__PROVIDER (and ANSWER__MODEL) to configure a server-side model, or use an MCP client that supports sampling so the client's model can complete the answer.
```

The server model and the sampling preferences are configured with the
`ANSWER__*` variables. See [Configuration](configuration.md#answering--answer__).

A collection can follow a user profile. `omrg answer` then runs the Answer pipeline of that
profile, with the answer model and the judge that the process builds from `ANSWER__*`. The command
reads the profile from the default workspace file, read-only. Without that file the command exits
with code 1 and names the profile and the path.

### list

```bash
# Human-readable table
omrg list

# Scope to a collection
omrg list --collection research

# JSON output
omrg list --json
```

The human table includes an `Orphaned` column:

- `Yes`: The absolute source path is missing on this machine.
- `No`: The absolute source path exists on this machine.
- `Unknown`: The row has no absolute path that this machine can check.

The JSON output preserves these states as `true`, `false`, and `null`.
This status describes only the current machine. It does not prove that a source
is missing elsewhere. Listing is read-only and never deletes indexed chunks.
Use the [delete command](#delete) with `--dry-run` to preview manual cleanup.

### list-collections

```bash
omrg list-collections
omrg list-collections --json
```

### delete

```bash
# Delete all chunks for a specific file
omrg delete --path /path/to/file.pdf

# Delete chunks matching a metadata filter
omrg delete --metadata '{"category":"uncategorised"}'

# Delete from a specific collection
omrg delete --path /path/to/file.pdf --collection research

# Preview without deleting
omrg delete --path /path/to/file.pdf --dry-run

# Drop an entire collection (prompts for confirmation)
omrg delete --collection research

# Drop without confirmation
omrg delete --collection research --yes
```

The three modes (`--path`, `--metadata`, `--collection`) are mutually exclusive. Only `--collection` alone requires confirmation — it permanently drops the collection.

### watch

```bash
# Watch a directory for new/changed files
omrg watch ~/Zotero/storage/

# Route into a specific collection
omrg watch ~/Zotero/storage/ --collection research

# Custom debounce interval
omrg watch /path/to/docs/ --debounce 5

# Verbose logging
omrg watch /path/to/docs/ --verbose
```

A collection that follows a user profile is ingested through the Ingest pipeline of that profile.
The watcher reads the profile from the default workspace file, read-only. If the file does not
exist, the watcher logs the error that names the profile and the path for each changed file and
keeps running. Create the workspace file with `omrg web`, or change the collection to `documents`
or `codebase`, and the next change of a file is ingested.

> **Cold-start gap:** The watcher only detects changes after it starts. Run `omrg ingest <path>` first to catch up on existing files.

> **Concurrency warning:** Do not run `omrg watch` and `omrg ingest` (or the MCP server) simultaneously against the same collection. Two processes do not share the internal write lock.

### install-login-watcher

```bash
# Guided install in a terminal
omrg install-login-watcher

# Scriptable install
omrg install-login-watcher --path /path/to/docs/ --collection research --yes

# Preview the plan without writing anything
omrg install-login-watcher --path /path/to/docs/ --dry-run

# Catch up existing files, then load and start the watcher now
omrg install-login-watcher --path /path/to/docs/ --initial-ingest --load --start

# Update a watcher you installed earlier
omrg install-login-watcher --path /path/to/docs/ --force
```

On macOS the command writes a per-user LaunchAgent that runs `omrg watch <dir>` at login. In an interactive terminal it prompts for the folder, the collection (default `documents`), and whether to run a catch-up ingest, then shows a summary of the full plan before installing. In scripts pass `--path` and add `--yes` to skip prompts. A second install over the same folder stops until you confirm it or pass `--force`. When the existing watcher uses a different label (for example a different collection), the installer refuses and prints the exact `launchctl bootout` and `rm` commands; confirming the prompt or passing `--force` removes the old watcher first, so exactly one watcher remains.

The label is deterministic: `com.omrg.watch.<slug>-<hash>`, built from the folder name and the collection. Files live at `~/Library/LaunchAgents/<label>.plist`, `~/Library/Logs/omrg/<label>.out.log`, and `~/Library/Logs/omrg/<label>.err.log`. Without `--load` or `--start` the watcher starts at your next login. Use `--command-path` to pin an exact `omrg` executable when you keep several Python environments.

With `--initial-ingest`, the installer indexes the folder before it writes the plist or touches launchctl. It reuses the `omrg ingest` pipeline, so the collection's profile governs chunking and extraction. A broken collection profile aborts the install; `--force` applies only to ordinary ingest errors. For a collection that follows a user profile, the catch-up ingest runs the Ingest pipeline of that profile. If the default workspace file does not exist, the install stops with the error that names the profile and the path.

> **Platform:** Installation is macOS-only. On any other platform the command exits unless you add `--dry-run`. A dry run prints the label, command, plist path, and log paths; it neither writes files nor calls launchctl.

> **Sparse LaunchAgent environment:** launchd gives the watcher no shell environment from your terminal. Export settings such as `OLLAMA_HOST` through `EnvironmentVariables` in the plist, or point `--command-path` at a wrapper script.

Remove a watcher manually:

```bash
launchctl bootout gui/$UID/com.omrg.watch.<slug>-<hash>
rm ~/Library/LaunchAgents/com.omrg.watch.<slug>-<hash>.plist
```

Re-run the command with `--force` to update an existing watcher instead.

### set-profile

```bash
# Preview the change and confirm
omrg set-profile --collection my_code --profile codebase

# Apply without the prompt
omrg set-profile -c my_code -p codebase --yes

# Print the safety contract as JSON (applies only with --yes)
omrg set-profile -c my_code -p codebase --json
```

The command takes `documents` or `codebase`. It prints which settings change and when, then asks
`Continue?` unless you pass `--yes`. The change does not re-chunk or re-embed existing chunks.
Any other name, including the id of a user profile, exits with code 1 and prints:

```text
Bind user profiles in Knowledge Base > Profile, or through the MCP endpoint of `omrg web`.
```

The collection tag stays unchanged. A user profile is bound in the web server only, so a delete and
a bind cannot cross in two processes. See [User profiles](configuration.md#user-profiles).

### config init

```bash
omrg config init            # write the starter file
omrg config init --force    # replace an existing file, keep a dated copy
```

`omrg.jsonc` holds every omrg setting. See [Configuration](configuration.md). `init` writes a starter file with every setting as a commented line. Each line shows the default and the environment name. The file sets nothing until you remove a comment mark.

The command builds the file from the `Settings` model and `config/defaults.yaml`, so a new setting appears in it without an edit. A file key is the environment name in lower case. `__` nests one level: `RETRIEVAL__TOP_K` is `top_k` inside `retrieval`. The settings `web_port`, `web_max_upload_mib` and `mcp_http_enabled` are file-only keys. A key field shows a reference such as `env://OPENROUTER_API_KEY`. Never write an API key in the file.

The folder is `$OMRG_CONFIG_DIR` when set, else `$XDG_CONFIG_HOME/omrg` when set, else `~/.config/omrg`. The command creates the folder with mode 0700 and the file with mode 0600.

| Flag | Default | Description |
| --- | --- | --- |
| `--force` | off | Replace an existing `omrg.jsonc`. The old file stays as `omrg.jsonc.<date>.bak`. When that name exists, the copy gets a number: `omrg.jsonc.<date>.2.bak`. |

| Exit code | When |
| --- | --- |
| 0 | The file was written. |
| 1 | `omrg.jsonc` exists and you did not pass `--force`, or the file could not be written. The message names the file. |

Output goes to stderr, like all CLI output.

### config show

```bash
omrg config show
```

Prints every setting with its value and the source that set it. The command writes nothing and prints to stderr only, so stdout stays free for the MCP channel. It exits 0 even when `omrg.jsonc` has problems.

Each line reads `key = value  (source)`. The source is one of `env` (the process environment), `dotenv` (a `.env` line), `config-file` (`omrg.jsonc`), `key-file` (`secrets/<provider>.key`), `keychain` (a `keychain://` reference that resolved) or `default`. A key field shows `set, ending <last four>` or `not set`, never the key. A key shorter than eight characters shows only `set`.

Below the list, a `Problems in` section names each key in `omrg.jsonc` that was ignored: a file that cannot be read, a value that breaks its rule, an unknown key, or a retired name with its replacement. The section never repeats a value. It also says when a `keychain://` reference found no key.

A `keychain://` reference makes the command read the system keychain. macOS may ask you to allow access. A file with no such reference never opens the keychain.

### web

Start the local browser workspace on a loopback address. It needs the optional `web` extra (`uv sync --extra web` or `pip install "omrg[web]"`).

```bash
# Start on the port in omrg.jsonc, else 8765, with the default workspace
omrg web

# Pick a free port instead
omrg web --port 0

# Approve two directories for file access
omrg web --root ~/papers --root ~/notes

# Use another workspace and a fixed port
omrg web --workspace ~/omrg-demo --port 8765

# Approve a root for experiment workspaces
omrg web --experiment-root ~/omrg-experiments

# Raise the per-file upload limit to 200 MiB for this run
omrg web --max-upload-mib 200

# Allow an embedded preview pane to sign in
omrg web --allow-origin http://name.orca.localhost:57977
```

| Option | Default | Use |
|---|---|---|
| `--workspace PATH` | `~/.omrg/workspace` | Directory for records, run artefacts and uploads. |
| `--port N` | `web_port` in `omrg.jsonc`, else `8765` | TCP port. `0` picks a free port. |
| `--root DIR` | none | Approve a directory for file access. Repeat for more directories. |
| `--host ADDR` | `127.0.0.1` | Loopback address only: `127.0.0.1`, `::1` or `localhost`. |
| `--experiment-root DIR` | none | Approve a directory for experiment workspaces. Repeat for more directories. |
| `--allow-origin ORIGIN` | none | Approve one extra loopback browser origin for this run, for example an embedded preview. Repeat for more origins. See [Web workspace](web-workspace.md). |
| `--max-upload-mib MIB` | `web_max_upload_mib` in `omrg.jsonc`, else `50` | Per-file upload limit in whole MiB, 1 to 2048. Also read from `WEB_MAX_UPLOAD_MIB`. |

The upload limit is the first value in this order: `--max-upload-mib`, then `WEB_MAX_UPLOAD_MIB` (environment or `.env`), then `web_max_upload_mib` in `omrg.jsonc` (Settings > Workspace writes it), then 50 MiB. A launch value locks the limit for that run, and Settings cannot change it. A value that is not a whole number from 1 to 2048 stops the command with exit code 2 before it binds a port. The message names the option, the variable and the range.

The port is `--port` if you give it, else `web_port` in `omrg.jsonc` (Settings > MCP writes it), else 8765. `--port 0` picks a free port. If the port is taken, the command exits with code 1 and prints `Port <n> is in use. Start with --port <n> to choose another port, then save it in Settings > MCP.` The command writes the one-time sign-in link to stderr. It does not run the legacy process-default installer. It refuses a non-loopback `--host`. Every option, sign-in, file grants, jobs and shutdown: [Web workspace](web-workspace.md).

### web install, uninstall, status, restart, start, open

Keep the web app running on a Mac. `omrg web` stops when you close its terminal window. The login item is a per-user LaunchAgent with the label `com.omrg.web`. It starts at every login. It starts again after a crash and after a stop signal. Two actions stop it: `omrg web uninstall` removes the login item for good, and Turn off in the power panel unloads it until the next login or `omrg web start`. The guide [Web workspace](web-workspace.md#keep-the-app-running) explains the sign-in link file.

```bash
# Show the plan and write nothing (works on any platform)
omrg web install --dry-run

# Install, load and start. The command waits up to 60 seconds for the app
omrg web install

# Open the app in your browser, signed in
omrg web open

# Check the state
omrg web status
omrg web status --json

# Start the installed version, for example after you installed a newer copy
omrg web restart

# Load the login item again after Turn off in the power panel
omrg web start

# Stop the app and remove the login item. The workspace and the logs stay
omrg web uninstall
```

Options of `omrg web install`:

| Option | Default | Use |
|---|---|---|
| `--workspace PATH` | `~/.omrg/workspace` | Workspace folder. The login item gets the option only when you give it. |
| `--port N` | `web_port` in `omrg.jsonc`, else `8765` | TCP port, 1 to 65535. A login item needs a stable port, so `0` is not allowed. |
| `--root DIR` | none | Approve a directory for file access. Repeat for more. The path is made absolute. |
| `--experiment-root DIR` | none | Approve a directory for experiment workspaces. Repeat for more. |
| `--command-path PATH` | `omrg` on your `PATH` | Absolute path of the `omrg` executable. |
| `--dry-run` | off | Show the plan. Write no file and do not call `launchctl`. |
| `--force` | off | Replace an existing login item. |
| `--yes`, `-y` | off | Skip the confirmations. |

Other options: `omrg web open --print` prints the full sign-in link to stderr and opens no browser. `omrg web uninstall --yes` skips the confirmation. `omrg web status --json` prints one JSON object.

| Command | Exit code |
|---|---|
| `install` | 0 when the app answers. 1 when the platform is not macOS, a login item exists and `--force` is missing, `launchctl` fails, you refuse a confirmation, or the app does not answer within 60 seconds. The login item stays installed after a time-out. |
| `uninstall` | 0 when it removed the login item, and also when nothing was installed. 1 when you refuse the confirmation or the agent stays loaded. |
| `status` | 0 when the app answers `GET /v1/health`. 1 when it does not answer, or no login item is installed. |
| `restart` | Sends `SIGTERM` and waits up to 15 seconds until the old process has ended. Then it waits up to 5 seconds for launchd to start a new process. It runs `launchctl kickstart` (never `-k`) only if none starts. Then it waits up to 60 seconds for the app to answer. 0 when the new app answers. 1 when no login item is installed, the old process does not end within 15 seconds, or the new app does not answer within 60 seconds. |
| `start` | Loads the agent with `launchctl bootstrap`, unless it is already loaded. Then it waits up to 60 seconds for the app to answer. When the app already answers, it says so and changes nothing. 0 when the app answers. 1 when no login item is installed (the message names `omrg web install`), the platform is not macOS, `launchctl` fails, or the app does not answer within 60 seconds. |
| `open` | 0 when it opened the link or printed it. 1 when the login item is not running. The command never starts a server. |

The login item is a copy of your `omrg` that launchd starts. A stop signal does not stop it, because launchd starts the app again about one second later. `kill` and Activity Monitor do not stop it. Use Turn off in the power panel, or `omrg web uninstall`. Turn off keeps the login item file, so the app starts again at the next login or when you run `omrg web start`. Four rules follow from that:

1. **Install `omrg` outside the checkout.** The login item runs the absolute path of the executable. A path inside a `.venv` of a source checkout stops working when you delete the checkout or its worktree. `install` shows a warning for such a path, and asks you to confirm or to pass `--yes`. Build the web front end first (`cd web && npm run build`), because the wheel ships the built files. Then install a copy from the checkout that holds the version you want. Run this from the checkout folder:

    ```bash
    uv tool install "omrg[web] @ file://$PWD"
    omrg --version
    ```

    Do not use editable mode (`-e`): it keeps running the source files of the checkout. To update the copy later, run the same command with `--reinstall`, then `omrg web restart`.
2. **Settings come from `omrg.jsonc`.** The login item reads `omrg.jsonc` in the user config folder (`~/.config/omrg/omrg.jsonc` by default). It also reads `~/.omrg/.env` when that file exists. That `.env` is optional and overrides the file. launchd starts the login item in `~/.omrg` with no shell variables, so variables you export in your shell do not reach it. `install` shows the path of the settings file. When the folder where you ran it has a `.env` file, `install` tells you that the login item does not read it. Run `omrg config init` to write a starter file, then copy the settings you need into it. The command never reads, copies or moves a `.env` file.
3. **The `PATH` is fixed.** The login item gets `/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin`, so it can start tools such as `llama-server`. A tool in another folder is not found.
4. **A running copy does not change when you install a newer one.** `status` shows the running version and the installed version. Run `omrg web restart` to start the installed version. A restart signs the browser out. Run `omrg web open` to sign in again.

`install` warns, and goes on, when something already listens on the target port. Stop a hand-started `omrg web` first, or the login item cannot bind the port. `install` reports success only when the app answers health and the sign-in link file names the target port, so a hand-started server on that port does not count. `restart` waits until the old process has ended, not only until health stops answering.

Files outside the repository: `~/Library/LaunchAgents/com.omrg.web.plist`, `~/Library/Logs/omrg/com.omrg.web.out.log`, `~/Library/Logs/omrg/com.omrg.web.err.log`, `<workspace>/launch-link` and the folder `~/.omrg`. The log files have no rotation. The access log is off, so they hold only start-up and error lines.

> **Platform:** `install` works on macOS only. On any other platform it exits with code 1 unless you add `--dry-run`.

### Shell tab completion

```bash
# Install once per machine
omrg --install-completion

# Or just view the script without installing
omrg --show-completion
```

After installation, press Tab after `omrg ` to see available subcommands and flags.
