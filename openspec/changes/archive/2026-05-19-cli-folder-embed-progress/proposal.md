## Why

The CLI already supports `rag-mcp ingest <path>` but there is no end-to-end workflow for embedding an entire folder of documents (like a Zotero PDF collection) with visibility into what's happening. Users need a single command that: (1) discovers all supported files in a folder, (2) shows real-time progress per file, (3) logs every action for audit, and (4) produces a summary report. This makes the tool practical for real document collections — the current progress bars work, but there is no structured logging or report output.

## What Changes

- Add structured file-level logging during ingestion (timestamps, file paths, chunk counts, errors)
- Add a `--report <path>` CLI flag that writes a JSON/Markdown ingestion report after completion
- Enhance the existing Rich progress bars to show per-file status (✓ indexed / ✗ failed / ⏭ skipped)
- Ensure the CLI gracefully handles mixed file types in a folder (skip unsupported, continue with rest)
- Add integration test that ingests a folder of real PDFs via the CLI and verifies the report

## Capabilities

### New Capabilities
- `cli-folder-embed`: End-to-end folder embedding from the CLI with structured logging, per-file progress status indicators, and a machine-readable report output (`--report`). Covers discovery, ingestion, error handling, and summary generation.

### Modified Capabilities
_(none — no existing spec-level requirements change)_

## Impact

- `src/rag_mcp/cli.py`: Add `--report` flag, structured logging output, report generation
- `src/rag_mcp/ingestion.py`: Add per-file result tracking (indexed/failed/skipped with reasons) to the return dict
- `tests/test_cli.py`: New tests for folder ingestion, report output, mixed file types
- `docs/adr/`: ADR documenting the folder embedding workflow
