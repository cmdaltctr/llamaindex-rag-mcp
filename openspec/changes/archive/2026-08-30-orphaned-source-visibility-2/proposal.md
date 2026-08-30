## Why

Moving or renaming an indexed file creates a new path-derived `source_id`, but
the previous chunks remain searchable with a path that no longer exists. The
system already supports manual deletion, yet it gives operators no way to find
these orphaned source rows.

## Context and Sequencing

This is the second of three ordered changes, as marked by the `-2` suffix.
Implement it after `search-diagnostics-passthrough-1`. The changes share
sequencing only and have no code dependency.

The existing behaviour is intentional and the visibility gap is verified:

- `src/rag_mcp/core/ingestion/source_state.py:190` defines
  `canonical_source_path()` as the shared canonical absolute-path rule for
  ingestion, deletion preview, and deletion.
- `src/rag_mcp/core/ingestion/source_state.py:199` derives `source_id` from
  `SHA-256("file\0" + canonical_path)`. Its docstring states that the identity
  intentionally changes after a move or copy.
- `src/rag_mcp/core/ingestion/loader.py:96` returns listed rows containing
  `source`, `source_id`, and `chunks`. At line 129, display values fall back from
  `file_path` to `file_name` and then `"unknown"`; legacy rows can therefore lack
  a usable absolute path.
- `src/rag_mcp/transports/mcp.py:331` and
  `src/rag_mcp/transports/cli/delete.py:17` already expose manual preview and
  deletion by path. Orphan visibility completes this operator-controlled flow.
- `src/rag_mcp/transports/mcp.py:280` exposes document listing as the
  `list_indexed_documents` MCP tool, which delegates directly to the core list
  function.

## What Changes

- Add an `orphaned` field to every `list_documents()` row.
- Report `true` only for an absolute source path that is missing on the current
  machine.
- Report `false` only for an absolute source path that exists on the current
  machine.
- Report `null` when no usable absolute source path exists. This includes
  basename-only legacy values and `"unknown"`.
- Restrict filesystem existence checks to absolute paths. A basename must never
  be tested against the process working directory.
- Add an `Orphaned` column to human CLI output. Keep JSON and MCP rows as direct,
  additive representations of the core field.
- State in the core docstring and CLI help that the field means “missing on this
  machine”. An index can contain canonical paths from another machine.
- Add focused core, CLI, and MCP regression tests.
- Update the CLI and MCP guides.

The change provides visibility only. It does not delete rows, alter
`source_id`, move files, collect garbage, or watch for moves.

## Capabilities

### New Capabilities

- `orphaned-source-visibility`: tri-state missing-source detection and its core,
  CLI, JSON, and MCP listing contracts.

### Modified Capabilities

None. `large-collection-statistics` owns complete paginated counts,
`document-deletion` owns explicit cleanup, and `collection-storage-layout` owns
backend storage paths. None defines missing-source visibility.

## Impact

**Code**

- `src/rag_mcp/core/ingestion/loader.py` gains the tri-state field while
  retaining source grouping and the injected store seam.
- `src/rag_mcp/transports/cli/list.py` displays the field and documents its local
  machine meaning.
- `src/rag_mcp/transports/mcp.py` retains thin pass-through behaviour. Its tool
  description or docstring records the additive field and local-machine scope.

**Tests**

- Core tests use a fake `VectorStore` through the existing `store` parameter and
  `iter_metadatas()`.
- `tmp_path` fixtures cover existing and missing absolute paths.
- Legacy-shaped metadata covers the unknown state without filesystem guessing.
- CLI tests cover the human column and unchanged JSON field values.
- MCP tests cover additive pass-through from `list_indexed_documents`.
- File-size verification keeps `core/ingestion/loader.py` below 500 lines.

**Documentation**

- `docs/guides/cli-reference.md` explains the column and “missing on this
  machine” semantics.
- `docs/guides/mcp-tools.md` documents the additive `orphaned` field.

No dependency, configuration, stored-data migration, or destructive behaviour
is introduced.
