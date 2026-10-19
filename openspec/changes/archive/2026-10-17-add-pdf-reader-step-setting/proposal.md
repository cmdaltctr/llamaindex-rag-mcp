# Proposal: PDF reader setting on the Read document step

## Why

A user profile is a set of pipelines (see `unify-profiles-and-pipelines`). Today every pipeline reads PDF files with the one reader the host chose in `PDF_READER`. A graph cannot change it: `pdf_reader` is a host-owned setting (`src/omrg/core/pipelines/levers.py:86-104`), and the `read.document` adapter ignores its parameters for reader choice (`src/omrg/core/ingestion/graph_adapters.py:192-215`). So two profiles cannot read PDFs differently, for example `pdf_inspector` Markdown for papers and `pypdf` for plain forms.

## What Changes

- Add a `pdf_reader` setting to the "Read document" step (`read.document`). Empty (`null`) means "inherit the host reader". The choices are the registered concrete readers (`pypdf`, `pypdfium2`, `liteparse`, `pdf_inspector`). `auto` is not a choice.
- The step reads PDF files with the chosen reader through the existing reader factory. The host default (`PDF_READER`, `.env`, composition-time resolution) does not change.
- A graph-wide override of `pdf_reader` stays refused (`host_owned_setting`). The message now tells the user to set the reader on the Read document step instead.
- The host probes each registered reader once per Engine. The operation catalogue reports, per step setting, which choices are not installed and why, and which value the step inherits.
- Validation refuses a step that names an uninstalled reader, with a new issue code `option_unavailable`. No node runs.
- The identify step computes the source identity with the reader that the Read document step uses. A reader change makes the source reprocess on its next ingest, and the stored identity names the correct reader.
- Studio shows uninstalled readers as disabled choices with the reason, and shows the inherited host reader.
- Documentation: `docs/guides/configuration.md` (PDF reading) and `docs/guides/pipelines.md` (catalogue, settings, validation errors). OpenAPI: two new catalogue fields.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `pdf-reader`: the environment value becomes the host default, and a pipeline step may choose another installed concrete reader for that step only. Reader installation is reported per reader.
- `pipeline-graphs`: ADDED requirements only (another change owns MODIFIED blocks here). The Read document step selects its reader, the ingestion identity records that reader, and the catalogue reports unavailable choices per step setting.

## Impact

- Python: `core/ingestion/graph_adapters_catalogue.py` (step parameter), `core/ingestion/graph_adapters.py` (read and identify adapters), `core/ingestion/graph_fingerprint.py` (reader carried with the ingestion shape), `core/pipelines/catalogue.py`, `core/pipelines/validation.py`, `core/pipelines/errors.py`, `core/pipelines/levers.py` (message only), `compose_pipelines.py`, `capabilities.py`.
- HTTP API: `GET` catalogue responses gain `unavailable_options` and `inherited_values` (`transports/api/openapi.yaml`, `OperationDescriptor`).
- Web: `web/src/api/pipelines.ts`, `web/src/studio/schema.ts`, `web/src/studio/ParamField.tsx`, catalogue test fixtures. The newest Studio code is in the `feat-studio-canvas-layout` worktree and merges first. The web tasks also wait for `studio-profiles-gallery` and `clarify-canvas-steps`, which edit the same files.
- Order: this change lands after `organise-backend-folders`. It cites no path that change moves.
- Data: sources that a custom (non-standard) ingestion graph indexed reprocess once on their next explicit ingest, because the Read document step has a new parameter. A later change of the reader or another step setting also reprocesses each source once on its next ingest. The fingerprint has no special case for it. The standard ingest path and the canonical ingestion template keep their identity.
- No new dependency. No change to `.env` handling, OCR routing settings or the decision-model gate.
