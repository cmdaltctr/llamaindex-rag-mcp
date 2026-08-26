## Context

The ingestion chunker currently branches on `DOCUMENT_BACKEND=azure`, while `integrations/azure.py` owns retries and another local fallback. Configuration also degrades Azure to local when credentials are absent. The behaviour is intentional, but dispatch and fallback ownership are split across three layers.

## Goals / Non-Goals

**Goals:**

- Define one async document-reader protocol.
- Register local and Azure implementations lazily.
- Keep the local default and current credential/runtime fallback outcomes.
- Keep optional SDK imports inside the Azure adapter.

**Non-Goals:**

- Change supported document types or chunk metadata.
- Make Azure a base dependency or default.
- Remove retry or local fallback.

## Decisions

### 1. Register concrete backends; keep fallback as orchestration

The registry maps configured names to async reader constructors or callables. Retry and fallback policy stays in an orchestrator so the registry remains a dispatch table rather than a workflow engine.

### 2. Make local reading an explicit backend

The local implementation wraps the existing PDF factory and LlamaIndex reader path. This gives `local` and `azure` one observable contract without changing parser selection within the local backend.

### 3. Preserve two failure phases

Missing credentials resolve to local at startup. Runtime Azure failures retry, then invoke the local backend. Diagnostics distinguish these cases.

### 4. Keep adapters acyclic and lazy

Azure imports its SDK only while building a client. Integration adapters receive plain settings data and do not import ingestion business logic.

### 5. Validate backend names at the composition boundary

The registry owns the accepted backend names. `config/` continues to declare `document_backend` as a plain string and must not import the runtime registry (leaf invariant). Startup validation moves to the composition boundary in `compose.py`, following the existing `community_algorithm` precedent, and replaces the hard-coded `("local", "azure")` tuple currently enforced in the settings validator. The Azure credential check stays in settings because it is graceful degradation under the cloud-opt-in boundary, not name validation.

## Risks / Trade-offs

- Metadata parity can drift between readers. Contract fixtures compare required fields.
- Moving fallback ownership can double-read documents. Tests assert one retry budget and one local fallback.
- A registry adds indirection to one branch. Startup validation and contract tests make failures earlier and clearer.
- `compose.py` sits at the 497-line ceiling. Implementation must land startup validation through a small helper extraction or a separate focused module, and must not bundle a broad refactor.

## Migration Plan

1. Lock current local and Azure output/fallback behaviour with tests.
2. Add the backend protocol and lazy registry.
3. Extract the current local path into a registered implementation.
4. Register Azure and move selection out of the chunker.
5. Verify base-only, Azure-extra, failure, and async responsiveness paths.

Rollback restores the chunker branch and keeps both existing adapters unchanged. No stored data migration is required.
