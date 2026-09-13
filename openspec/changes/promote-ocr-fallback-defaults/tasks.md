# Tasks: promote-ocr-fallback-defaults

## 1. Packaged defaults

- [ ] 1.1 Flip the three defaults in `src/omrg/config/__init__.py`:
  `ocr_fallback_enabled=True`,
  `ocr_fallback_min_confidence=0.5`,
  `ocr_fallback_page_fraction=0.10`.
- [ ] 1.2 Mirror the same three defaults in
  `src/omrg/core/settings.py` (EffectiveSettings model) in the same
  commit.
- [ ] 1.3 Update every test that asserts the old packaged defaults
  (`tests/test_settings_resolver.py`,
  `tests/test_ocr_routing_gate.py`,
  `tests/test_ocr_routing_seam.py`,
  `tests/test_compose.py` and any default-snapshot test found by
  `rg -n "ocr_fallback" tests/`).

## 2. Docs and records

- [ ] 2.1 Write the new ADR superseding ADR-064 items 1–2: promotion
  decision, Experiment 29 citation, the
  thresholds-ship-with-the-flag condition, and the degrade path for
  worker-less installs.
- [ ] 2.2 Correct `.env.example`: uncommented promoted values or a
  comment block naming the promoted defaults; replace the superseded
  `PAGE_FRACTION=0.5` with `0.10`.
- [ ] 2.3 Update the default-value table in
  `docs/guides/configuration.md` (`OCR_FALLBACK_ENABLED`,
  `OCR_FALLBACK_MIN_CONFIDENCE`, `OCR_FALLBACK_PAGE_FRACTION` rows) and
  grep `docs/guides/` for any remaining `0.0` default claims
  (documentation drift check).
- [ ] 2.4 Check ADR-064 status line and add a superseded-by reference
  if the house style requires it (do not rewrite its body).

## 3. Verification

- [ ] 3.1 `uv run pytest tests/test_settings_resolver.py tests/test_ocr_routing_gate.py tests/test_ocr_routing_seam.py tests/test_ocr_error_boundary.py tests/test_ocr_identity_reingestion.py -v` green.
- [ ] 3.2 `uv run pytest -m "not slow" --cov=omrg` meets coverage
  floors; no test depends on a worker being present.
- [ ] 3.3 `uv run openspec validate promote-ocr-fallback-defaults --strict` passes.
