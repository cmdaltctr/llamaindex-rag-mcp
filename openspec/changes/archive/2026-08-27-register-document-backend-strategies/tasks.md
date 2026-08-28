## 1. Baseline Contracts

- [x] 1.1 Add fixtures that pin local and Azure document output metadata and supported file types.
- [x] 1.2 Add retry, missing-credential, missing-SDK, and runtime-fallback tests.
- [x] 1.3 Add async responsiveness tests for both backends.

## 2. Backend Registry

> `src/rag_mcp/compose.py` is at the 497-line file ceiling. Tasks 2.1 and 2.4 that add code there must use a small helper extraction or a separate focused module.

- [x] 2.1 Define the shared async document-backend protocol and lazy registry.
- [x] 2.2 Extract the current local reader chain into a registered `local` implementation.
- [x] 2.3 Adapt and register the existing Azure path without eager SDK imports.
- [x] 2.4 Validate configured backend names at startup at the composition boundary, replacing the hard-coded `("local", "azure")` tuple in `config/`, listing registered names on failure. `config/` must not import the runtime registry.

## 3. Dispatch and Fallback

- [x] 3.1 Replace the ingestion chunker's inline backend branch with registry dispatch.
- [x] 3.2 Centralise Azure retry and local fallback ownership without double-reading.
- [x] 3.3 Preserve local-first credential degradation and diagnostics.

## 4. Verification and Documentation

- [x] 4.1 Run local-only, Azure-extra, failure, metadata-parity, and responsiveness tests.
- [x] 4.2 Extend import contracts for the new registry and acyclic adapters.
- [x] 4.3 Document backend names, optional installation, retries, and fallback behaviour.
- [x] 4.4 Run strict OpenSpec validation, targeted tests, Ruff, Pyright, and import-linter.
