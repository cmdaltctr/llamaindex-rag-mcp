# Proposal

## Why

The web workspace built in `add-local-web-pipeline-workspace` works but presents itself badly. The navigation is feature-shaped (seven items including two retrieval views), the landing view is an empty pipeline canvas, API failures print parser text into the page, and no icons, badges, or elevation exist anywhere. The visual target is OpenChamber's warm neutral system (already adapted into `web/src/styles/tokens.css`) plus its component treatment, which the current app never received.

The foundation under the views is also weak. Location is stored in three places, request handling is copied across five modules, errors reach the UI as strings, each view fetches collections on its own and never refreshes them, and 1,413 lines of hand-written CSS sit beside the new primitives. The app is pre-release, so this change replaces these parts instead of patching them.

The owner wants a job-shaped workspace: open a project, chat with its knowledge base, manage and search its sources, build pipelines in a studio, and organise experiments in folders.

## What Changes

- **Foundation first**: a typed route model where the URL is the only source of location; one API client with typed errors and one friendly-error mapper; one query cache (`@tanstack/react-query`) shared by every view with explicit invalidation; browser storage limited to preferences and canvas drafts. The four duplicate request helpers, `useLoad`, string errors, `fetchImpl` prop threading and the `omrg-workspace-ui` and `omrg-canvas-session` keys are removed.
- **Navigation becomes seven areas**: Home, Chat, Knowledge Base, Studio, Experiments, Integrations, Settings, with Home as the landing view. Ask merges into Chat, search moves into Knowledge Base, Runs merges into Experiments, Canvas becomes Studio. Unknown hashes open Home; routes from before this change are not redirected.
- **Home** lists projects. A project is a collection. Each project card shows name, profile, document and chunk counts and opens that project's Knowledge Base.
- **Chat** replaces Ask. A centred transcript with a composer; the right panel selects the knowledge base (collection), which is part of the route. Each assistant turn calls `answerCollection` and renders the answer, citations, verification status and evidence. No chat framework dependency; built from scratch.
- **Knowledge Base** manages and searches the active project: file upload (managed upload plus ingest job), folder ingest from approved roots, source table with orphan status, profile and deletion, and metadata-filtered search with ranked, score-kind-labelled results.
- **Studio** replaces Canvas. A gallery of engine templates, profile presets (documents, codebase) and saved pipelines; creating from a card creates the pipeline on the server and opens its full-width canvas sub-page with the operation palette on the right and node settings on selection.
- **Experiments** groups experiment contexts under named main folders (directories below the approved experiment root), lists sub-experiments, loads marimo through the existing plugin approval, and carries the pipeline runs list with run detail on its own route.
- **Integrations** lists the installable integration extras (chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web) and magika with availability status, purpose and the exact install command. The page never installs packages; it shows the command to copy.
- **Settings** has Appearance, Connections, MCP, Server log, Runtime and Workspace sections. Connections shows each LLM provider (Ollama, llama.cpp, OpenRouter) with its URLs, models, whether a key is set, the roles that use it, and a Test button; it does not edit settings. Server log streams the server's recent log lines, redacted, in a terminal-style panel. MCP shows the stdio client configuration and an on/off switch for MCP over HTTP, which `add-mcp-http-transport` provides.
- **Presentation**: every view is rebuilt on the `add-web-ui-stack` primitives and Tailwind utilities, with lucide-react icons, tinted badges for status/profile/kind labels, a top-bar theme `Select` plus a one-click light/dark icon button, friendly error and empty states with one action, elevation for floating chrome, and contextual detail regions instead of the global Inspector. All hand-written stylesheets, the `legacy` cascade layer and the `.type-*` classes are deleted, and Tailwind's preflight is loaded.
- **Backend additions**: create and list experiment folders below approved roots (because `core/experiments` requires the workspace directory to exist before registration), a `GET /v1/integrations` catalogue with availability from the existing runtime probes, `GET /v1/connections` with a per-provider connection test, and `GET /v1/logs` with an event stream over an in-memory, redacted log buffer.

## Capabilities

### New Capabilities

- `workspace-projects`: Home project list and the per-project Knowledge Base (sources, upload, folder ingest, profile, deletion, search).
- `workspace-chat`: chat transcript over `answerCollection` with knowledge base selection, citations, evidence and failure handling.
- `workspace-studio`: studio gallery (templates, profile presets, saved pipelines) and the full-width canvas sub-page layout.
- `workspace-experiments`: experiment folders, sub-experiments, marimo notebook loading, and the merged runs list.
- `workspace-integrations`: the integrations page listing installable extras with availability and install commands.
- `workspace-settings`: the Settings sections, read-only provider connections with a connection test, the live server log, and MCP access.
- `workspace-presentation`: navigation and routes, shared workspace data, friendly errors, icons, badges, elevation, and contextual detail regions.

### Modified Capabilities

- `web-ui-stack`: two requirements are replaced under new names, "Tailwind builds with preflight and the token bridge" and "Only two stylesheets exist, loaded through one layered entry" (no `legacy` layer; only `tokens.css` and `app.css`); "Legacy class names never collide with utilities" and "No view changes in this change" are removed.
- `pipeline-canvas`: "Application navigation preserves working state" no longer lists the views; `workspace-presentation` owns the navigation structure.

`local-web-workspace`, `notebook-plugins`, `pipeline-graphs` and `pipeline-run-records` are main specs and stay unchanged; the new views meet them as written, and the Knowledge Base keeps metadata-filtered search.

## Impact

- **Frontend**: `web/src/` restructured around the seven areas; new `lib/routes.ts`, `lib/storage.ts`, `lib/errors.ts`, `api/queries.ts`; new `home/`, `chat/`, `knowledge-base/`, `studio/`, `integrations/` directories; `App.tsx`, `views.ts`, `api/client.ts` and `preferences.ts` rewritten; `useLoad.ts`, `components/Inspector.tsx` and every hand-written stylesheet except `tokens.css` and `app.css` deleted. Moved components keep their behaviour and tests and are rebuilt on primitives.
- **Backend**: `src/omrg/transports/api/routes_experiments.py` gains folder create/list endpoints; `core/experiments` gains directory creation with path validation. A new integrations route exposes the extras catalogue with availability from the existing probes. New connections and logs routes, `compose.connection_summary()`, and a ring-buffer log handler installed by `omrg web`. OpenAPI contract updated.
- **Dependencies**: one direct frontend dependency, `@tanstack/react-query` (MIT), pinned exactly; approved by the owner on 14 October 2026. Everything else comes from `add-web-ui-stack`.
- **Docs**: `docs/guides/` web references updated; the `omrg-design` skill updated for the no-legacy styling rule and the new foundation.
- **Tests**: new view tests following the existing Vitest patterns with a fresh `QueryClient` per test; route round-trip, storage and error-mapper unit tests; stylesheet guard tests updated; backend tests for the folder and integrations endpoints.
- **Out of scope**: re-indexing stored rows without a `source_id`, which is a separate backend change. Editing provider settings from the web app (`add-runtime-settings`) and serving MCP over HTTP (`add-mcp-http-transport`) are separate changes; the Settings MCP switch waits for the second.
