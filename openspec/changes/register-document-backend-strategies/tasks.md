## 1. Baseline Contracts

- [ ] 1.1 Add fixtures that pin local and Azure document output metadata and supported file types.
- [ ] 1.2 Add retry, missing-credential, missing-SDK, and runtime-fallback tests.
- [ ] 1.3 Add async responsiveness tests for both backends.

## 2. Backend Registry

> `src/rag_mcp/compose.py` is at the 498-line file ceiling. Tasks 2.1 and 2.4 that add code there must use a small helper extraction or a separate focused module.

- [ ] 2.1 Define the shared async document-backend protocol and lazy registry.
- [ ] 2.2 Extract the current local reader chain into a registered `local` implementation.
- [ ] 2.3 Adapt and register the existing Azure path without eager SDK imports.
- [ ] 2.4 Validate configured backend names at startup at the composition boundary, replacing the hard-coded `("local", "azure")` tuple in `config/`, listing registered names on failure. `config/` must not import the runtime registry.

## 3. Dispatch and Fallback

- [ ] 3.1 Replace the ingestion chunker's inline backend branch with registry dispatch.
- [ ] 3.2 Centralise Azure retry and local fallback ownership without double-reading.
- [ ] 3.3 Preserve local-first credential degradation and diagnostics.

## 4. Verification and Documentation

- [ ] 4.1 Run local-only, Azure-extra, failure, metadata-parity, and responsiveness tests.
- [ ] 4.2 Extend import contracts for the new registry and acyclic adapters.
- [ ] 4.3 Document backend names, optional installation, retries, and fallback behaviour.
- [ ] 4.4 Run strict OpenSpec validation, targeted tests, Ruff, Pyright, and import-linter.
