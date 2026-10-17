# Design: PDF reader setting on the Read document step

See proposal.md for the reason. Requirements are in `specs/pdf-reader/spec.md` and `specs/pipeline-graphs/spec.md`.

## Context

What exists today (evidence):

- `EffectiveSettings.pdf_reader` is a top-level field (`src/omrg/core/settings.py:291`), not part of a settings block. The composition root resolves `auto` once and bakes in a concrete name (`src/omrg/compose_settings.py:85`, `src/omrg/capabilities.py:243-276`). A configured reader that is not installed falls back to `pypdf` with a logged error.
- A reader is built per read call from `settings.pdf_reader` (`src/omrg/core/ingestion/backends/local.py:41-43`, `build_pdf_reader` in `src/omrg/integrations/pdf/factory.py:107-138`). The OCR seam wraps the reader only when the resolved reader is `pdf_inspector` and `ocr_fallback_enabled` is on.
- Graph levers are `block.field` paths (`src/omrg/core/pipelines/levers.py:147-177`). `pdf_reader` is in `_HOST_OWNED_EXACT` (`levers.py:86-104`), and the whole `ingestion.` prefix is host-owned (`levers.py:107`). A graph override of `pdf_reader` fails with `host_owned_setting` (`levers.py:131-136`).
- `read_adapter` reads with `context.settings` and does not use its parameters for reader choice (`src/omrg/core/ingestion/graph_adapters.py:192-221`). `ReadParams` holds only two chunking levers (`src/omrg/core/ingestion/graph_adapters_catalogue.py:73-87`).
- `identify_adapter` builds the source identity from its own node settings (`graph_adapters.py:155-186`). The identity records `parser.pdf_reader` and the pre-resolved `parser.text_format` (`src/omrg/core/ingestion/source_state.py:171-178`; text format from `declared_text_format(settings.pdf_reader)` in `src/omrg/core/ingestion/backends/orchestrator.py:73-89`).
- Operation availability is per operation (`src/omrg/core/pipelines/catalogue.py:238-271`). The host supplies capabilities through `HostContext` (`src/omrg/core/pipelines/validation.py:38-51`), built by `build_graph_host` on every describe, validate and run call (`src/omrg/compose_pipelines.py:162-195`, `src/omrg/engine.py:439-457`).
- Four readers are registered: `pypdf`, `pypdfium2`, `liteparse`, `pdf_inspector` (`src/omrg/integrations/pdf/registry.py:148-175`). `auto` is deliberately not in the registry (`registry.py:3-7`). In this environment `pypdfium2` is not installed (optional extra `pdf-pypdfium2`, `pyproject.toml:92-93`).
- The ingestion fingerprint hashes every parameter of each index-shaping node, nulls included (`src/omrg/core/ingestion/graph_fingerprint.py:126-141`).

### Why `pdf_reader` is host-owned

The rule came with the graph runner (commit `879145a`, change `add-local-web-pipeline-workspace`). Its design D5 says: "Runtime capabilities, provider/model identity, secrets, storage locations, and file access grants remain host-owned. A graph cannot change `.env`, construct a different provider, or silently download a model" (`openspec/changes/archive/2026-10-14-add-local-web-pipeline-workspace/design.md:125`). The lever module repeats it for reader backends (`levers.py:1-8`), and so does `docs/guides/pipelines.md` (section "Profiles and overrides").

A PDF reader is a runtime capability: its package may or may not be installed, and the composition root probes it once. The rule exists so that a graph cannot (1) change the host configuration, (2) name a reader the host has not probed, which would fail at read time or fall back silently, or (3) reach a model or worker the operator has not configured.

## Goals / Non-Goals

**Goals:**

- One Read document step can read PDF sources with a reader other than the host default.
- The host default and the host-owned rule for overrides stay as they are.
- A missing reader fails validation with a clear message, never silently at read time.
- The stored identity of a committed source names the reader that read it.

**Non-Goals:**

- No per-step OCR, LiteParse or Azure settings. They stay host-owned.
- No change to `PDF_READER`, `auto` resolution, config validation or the standard ingest path.
- No plain-English labels for reader names. The `clarify-canvas-steps` change owns step and setting labels.

## Decisions

### D1. A plain node parameter, applied by the read adapter (recommended)

`ReadParams` gains `pdf_reader`. `null` inherits. `read_adapter` reads with a copy of its settings: `context.settings.model_copy(update={"pdf_reader": params.pdf_reader})` when the value is set. `EffectiveSettings` is frozen, so the copy is the same mechanism `apply_levers` uses (`levers.py:173-177`). `pdf_reader` stays in `_HOST_OWNED_EXACT`. A graph-wide `overrides.pdf_reader` still fails with `host_owned_setting`. The message gains one hint for this path: "set the reader on the Read document step instead".

How this keeps the reason for the host-owned rule:

1. The host default does not change. `.env`, `Settings.pdf_reader` and composition-time resolution are untouched. Every inheriting step, every other pipeline and the standard ingest path keep the host reader.
2. The step can choose only a registered concrete reader that the host probe found installed (D3). Validation refuses any other value before a node runs. There is no silent fallback to `pypdf`.
3. `auto` is not a step value (D2), so the capability policy stays at the composition root.
4. The reader is built through the same registry factory. No new provider path exists. OCR routes, the worker and the local OCR tier stay governed by host settings (D5).
5. The choice is recorded: the run snapshot keeps it in `params_json` (`src/omrg/core/pipelines/admission.py:190-192`), and the source identity records the reader (D4).

**Alternative: a new lever `pdf_reader` allowed for graphs.** Rejected, for these reasons:

- Lever paths are `block.field`. `pdf_reader` is a top-level field. A lever needs either special top-level handling in `read_lever` and `apply_levers`, or a move to `ingestion.pdf_reader`. The move renames the environment variable (`PDF_READER` to `INGESTION__PDF_READER`), adds a legacy tripwire entry (CLAUDE.md gotcha 11) and touches the config used by CLI, MCP and the daemon. The `ingestion.` prefix is also host-owned as a whole.
- A lever also permits a graph-wide `overrides.pdf_reader`. That is the change the host-owned rule exists to stop.
- Lever validation lives in `core/pipelines`, which must stay independent of domain code (import contract `pipeline-runner-independent-of-domains`, `pyproject.toml:293-307`). The reader names would have to be injected anyway.
- Benefit lost by not choosing it: admission controls would show the effective value and its source. D3 covers this with `inherited_values`.

### D2. Choices come from the reader registry; `auto` is not a choice

`ReadParams.pdf_reader` accepts only `registry.available()`. The JSON schema carries these names as an `enum`, so the existing generic enum control in Studio shows them and pydantic rejects other values with `invalid_parameter` even without a host. Build the type from the registry at module import (a `Literal` built from the tuple, or an annotated `str` with a validator and a schema `enum`; pick the form `pyright` accepts). This adds a module-level import `core.ingestion.graph_adapters_catalogue -> integrations.pdf.registry`. The import contracts allow it (precedent: `src/omrg/core/ingestion/ocr_identity.py:47`), and the registry imports no adapter or optional package (`registry.py:15`). A new reader still needs only one `register()` call to appear as a step choice.

`auto` is excluded because it is a resolution policy, not a reader (`registry.py:3-7`). "Inherit" already means "use the host's resolved reader". A step-level `auto` would re-probe at read time through the factory and would record `auto`, not a concrete reader, in the source identity.

Alternative: the host supplies the choice list and the model takes any string. Rejected: the parameter schema would carry no `enum`, a run without a host would accept any string, and clients would need a second list.

### D3. Per-choice availability through the host, probed once per Engine

Keep `core/pipelines` domain-free and generic:

- `OperationDescriptor` gains `option_params: Mapping[str, str]`, a map from parameter name to a host option-set name. The model validator checks that each parameter exists, as it does for `lever_params` (`catalogue.py:112-116`). `read.document` declares `{"pdf_reader": "pdf_reader"}`.
- `HostContext` gains `options: Mapping[str, HostOptionSet]`. A `HostOptionSet` holds `inherited` (the host value) and `unavailable` (value to reason).
- `OperationCatalogue.describe` adds two fields to each operation: `unavailable_options` (`{param: {value: reason}}`) and `inherited_values` (`{param: value}`). Both are empty maps when the operation has no option parameters. `available` stays per operation.
- Preflight `check_resources` adds an issue for each enabled node whose option parameter names an unavailable value. New code `IssueCode.OPTION_UNAVAILABLE = "option_unavailable"` (`src/omrg/core/pipelines/errors.py`; codes are add-only). The message names the node, the reader and the package, and gives the fix: "Install the package and restart OMRG, or choose another reader or Inherit." Without a host (draft preflight) the check is skipped, as for capabilities.
- `capabilities.py` gains `pdf_reader_options()`. It returns, for each registered reader, `None` or a reason built from `registry.describe(name)["probe_module"]`, with the same probe as `pdf_reader_installed` (`capabilities.py:63-77`). `EnginePipelines` calls it on first use and keeps the result, so each Engine probes once. `Engine._graph_host` passes the cached options and `settings.pdf_reader` (the inherited value) to `build_graph_host`. Keep `compose_pipelines.py` (461 lines) under the 500-line ceiling.

Alternative: encode each reader as a capability string such as `pdf_reader:pypdfium2`. Rejected: capabilities make a whole operation unavailable, and the Read document step must stay available.

### D4. The identify step uses the reader of the Read document step

`IngestionShape` gains `pdf_reader: str | None`. `_Slice` in `graph_fingerprint.py` takes it from the `read.document` node in the commit node's ancestor slice. Every ingestion operation has one input of cardinality one, so the slice holds at most one read node. Without a commit node, use the only `read.document` node when there is exactly one, else `None`. `plan_run` already computes the shape once per run and passes it as resource `ingestion_shape` (`src/omrg/compose_pipeline_runs.py:61`).

`identify_adapter` applies the shape reader to its settings before `build_ingestion_context`. Then `prepare_source` resolves `parser.text_format` and `build_index_identity` records `parser.pdf_reader` from the step reader. One small helper applies a reader to settings for both adapters, so the read and the identity cannot drift.

Effect: a reader change gives a new `parser.pdf_reader`, often a new `parser.text_format`, and a new graph shape. The source reprocesses on its next explicit ingest. A rerun with the same reader reuses it.

Alternative: find the downstream read node per identify node in `plan_run` and pass a separate resource. Rejected: it repeats the slice walk that `graph_fingerprint` already does.

### D5. OCR routing and the rescue gate follow the chosen reader

- OCR routing applies only to `pdf_inspector` (`factory.py:132-137`). A step that selects `pdf_inspector` on a `pypdf` host turns routing on for that step. A step that selects another reader turns it off for that step.
- The tiered rescue for silent-empty PDFs (ADR-066: liteparse, then pypdf) and maths-page routing live on the `pdf_inspector` path only. A scanned PDF read with `pypdf` can give no text and fail with "No chunks produced". The pipelines guide must say this.
- The OCR client is the Engine's client. `plan_run` borrows it when a node's settings enable OCR fallback (`compose_pipeline_runs.py:65-67`). That decision reads host settings only. With no OCR route configured, the seam keeps partial text and reports degradation (`src/omrg/integrations/pdf/ocr_routing.py:23-28`).
- The local OCR tier can load a model only when the operator set `OCR_ROUTING_UNIT=page`; `OCR_LOCAL_OFFLINE` and the model directory stay host settings (`src/omrg/integrations/pdf/page_routing.py:182-188`). Engine routes in `config/ocr_routes.py` are untouched.
- The OCR routing payload is already in every identity (`source_state.py:186-188`), so no identity change is needed for routing.
- Decision-model rescue gate (ADR-074, CLAUDE.md gotcha 16): ADR-074 is Proposed and does not adopt the gate in production. `src/omrg` makes no `/v1/systemone` call today. No interaction now. If change `experiment-42-clef-flash-confirmation` ships the gate on the `pdf_inspector` path, a step with another reader bypasses it, and that change must state its scope per reader.

### D6. Fingerprint effect: accept one reprocess of custom ingestion graphs

The new parameter adds `"pdf_reader": null` to every `read.document` parameter dump. The canonical graph stays standard, because `_standard_fingerprint` uses the same code (`graph_fingerprint.py:178-193`) and the standard identity has no `graph_shape` block. Sources that a non-standard graph indexed get a new fingerprint and reprocess once on their next explicit ingest. This matches the shared brief's rule D5 (reprocess on next ingest, no automatic re-ingest). Studio ingestion graphs are new (archived 2026-10-14), so few sources are affected.

Alternative: drop a null `pdf_reader` from the dump. Rejected: a special case in a generic hash, and the existing scenario "Explicit parameter equals its default" relies on full dumps.

The same rule covers later edits. Changing the reader, or any other Read document setting, reprocesses each affected source once, on its next explicit ingest. A rerun with the same settings reuses the source. The fingerprint has no special case for the reader or for null values.

- Alternative: keep the identity when only the reader changes. Rejected: the stored identity would name a reader that did not read the source, and a source read with a new reader would not get its new text.
- Alternative: re-ingest automatically when a step setting changes. Rejected: `unify-profiles-and-pipelines` D5 applies Ingest changes on the next ingestion only.

### D7. Web: disable uninstalled choices; show the inherited reader

Minimal change to the generic controls, no canvas spec change (`clarify-canvas-steps` owns `pipeline-canvas`):

- `web/src/api/pipelines.ts`: add `unavailable_options` and `inherited_values` to `OperationDescriptor`.
- `web/src/studio/schema.ts`: `paramFields` adds `unavailableOptions` and `inheritedValue` to each field.
- `web/src/studio/ParamField.tsx`: `EnumSelect` renders an unavailable choice as a disabled `SelectItem` with "(not installed)" and lists each reason under the control in Step settings. `InheritNote` says "Inherit uses the host value: pdf_inspector." when an inherited value exists.
- The newest Studio code is uncommitted in the `feat-studio-canvas-layout` worktree. Implement the web tasks after it merges into `integration/core-web`.

### D8. Spec ownership

`pdf-reader`: one MODIFIED requirement (environment selection, full text kept) and one ADDED requirement. `pipeline-graphs`: ADDED requirements only, because `unify-profiles-and-pipelines` owns its MODIFIED blocks. The Studio behaviour is stated as client information in the catalogue requirement, so `pipeline-canvas` stays untouched.

### D9. Order

This change lands after `organise-backend-folders`. It cites no file that change moves. Its web tasks run after `studio-profiles-gallery`, which renames the settings section to "Step settings", and after `clarify-canvas-steps`, which edits `ParamField.tsx` too. No ADR is planned; the design and the pipelines guide record the decision.

## Risks / Trade-offs

- [The first catalogue call imports native reader packages] → The probe runs once per Engine, lazily, with the same registry probe the integrations catalogue uses (`src/omrg/transports/api/integrations_catalogue.py:52-55`).
- [A reader change reprocesses non-PDF sources too] → `parser.pdf_reader` is in every identity (`source_state.py:175`). Changing `PDF_READER` does the same today. Document it.
- [Host uses the Azure document backend] → PDFs go to Azure by the suffix gate (`src/omrg/core/ingestion/backends/registry.py:166-174`). The step reader applies only when a read falls back to the local backend. Document it.
- [A step reader without OCR or rescue on scanned PDFs] → Document it in the pipelines guide. The failure is per file and visible.
- [Registry and config accepted values drift] → A test pins the step enum to `registry.available()`.
- [Rollback] → After rollback, a saved graph with `pdf_reader` fails validation (`extra="forbid"`). The user clears the setting and saves again.

## Migration Plan

1. Before apply: `organise-backend-folders` has landed.
2. Ship the backend (catalogue fields, step parameter, identity) and the OpenAPI fields together.
3. Ship the web change after `feat-studio-canvas-layout`, `studio-profiles-gallery` and `clarify-canvas-steps` merge.
4. No data migration. Sources from custom ingestion graphs reprocess once on their next explicit ingest (D6).

## Open Questions

- Should Studio later show each reader's text format and page support beside its name (`registry.describe`)? This does not change the specs or tasks here.
