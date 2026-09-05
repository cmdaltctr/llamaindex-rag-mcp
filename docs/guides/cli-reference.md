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
| `omrg benchmark`             | Benchmark embedding throughput without vector-store writes                       |
| `omrg --version`             | Show version                                                                     |
| `omrg --help`                | Show help                                                                        |
| `omrg --install-completion`  | Install shell tab completion                                                     |

## Common flags

| Flag                 | Applies to                                               | Description                                                          |
| -------------------- | -------------------------------------------------------- | -------------------------------------------------------------------- |
| `--collection`, `-c` | `ingest`, `search`, `list`, `watch`, `delete`, `answer`  | Collection name in the selected vector store (default `"documents"`) |
| `--json`             | `ingest`, `search`, `list`, `list-collections`, `delete`, `answer` | Output results as JSON (written to stderr like all CLI output; stdout stays the MCP protocol channel) |
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
| `--yes`, `-y`        | `delete`                                                 | Skip confirmation prompt for collection deletion                     |

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

With `--initial-ingest`, the installer indexes the folder before it writes the plist or touches launchctl. It reuses the `omrg ingest` pipeline, so the collection's profile governs chunking and extraction. A broken collection profile aborts the install; `--force` applies only to ordinary ingest errors.

> **Platform:** Installation is macOS-only. On any other platform the command exits unless you add `--dry-run`. A dry run prints the label, command, plist path, and log paths; it neither writes files nor calls launchctl.

> **Sparse LaunchAgent environment:** launchd gives the watcher no shell environment from your terminal. Export settings such as `OLLAMA_HOST` through `EnvironmentVariables` in the plist, or point `--command-path` at a wrapper script.

Remove a watcher manually:

```bash
launchctl bootout gui/$UID/com.omrg.watch.<slug>-<hash>
rm ~/Library/LaunchAgents/com.omrg.watch.<slug>-<hash>.plist
```

Re-run the command with `--force` to update an existing watcher instead.

### Shell tab completion

```bash
# Install once per machine
omrg --install-completion

# Or just view the script without installing
omrg --show-completion
```

After installation, press Tab after `omrg ` to see available subcommands and flags.
