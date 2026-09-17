# Design: Thread settings through Magika content-type detection

## Context

The ingestion pipeline resolves `EffectiveSettings` once per operation and
passes it to the reader, chunker, and writer — but its content-type scan
calls `detect_file_types(path)` bare (`core/ingestion/pipeline.py:195`).
The resolution chain then bottoms out in
`integrations/magika.py:_magika_binary()`, which reads
`get_default_effective_settings().magika_binary`. Processes that built an
`Engine` directly (`omrg.Engine` is the public API; `build_engine`
installs nothing process-global) have no default installed, the lookup
raises, and the pipeline catches the failure into silent extension-based
routing. The shipped MCP server installs the global via
`ensure_runtime_setup()`, which is why production looks healthy while
every direct-API consumer degrades.

## Goals

- Content-type detection in ingestion uses the injected settings.
- No behaviour change for existing callers: the codebase-map transport
  path and the MCP server path behave exactly as today.
- The extension-based fallback remains the documented degradation when
  the Magika binary is genuinely unavailable.
- A regression test that fails on the current code and passes after.

## Non-Goals

- No change to chunking dispatch, index identity computation, or the
  fallback policy itself.
- No new settings; `magika_binary` keeps its meaning.
- No change to the legacy `ensure_runtime_setup()` installer or the
  sanctioned boundary resolution in `generate_codebase_map`.

## Decisions

### D1 — Optional `settings` parameter threaded to the leaf

`detect_file_types(path, settings=None)`,
`scan_with_magika(path, settings=None)`, `_is_magika_available(settings=None)`,
and `_magika_binary(settings=None)` accept the caller's settings. When
`settings` is provided the leaf reads `settings.magika_binary` and never
touches the global; when it is `None` the existing global resolution runs
(legacy entry paths). This is the smallest signature change that satisfies
"pass it down to every module they call" without breaking the codebase-map
entry boundary, whose own resolution at `codebase_map.py:332` is sanctioned
(invariant #9: entry points resolve once at the boundary).

### D2 — Pipeline passes its resolved settings

`pipeline.py` passes `settings=resolved_settings` at the existing call
site. Nothing else in the pipeline changes; the surrounding try/except
stays as the guard for a genuinely broken Magika invocation.

### D3 — Boundary call tightens while touched

`generate_codebase_map` (`codebase_map.py:330`) already resolves
`effective` at its boundary; it now passes it into
`detect_file_types(path, settings=effective)`, removing one of the two
global reads on that path. The remaining global read disappears only if
that entry point itself is later converted to injection — out of scope.

### D4 — Index-identity staleness is accepted and documented

`content_type` participates in `build_index_identity`. After the fix,
direct-Engine ingests populate it where they previously built identities
with `content_type=None`, so rows written by such processes go stale and
rebuild on their next re-ingest. Server-written collections already carry
the label and are unaffected. This one-time rebuild is correct staleness
semantics, not data loss; the proposal records it.

## Risks / Trade-offs

- The optional-parameter pattern leaves a `None` default that still reads
  the global; a stricter required-parameter change would break the
  codebase-map entry path that legitimately owns boundary resolution.
  The DI spec gains a scenario pinning the ingestion path so the `None`
  default cannot quietly spread to new ingestion call sites.
- CI environments without the `magika` binary exercise the
  "CLI not installed" warning instead of a live scan; the regression
  test asserts on the settings-lookup path, not on the binary's presence.
