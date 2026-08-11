## Tasks

- [ ] 1. Enumerate the full accepted set for `METADATA__EXTRACTION_MODE`, including inline-dispatched values (`local`) that are absent from the metadata registry.
- [ ] 2. Add validation for `METADATA__EXTRACTION_MODE` in `MetadataSettings` or `_validate_provider_selections` that raises on unrecognised values.
- [ ] 3. Add validation for `CHUNKING__STRATEGY_FALLBACK` against the chunking registry's available names.
- [ ] 4. Update `_resolve_active_strategies` in `compose.py` to remove or document the silent `continue` for pre-validated names.
- [ ] 5. Test: `METADATA__EXTRACTION_MODE=local` is accepted (inline-dispatched, not in registry).
- [ ] 6. Test: `METADATA__EXTRACTION_MODE=typo` raises at settings resolution.
- [ ] 7. Test: `CHUNKING__STRATEGY_FALLBACK=typo` raises at settings resolution.
- [ ] 8. Update `docs/guides/configuration.md` and `docs/guides/metadata-extraction.md` with the accepted sets.
