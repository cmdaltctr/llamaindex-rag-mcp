# Tasks: Pin google-magika as the base content-type detector

## 1. Failing tests first

- [ ] 1.1 Write a failing test: in the current environment `_is_magika_available()` is False (no binary) — the new "standard install detects by content" test asserts a Magika-modelled label for a probe file and FAILS before the dependency lands.
- [ ] 1.2 Write a test asserting the smoke tool cannot import `ingest_path_async` (mechanical no-re-ingest constraint) and that running it over fixture paths produces a label comparison without any store/embedding call.

## 2. Dependency and tooling

- [ ] 2.1 `uv add google-magika` (pin); confirm `.venv/bin/magika` resolves via `shutil.which` under `uv run`.
- [ ] 2.2 Add `scripts/magika_label_smoke.py`: suffix-map vs Magika label comparison over supplied paths, detection only, would-change report; no ingestion imports.
- [ ] 2.3 Update `tests/test_dependency_floors.py` if the new package needs a floor entry (gotcha #13).

## 3. Verification (smoke only — NO re-ingest)

- [ ] 3.1 Run the smoke tool over the operator's real corpus paths ( Zotero-backed experiment corpora acceptable) and record the would-change count in the ADR; if common types mismatch the suffix map, stop and report before proceeding.
- [ ] 3.2 Run the fast suite and `scripts/local_ci.sh`; re-baseline the base-suite tripwire counts for the new tests.
- [ ] 3.3 Write the ADR (`s-adr`): new base dependency, onnxruntime basis, startup cost, taxonomy-stability revisit trigger; cross-reference TDR-025 (amended) and this change.
- [ ] 3.4 Confirm no collection was ingested, embedded, or modified during the change (git status plus store directories untouched).
