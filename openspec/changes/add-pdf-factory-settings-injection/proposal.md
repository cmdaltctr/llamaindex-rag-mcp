## Why

`integrations/pdf/factory.py:get_pdf_reader()` fetches its configuration by
calling `get_default_effective_settings()` inside `integrations/`. Every other
module under `core/` and `integrations/` receives settings as a parameter
(ADR-037, invariant 9). The factory is the lone remaining self-fetcher, so the
pattern it models for future direct callers is the wrong one.

The same function carries a second, behavioural defect: its local `auto`
fallback probe checks `liteparse → pypdf`, skipping `pypdfium2`. The
`pdf-reader` capability spec and `compose.py` both define the order as
`liteparse → pypdfium2 → pypdf`. A caller that builds settings directly
(tests, library use) with `PDF_READER=auto` therefore resolves to `pypdf` even
when `pypdfium2` is installed — a spec violation on the non-composition-root
path.

## What Changes

- `get_pdf_reader()` takes the resolved reader name as a parameter instead of
  reading the composition-root default.
- The local `auto` probe in the factory aligns with the spec order:
  `liteparse → pypdfium2 → pypdf`.
- `core/ingestion/chunker.py` passes `resolved.pdf_reader` at its call site.
- `integrations/azure.py` threads the reader name through
  `read_with_azure_fallback()` and `_read_with_local_chain()` so the fallback
  chain uses the caller's configured reader rather than the process default.
- The "PDF reader backend" one-shot log moves to key on the reader name so the
  first call per name logs once without module-level settings state.

No MCP tool, CLI command, environment variable, default value, or registry
entry changes. The composition-root production path behaves identically
because `compose.py` already bakes the resolved concrete name in.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: the auto-resolution requirement gains the factory-local probe
  path; the local probe order becomes `liteparse → pypdfium2 → pypdf`,
  matching the composition root.
- `settings-dependency-injection`: the parameter-injection requirement gains
  the PDF factory — `get_pdf_reader()` receives the reader name from its
  caller and no module under `integrations/` fetches the composition-root
  default.

## Impact

**Code**

- `src/rag_mcp/integrations/pdf/factory.py` — signature change, probe fix.
- `src/rag_mcp/core/ingestion/chunker.py` — one call site passes the name.
- `src/rag_mcp/integrations/azure.py` — two signatures gain a reader
  parameter.

**Tests**

- Existing factory tests that call `get_pdf_reader()` with no argument update
  to pass a name; new tests cover the `pypdfium2` auto path and azure chain
  threading.

**Compatibility**

- `get_pdf_reader()` is an internal API. Its signature change is breaking for
  direct callers only; both in-tree call sites are updated in this change.

**Documentation**

- `docs/guides/` references to the factory, if any describe the self-fetch.
