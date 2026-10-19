# Tasks

Test rule: every Python test keeps the host reader at `pypdf` (CLAUDE.md gotcha 6). Use the `effective_settings(...)` conftest factory, which sets `pdf_reader="pypdf"` and turns OCR fallback off where the existing ingestion tests do. Write each failing test first, run it, and confirm it fails for the expected reason.

## 1. Per-setting choices in the operation catalogue (`core/pipelines`)

- [x] 1.1 Write failing tests in `tests/unit/test_pipeline_catalogue.py`: `option_params` that names a missing parameter raises `ValueError`; `describe` reports `unavailable_options` and `inherited_values` from host options; an operation without option parameters reports two empty maps; the operation stays `available`. Run them and confirm they fail.
- [x] 1.2 Add `option_params` to `OperationDescriptor` with the parameter check and include it in `to_schema`. Verify the 1.1 descriptor test passes.
- [x] 1.3 Add `HostOptionSet` (`inherited`, `unavailable`) and `HostContext.options`. Extend `OperationCatalogue.describe` to accept the options and emit the two maps. Verify all 1.1 tests pass.
- [x] 1.4 Write failing tests in `tests/unit/test_pipeline_preflight.py`: a node value in the unavailable set gives `option_unavailable` with the node id and a message that names the value and the reason; `null` gives no issue; preflight without a host gives no issue. Run them and confirm they fail.
- [x] 1.5 Add `IssueCode.OPTION_UNAVAILABLE = "option_unavailable"` and the check in `check_resources`. Verify the 1.4 tests pass.
- [x] 1.6 Add a failing case to `test_graph_overrides_outside_allowed_levers`: `overrides.pdf_reader` gives `host_owned_setting` and the message names the Read document step. Add the hint to `lever_error` for `pdf_reader` only. Verify the test passes.
- [x] 1.7 Add the `option_unavailable` row to the validation errors table in `docs/guides/pipelines.md`. Verify `uv run pytest tests/unit/test_pipeline_guide.py -q` passes (`test_guide_lists_every_issue_code` fails before this step).

## 2. Reader setting on the Read document step

- [x] 2.1 Write failing tests in `tests/unit/test_ingestion_graph_adapters.py` (or a new `tests/unit/test_ingestion_graph_pdf_reader.py` if the file passes 450 lines): the `pdf_reader` schema `enum` equals `registry.available()`; `auto` and an unknown name fail validation; the default is `null`; `read.document` declares `option_params={"pdf_reader": "pdf_reader"}`; `read_adapter` passes settings with the step reader to `read_document`; with `null` it passes the host reader. Capture the settings with a monkeypatched `read_document`. Confirm the tests fail.
- [x] 2.2 Add `pdf_reader` to `ReadParams`, built from `integrations.pdf.registry.available()`, and declare `option_params` on `READ`. Verify the schema tests pass and `npx --yes pyright@1.1.412 src/omrg/core/ingestion` reports no new finding.
- [x] 2.3 Add one helper that returns settings with a given reader (unchanged when `None`). Use it in `read_adapter`. Verify the 2.1 adapter tests pass.
- [x] 2.4 Add a `pdf_reader` case to `test_shaping_changes_change_the_shape` in `tests/unit/test_ingestion_graph_fingerprint.py`. Verify it passes and `test_canonical_graph_has_the_standard_shape` and `tests/unit/test_pipeline_templates_parity.py` still pass.
- [x] 2.5 Run `uv run lint-imports` and verify all contracts pass with the new `graph_adapters_catalogue -> integrations.pdf.registry` import.
- [x] 2.6 Document the step setting in `docs/guides/pipelines.md`: inherit, choices, no `auto`, the two new catalogue fields, OCR routing and the silent-empty rescue only on `pdf_inspector`, the Azure backend note, and reprocessing after a change. Verify `uv run pytest tests/unit/test_pipeline_guide.py -q` passes.

## 3. Identity records the step reader

- [x] 3.1 Write failing tests in `tests/unit/test_ingestion_graph_fingerprint.py`: `IngestionShape.pdf_reader` equals the value of the read node in the commit slice; it is `None` when the node inherits; a read node outside the commit slice does not set it. Confirm they fail.
- [x] 3.2 Add `pdf_reader` to `IngestionShape` and collect it in `_Slice`. Verify the 3.1 tests pass.
- [x] 3.3 Write a failing test for `identify_adapter` with `tests/fixtures/smoke_text.pdf`: with a shape reader `pdf_inspector` and host reader `pypdf`, the identity equals `build_index_identity` computed with `pdf_inspector` and text format `markdown`, and differs from the host-reader identity. Confirm it fails.
- [x] 3.4 Write a failing end-to-end test in `tests/unit/test_ingestion_graph_fingerprint_reuse.py`: ingest `smoke_text.pdf` through the canonical graph (status `indexed`), run again (`unchanged`), set the read node `pdf_reader` to `pdf_inspector` (`indexed` again; stored chunks carry `pdf_reader == "pdf_inspector"`; the stored source identity equals the `pdf_inspector` identity), run again (`unchanged`). Confirm it fails on the identity assertion.
- [x] 3.5 Apply the shape reader in `identify_adapter` with the 2.3 helper before `build_ingestion_context`. Verify 3.3 and 3.4 pass.
- [x] 3.6 Verify `test_standard_identity_digest_is_unchanged` and `tests/unit/test_pipeline_templates_parity.py` pass unchanged.

## 4. Host probe and Engine wiring

- [x] 4.1 Write failing tests in `tests/unit/test_engine_pipelines.py` (305 lines; use a new `tests/unit/test_engine_pipelines_reader_options.py` if it would pass 450 lines): with `registry.probe` monkeypatched to fail for `pypdfium2`, `Engine.describe_operations()` keeps `read.document` available, lists `pypdfium2` under `unavailable_options.pdf_reader` with a reason that names the package, and reports `inherited_values.pdf_reader == "pypdf"`; two catalogue calls and one validation probe each reader once; validating a graph whose read node selects `pypdfium2` raises `PipelineValidationError` with `option_unavailable`. Confirm they fail.
- [x] 4.2 Add `pdf_reader_options()` to `capabilities.py` beside `pdf_reader_installed`, with the same registry probe. Verify its unit test passes.
- [x] 4.3 Cache the options in `EnginePipelines` on first use. Pass them and `settings.pdf_reader` through `Engine._graph_host` and `build_graph_host` into `HostContext.options`. Pass the options to `describe`. Verify the 4.1 tests pass and `uv run pytest tests/test_file_size_ceiling.py -q` passes.
- [x] 4.4 Update the "PDF reading" section of `docs/guides/configuration.md`: `PDF_READER` is the host default; a Read document step may choose another installed reader; an uninstalled choice fails validation; `auto` is host-only. Search `docs/guides/` for text that says a graph cannot choose a reader, and correct it. Verify the reader table guard test passes (`uv run pytest tests/test_page_provenance.py -q`).

## 5. HTTP API contract

- [x] 5.1 Add required `unavailable_options` (object of objects of strings) and `inherited_values` (object) to `OperationDescriptor` in `src/omrg/transports/api/openapi.yaml`. Verify `uv run pytest tests/unit/test_web_openapi_conformance.py tests/unit/test_web_openapi_conformance_runs.py tests/test_openapi_conformance.py -q` passes, and that it failed before the schema edit.

## 6. Studio (after `feat-studio-canvas-layout` merges)

- [x] 6.1 Confirm that `feat-studio-canvas-layout`, `studio-profiles-gallery` and `clarify-canvas-steps` are merged into `integration/core-web`. Work in a feature worktree from that branch. Verify with `git log --oneline -1 -- web/src/studio/CanvasPanel.tsx` and that `web/src/studio/panelSections.ts` holds the title "Step settings".
- [x] 6.2 Recapture the `read.document` entry and the two new fields in `web/src/studio/test/catalogueOne.ts` / `catalogueTwo.ts` from `build_operation_catalogue().describe(...)`. Add both fields to `OperationDescriptor` in `web/src/api/pipelines.ts`. Verify `npm test -- schema` passes.
- [x] 6.3 Write a failing test in `web/src/studio/schema.test.ts`: `paramFields` reads `pdf_reader` as a nullable enum with `unavailableOptions` and `inheritedValue`. Implement it in `schema.ts`. Verify the test passes.
- [x] 6.4 Write a failing test in `web/src/studio/CanvasEditor.settings.test.tsx`: in Step settings for the Read document step, `pypdfium2` is disabled with "(not installed)" and its reason is shown; choosing `liteparse` writes `pdf_reader: "liteparse"` to the draft; Inherit shows "Inherit uses the host value: pdf_inspector." Confirm it fails.
- [x] 6.5 Implement the disabled choice and the inherit note in `ParamField.tsx`. Verify the 6.4 test passes, and `npm run typecheck` and `npm run lint` pass.

## 7. Final verification

- [x] 7.1 Run the targeted Python tests: `uv run pytest tests/unit/test_pipeline_catalogue.py tests/unit/test_pipeline_preflight.py tests/unit/test_ingestion_graph_adapters.py tests/unit/test_ingestion_graph_fingerprint.py tests/unit/test_ingestion_graph_fingerprint_reuse.py tests/unit/test_engine_pipelines.py tests/unit/test_pipeline_guide.py -q`. Verify all pass.
- [x] 7.2 Run `uv run pytest -n auto -m "not slow" tests/unit -q` and `uv run lint-imports`. Verify both pass.
- [x] 7.3 Run `npm test`, `npm run typecheck` and `npm run lint` in `web/`. Verify all pass.
- [x] 7.4 Run `openspec validate add-pdf-reader-step-setting --strict`. Verify it passes.
