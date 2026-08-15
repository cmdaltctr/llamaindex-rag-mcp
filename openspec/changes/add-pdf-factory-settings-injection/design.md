## Context

See `proposal.md` for the motivation. The constraints that shape the design:

- `compose.py` already resolves `PDF_READER` (including `auto`) once at
  startup and bakes the concrete name into `EffectiveSettings.pdf_reader`.
- `get_pdf_reader()` in `integrations/pdf/factory.py` has two in-tree call
  sites: `core/ingestion/chunker.py` `_read_sync()` and
  `integrations/azure.py` `_read_with_local_chain()`.
- The chunker already holds the injected `resolved` settings at its call
  site; the Azure path (`read_with_azure_fallback` →
  `_read_with_local_chain`) carries no settings today.
- The factory's local `auto` probe checks `liteparse → pypdf`, diverging
  from the spec and compose order `liteparse → pypdfium2 → pypdf`.
- `get_default_effective_settings()` is the composition-root default
  accessor (AGENTS.md gotcha 8a). Reading it from `integrations/` models
  the wrong pattern for future direct callers.

## Goals / Non-Goals

**Goals:**

- `get_pdf_reader()` receives the reader name; it never fetches settings.
- The local `auto` probe matches the composition-root preference order.
- Both call sites and the Azure fallback chain thread the caller's reader.

**Non-Goals:**

- Changing `compose.py` resolution, defaults, env vars, or the registry.
- Extracting a shared probe helper for compose and the factory.
- Retrofitting the whole `EffectiveSettings` object through the Azure path
  when only the reader name is needed.
- Fixing unrelated stale scenarios elsewhere in the two spec files.

## Decisions

### 1. Required parameter, no default pull

`get_pdf_reader(reader: str) -> Any`. Calling without a name raises
`TypeError`. An optional parameter defaulting to
`get_default_effective_settings().pdf_reader` was rejected: it preserves the
exact smell this change removes. This is an internal API with two in-tree
callers, both updated here.

### 2. Pass the reader name, not the settings object

Call sites pass `resolved.pdf_reader` (a `str`). Passing the whole
`EffectiveSettings` was rejected: the factory needs one field, and the Azure
chain would then appear to need the full object when it does not. Narrow
parameters keep the dependency honest.

### 3. Align the local `auto` probe inline

The factory's local fallback becomes a three-step probe:
`liteparse → pypdfium2 → pypdf`. A shared helper module used by both
`compose.py` and the factory was rejected: compose's resolver also owns
explicit-name fallback logging policy, the probe is six lines, and compose
already carries a parallel inline probe for the sparse backend. Two
six-line probes keyed by the same spec requirement cost less than a new
module and a new import edge.

### 4. Thread the reader through the Azure fallback chain

`read_with_azure_fallback(file_path, pdf_reader: str, ...)` and
`_read_with_local_chain(file_path, pdf_reader: str)`. The chunker passes
`resolved.pdf_reader`. This keeps the fallback chain on the caller's
configured reader rather than silently switching to the process default
after an Azure failure.

### 5. Log-once keys on the reader name

`_pdf_reader_logged` becomes a set of names already logged. The first
construction per name logs the backend line. This preserves the existing
noise-reduction intent without module-level settings state.

## Risks / Trade-offs

- [Signature break for out-of-tree callers] → Internal API; both call sites
  updated; CHANGELOG entry notes the break.
- [Factory and compose probes can drift again] → The pdf-reader spec now
  states both paths MUST produce identical selections; a contract test
  asserts it.
- [Azure chain signature churn] → Keyword-only parameter keeps the diff
  mechanical; behaviour is otherwise untouched.

## Migration Plan

Single PR, no runtime configuration change. Rollback is revert: no data or
settings migration applies.
