## Context

See `proposal.md` for the motivation and verified source references.

`list_documents()` already scans metadata through an injected `VectorStore`,
groups production rows by `source_id`, and returns one row per source. A row's
display source falls back from `file_path` to `file_name` and then `"unknown"`.
Only `file_path` from production ingestion is expected to be canonical and
absolute.

The CLI serialises the core rows directly for JSON and builds a Rich table for
human output. The MCP `list_indexed_documents` tool returns the same core rows
without adapting their successful shape. Existing delete commands already own
all cleanup behaviour.

`core/ingestion/loader.py` is currently 145 lines. The repository-wide ceiling
is 500 lines, enforced by `tests/test_file_size_ceiling.py`.

## Goals / Non-Goals

**Goals**

- Classify each grouped listing row as missing, present, or unknown.
- Avoid filesystem checks for non-absolute display values.
- Keep classification machine-local and calculated at listing time.
- Preserve thin CLI and MCP transport boundaries.
- Keep listing read-only and source identity unchanged.

**Non-Goals**

- Add pruning, automatic cleanup, or garbage collection.
- Preserve identity across file moves or renames.
- Move source files or watch for moves.
- Persist an orphan marker in vector metadata.
- Add a new dependency, setting, store method, or migration.

## Decisions

### D1. Derive orphan status from the grouped display source at listing time

Classification happens after metadata rows are grouped. Each returned source is
therefore checked at most once, regardless of its chunk count.

For each grouped row:

1. Treat the display source as unknown when it is not absolute locally.
2. Return `orphaned: null` without an existence check for that case.
3. For an absolute source, check local existence once.
4. Return `false` when it exists and `true` when it does not.

This keeps the field current. Persisting a marker would become stale after any
filesystem change and would record one machine's state as collection data.

**Alternative considered:** classify every chunk metadata row. Rejected because
it repeats the same filesystem call for all chunks belonging to one source.

**Alternative considered:** derive status from `source_id`. Rejected because the
identifier is a one-way hash and contains no recoverable path information.

### D2. Non-absolute source values always produce the unknown state

A basename can coincide with a file in the process working directory. Running
an existence check would then report a false present state. It could also report
a false missing state when the basename refers to a file elsewhere.

The implementation first applies the host runtime's absolute-path predicate.
Only a positive result permits an existence check. A foreign path syntax that
is not absolute on the current host therefore produces `null`.

**Alternative considered:** test every non-empty string. Rejected because its
meaning depends on the process working directory and can change between calls.

**Alternative considered:** parse foreign operating-system path formats.
Rejected because the current machine cannot perform a meaningful local
existence check for those paths.

### D3. Core owns the tri-state value; transports only present it

`core/ingestion/loader.py` adds `orphaned` to the returned row. It also updates
the public docstring to define the field as “missing on this machine”.

The CLI JSON branch continues to serialise `docs` directly. The human table adds
an `Orphaned` column and maps the values to `Yes`, `No`, and `Unknown`. Its help
text states the machine-local limit.

The MCP handler keeps direct pass-through behaviour. Its description and
docstring describe the additive field and local meaning. No MCP parameter or
error envelope changes.

**Alternative considered:** calculate status independently in each transport.
Rejected because CLI and MCP could disagree and transport code would gain
filesystem business logic.

### D4. Existing explicit deletion remains the only cleanup path

Listing performs no store mutation. A reported row can feed the existing delete
preview or delete command, but the operator decides whether to act. The
canonical path and `source_id` formula remain unchanged.

**Alternative considered:** delete missing rows during listing. Rejected because
the path can belong to another machine or a temporarily unavailable mount.

### D5. Tests use the injected store seam and temporary paths

Core tests inject a small fake `VectorStore` through `store=`. The fake supplies
`count()` and `iter_metadatas()` only as required by the listing contract.

`tmp_path` supplies one existing absolute path and one absent absolute path.
Legacy metadata supplies basename-only and missing-source cases. A spy or
failing existence probe proves that neither case reaches the filesystem check.

CLI tests cover the column, the three human labels, and direct JSON values. MCP
tests confirm that `list_indexed_documents` returns the additive key unchanged.

## Risks / Trade-offs

- **A removable drive is temporarily unavailable** → Report only machine-local
  state and require explicit deletion.
- **A foreign path looks relative on this host** → Return `null`; never guess
  from the working directory.
- **Listing performs filesystem input/output** → Check once per grouped source,
  not once per chunk.
- **An additive key breaks an exact-shape test** → Update contract tests while
  retaining all previous keys.
- **The core file grows unnecessarily** → Keep the logic local and verify the
  500-line ceiling.

## Migration Plan

No stored-data migration is required. Deploy the additive core field, transport
presentation, tests, and documentation together.

Rollback removes the field and CLI column. It does not change stored rows,
source identities, or deletion behaviour.
