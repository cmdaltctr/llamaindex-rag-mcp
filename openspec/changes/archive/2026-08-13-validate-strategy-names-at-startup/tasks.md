## Tasks

- [x] 1. Enumerate the full accepted set for `METADATA__EXTRACTION_MODE`, including inline-dispatched values (`local`) that are absent from the metadata registry.
- [x] 2. Add validation for `METADATA__EXTRACTION_MODE` in `MetadataSettings` or `_validate_provider_selections` that raises on unrecognised values.
- [x] 3. Add validation for `CHUNKING__STRATEGY_FALLBACK` against the chunking registry's available names **in `compose.py::_resolve_active_strategies`**, while accepting the inline `markdown` document-path fallback (not in `config/` — the config package is a leaf that cannot import `core/` registries).
- [x] 4. Update `_resolve_active_strategies` in `compose.py` to remove or document the silent `continue` for pre-validated names.
- [x] 5. Test: `METADATA__EXTRACTION_MODE=local` is accepted (inline-dispatched, not in registry).
- [x] 6. Test: `METADATA__EXTRACTION_MODE=typo` raises at settings resolution.
- [x] 7. Test: `CHUNKING__STRATEGY_FALLBACK=typo` raises at startup in `compose.py` (registry membership check, not settings resolution).
- [x] 8. Update `docs/guides/configuration.md` and `docs/guides/metadata-extraction.md` with the accepted sets.
- [x] 9. Add an import-boundary test asserting `src/rag_mcp/config/**` does not import `core/chunking/` registries (guards the architecture invariant that chunking-registry validation stays in `compose.py`).
