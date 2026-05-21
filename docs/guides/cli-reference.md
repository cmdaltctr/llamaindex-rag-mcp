# CLI Reference

The `rag-mcp` command doubles as an MCP server and a CLI tool. With no arguments it starts the MCP stdio server. With subcommands it operates directly from the terminal.

## Subcommands

| Command | Description |
|---------|-------------|
| `rag-mcp` | Start the MCP stdio server |
| `rag-mcp ingest <path>` | Index a file or directory into the vector store |
| `rag-mcp search <query>` | Search indexed documents for semantically relevant chunks |
| `rag-mcp list` | Show indexed documents with chunk counts |
| `rag-mcp list-collections` | Show all ChromaDB collections with document and chunk counts |
| `rag-mcp watch <dir>` | Watch a directory for new/changed documents and auto-ingest them |
| `rag-mcp delete` | Delete documents by file path, metadata filter, or drop a collection |
| `rag-mcp benchmark` | Benchmark embedding throughput (no ChromaDB writes) |
| `rag-mcp --version` | Show version |
| `rag-mcp --help` | Show help |
| `rag-mcp --install-completion` | Install shell tab completion |

## Common flags

| Flag | Applies to | Description |
|------|-----------|-------------|
| `--collection`, `-c` | `ingest`, `search`, `list`, `watch`, `delete` | ChromaDB collection name (default `"documents"`) |
| `--json` | `ingest`, `search`, `list`, `list-collections`, `delete` | Output results as JSON |
| `--workers`, `-w` | `ingest` | Number of parallel file readers |
| `--chunk-size` | `ingest` | Override chunk size (characters) |
| `--chunk-overlap` | `ingest` | Override chunk overlap (characters) |
| `--report`, `-r` | `ingest` | Write ingestion report to a file |
| `--top-k`, `-k` | `search` | Max results to return |
| `--threshold`, `-t` | `search` | Minimum similarity score |
| `--rerank` | `search` | Re-score with cross-encoder reranker |
| `--debounce`, `-d` | `watch` | Debounce interval in seconds (default: 2) |
| `--verbose`, `-v` | `watch` | Enable DEBUG-level logging |
| `--dry-run` | `delete` | Preview deletion without modifying ChromaDB |
| `--yes`, `-y` | `delete` | Skip confirmation prompt for collection deletion |

## Examples

### ingest

```bash
# Index a single file
rag-mcp ingest ~/Documents/paper.pdf

# Index a directory (4 workers by default)
rag-mcp ingest /path/to/docs/

# Index into a named collection
rag-mcp ingest /path/to/papers/ --collection research

# Custom parallelism and chunking
rag-mcp ingest /path/to/docs/ --workers 8 --chunk-size 1024 --chunk-overlap 128

# JSON output for scripts
rag-mcp ingest /path/to/docs/ --json
```

Collections are created automatically on first ingest — nothing to set up.

### search

```bash
# Basic semantic search
rag-mcp search "quantum entanglement"

# Search a specific collection
rag-mcp search "transformer architecture" --collection research

# With reranking and threshold
rag-mcp search "machine learning" --rerank --threshold 0.3 --top-k 10

# JSON output
rag-mcp search "climate change" --json
```

> Metadata filtering is only available via the `search_documents` MCP tool, not the CLI.

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

> **Concurrency warning:** Do not run `rag-mcp watch` and `rag-mcp ingest` (or the MCP server) simultaneously on the same ChromaDB — two processes do not share the internal write lock.

### Shell tab completion

```bash
# Install once per machine
rag-mcp --install-completion

# Or just view the script without installing
rag-mcp --show-completion
```

After installation, press Tab after `rag-mcp ` to see available subcommands and flags.
