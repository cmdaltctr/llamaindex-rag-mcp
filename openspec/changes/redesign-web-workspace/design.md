# Design

## Context

The existing web app (`web/src/`) is a React 19 + Vite SPA. `add-web-ui-stack` added Tailwind v4, the token bridge over `web/src/styles/tokens.css` (adapted from OpenChamber revision `02306f32e4d191e4840440cbafa643ae899471c2`), and the primitives in `web/src/components/ui/`. The views (canvas with React Flow, library, search, ask, runs, experiments, settings) still use hand-written CSS loaded into the `legacy` cascade layer. The FastAPI transport under `src/omrg/transports/api/` exposes `/v1` operations: collections/documents/search/answer, uploads, ingest jobs, pipelines and templates, runs with SSE, experiment contexts, notebook plugins.

A read of the current code (October 2026) found these foundation problems, which the redesign fixes before it builds views:

- Location lives in three places: the URL hash, `view` in `omrg-workspace-ui` (`lib/preferences.ts`), and `pipelineId` in `omrg-canvas-session` (`canvas/storage.ts`). `viewFromHash` parses only flat `#/<view>`.
- `omrg-canvas-session` caches the full submitted run document, although `GET /v1/runs?pipeline_id=&limit=` returns it from the server.
- Request handling is copied five times: `getJson` in `api/client.ts` and separate `sendJson`/`postJson`/`isJson` helpers in `api/documents.ts`, `api/experiments.ts`, `api/pipelines.ts` and `api/runs.ts`.
- `views/shared/useLoad.ts` turns every failure into a string through `messageOf`, so the typed `ApiError` (`kind`, `status`) never reaches the UI.
- Ask, Library and Search each fetch `listCollections` on their own; nothing is shared or refreshed after an ingest or deletion.
- `fetchImpl` is threaded through component props 132 times in 28 files, only so tests can inject a fixture server.
- `lib/views.ts` holds placeholder copy ("not available yet … when the local server is connected").

OpenChamber's component layer (studied in `packages/ui/src`): flat tinted buttons (`color-mix` primary 10/16/22% light, 16/22/30% dark, saturated border and text, lowercase, h-9 default, squircle-capable 10px radius, 3px focus ring), elevated cards with `shadow-none`, chip variant for selection distinct from primary, semantic typography, chat as a centred `min(100%, 48rem)` column with a docked composer. Its chat implementation is far too large to copy (`ChatInput.tsx` alone is 208 KB); we take the visual structure only. The distilled palette, typography, geometry, interaction states, badge convention and chat skeleton live in `references/openchamber-design.md`, with the two source theme JSONs beside it.

## Goals and Non-Goals

Goals: one correct foundation (typed routes, one API client, typed errors, shared server state, minimal browser storage); job-shaped navigation; chat over the answer API with citations; project-scoped knowledge base with search; studio gallery with wide canvas; experiment folders; integrations catalogue; OpenChamber-grade presentation built only on primitives and utilities; no legacy code, CSS, routes or stored-state shims left at the end.

Non-goals: multi-turn conversational memory in the Engine (each chat turn answers independently; follow-up context needs an Engine change and is deferred); streaming chat tokens; mobile app; new pipeline semantics; the deferred Quick/Standard/Full optimiser; re-indexing stored rows that have no `source_id` (a data migration, planned as a separate backend change; until then the source table keeps the path-keyed row handling that `orphaned-source-visibility` requires).

## Decisions

### D1. A project is a collection

`GET /v1/collections` already returns name, document count, chunk count and stored profile. Home renders these as project cards. No new backend entity, no migration. Creating a project happens through the first ingest (the Knowledge Base upload panel names the target collection). The active project is the collection segment of the route (D9); the last-used collection is remembered only as a navigation default (D12).

### D2. Chat is sequential Q&A, from scratch

Each turn posts `POST /v1/collections/{collection}/answer` (query limit 4096) and renders the returned answer, citations, verification status and evidence rows. The transcript is presentation only; turns do not see each other. "New chat" clears it. Rationale: the answer pipeline is single-shot; bolting on server-side conversation state would be a new subsystem for unclear gain. UI structure follows OpenChamber: centred `min(100%, 48rem)` transcript column, composer docked at the bottom, citations as chips under each answer, evidence in a collapsible section that reuses the chunk viewer. Answers are mutations (D11), not cached queries. No chat framework: a message list plus composer is roughly 200 lines.

### D3. Studio is a shell change, not a pipeline change

Graph semantics, revisions, validation and runs stay as specified in `pipeline-graphs`, `pipeline-canvas` and `pipeline-run-records`. Studio adds a gallery landing (`GET /v1/pipeline-templates`, profile presets, saved pipelines from `GET /v1/pipelines`) and the sub-page route `#/studio/<pipeline-id>`, where the canvas takes the full main area, the palette moves to the right column, and node settings open on selection. Creating from any gallery card calls `createPipeline` (title only, no revision) and opens the new pipeline's route with the draft seeded from the card, so every canvas has a server identity and no "unsaved new pipeline" state exists. Profile presets ("documents", "codebase") seed the search template with the profile's retrieval defaults (rerank on for documents, off for codebase) and the target collection pre-filled.

### D4. Experiment folders need one backend addition

`core/experiments/contexts.py` raises `ExperimentPathError("not_found")` when the workspace directory does not exist, so the UI cannot create folders today. Add `POST /v1/experiment-folders` (session `manage` scope; validated relative path, no `..`, below an approved root, depth limit) and include the directory tree in the experiments listing. The web groups contexts under their parent directory; a main folder with no contexts still shows. Registration, credentials, trust notices and marimo plugin approval flow through the existing endpoints unchanged.

### D5. Icons come from lucide-react via the UI stack

`add-web-ui-stack` installs `lucide-react`. Every icon renders at 16px (larger for empty states), inherits `currentColor`, and is marked decorative (`aria-hidden="true"`) when it accompanies text. Icon-only controls carry an accessible name.

### D6. Presentation is built only on primitives and utilities

Every view is rebuilt with the primitives from `web/src/components/ui/` (button, badge, card, dialog, input, select, label, tooltip, separator, table) and Tailwind utilities over the token bridge. Moved components keep their behaviour and tests, not their markup or CSS. When the last view has moved, `legacy.css`, `canvas/canvas.css`, `runs/runs.css`, `views/views.css` and `experiments/experiments.css` are deleted with the `legacy` layer and the `.type-*` classes. Typography uses the bridged `text-page-title`, `text-section-title`, `text-meta` and `text-code` utilities.

- Buttons: the `Button` primitive only. It gains a `chip` variant (selection, distinct from primary) beside the existing tinted default, destructive, outline, secondary and ghost variants. The `.button`, `.control` and `.panel` classes are deleted.
- Badges: the `Badge` primitive for run status and answer status. Its status variants use tinted fill, coloured border and `--status-*-label` text, because raw status colours fail 4.5:1 on their own tint; the ratio is defined and tested in the `web-ui-stack` spec. This change adds keyword-style hue hashing for profile labels (`documents`, `codebase`) and node kinds. Colour never carries meaning alone; text always states it.
- Elevation: the `shadow-floating` utility on the top bar and floating panels only; cards stay flat with 1px borders.
- Theme control (owner decision, 14 October 2026): the top bar holds a `Select` with System, Light and Dark, and beside it an icon-only `Button` that shows the theme in effect (sun in light, moon in dark) and switches between Light and Dark in one click. Its accessible name states the target, for example "Switch to dark theme". Both controls write `omrg-preferences.theme`; Settings shows the same `Select`.
- Empty states: an icon, one sentence and one action. No placeholder copy.
- Narrow screens (owner decision, 14 October 2026): below the `md` breakpoint the side navigation becomes one row of the seven area icons with short labels, each target at least 44px, under the top bar. No menu button; every area stays one tap away.
- Knowledge Base sections (owner decision, 14 October 2026): Sources, Search, Add and Profile are switched with `chip` buttons, one section at a time, so long tables and result lists do not stack. The selected section is part of the view state, not the route.
- React Flow: its stylesheet stays in the `vendor` layer. Overrides that must target React Flow's own class names live in `app.css` under `@layer components`; everything else is utilities on our elements.
- Reset: with no hand-written CSS left, Tailwind's preflight loads into the `base` layer, which the shadcn primitives assume. Only `tokens.css` and `app.css` exist as stylesheets.
- Dev proxy: `vite.config.ts` gains `server.proxy` forwarding `/v1` to the local web transport (default `http://127.0.0.1:8765`, the `omrg web` default port set by `add-mcp-http-transport`; overridable by env).

### D7. The Integrations page shows, it does not install

The web transport cannot pip-install into its own environment from a browser, and should not. `GET /v1/integrations` (read scope) returns one entry per installable extra in `pyproject.toml` (chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web) plus the always-on magika integration, each with id, name, purpose, pip extra, copy-ready install command (`uv sync --extra <name>` / `pip install "omrg[<name>]"`) and availability. Availability reuses the existing probes in `omrg/capabilities.py` (PDF reader and sparse backend resolution), `core/vectordb/registry.available()` for chroma, `core/community/registry.available()` for leiden, and import checks for azure, llamacpp, openrouter and torch. The catalogue is declared once in the transport layer; the page renders it with status badges and a copy button per entry.

### D8. Detail regions are contextual

The top-bar Inspector toggle, the global `Inspector` component and the `inspectorOpen` state are removed. Chat, Studio and Experiments own their detail regions inside their layouts. Focus management follows the existing skip-link and focus-visible patterns.

### D9. The URL is the only source of location

`lib/routes.ts` defines a typed `Route` union with `parseRoute(hash): Route` and `formatRoute(route): string`, round-trip tested:

| Route | Hash |
|---|---|
| Home | `#/home` |
| Knowledge Base (project picker) | `#/knowledge-base` |
| Knowledge Base for a project | `#/knowledge-base/<collection>` |
| Chat (knowledge base picker) | `#/chat` |
| Chat on a knowledge base | `#/chat/<collection>` |
| Studio gallery | `#/studio` |
| Studio canvas | `#/studio/<pipeline-id>` |
| Experiments | `#/experiments` |
| Run detail | `#/experiments/runs/<run-id>` |
| Integrations | `#/integrations` |
| Settings | `#/settings` |

Segments are `encodeURIComponent`-encoded. A hash that does not parse resolves to Home and the address bar is rewritten to `#/home`; there are no name-specific redirects for routes that existed before this change. Navigation pushes history entries; back and forward re-parse the hash. Nothing else stores the current view, project or pipeline. `lib/views.ts` keeps only the seven area definitions (id, label, icon, summary). Opening a Home card goes to `#/knowledge-base/<collection>`; the knowledge base panel in Chat rewrites `#/chat/<collection>`. A route naming a collection or pipeline the server does not return shows a not-found state with a link back to its picker.

### D10. One API client with typed errors

`api/client.ts` owns a single `request<T>(method, path, { query, body, signal })`: it enforces the `/v1` prefix, sends and parses JSON, reads the error envelope, and throws `ApiError` with `kind` (`invalid-path`, `network`, `not-json`, `invalid-json`, `http`) and `status`. The per-module `sendJson`, `postJson` and `isJson` copies are deleted; `api/*.ts` become thin typed functions over `request`. The fetch implementation is set once when the client is created and provided through React context (`ApiProvider`); components never receive `fetchImpl` props. Tests build the client with the existing fixture servers under `web/src/*/test/` (for example `views/test/fakeDocumentsServer.ts`, `canvas/test/fakeServer.ts`, `runs/test/runServer.ts`, `experiments/test/experimentsServer.ts`).

`lib/errors.ts` exports `describeError(error): { message, action }`, keyed on `ApiError.kind` and `status` (for example `network` → "The local server is not reachable." with Retry; 401/403 → session guidance; 404 → not-found with a link back; 413 → file too large). The raw `ApiError.message` goes to `console.error` only. `messageOf` and every string-typed error state are removed.

### D11. Server state lives in one query cache

`@tanstack/react-query` v5 is the single owner of server data in the browser. The owner approved this one dependency on 14 October 2026; it is pinned exactly and its MIT notice is added to `web/THIRD_PARTY_NOTICES.md`. Rationale: Home, Chat and Knowledge Base all read collections, and uploads, deletions, profile changes and finished ingest jobs must refresh them everywhere; a hand-written keyed cache would re-implement deduplication, invalidation, retry and stale handling with weaker guarantees.

- `api/queries.ts` declares every read once with `queryOptions` and a hierarchical key: `["collections"]`, `["collections", name, "documents"]`, `["pipelines"]`, `["pipelines", id]`, `["pipeline-templates"]`, `["runs", filters]`, `["runs", id]`, `["experiments"]`, `["plugins"]`, `["roots"]`, `["session"]`, `["integrations"]`, `["connections"]`.
- Writes use `useMutation`; each declares the keys it invalidates (ingest job completion, upload, delete and profile change invalidate `["collections"]` and the collection's documents; revision save invalidates `["pipelines"]`). Answers and searches are mutations because each submission is a fresh request.
- `Register.defaultError` is set to `ApiError`, so every `error` is typed and goes through `describeError`.
- Defaults: one retry for `network` errors only, no retry for `http` errors, refetch on window focus off. Tests create a fresh `QueryClient` per test with `retry: false`.
- Run event streams stay on `runs/eventClient.ts` (SSE); on a terminal event the stream invalidates `["runs", id]` and `["runs"]`.
- `views/shared/useLoad.ts` is deleted.

### D12. Browser storage holds preferences and drafts only

One helper, `lib/storage.ts`, exposes `readStored(key, validate)`, `writeStored(key, value)` and `removeStored(key)`. Every access is guarded because storage can be missing or throw. Values carry no version field: a value that fails its validator is ignored and removed, so a changed shape resets to defaults instead of being migrated. Exactly two kinds of key exist:

- `omrg-preferences`: `{ theme, lastCollection }`. `lastCollection` is a navigation default for `#/chat` and `#/knowledge-base` and is dropped when the server no longer lists that collection.
- `omrg-canvas-draft:<pipeline-id>`: the unsaved graph and layout for one pipeline, cleared when a revision is saved.

`omrg-workspace-ui` and `omrg-canvas-session` are deleted. The open pipeline comes from the route, and the latest run from `GET /v1/runs?pipeline_id=<id>&limit=1`.

### D13. Settings shows connections, the server log and MCP access

Settings has six sections, switched with `chip` buttons like the Knowledge Base: Appearance, Connections, MCP, Server log, Runtime and Workspace.

**Connections (read-only, owner decision 14 October 2026).** Provider settings come from `.env` and `config/defaults.yaml`, are resolved once at startup and are frozen. This change shows them and tests them; it does not edit them.

- `GET /v1/connections` (read scope) returns `config_dir`, the server's working directory whose `.env` the settings read, and one entry for each LLM registry provider: `ollama`, `llamacpp` and `openrouter`. Each entry has the endpoint URLs (`OLLAMA_BASE_URL`; `LLAMACPP_EMBED_URL` and `LLAMACPP_CHAT_URL`; the fixed OpenRouter base `https://openrouter.ai/api/v1`), the configured model names, `key_set` (a boolean; the key itself never leaves the server) and the roles that use the provider: embeddings, answers, metadata extraction and claim verification.
- Roles are resolved by the same rules as startup: `EMBED_PROVIDER` with `LOCAL_BACKEND` and `CLOUD_BACKEND`, `ANSWER__PROVIDER`, `METADATA_LLM_PROVIDER` and `ANSWER__VERIFY_PROVIDER`. A new `compose.connection_summary()` builds the payload, because `compose` is the only production caller of `get_settings()`.
- `POST /v1/connections/{provider}/test` (`manage` scope) sends one model-list request with `httpx` and a 5-second timeout: Ollama `GET /api/tags`, llama.cpp `GET /models` on each configured URL, OpenRouter `GET /models` with the key. The response is `{ reachable, reason }`, where `reason` is one of `refused`, `timeout`, `unauthorised`, `http-<status>` or `not-configured`. Response bodies and exception text are never returned. The OpenRouter test is the only cloud request and runs only when the user presses Test.
- The section states that values come from `<config_dir>/.env` and need a server restart. Editing is a separate change, `add-runtime-settings`, which must design settings-file precedence, keep secrets in `.env`, rebuild the Engine safely and lock the embedding model for each collection, because a different embedding model makes existing indexes unusable.

**Server log.** `omrg web` attaches an in-memory ring-buffer handler (the last 1,000 records) to the root logger at startup, with the existing `RedactingFilter` attached to the handler itself so provider keys and bearer tokens never enter the buffer.

- `GET /v1/logs?after=<seq>` (`manage` scope, browser session only) returns records `{ seq, time, level, logger, message }`.
- `GET /v1/logs/stream?after=<seq>` streams new records as `text/event-stream` with replay after a sequence, like the run event stream, and ends when `runtime.admission.is_open` becomes false so shutdown does not wait on it.
- The panel is a monospace, terminal-style region with a level filter (info, warning, error), pause, copy and auto-scroll while the view is at the bottom. Records stay in memory; this change writes no log file.

**MCP.** Today MCP runs only on stdio: the MCP client starts its own `omrg` process (`mcp.run(transport="stdio")` in `transports/mcp/__init__.py`). The MCP section shows two things:

- A copyable stdio client configuration that runs `uv run --directory <project> omrg`, so `omrg` starts in the folder that holds `.env` (settings read `.env` from the working directory). The page fills `<project>` with `config_dir` from `GET /v1/connections`. This works today.
- MCP over streamable HTTP at `/mcp` on the `omrg web` server, sharing its one Engine, from `add-mcp-http-transport` (design D7 there): an on/off switch (`GET` and `PUT /v1/mcp`), the HTTP client configuration with the URL from `GET /v1/mcp`, the token controls (`POST /v1/mcp/token` shows the token once with a copy action; `DELETE` revokes it; the page states rotation breaks existing clients), and the saved web port (`GET` and `PUT /v1/settings/web-port`, applied on the next launch). That change must merge before task 7.6.

## Risks and Trade-offs

- Rebuilding every view on primitives is more work than restyling; accepted because it removes 1,413 lines of hand-written CSS and the `legacy` layer for good, and the foundation tasks land first so views are built once.
- One new dependency (`@tanstack/react-query`); accepted by the owner for a cache shared across views with correct invalidation.
- Bookmarks to old hashes open Home. Accepted: the app is pre-release with no external links to preserve.
- Stored UI state from earlier builds is ignored and removed on first read. Accepted for the same reason.
- Chat without turn memory will feel limited; accepted for v1 and stated in the UI ("each question answers from the knowledge base on its own").
- Folding Runs into Experiments lengthens that view; mitigated with two sections, the status filter, and run detail on its own route.
- The main specs from `add-local-web-pipeline-workspace` still govern the moved views. Only the `pipeline-canvas` navigation requirement changes; task 8.4 checks the others against the finished views.
- Removing the Search view could have dropped metadata-filtered search, which `local-web-workspace` requires; the Knowledge Base keeps it (task 2.5).
- Integration availability reflects this launch only; the page states that the install command must run outside the app and the server restarted.
- Connections are read-only until `add-runtime-settings` lands; the section says where each value comes from, so the user can change it in `.env`.
- The MCP switch (task 7.6) is blocked until `add-mcp-http-transport` merges. The stdio configuration ships with this change.
- The server log can show local file paths. It is limited to the browser session (`manage` scope) on the loopback server, and keys are redacted before a record enters the buffer.

## Migration Plan

None. The workspace is pre-release: routes, stored UI state and stylesheets are replaced, not migrated. Rollback is reverting the change.

## Open Questions

None blocking. Profile-preset seeding (D3) depends only on existing template, pipeline and profile APIs. Task 7.6 depends on `add-mcp-http-transport`, which is planned next as its own change.
