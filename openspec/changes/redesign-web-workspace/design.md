# Design

## Context

The existing web app (`web/src/`) is a React 19 + Vite SPA with hand-written CSS on semantic tokens (`web/src/styles/tokens.css`, already adapted from OpenChamber revision `02306f32e4d191e4840440cbafa643ae899471c2`). Views: canvas (React Flow), library, search, ask, runs, experiments, settings. The FastAPI transport under `src/omrg/transports/api/` exposes `/v1` operations: collections/documents/search/answer, uploads, ingest jobs, pipelines and templates, runs with SSE, experiment contexts, notebook plugins.

OpenChamber's component layer (studied in `packages/ui/src`): flat tinted buttons (`color-mix` primary 10/16/22% light, 16/22/30% dark, saturated border and text, lowercase, h-9 default, squircle-capable 10px radius, 3px focus ring), elevated cards with `shadow-none`, chip variant for selection distinct from primary, semantic typography classes (`typography-ui-label`, `typography-meta`, headings differentiated by weight), chat as a centred `min(100%, 48rem)` column with a docked composer. Its chat implementation is far too large to copy (`ChatInput.tsx` alone is 208 KB); we take the visual structure only. The distilled palette, typography, geometry, interaction states, badge convention and chat skeleton live in `references/openchamber-design.md`, with the two source theme JSONs beside it, so implementation needs no OpenChamber checkout.

## Goals and Non-Goals

Goals: job-shaped navigation; chat over the answer API with citations; project-scoped library; studio gallery with wide canvas; experiment folders; OpenChamber-grade presentation; no dependencies beyond `add-web-ui-stack` (applied first).

Non-goals: multi-turn conversational memory in the Engine (each chat turn answers independently; follow-up context needs an Engine change and is deferred); streaming chat tokens; mobile app; new pipeline semantics; the deferred Quick/Standard/Full optimiser.

## Decisions

### D1. A project is a collection

`GET /v1/collections` already returns name, document count, chunk count and stored profile. Home renders these as project cards. No new backend entity, no migration. Creating a project happens through the first ingest (the Knowledge Base upload panel names the target collection). Active project state lives in the app shell (URL hash segment plus localStorage), consumed by Chat and Knowledge Base.

### D2. Chat is sequential Q&A, from scratch

Each turn posts `POST /v1/collections/{collection}/answer` (query limit 4096) and renders the returned answer, citations, verification status and evidence rows. The transcript is presentation only; turns do not see each other. "New chat" clears it. Rationale: the answer pipeline is single-shot; bolting on server-side conversation state would be a new subsystem for unclear gain. UI structure follows OpenChamber: centred `min(100%, 48rem)` transcript column, composer docked at the bottom, citations as chips under each answer, evidence in a collapsible section that reuses the existing chunk viewer. No chat framework: a message list plus composer is roughly 200 lines.

### D3. Studio is a shell change, not a pipeline change

Graph semantics, revisions, validation and runs stay as specced in `add-local-web-pipeline-workspace` (`pipeline-graphs`, `pipeline-canvas`). Studio adds: a gallery landing (`GET /v1/pipeline-templates`, profile presets, saved pipelines from `GET /v1/pipelines`) and a sub-page route (`#/studio/<pipeline-id>`) where the canvas takes the full main area, the palette moves to the right column, and the inspector opens on node selection. Profile presets ("documents", "codebase") are gallery cards that seed the search template with the profile's retrieval defaults (rerank on for documents, off for codebase) and the target collection pre-filled.

### D4. Experiment folders need one backend addition

`core/experiments/contexts.py` raises `ExperimentPathError("not_found")` when the workspace directory does not exist, so the UI cannot create folders today. Add `POST /v1/experiment-folders` (session `manage` scope; validated relative path, no `..`, below an approved root, depth limit) and include the directory tree in the experiments listing. The web groups contexts under their parent directory; a main folder with no contexts still shows. Registration, credentials, trust notices and marimo plugin approval flow through the existing endpoints unchanged.

### D5. Icons come from lucide-react via the UI stack

`add-web-ui-stack` installs `lucide-react`. Every icon renders at 16px (larger for empty states), inherits `currentColor`, and is marked decorative (`aria-hidden="true"`) when it accompanies text. Icon-only controls carry an accessible name. This replaces the earlier inline-SVG plan.

### D6. Presentation rules adapted from OpenChamber

New view markup uses the primitives from `web/src/components/ui/` (button, badge, card, dialog, input, select, label, tooltip, separator, table) with Tailwind utility classes over the token bridge; legacy CSS stays for untouched components and retires as views migrate. Legacy CSS sits in the `legacy` cascade layer, so a utility on a migrated element always wins. Migrating a view means moving it off `.type-*` and the legacy rules, then deleting those rules from `legacy.css`.

- Buttons: keep the existing `.button` classes; primary becomes the tinted treatment already tokenised (`--accent-tint` 10/16/22% light, 16/22/30% dark) with `--accent-tint-border` and `--accent-label`; add a `chip` variant (selection) and keep `ghost`.
- Badges: the `Badge` primitive from `add-web-ui-stack` for run status and answer status. Its status variants use tinted fill, coloured border and `--status-*-label` text, because raw status colours fail 4.5:1 on their own tint; the ratio is defined and tested in the `web-ui-stack` spec. This change adds keyword-style hue hashing for profile labels (`documents`, `codebase`) and node kinds. Colour never carries meaning alone; text always states it.
- Elevation: `box-shadow: 0 1px 3px rgb(0 0 0 / 0.08)` (light) / `0 1px 3px rgb(0 0 0 / 0.4)` (dark) on the top bar and floating panels only; cards stay flat with 1px borders.
- Errors: one shared mapper converts fetch/HTTP failures to a friendly line plus a Retry button; parser messages are logged, never rendered. Empty states gain an icon, one sentence, and one action.
- Dev proxy: `vite.config.ts` gains `server.proxy` forwarding `/v1` to the local web transport (default `http://127.0.0.1:8000`, overridable by env), so `npm run dev` stops showing raw 404 text.

### D7. The Integrations page shows, it does not install

The web transport cannot pip-install into its own environment from a browser, and should not. `GET /v1/integrations` (read scope) returns one entry per installable extra in `pyproject.toml` (chroma, hybrid, pdf-pypdfium2, pdf-inspector, community-leiden, azure, llamacpp, openrouter, torch, web) plus the always-on magika integration, each with id, name, purpose, pip extra, copy-ready install command (`uv sync --extra <name>` / `pip install "omrg[<name>]"`) and availability. Availability reuses the existing probes: PDF reader resolution and sparse backend from `compose.py`, `vectordb_registry.available()` for chroma, `community_registry.available()` for leiden, and import checks for azure, llamacpp, openrouter and torch. The catalogue is declared once in the transport layer; the page renders it with status badges and a copy button per entry.

### D8. Inspector becomes contextual

The top-bar Inspector toggle and the empty global inspector are removed. Chat, Studio and Experiments own their detail regions inside their layouts. Focus management follows the existing skip-link and focus-visible patterns.

## Risks and Trade-offs

- Chat without turn memory will feel limited; accepted for v1 and stated in the UI ("each question answers from the knowledge base on its own").
- Folding Runs into Experiments lengthens that view; mitigated with two sections and the existing filters.
- The main specs from `add-local-web-pipeline-workspace` still govern the moved views. Only the `pipeline-canvas` navigation requirement changes; task 8.4 checks the others against the finished views.
- Removing the Search view could have dropped metadata-filtered search, which `local-web-workspace` requires; the Knowledge Base keeps it (task 2.5).
- Integration availability reflects this launch only; the page states that the install command must run outside the app and the server restarted.

## Migration Plan

Hash routes change (`#/canvas` → `#/studio`, `#/library` → `#/home`, `#/search`/`#/ask` → `#/chat`, `#/runs` → `#/experiments`). The router maps old hashes to their new homes once, then writes the new hash. localStorage keys for view state gain a version; stale keys are dropped.

## Open Questions

None blocking. Profile-preset seeding (D3) depends only on existing template and profile APIs.
