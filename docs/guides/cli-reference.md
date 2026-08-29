# CLI Reference

The `rag-mcp` command doubles as an MCP server and a CLI tool. With no arguments it starts the MCP stdio server. With subcommands it operates directly from the terminal.

## Subcommands

| Command | Description |
|---------|-------------|
| `rag-mcp` | Start the MCP stdio server |
| `rag-mcp ingest <path>` | Index a file or directory into the vector store |
| `rag-mcp search <query>` | Search indexed documents for semantically relevant chunks |
| `rag-mcp list` | Show indexed documents with chunk counts |
| `rag-mcp list-collections` | Show all collections in the selected vector store with document and chunk counts |
| `rag-mcp watch <dir>` | Watch a directory for new/changed documents and auto-ingest them |
| `rag-mcp install-login-watcher` | Install a macOS LaunchAgent that runs the document watcher at login |
| `rag-mcp delete` | Delete documents by file path, metadata filter, or drop a collection |
| `rag-mcp benchmark` | Benchmark embedding throughput without vector-store writes |
| `rag-mcp --version` | Show version |
| `rag-mcp --help` | Show help |
| `rag-mcp --install-completion` | Install shell tab completion |

## Common flags

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--collection`, `-c` | `ingest`, `search`, `list`, `watch`, `delete` | Collection name in the selected vector store (default `"documents"`) |
| `--json` | `ingest`, `search`, `list`, `list-collections`, `delete` | Output results as JSON |
| `--chunk-size` | `ingest` | Override chunk size (characters) |
| `--chunk-overlap` | `ingest` | Override chunk overlap (characters) |
| `--report`, `-r` | `ingest` | Write ingestion report to a file |
| `--top-k`, `-k` | `search` | Max results to return |
| `--threshold`, `-t` | `search` | Minimum similarity score |
| `--rerank` | `search` | Re-score with cross-encoder reranker |
| `--hybrid` | `search` | Fuse dense vector search with sparse BM25 via RRF |
| `--diagnostics` | `search` | Include core-produced retrieval diagnostics. Disabled by default. |
| `--debounce`, `-d` | `watch` | Debounce interval in seconds (default: 2) |
| `--verbose`, `-v` | `watch` | Enable DEBUG-level logging |
| `--dry-run` | `delete` | Preview deletion without modifying the selected vector store |
| `--yes`, `-y` | `delete` | Skip confirmation prompt for collection deletion |

## Examples

### ingest

```bash
# Index a single file
rag-mcp ingest ~/Documents/paper.pdf

# Index a directory
rag-mcp ingest /path/to/docs/

# Index into a named collection
rag-mcp ingest /path/to/papers/ --collection research

# Custom chunking
rag-mcp ingest /path/to/docs/ --chunk-size 1024 --chunk-overlap 128

# JSON output for scripts
rag-mcp ingest /path/to/docs/ --json
```

Collections are created automatically on first ingest — nothing to set up.

File reading is sequential. For ingestion throughput, tune `INGESTION__EMBED_BATCH_SIZE` and `INGESTION__EMBED_CONCURRENCY` in your environment.

### search

```bash
# Basic semantic search
rag-mcp search "quantum entanglement"

# Search a specific collection
rag-mcp search "transformer architecture" --collection research

# With reranking and threshold
rag-mcp search "machine learning" --rerank --threshold 0.3 --top-k 10

# Hybrid retrieval for rare terms / exact identifiers
rag-mcp search "What fixes MCP-1138?" --hybrid

# JSON output
rag-mcp search "climate change" --json

# JSON output with retrieval diagnostics for debugging
rag-mcp search "climate change" --diagnostics --json
```

The `--diagnostics` flag changes JSON output only. The human-readable table
keeps the existing Score, Source, Page, and Text columns.

> Search-time metadata filtering is available via the `search_documents` MCP tool. The CLI supports metadata filters for deletion via `rag-mcp delete --metadata`.

### list

```bash
# Human-readable table
rag-mcp list

# Scope to a collection
rag-mcp list --collection research

# JSON output
rag-mcp list --json
```

### list-collections

```bash
rag-mcp list-collections
rag-mcp list-collections --json
```

### delete

```bash
# Delete all chunks for a specific file
rag-mcp delete --path /path/to/file.pdf

# Delete chunks matching a metadata filter
rag-mcp delete --metadata '{"category":"uncategorised"}'

# Delete from a specific collection
rag-mcp delete --path /path/to/file.pdf --collection research

# Preview without deleting
rag-mcp delete --path /path/to/file.pdf --dry-run

# Drop an entire collection (prompts for confirmation)
rag-mcp delete --collection research

# Drop without confirmation
rag-mcp delete --collection research --yes
```

The three modes (`--path`, `--metadata`, `--collection`) are mutually exclusive. Only `--collection` alone requires confirmation — it permanently drops the collection.

### watch

```bash
# Watch a directory for new/changed files
rag-mcp watch ~/Zotero/storage/

# Route into a specific collection
rag-mcp watch ~/Zotero/storage/ --collection research

# Custom debounce interval
rag-mcp watch /path/to/docs/ --debounce 5

# Verbose logging
rag-mcp watch /path/to/docs/ --verbose
```

> **Cold-start gap:** The watcher only detects changes after it starts. Run `rag-mcp ingest <path>` first to catch up on existing files.

> **Concurrency warning:** Do not run `rag-mcp watch` and `rag-mcp ingest` (or the MCP server) simultaneously against the same collection. Two processes do not share the internal write lock.

### install-login-watcher

```bash
# Guided install in a terminal
rag-mcp install-login-watcher

# Scriptable install
rag-mcp install-login-watcher --path /path/to/docs/ --collection research --yes

# Preview the plan without writing anything
rag-mcp install-login-watcher --path /path/to/docs/ --dry-run

# Catch up existing files, then load and start the watcher now
rag-mcp install-login-watcher --path /path/to/docs/ --initial-ingest --load --start

# Update a watcher you installed earlier
rag-mcp install-login-watcher --path /path/to/docs/ --force
```

On macOS the command writes a per-user LaunchAgent that runs `rag-mcp watch <dir>` at login. In an interactive terminal it prompts for the folder, the collection (default `documents`), and whether to run a catch-up ingest, then shows a summary of the full plan before installing. In scripts pass `--path` and add `--yes` to skip prompts. A second install over the same folder stops until you confirm it or pass `--force`. When the existing watcher uses a different label (for example a different collection), the installer refuses and prints the exact `launchctl bootout` and `rm` commands; confirming the prompt or passing `--force` removes the old watcher first, so exactly one watcher remains.

The label is deterministic: `com.rag-mcp.watch.<slug>-<hash>`, built from the folder name and the collection. Files live at `~/Library/LaunchAgents/<label>.plist`, `~/Library/Logs/rag-mcp/<label>.out.log`, and `~/Library/Logs/rag-mcp/<label>.err.log`. Without `--load` or `--start` the watcher starts at your next login. Use `--command-path` to pin an exact `rag-mcp` executable when you keep several Python environments.

With `--initial-ingest`, the installer indexes the folder before it writes the plist or touches launchctl. It reuses the `rag-mcp ingest` pipeline, so the collection's profile governs chunking and extraction. A broken collection profile aborts the install; `--force` applies only to ordinary ingest errors.

> **Platform:** Installation is macOS-only. On any other platform the command exits unless you add `--dry-run`. A dry run prints the label, command, plist path, and log paths; it neither writes files nor calls launchctl.

> **Sparse LaunchAgent environment:** launchd gives the watcher no shell environment from your terminal. Export settings such as `OLLAMA_HOST` through `EnvironmentVariables` in the plist, or point `--command-path` at a wrapper script.

Remove a watcher manually:

```bash
launchctl bootout gui/$UID/com.rag-mcp.watch.<slug>-<hash>
rm ~/Library/LaunchAgents/com.rag-mcp.watch.<slug>-<hash>.plist
```

Re-run the command with `--force` to update an existing watcher instead.

### Shell tab completion

```bash
# Install once per machine
rag-mcp --install-completion

# Or just view the script without installing
rag-mcp --show-completion
```

After installation, press Tab after `rag-mcp ` to see available subcommands and flags.
