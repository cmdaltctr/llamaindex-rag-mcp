## Why

`DOCUMENT_BACKEND=local|azure` selects between interchangeable document-reading paths, but dispatch is split across `core/ingestion/chunker.py`, `integrations/azure.py`, and the PDF factory. Azure also owns retry and local fallback, while configuration silently degrades to local when credentials are missing. Registering these implementations during the community-strategy audit would change fallback ownership and startup behaviour, so the migration needs its own reviewed contract.

## What Changes

- Define one async document-backend contract shared by local and Azure implementations.
- Register `local` and `azure` lazily under their configured names.
- Move dispatch out of the ingestion chunker without changing supported file types or emitted document metadata.
- Preserve cloud opt-in: missing credentials, missing Azure SDK dependencies, and Azure runtime failures degrade to the local backend with visible diagnostics naming the reason.
- Add contract tests for retry, fallback, optional SDK imports, metadata parity, and no event-loop blocking.

## Capabilities

### New Capabilities

- `document-backend-strategies`: Registry dispatch and fallback rules for configured local and Azure document readers.

### Modified Capabilities

- None. The async ingestion contract remains externally unchanged; this proposal makes backend selection and fallback explicit behind it.

## Impact

- Code: `core/ingestion/chunker.py`, a new document-backend registry and local adapter, `integrations/azure.py`, and `compose.py`.
- Configuration: `DOCUMENT_BACKEND` keeps `local|azure`; no default changes.
- Dependencies: Azure remains optional behind the existing `azure` extra.
- Behaviour: fallback outcomes stay local-first, but ownership and diagnostics become explicit and testable.

## Filed by

`add-pluggable-community-detection` task 4.8. The registry eligibility audit identified this behaviour-changing migration and deliberately left it out of that implementation.
