## Context

See `proposal.md` for the motivation. Every factual claim in the delta was
verified against the code before writing:

- `RESOLVED_*` constants were deleted in v2.0.0; only a comment in
  `config/__init__.py` mentions them.
- Unknown `PDF_READER` values warn and fall back to `auto` at
  `config/__init__.py` (frozen `Settings.pdf_reader` field).
- `compose.resolve_pdf_reader` resolves `auto` once at startup.
- Per-file error conversion lives in `core/ingestion/pipeline.py` around
  `read_and_chunk_file_async`, using `core/ingestion/loader.py:make_file_detail`.
- `src/rag_mcp/integrations/pdf/` has no `base.py`; the contract is the
  duck-typed `load_data` enforced by the registry dispatch.
- `src/rag_mcp/readers/` no longer exists (shim deleted in v2.0.0).
- `liteparse>=2.0.0` is a main `[project.dependencies]` entry.

## Goals / Non-Goals

**Goals:**

- Every scenario in the `pdf-reader` baseline describes shipped behaviour.
- Remove the transition requirement superseded by two later requirements.

**Non-Goals:**

- Any runtime, configuration, or test change.
- Rewriting requirements that are already accurate (auto probe order,
  bbox metadata, core dependency).
- Touching other baseline specs with unrelated staleness.

## Decisions

### 1. Correct by verification, not by memory

Each rewritten scenario was checked against current source before writing.
Where the spec and code disagreed on mechanism but agreed on behaviour
(error dictionaries), the delta attributes the mechanism to the code
(pipeline-owned conversion) rather than preserving the fictional adapter
contract.

### 2. Remove rather than weaken the transition requirement

The "default preserved when LiteParse not installed" requirement cannot be
salvaged by rewording: its premise (optional extra, pre-Experiment-11
default) is false on every axis. OpenSpec's REMOVED format records the
reason and confirms no migration is needed.

## Risks / Trade-offs

- [A future reader diffs archived deltas against the new baseline] → The
  archive of this change records the removal and rewrites explicitly, which
  is the audit trail.

## Migration Plan

Archive syncs the delta into the baseline. Rollback is revert.
