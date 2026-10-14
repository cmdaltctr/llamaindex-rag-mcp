# Tasks

Prerequisite: `add-web-ui-stack` is merged and archived (main spec `web-ui-stack`). Its primitives in `web/src/components/ui/`, `lucide-react`, the `--status-*-label` and `--shadow-floating` tokens and the cascade layers in `app.css` are assumed below.

Rules for every task: build views only from primitives and Tailwind utilities; add no hand-written CSS; keep each file under 500 lines; write the test first and confirm it fails against the old code; a moved component keeps its behaviour and tests, not its markup or CSS.

## 0. Foundation

- [ ] 0.1 Add `@tanstack/react-query` (exact pin, approved 14 October 2026) and its MIT notice in `web/THIRD_PARTY_NOTICES.md`.
- [ ] 0.2 Rewrite `api/client.ts` around one `request<T>(method, path, { query, body, signal })` that throws `ApiError` with `kind` and `status`; delete the `sendJson`, `postJson` and `isJson` copies in `api/documents.ts`, `api/experiments.ts`, `api/pipelines.ts` and `api/runs.ts`; port their tests; test each `ApiError` kind.
- [ ] 0.3 Add `ApiProvider` (React context holding the client built from one fetch implementation); remove every `fetchImpl` prop from components; tests build the client from the existing fixture servers under `web/src/*/test/`.
- [ ] 0.4 Add `lib/errors.ts` `describeError(error) → { message, action }` keyed on `ApiError.kind` and `status`, logging the raw message to the console only; unit-test every kind and the 401, 403, 404 and 413 statuses; assert no raw message reaches the returned text.
- [ ] 0.5 Add `api/queries.ts`: `queryOptions` for every read with the hierarchical keys in design D11, mutation helpers that declare their invalidated keys, `Register.defaultError = ApiError`, and the `QueryClient` defaults (retry once on `network` only, no focus refetch); add a test helper that creates a fresh `QueryClient` with `retry: false`; test that an upload, a deletion, a profile change and a finished ingest job invalidate `["collections"]`.
- [ ] 0.6 Make the SSE run stream invalidate `["runs", id]` and `["runs"]` on a terminal event; test it with `runs/test/runServer.ts`.
- [ ] 0.7 Add `lib/routes.ts` (`Route` union, `parseRoute`, `formatRoute`) for every route in design D9 with encoded segments; test the round trip for every route, encoding of names with spaces and slashes, and that an unknown hash parses to Home.
- [ ] 0.8 Add `lib/storage.ts` (`readStored`, `writeStored`, `removeStored` with validators, no version fields); move preferences to `omrg-preferences` `{ theme, lastCollection }` and drafts to `omrg-canvas-draft:<pipeline-id>`; delete `omrg-workspace-ui`, `omrg-canvas-session` and the `inspectorOpen` state; test that throwing storage, malformed values and old-shape values fall back to defaults and are removed.
- [ ] 0.9 Rewrite `App.tsx` as the shell: route from the hash only (push on navigate, re-parse on back and forward, rewrite unknown hashes to `#/home`), `QueryClientProvider` and `ApiProvider` at the root, theme from preferences; delete `useLoad.ts`, `messageOf` and `components/Inspector.tsx`; update `App.test.tsx`.

## 1. Shell and presentation

- [ ] 1.1 Add the `/v1` proxy to `web/vite.config.ts` (target overridable by env) with a test proving dev requests reach the transport path.
- [ ] 1.2 Use `lucide-react` icons (home, message-circle, database, workflow, flask, plug, settings, upload, folder, search, x, play, trash, refresh, chevron-down) at 16px with `currentColor`; decorative when beside text, accessible names when alone.
- [ ] 1.3 Extend the `Badge` primitive with a hue-hash variant for profile labels and node kinds, and the `Button` primitive with a `chip` variant for selection; the status variants and `--status-*-label` tokens already exist. Unit-test the colour and text pairing for the hue-hash variant and the chip's selected state.
- [ ] 1.4 Render every failure through `describeError`: one line plus one action; unit-test that no parser or status text reaches the DOM in any view.
- [ ] 1.5 Rewrite `lib/views.ts` to the seven areas (id, label, icon, summary) and `AppNav` with icons and the active state from the route, switching to a single icon row with short labels and 44px targets below the `md` breakpoint (design D6); remove the placeholder copy; update tests.
- [ ] 1.6 Build the top bar with the `shadow-floating` utility, the engine status pill (collection count from `["collections"]`, or offline), and the theme select; test both pill states.
- [ ] 1.7 Add the shared empty and not-found states (icon, one sentence, one action) used by every view; test that a route naming an unknown collection or pipeline shows not-found with a link back to its picker.

## 2. Home and Knowledge Base

- [ ] 2.1 Create `web/src/home/HomeView.tsx`: project cards from `["collections"]` (name, profile badge, counts) linking to `#/knowledge-base/<collection>`, and the no-collection empty state with an ingest action; test both states.
- [ ] 2.2 Create `web/src/knowledge-base/KnowledgeBaseView.tsx` for `#/knowledge-base` (project picker that opens `lastCollection` when the server still lists it) and `#/knowledge-base/<collection>`; write `lastCollection` on open; test reload restoring the project from the URL and a deleted `lastCollection` being dropped.
- [ ] 2.3 Add the Knowledge Base section chips (Sources, Search, Add, Profile; one section shown at a time, design D6) and rebuild the source table, orphan status, upload panel, folder ingest panel, job list, profile and deletion panels in `web/src/knowledge-base/` on primitives, scoped to the route's collection, with mutations that invalidate `["collections"]` and the collection's documents; port the `LibraryView`, `LibraryConfirm` and `LibraryProfile` tests; delete `views/library/`.
- [ ] 2.4 Enforce the client-side per-file size check with a friendly refusal; test the oversized-file path.
- [ ] 2.5 Rebuild search in `web/src/knowledge-base/` on primitives: metadata filters, rank order, score-kind labels, and results opening in the chunk viewer; port the `SearchView` tests.

## 3. Chat

- [ ] 3.1 Create `web/src/chat/ChatView.tsx` for `#/chat` and `#/chat/<collection>`: transcript column (`min(100%, 48rem)`), composer docked at the bottom, New chat action, and the standalone-turn notice.
- [ ] 3.2 Add the right-hand knowledge base panel from `["collections"]` with counts; selecting a collection rewrites the route and `lastCollection`; test switching mid-conversation keeps earlier turns and queries the new collection.
- [ ] 3.3 Implement the turn flow as a mutation: user message, `answerCollection`, assistant turn with status text, citation chips, collapsible evidence; failure turns show `describeError` with Retry; test ok, error-status and transport-failure turns.
- [ ] 3.4 Rebuild the chunk viewer on primitives and use it for citations, evidence rows and search results; test opening a citation renders the chunk.
- [ ] 3.5 Delete `views/search/`, `views/ask/` and `views/DocumentView.tsx` once tasks 2.5 and 3.1 to 3.4 cover their behaviour.

## 4. Studio

- [ ] 4.1 Create `web/src/studio/StudioView.tsx` gallery: template cards, documents and codebase preset cards, saved pipeline cards from `["pipelines"]`; test gallery contents against the fixture server.
- [ ] 4.2 Creating from a card calls `createPipeline`, seeds the draft for the new id (presets use the search template with the profile's retrieval defaults and the target collection), and opens `#/studio/<pipeline-id>`; test the seeded graph for each preset.
- [ ] 4.3 Rebuild the canvas sub-page in `web/src/studio/` on primitives: full-width flow surface, palette as the right column, node settings on selection; React Flow overrides only in `app.css` `@layer components`; load the open pipeline from the route and its latest run from `GET /v1/runs?pipeline_id=<id>&limit=1`; delete `web/src/canvas/`.
- [ ] 4.4 Port the canvas tests to the new layout and keep revision, validation, run, keyboard editing and draft-persistence flows green.

## 5. Experiments

- [ ] 5.1 Add folder support to the backend: `POST /v1/experiment-folders` and directory-tree data in the experiments listing, with path validation (no `..`, below approved roots, depth limit); extend `core/experiments` with directory creation; add backend tests including traversal rejection.
- [ ] 5.2 Update the OpenAPI contract artifacts for the new operations.
- [ ] 5.3 Rebuild `web/src/experiments/ExperimentsView.tsx` on primitives: folder groups with sub-experiments, empty-folder display, folder and sub-experiment creation forms with declared factors; test grouping, creation and the no-root guidance.
- [ ] 5.4 Rebuild the notebook plugin panels (registration, trust notice, one-time credentials, editor launch and stop) on primitives inside Experiments; port their tests.
- [ ] 5.5 Rebuild the runs list (status filter from the `GET /v1/runs` query) and run detail at `#/experiments/runs/<run-id>` (snapshot, node outcomes, evidence, replay) on primitives; port the runs tests; delete `web/src/runs/` view code, keeping `eventClient.ts` and `useRunMonitor.ts` where Studio and Experiments use them.

## 6. Integrations

- [ ] 6.1 Add `GET /v1/integrations` (read scope): one catalogue entry per declared extra plus magika, with availability resolved through the existing probes (`omrg/capabilities.py` for the PDF reader and sparse backend, `core/vectordb/registry.available()`, `core/community/registry.available()`, import checks for azure, llamacpp, openrouter and torch); add backend tests for available, not-installed and probe-failure states.
- [ ] 6.2 Update the OpenAPI contract artifacts for the new operation.
- [ ] 6.3 Create `web/src/integrations/IntegrationsView.tsx` from `["integrations"]`: catalogue cards with status badges, purpose, copyable install command, the running-launch notice, and the friendly Retry on failure; test the full catalogue, the installed-versus-absent states and the copy action.

## 7. Settings and removal of legacy

- [ ] 7.1 Rebuild Settings on primitives: appearance (theme), runtime capabilities and workspace information; remove controls that moved to other views; update tests.
- [ ] 7.2 Delete `styles/legacy.css`, `canvas/canvas.css`, `runs/runs.css`, `views/views.css` and `experiments/experiments.css`, the `legacy` layer and every `.type-*` class; load Tailwind's preflight into the `base` layer; change `cascade.test.ts` so any stylesheet other than `tokens.css` and `app.css` fails, and drop the legacy collision test; confirm with `grep` that no `button`, `control`, `panel` or `type-*` legacy class name remains in `web/src`.
- [ ] 7.3 Sweep `web/src` for dead components, hooks, fixtures and copy left by the moves; confirm every file is under 500 lines.
- [ ] 7.4 Add `web/src/styles/design-md.test.ts`: parse the front matter of `web/DESIGN.md` and assert every colour, size, radius and spacing value equals the light-theme value in `tokens.css` (status labels computed from the 60/40 mix); confirm it fails when either file changes alone. Update `web/DESIGN.md` for the `chip` and hue-hash variants once they exist.

## 8. Verification

- [ ] 8.1 Run `uv run pytest -m "not slow"` for backend changes and `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build` in `web/`; record exact results.
- [ ] 8.2 Capture the visual matrix per the `omrg-design` verification reference: Home, Chat, Knowledge Base, Studio gallery, Studio canvas, Experiments, run detail, Integrations and Settings at 1280px and 390px in light and dark themes; check status badges, elevation, focus rings and keyboard reachability.
- [ ] 8.3 Run `openspec validate redesign-web-workspace --strict` and resolve every finding.
- [ ] 8.4 Check the finished views against the unchanged main specs `local-web-workspace`, `notebook-plugins`, `pipeline-graphs` and `pipeline-run-records`, and against the modified `pipeline-canvas` and `web-ui-stack`; fix any gap in code or raise a spec change; update `docs/guides/` web references to the new navigation and routes.
