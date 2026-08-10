# ADR-008: CLI Folder Embedding with Progress and Reports

**Status**: Accepted

> **Superseded note (2026-05-25):** the ingest report no longer includes a
> file-reader worker count. File reading is sequential; embedding throughput is
> tuned with `EMBED_BATCH_SIZE` and `EMBED_CONCURRENCY`.
**Proposed**: 2026-05-19
**Accepted**: 2026-05-19
**Change**: `cli-folder-embed-progress`

## Context

The `rag-mcp ingest` CLI command supports folder ingestion with Rich progress bars. However, it lacks structured per-file tracking, logging, and report generation. When ingesting a Zotero library or document collection, users need visibility into which files succeeded, which failed, and a machine-readable summary for verification.

## Decision

### 1. Per-file tracking in `ingest_path()` return value

Extend the return dict with a `file_details` list containing per-file status:

```python
{
    "status": "ok",
    "files_indexed": 3,
    "chunks_created": 45,
    "file_details": [
        {"file": "doc1.pdf", "status": "indexed", "chunks": 20},
        {"file": "doc2.txt", "status": "indexed", "chunks": 15},
        {"file": "corrupt.pdf", "status": "failed", "chunks": 0, "error": "..."},
    ],
}
```

**Rationale**: Additive change — the existing `files_indexed`, `chunks_created`, and `warnings` keys remain unchanged. MCP server tools ignore the extra key.

### 2. `--report` CLI flag

Add `--report <path>` to `rag-mcp ingest`. The format is inferred from the file extension:

- `.json` → JSON with `timestamp`, `config`, `input_path`, `summary`, `files` keys
- `.md` or any other extension → Markdown with Summary, Configuration, and Per-File Details tables

**Rationale**: No extra `--format` flag needed. Extension-based detection is the lightest approach. JSON enables CI/CD integration; Markdown is human-readable.

### 3. Structured per-file logging

Each file processed generates an INFO-level log line:

```
✓ document.pdf — 20 chunk(s)
✗ corrupt.pdf — Failed to parse...
```

**Rationale**: Makes `rag-mcp ingest` output scannable in CI logs and terminal history.

## Consequences

- **Positive**: Users get a complete audit trail for ingestion runs. Reports can be diffed between runs to detect changes.
- **Positive**: CI/CD pipelines can use `--report report.json` and parse the result for assertions.
- **Neutral**: The `file_details` list is always present in the return value, even for single-file ingests. This is harmless.
- **Risk**: Large folders (>1000 files) produce large reports. Mitigated by the fact that reports are opt-in via `--report`.

## Alternatives Considered

### `--format json|markdown` flag instead of extension-based detection
Rejected because extension-based detection requires no extra flag to remember
and maps naturally to user expectation (`.json` → JSON, everything else → Markdown).
The file extension acts as the self-documenting format selector.

### Standalone report module (`report.py`)
Rejected to keep the change small and co-located with the CLI logic that generates
reports. If report generation grows beyond the current `_write_report()` function
(~60 lines), extracting to a dedicated module would be warranted.

### Gating `file_details` behind a `--detailed` flag
Rejected because the per-file data is already collected during ingestion for
logging and progress display. The `file_details` field is always present in the
return dict — clients that do not need it can safely ignore it. There is no
performance cost since the data is collected regardless.

### `--report` as a directory-only feature
Rejected because single-file ingestion also benefits from structured reporting
(e.g., in CI/CD pipelines where a single file is ingested and the result
verified). The feature works uniformly for both files and directories.

## Format Specifications

### JSON Report Structure

```json
{
  "timestamp": "2026-05-19T12:00:00+00:00",
  "config": {
    "model": "qwen3-embedding:0.6b",
    "batch_size": 100,
    "concurrency": 2,
    "chunk_size": 512,
    "chunk_overlap": 64
  },
  "input_path": "/path/to/docs",
  "summary": {
    "total": 5,
    "indexed": 4,
    "failed": 1,
    "skipped": 0,
    "chunks": 234
  },
  "files": [
    {"file": "doc1.pdf", "status": "indexed", "chunks": 50},
    {"file": "doc2.pdf", "status": "indexed", "chunks": 40},
    {"file": "bad.pdf", "status": "failed", "chunks": 0, "error": "..."}
  ]
}
```
