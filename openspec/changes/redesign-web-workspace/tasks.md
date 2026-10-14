# Tasks

Prerequisite: `add-web-ui-stack` is merged and archived (main spec `web-ui-stack`). Its primitives in `web/src/components/ui/`, `lucide-react`, the `--status-*-label` and `--shadow-floating` tokens, and the cascade layers in `app.css` are assumed below. Legacy typography classes are `.type-*`; migrated views use the `text-*` utilities instead.

## 1. Foundations and presentation

- [ ] 1.1 Add the `/v1` proxy to `web/vite.config.ts` (target overridable by env) with a test proving dev requests reach the transport path.
- [ ] 1.2 Use `lucide-react` icons (home, message-circle, database, workflow, flask, plug, settings, upload, folder, search, x, play, trash, refresh, chevron-down) at 16px with `currentColor`; decorative when beside text, accessible names when alone.
- [ ] 1.3 Extend the `Badge` primitive from `web/src/components/ui/` with a hue-hash variant for profile labels and node kinds. The status variants and `--status-*-label` tokens already exist, with contrast tested in `tokens.test.ts`. Unit-test the colour and text pairing for the hue-hash variant.
- [ ] 1.4 Add the shared error mapper (`friendly failure line + one action`) and replace direct parser-text rendering in every fetch path; unit-test that parser messages never reach the DOM.
- [ ] 1.5 Restructure `views.ts` and `AppNav` to the seven areas with icons, Home landing, and one-time redirects for legacy hashes; update `App.test.tsx`.
- [ ] 1.6 Apply the `shadow-floating` utility (token from `add-web-ui-stack`) to the top bar and floating panels; add the top-bar engine status pill (collections count or offline); remove the global Inspector toggle and empty inspector; update affected tests.
- [ ] 1.7 Refresh empty states across views: icon, one sentence, one action; update tests.

## 2. Home and projects

- [ ] 2.1 Create `web/src/home/HomeView.tsx` rendering project cards from `listCollections` (name, profile badge, counts) and the no-collection empty state with an ingest action.
- [ ] 2.2 Add active-project state (URL segment plus localStorage with versioned keys) and the route `#/home/<collection>` opening the project library; test persistence across reload and stale-key dropping.
- [ ] 2.3 Move the library components (source table, orphan status, upload panel, folder ingest panel, profile and deletion) into `web/src/knowledge-base/` scoped to the active project; port the existing `LibraryView` tests.
- [ ] 2.4 Enforce the client-side per-file size check with a friendly refusal; test the oversized-file path.

## 3. Chat

- [ ] 3.1 Create `web/src/chat/ChatView.tsx`: transcript column (`min(100%, 48rem)`), composer docked at the bottom, New chat action, and the standalone-turn notice.
- [ ] 3.2 Add the right-hand knowledge base panel listing collections with counts, selection state, and mid-conversation switching; test selection persistence and switching.
- [ ] 3.3 Implement the turn flow: user message, `answerCollection` call, assistant turn with status text, citation chips, collapsible evidence; failure turns show the friendly line with Retry; test ok, error-status and transport-failure turns.
- [ ] 3.4 Reuse the chunk viewer for citations and evidence rows; test opening a citation renders the chunk.
- [ ] 3.5 Delete `views/search/` and `views/ask/` after their behaviour is covered by chat tests; remove their routes.

## 4. Studio

- [ ] 4.1 Create `web/src/studio/StudioView.tsx` gallery: template cards, documents and codebase preset cards, saved pipeline cards; test gallery contents against the fixture server.
- [ ] 4.2 Implement preset seeding: documents and codebase cards create a pipeline from the search template with the profile's retrieval defaults; test the seeded graph.
- [ ] 4.3 Add the `#/studio/<pipeline-id>` sub-page: full-width flow surface, palette as the right column, node settings on selection; move `web/src/canvas/` components under `web/src/studio/` and update imports.
- [ ] 4.4 Update canvas tests for the new layout (palette right, inspector contextual) and keep revision, validation and run flows green.

## 5. Experiments

- [ ] 5.1 Add folder support to the backend: `POST /v1/experiment-folders` and directory-tree data in the experiments listing, with path validation (no `..`, below approved roots, depth limit); extend `core/experiments` with directory creation; add backend tests including traversal rejection.
- [ ] 5.2 Update the OpenAPI contract artifacts for the new operations.
- [ ] 5.3 Create `web/src/experiments/ExperimentsView.tsx` (renamed area): folder groups with sub-experiments, empty-folder display, folder and sub-experiment creation forms with declared factors; test grouping, creation and the no-root guidance.
- [ ] 5.4 Move the notebook plugin panels (registration, trust notice, one-time credentials, editor launch and stop) into the experiments area; port their tests.
- [ ] 5.5 Move the runs list, filters and run detail with evidence into the experiments area under a Runs section; port the runs tests; delete `web/src/runs/` view wiring that duplicates them.

## 6. Integrations

- [ ] 6.1 Add `GET /v1/integrations` (read scope): one catalogue entry per declared extra plus magika, with availability resolved through the existing probes (PDF reader and sparse backend from `compose.py`, `vectordb_registry.available()`, `community_registry.available()`, import checks for azure, llamacpp, openrouter, torch); add backend tests for available, not-installed and probe-failure states.
- [ ] 6.2 Update the OpenAPI contract artifacts for the new operation.
- [ ] 6.3 Create `web/src/integrations/IntegrationsView.tsx`: catalogue cards with status badges, purpose, copyable install command, the running-launch notice, and the friendly retry on failure; test the full catalogue, the installed-versus-absent states and the copy action.

## 7. Settings and cleanup

- [ ] 7.1 Trim Settings to appearance (theme), runtime capabilities and workspace information; remove controls that moved to other views; update tests.
- [ ] 7.2 Sweep `web/src` for dead CSS and components after the moves; keep every file under 500 lines; run lint, typecheck and the full vitest suite.

## 8. Verification

- [ ] 8.1 Run `uv run pytest -m "not slow"` for backend changes and `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build` in `web/`; record exact results.
- [ ] 8.2 Capture the visual matrix per the omms-design reference: Home, Chat, Knowledge Base, Studio gallery, Studio canvas, Experiments, Integrations and Settings at 1280px and 390px in light and dark themes; check status badges, elevation and focus rings.
- [ ] 8.3 Run `openspec validate redesign-web-workspace --strict` and resolve every finding; run `graphify update .`.
- [ ] 8.4 Reconcile ADDED deltas with `local-web-workspace`, `pipeline-canvas` and `notebook-plugins` if `add-local-web-pipeline-workspace` has been archived first; update `docs/guides/` web references to the new navigation.
