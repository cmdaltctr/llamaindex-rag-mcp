## Why

The PDF reader and the OCR routing settings decide how OMRG reads every document. Today the Settings page shows them only read-only in the Configuration section, so the user must edit `omrg.jsonc` by hand and guess which reader and which OCR engines are installed. ADR-087 made the page a second editor of `omrg.jsonc` and said a later change can add edit rows for engine settings. This change adds those rows for document reading.

## What Changes

- Add a Settings section "Document reading" at `#/settings/document-reading`, placed before Configuration. It edits nine server-wide keys in `omrg.jsonc`: `pdf_reader`, `ocr_fallback_enabled`, `ocr_engine_primary`, `ocr_engine_fallback`, `ocr_routing_unit`, `ocr_fallback_min_confidence`, `ocr_fallback_page_fraction`, `ocr_maths_routing_enabled` and `ocr_maths_page_fraction`.
- The section shows, for each key, the value in force since launch, the saved file value, the source and the default. It shows which PDF readers and which OCR engines are installed, and says when `OCR_WORKER_COMMAND` replaces the primary engine.
- Every one of the nine keys applies only after a restart. The section says so, and offers the existing restart dialog after a save. It also says that the keys are part of the index identity, so the next ingest after the restart can read existing files again.
- A key set in the environment or `.env` is read-only, with the existing lock message.
- Add `GET /v1/settings/document-reading` (read scope) and `PUT /v1/settings/document-reading` (manage scope). The contract is in `design.md`.
- The file writer accepts the nine keys. A page write checks `pdf_reader` against the five reader names, refuses a reader that is not installed, checks an engine name against the folder-name rule, and refuses a blank text value. The startup behaviour does not change: a bad `pdf_reader` from any source still warns and falls back to `auto`.
- Fix the baseline `workspace-settings` spec, which lists seven sections. The page has eight (Configuration is missing), and this change adds the ninth.
- Add an ADR-087 addendum: these nine keys become page-editable.

Out of scope: other OCR fields (`ocr_workers_dir`, `ocr_worker_command`, timeouts, the local tier), installing or provisioning engines, new engines, per-profile OCR settings, and pipeline levers (`pdf_reader` on the Read document step stays host-owned in `core/pipelines/levers.py`). "No fallback engine" is deferred (see design D8).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-settings`: the section list gains Configuration (a baseline fix) and Document reading. New requirements cover the Document reading section and its HTTP routes.
- `settings-file`: the page may write the nine document-reading keys, with write-time value checks that leave the startup behaviour unchanged.

## Impact

- Backend: `src/omrg/config/rules.py`, `src/omrg/config/settings_file_write.py`, `src/omrg/config/__init__.py` (one shared constant, no behaviour change), `src/omrg/capabilities.py` (an OCR engine probe), a new route module under `src/omrg/transports/api/routes/`, `src/omrg/transports/api/app.py`, `src/omrg/transports/api/openapi.yaml`, tests under `tests/`.
- Web: `web/src/settings/`, `web/src/api/settings*.ts`, `web/src/api/queries.ts`, `web/src/lib/routes.ts` and its test.
- Docs: `docs/guides/configuration.md`, `docs/guides/web-workspace.md` (Settings part), `docs/adr/087-settings-live-in-omrg-jsonc.md` (addendum).
- No new dependency. No change to ingestion, the OCR routes, the index identity payload or the startup resolution of any setting.
- The tripwire counts in `tests/test_clean_base_tripwire.py` change. The integrator re-measures them once after both groups merge.
