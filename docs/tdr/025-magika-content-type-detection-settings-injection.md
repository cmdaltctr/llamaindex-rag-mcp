# TDR-025: Content-type detection silently degraded to suffix routing in direct-Engine processes — settings now threaded through the detector

**Date:** 2026-09-15
**Status:** Accepted (amended same day — verified consequence scope of detection below)
**Deciders:** Aizat
**Tags:** magika | ingestion | settings-injection | dependency-injection | codebase-map

## Context

Experiment 31 (`experiments/31-reader-rescue-retrieval-impact-2026-09-15/`)
logged `Magika detection failed, using extension-based routing: No default
EffectiveSettings installed` once per document (57 times) while building its
three indexes through directly-constructed engines.

### Root Cause Analysis

The ingestion pipeline resolved `EffectiveSettings` per operation and passed
it to the reader, chunker, and writer — but called
`detect_file_types(str(path))` bare (`core/ingestion/pipeline.py`). The
resolution chain bottomed out in **three** process-global reads, not one:

1. `integrations/magika.py:_magika_binary()` — `get_default_effective_settings().magika_binary`
2. `core/codebase/codebase_map.py:scan_with_suffix` → `_walk` — `codebase_map_max_depth`
3. the file-count gate in `detect_file_types` — `codebase_map_max_files`

`compose.build_engine()` installs no process-global state (by design,
ADR-061); only the legacy `ensure_runtime_setup()` installer does. Any
process using the public `omrg.Engine` API directly — library consumers,
tests, experiment harnesses — has no default installed, so the first global
read raised `RuntimeError`, the pipeline caught it
(`pipeline.py:195-202`), and every file silently degraded to suffix routing.
The shipped MCP server installs the global at startup, which is why
production looked healthy while every direct-API consumer degraded.

Blast radius: direct-Engine processes only. Chunking was unaffected for
Experiment 31 (PDF dispatch keys on the reader's declared `text_format`,
identical in all cells), so its measured comparison stood.

## Decision

Thread the caller's settings through the detection chain as an optional
parameter (change `thread-settings-through-magika-detection`):

- `integrations/magika.py`: `_magika_binary(settings=None)`,
  `_is_magika_available(settings=None)`, `scan_with_magika(path, settings=None)`
  — inject when given; `None` keeps the legacy global resolution for
  entry points that resolve at their own boundary (ADR-037 invariant #9).
- `codebase_map.detect_file_types(path, settings=None)` resolves once at
  the top (`effective = settings or global`) and passes it to the Magika
  branch, both `scan_with_suffix` calls, `_walk`, and the count gate.
- `pipeline.py` passes `settings=resolved_settings` at the call site.
- `build_codebase_map` passes its boundary-resolved `effective` into
  `detect_file_types`, removing a duplicate global read.

Regression tests: `tests/test_magika_settings_injection.py` — (1) an
ingest with injected settings and the process default reset produces no
`Magika detection failed` warning and either a live scan or the documented
`Magika CLI not installed` degradation; (2) `_magika_binary(settings=...)`
never consults the global (proven by a raising stub on the module's getter).
Both failed before the fix and pass after.

## Consequences

**Positive:** direct-Engine processes get real content typing; the
`settings-dependency-injection` spec gains an enforcement scenario; the
suffix fallback also works standalone.

**Negative:** `content_type` participates in `build_index_identity`, so rows
written by direct-Engine processes (identities built with
`content_type=None`) go stale and rebuild on their next re-ingest. One-time,
correct staleness semantics; server-written collections already carry the
label.

**Neutral:** the `None` default still reaches the global on legacy paths —
required for the codebase-map entry boundary.

## Alternatives Considered

| Alternative | Rejected because |
| --- | --- |
| Install a global default in `build_engine()` | Violates side-effect-free construction (ADR-061); masks the DI defect |
| Catch the `RuntimeError` and construct class-default settings | Silently discards operator configuration (the H-7 failure mode the settings getter documents) |
| Required (non-optional) settings parameter | Breaks the codebase-map entry boundary that legitimately resolves the global |

## How to Recognise / Handle This Again

Symptom: `Magika detection failed, using extension-based routing: No default
EffectiveSettings installed` in logs of an Engine-constructed process.
Diagnose: `grep -rn "get_default_effective_settings" src/omrg/core src/omrg/integrations`
and check each hit is either an entry-point boundary or receives injected
settings. The regression test
(`uv run pytest tests/test_magika_settings_injection.py`) pins the
ingestion path.

## Revisit Triggers

- A new global-settings read appears under `core/` or `integrations/`
  reachable from an operation that already holds injected settings.
- `detect_file_types` grows a new branch (a future detector) — thread
  `settings` into it at birth.

### Amendment (2026-09-15): verified consequence scope of detection

Two facts confirmed against source after the fix landed, sharpening what
the silent degradation actually cost beyond label provenance:

1. **Detection drives chunking dispatch, not just labels.** A
   `code/<language>` content type routes through
   `MAGIKA_LABEL_TO_TREESITTER` (`core/codebase/ast_extract.py:43-60`)
   into the AST-aware CodeSplitter (`core/ingestion/chunker.py:57-79`);
   a `binary/…` type skips the file before any reader runs
   (`core/ingestion/pipeline.py:252-258`). The suffix map already labels
   honest extensions (`.py` → `code/python`), so the degradation's real
   cost was mislabelled files (code named `.txt` chunked as prose) and
   junk files (binary renamed `.pdf` reaching the PDF reader as an
   error instead of being skipped).
2. **Skip semantics make label stability the deployment concern.** The
   unchanged-skip keys on an identity built from the content hash,
   settings, and the content-type label
   (`core/ingestion/source_state.py:150-153`; skip branch at
   `pipeline.py:327-330`). Identical labels mean identical identity —
   re-ingest skips with zero cost. A label-string change (for example a
   Magika taxonomy differing from the suffix map) rebuilds every
   affected file.

   **Superseded statement (2026-09-16):** “Whether google-magika emits
   the same `group/label` strings as `_SUFFIX_MAP` is unverified until
   the package is installed.” The official PyPI package is `magika`,
   not `google-magika`. The nested `result.value.output` parser shape
   and the accepted boundary normalisation are now verified below.

### Update (2026-09-16): pinned Magika parser and gate

`magika==1.0.3` is a packaged CLI base dependency. `MAGIKA_BINARY`
remains the injected executable override. Missing binaries, non-zero
exits, timeouts, and parser failures use the existing warned suffix
fallback.

The parser accepts only `result.status == "ok"` rows. It reads
`result.value.output`, validates `group`, `label`, and `is_text`, and
fails the complete scan for any invalid row. Normalisation remains
narrow: `text/markdown` becomes `document/markdown`, `text/txt`
becomes `document/text`, and only non-document, non-code, non-text
`is_text=false` rows change group to `binary`.

The frozen 16-file gate passed on 2026-09-16: 16/16 all-match and exit
0. See `openspec/changes/pin-magika-detection/acceptance-corpus.md`
and [ADR-068](../adr/068-pin-magika-content-detection.md). This TDR
remains authoritative for settings injection and index identity.

## References

- Change: `openspec/changes/thread-settings-through-magika-detection/`
- Spec: `openspec/specs/settings-dependency-injection/spec.md` (content-type
  detection scenario)
- Finding record: Experiment 31 report, Limitations
- Related: ADR-037 (nested settings + injection), ADR-061 (engine-scoped
  composition), TDR-001 (codebase-map boundary)
