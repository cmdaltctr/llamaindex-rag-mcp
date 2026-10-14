# Proposal

## Why

The web workspace built in `add-local-web-pipeline-workspace` works but presents itself badly. The navigation is feature-shaped (seven items including two retrieval views), the landing view is an empty pipeline canvas, API failures print parser text into the page, and no icons, badges, or elevation exist anywhere. The visual target is OpenChamber's warm neutral system (already adapted into `web/src/styles/tokens.css`) plus its component treatment, which the current app never received.

The owner wants a job-shaped workspace: open a project, chat with its knowledge base, manage its sources, build pipelines in a studio, and organise experiments in folders.

## What Changes

- **Navigation becomes seven items**: Home, Chat, Knowledge Base, Studio, Experiments, Integrations, Settings. Search and Ask merge into Chat. Runs merges into Experiments. Canvas becomes Studio. The landing view becomes Home.
- **Home** lists projects. A project is a collection. Each project card shows name, profile, document and chunk counts. Opening a project shows its library: sources, uploads, folder ingest, profile and deletion.
- **Chat** replaces Search and Ask. A centred transcript with a composer; the right panel selects the knowledge base (collection). Each assistant turn calls `answerCollection` and renders the answer, citations, verification status and evidence. No chat framework dependency; built from scratch.
- **Knowledge Base** manages the active project's sources: file upload (managed upload plus ingest job), folder ingest from approved roots, source table with orphan status.
- **Studio** replaces Pipeline. A gallery of engine templates and profile presets (documents, codebase); "New pipeline" and saved pipelines open a full-width canvas sub-page with the operation palette on the right and node settings on selection.
- **Experiments** groups experiment contexts under named main folders (directories below the approved experiment root), lists sub-experiments, loads marimo through the existing plugin approval, and carries the pipeline runs list.
- **Small backend additions**: create and list experiment folders below approved roots (because `core/experiments` requires the workspace directory to exist before registration), and a `GET /v1/integrations` catalogue with availability from the existing runtime probes.
- **Integrations** lists the installable integration extras (chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web) with availability status, purpose and the exact install command. The page never installs packages; it shows the command to copy.
- **Presentation pass**: OpenChamber-grade controls through the Tailwind v4 + shadcn-style primitives added by `add-web-ui-stack` (applied first), lucide-react icons, tinted badges for status/profile/kind labels, friendly error and empty states with one action, a `/v1` dev proxy in Vite, elevation for floating chrome, and removal of the global Inspector toggle (contextual panels instead).
- **Small backend addition**: create and list experiment folders below approved roots, because `core/experiments` requires the workspace directory to exist before registration.

## Capabilities

### New Capabilities

- `workspace-projects`: Home project list and the per-project library (sources, upload, folder ingest, profile, deletion).
- `workspace-chat`: chat transcript over `answerCollection` with knowledge base selection, citations, evidence and failure handling.
- `workspace-studio`: studio gallery (templates, profile presets, saved pipelines) and the full-width canvas sub-page layout.
- `workspace-experiments`: experiment folders, sub-experiments, marimo notebook loading, and the merged runs list.
- `workspace-integrations`: the integrations page listing installable extras with availability and install commands.
- `workspace-presentation`: navigation structure, friendly errors, icons, badges, elevation, and contextual detail panels.

### Modified Capabilities

- `web-ui-stack`: removes the requirement "No view changes in this change", which described the stack change only.

Otherwise none at the main-spec level. `local-web-workspace`, `pipeline-canvas` and `notebook-plugins` exist only in the unarchived `add-local-web-pipeline-workspace` change, so strict validation has no baseline for them; this change writes ADDED deltas and merges them into those capabilities at archive time if the prior change lands first.

## Impact

- **Frontend**: `web/src/` restructured around the seven views; new `home/`, `chat/`, `knowledge-base/`, `studio/` directories; `views.ts` and `App.tsx` rewritten; legacy rules retire from `legacy.css` as views migrate; existing canvas, runs, experiments, library components reused where possible.
- **Backend**: `src/omrg/transports/api/routes_experiments.py` gains folder create/list endpoints; `core/experiments` gains directory creation with path validation. A new integrations route exposes the extras catalogue with availability from the existing probes. OpenAPI contract updated.
- **Dependencies**: none added by this change. The UI stack (Tailwind v4, shadcn-style primitives, Radix, lucide-react) comes from `add-web-ui-stack`, which applies first.
- **Docs**: `docs/guides/` web references updated; omms-design visual matrix used for verification.
- **Tests**: new view tests following the existing vitest patterns; backend tests for folder endpoints.
