# Document views: Library, Search, Ask and Settings (task 7.6)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted working tree.
Design D8 and D9. Specs `local-web-workspace` and `pipeline-canvas` (workspace views requirement).

## Files

All files are new, except one edit to `web/src/App.tsx`.

| File | Job |
|---|---|
| `web/src/api/documents.ts` | Typed client for the collection, source, search, answer, chunk, job, ingestion, upload, root, session, deletion and profile routes. |
| `web/src/api/documents.test.ts` | 26 tests for the client. |
| `web/src/views/DocumentView.tsx` | Selects Library, Search, Ask or Settings by view id. |
| `web/src/views/views.css` | View styles. Semantic tokens and logical properties only. |
| `web/src/views/shared/` | `controls.tsx` (heading, collection select, inherit/on/off select, error notice), `ChunkViewer.tsx`, `labels.ts`, `useLoad.ts`. |
| `web/src/views/library/` | `LibraryView`, `SourceTable`, `UploadPanel`, `IngestPanel`, `JobList`, `DeletePanel`, `ProfilePanel`, `FlowControls`, `usePreviewConfirm`. |
| `web/src/views/search/` | `SearchView`, `SearchForm`, `ResultList`. |
| `web/src/views/ask/` | `AskView`, `AnswerPanel`, `answerStatus.ts`. |
| `web/src/views/settings/` | `SettingsView`, `RuntimeSection`. |
| `web/src/views/test/fakeDocumentsServer.ts` | In-memory stand-in for the document routes. It records every request. |

The largest component is `LibraryView.tsx` (148 lines). `api/documents.ts` has 347 lines, most of them types.

`App.tsx` change: one import line and one extra branch (`isDocumentView(view.id) ? <DocumentView .../>`) between the `canvas` branch and the `ViewShell` fallback. The Runs agent can add its `runs` branch next to it.

## Routes used

| View | Routes |
|---|---|
| Library | `GET /v1/collections`, `GET /v1/collections/{c}/documents`, `GET /v1/roots`, `POST /v1/uploads/preflight`, `POST /v1/uploads`, `POST /v1/ingestions`, `GET /v1/jobs/{id}`, `DELETE /v1/collections/{c}/documents`, `PATCH /v1/collections/{c}/profile` |
| Search | `GET /v1/collections`, `POST /v1/collections/{c}/search`, `GET /v1/collections/{c}/documents` (availability), `GET /v1/collections/{c}/chunks/{id}?window=1` |
| Ask | `GET /v1/collections`, `POST /v1/collections/{c}/answer`, `GET /v1/collections/{c}/chunks/{id}?window=1` |
| Settings | `GET /v1/health`, `GET /v1/session`, `GET /v1/roots`, `GET /v1/pipeline-operations` |

## Behaviour

### Library

- Collections show source and chunk counts. Sources show the stored path, the stable ID (or "No stable ID (legacy row)"), the chunk count and availability.
- Availability is machine-local and tri-state: "Present on this machine", "Missing on this machine", "Unknown on this machine". `null` never reads as missing or lost.
- Upload: the server preflight checks name, size and type for each file before the bytes are sent. A 400, 413 or 415 shows as "`name`: rejected. `server message`". Other files continue. The panel states the 50 MiB per-file limit. The name travels percent-encoded in `X-Upload-Name`.
- An accepted upload is ingested by its managed-root path (`<managed root>/<upload id>/<name>`).
- Ingest from an approved folder: the user picks an operator root from `GET /v1/roots` and types a relative path. `joinRootPath` refuses absolute paths, `~`, drive letters, UNC paths, `..` segments, empty input and NUL characters before any request. The server checks the grant again.
- Jobs are polled until `completed` or `failed`. A failed job shows the redacted server error. A finished job reloads the collection and source listings.
- Deletion (one source or a whole collection): the panel previews first. It shows the chunk count, the source and stable ID, the expiry, and the weaker-guarantee warning when `validity` is `process_local`. Nothing is sent with a token until the user selects "Confirm deletion".
- A source with a stable ID is selected by `metadata_filter: {source_id}`. A legacy row is selected by its stored `path`.
- Profile change: preview shows old and new profile, the unchanged chunk count, each lever change with "Next query" or "Next ingestion only", the re-ingest pointer and the warning. Confirm sends the token.
- 409 shows the server's reason. 428 states that the server needs a fresh preview and that nothing changed. After any rejected confirmation the Confirm button goes away and "Preview again" appears, because the server spends the token on every rejection.

### Search

- Controls: collection, query, `top_k`, rerank (Profile decides, On, Off), hybrid (same), metadata filter as JSON. Empty controls are sent as `null`, so the profile decides.
- A metadata filter that is not a JSON object, or a `top_k` below 1, is refused before the request.
- Each result shows the score with its score kind ("Dense similarity (dense_similarity_v1)", "Reciprocal rank fusion (rrf_v1)", "Reranker sigmoid (reranker_sigmoid_v1)"). Rows added by neighbour expansion show "Not ranked: neighbour context".
- Each result shows its source and machine-local availability, matched from the source listing by stable ID (or by stored path for legacy rows). If the listing fails, availability is "Unknown".
- "Show chunk" opens the stored chunk from the protected chunk route, with Previous and Next neighbour buttons. Rows without `chunk_id` show "No stored chunk ID". The viewer states that the original file is not opened.

### Ask

- Sends the question with `top_k`, `rerank`, `hybrid` and `metadata_filter` as `null`.
- Status labels keep their meaning: `ok` is "Cited" (no verifier claim) or "Cited and verified" only when `verified: true`; `no_evidence` says no model was called; `generation_unverified` says to treat the answer as unsupported; `unverified_claims` lists each failing claim with its verdict and ordinals; `error` names the failure stage. `verification_skipped` shows its reason and keeps the citation-only guarantee.
- Only entries in `citations` get a "Show chunk" button. Markers such as `[7]` in the answer text stay plain text, so no citation is invented. A citation without `chunk_id` gets no button.
- Supplied evidence is listed separately from citations, with score kind labels.

### Settings

- Workspace folder: the parent of the managed `uploads` root. The server has no route for the workspace path, so this is derived from `GET /v1/roots`; if the managed root does not end in `uploads`, the view says the server did not report it.
- Runtime: server readiness, session kind and scopes, and how many pipeline operations are available, with the unavailable ones named.
- File access: every root with its kind and ID.
- Appearance: the existing `ThemeSelect`, bound to the application theme state.
- Plugins: "No plugin routes yet" (no plugin route exists).
- The view is read-only. It has no text inputs and states that it does not edit `.env` or switch models or providers.

### Safe rendering

All server text renders as React text nodes. There is no `dangerouslySetInnerHTML` and no Markdown renderer. A test checks that `<b>not markup</b>` in a result appears as literal text.

## Test-first record

1. `src/api/documents.test.ts` written first. Run: **1 file failed, no tests** (module missing).
2. Implementation run: **1 failed, 25 passed**. A collection name `../x` was encoded and sent. Fix: path segments with `/` or `\` are refused. Then **26 passed**.
3. View tests written first (`LibraryView.test.tsx`, `LibraryConfirm.test.tsx`, `SearchView.test.tsx`, `AskView.test.tsx`, `SettingsView.test.tsx`). Run: **5 files failed to import**.
4. Library run: **1 failed, 15 passed**. The listing refresh after a finished job happens one render later; the assertion now uses `waitFor`. Then **16 passed**.
5. Search 6 passed, Ask 11 passed, Settings 6 passed on the first implementation run.
6. Existing `App.test.tsx` and `theme.test.tsx` still pass. Each document view renders an `empty-state` before data arrives.

## Guard breaks

Script: `scratchpad/m76/mutate.py`. Each check edits one guard, runs the full Vitest suite, then restores the file.

| Id | Change | Result |
|---|---|---|
| M1 | Omitted `top_k` sent as 10 | 3 failed |
| M2 | Confirm offered again after a rejected token | 1 failed |
| M3 | Unknown availability shown as missing | 2 failed |
| M4 | Evidence listed as citations | 2 failed |
| M5 | Absolute path accepted for ingestion | 5 failed |
| M6 | Weaker-guarantee warning hidden | 2 failed |

## Commands

All commands ran in `web/`.

| Command | Result |
|---|---|
| `npm run lint` | FAIL, 1 error, in `src/runs/eventClient.ts` (Runs agent, in progress). `eslint . --ignore-pattern 'src/runs/**'`: PASS. |
| `npm run typecheck` | FAIL, 4 errors, all in `src/runs/` (Runs agent tests written before their modules). Errors outside `src/runs/`: 0. |
| `npm test` | 199 tests passed. 2 files failed to import, both in `src/runs/` (`./RunsView`, `./EvidenceInspector` not yet written). |
| `npm run build` | FAIL at its `tsc` step for the same `src/runs/` errors. `vite build` alone: PASS (JS 491.52 kB, 151.06 kB gzip; CSS 34.32 kB). |

Action for the lead: run the four commands again after the Runs agent finishes. The task 7.6 files cause no failures.

## Not run

- **NOT RUN:** browser checks at 1280, 768, 390 and 320 px in both themes, 200% zoom and keyboard walk-through. jsdom tests cover labels, roles and focus targets only.
- **NOT RUN:** a real `omrg web` server. Tests use the recorded fake routes, whose shapes follow the route modules and `openapi.yaml`.
- **NOT RUN:** Arabic prose content. Technical text uses `dir="ltr"` and server text uses `unicode-bidi: plaintext`.

## Open points

1. **Workspace path.** No route reports it. Add one (for example to `GET /v1/session` or a settings route) if the derived value is not enough.
2. **Plugin status.** No plugin route exists yet, so Settings shows "No plugin routes yet". Wire it when the plugin routes land.
3. **Current collection profile.** No route reads the stored profile, so the profile panel learns the old profile only from the preview.
4. **Mutation script location.** `scratchpad/m76/mutate.py` is in the session scratchpad, not the repository.
