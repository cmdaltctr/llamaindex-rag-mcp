## Context

The `rag-mcp` CLI already has an `ingest` subcommand that accepts a file or directory path, uses Rich progress bars to show file reading and chunk embedding progress, and supports parallel file reading via `--workers`. However, it lacks:

1. **Structured per-file logging** — the current logging is at the module level (batch-level), not per-file with clear success/failure/skip status.
2. **Report generation** — there's no way to produce a machine-readable summary of what was ingested, what failed, and why.
3. **Folder-specific workflow** — users with Zotero libraries or document collections need a single command that handles discovery → ingestion → verification → report.

The existing `ingestion.ingest_path()` returns `{"status", "files_indexed", "chunks_created", "warnings"}`. This is sufficient for the CLI's current display but doesn't carry per-file detail needed for a report.

## Goals / Non-Goals

**Goals:**
- Add a `--report <path>` flag to `rag-mcp ingest` that writes a structured ingestion report
- Enhance `ingest_path()` return value with per-file details (file, status, chunks, error)
- Add structured logging with timestamps for every file processed
- Support JSON and Markdown report formats
- Test the full workflow with real PDFs from Zotero storage

**Non-Goals:**
- Changing the MCP server tools or protocol
- Adding a new CLI subcommand (enhancing the existing `ingest`)
- Resume/retry logic for previously failed files
- Watching folders for new files (inotify/fsevents)

## Decisions

### D1: Report format — JSON and Markdown via `--report`

**Decision**: The `--report` flag accepts a file path. The format is inferred from the extension: `.json` for JSON, `.md` or anything else for Markdown.

**Rationale**: JSON enables machine parsing (CI/CD, scripts), Markdown is human-readable. Using the file extension is the lightest-weight approach — no extra flags needed.

**Alternatives considered**:
- Separate `--report-format` flag — adds unnecessary complexity for a simple feature.
- Only JSON — not user-friendly for manual review.

### D2: Per-file tracking in `ingest_path()`

**Decision**: Extend the return dict with a `"file_details"` key containing a list of `{file, status, chunks, error}` entries.

**Rationale**: The CLI already has progress callbacks. Adding per-file results to the return value is backward-compatible (new key, doesn't break existing consumers). The MCP server tools ignore extra keys.

**Alternatives considered**:
- Separate function for "detailed ingest" — code duplication.
- Callback-based collection — over-engineering for this use case.

### D3: Report content structure

**Decision**: The report includes:
- Timestamp (ISO 8601)
- Configuration used (model, batch size, concurrency, workers)
- Input path
- Summary (total files, indexed, failed, skipped, total chunks)
- Per-file details (file name, status, chunks, duration, error if any)

**Rationale**: This matches what a user needs to verify a successful ingestion run and diagnose failures.

### D4: ADR placement

**Decision**: Write an ADR in `docs/adr/` documenting the folder embedding workflow.

**Rationale**: Follows the project's existing convention of recording architectural decisions.

## Risks / Trade-offs

- **Large return dicts** → `file_details` could be large for 100+ files. Mitigation: it's a CLI-only feature; MCP tools don't use it.
- **Report file overwrites** → `--report` will overwrite existing files silently. Mitigation: log a warning when overwriting.
- **Backward compatibility** → Adding `file_details` key is additive. No breaking changes.
