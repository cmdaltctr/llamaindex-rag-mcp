# Canvas run state, inspectors and Runs view (tasks 7.4 and 7.5)

Date: 2026-10-13. Branch `feat/add-local-web-pipeline-workspace`, uncommitted work tree.

All commands ran in `web/`. No npm dependency was added. `client.ts` and `pipelines.ts` are unchanged.

## Scope

- **7.4:** an event client (server-sent events, reconnect, deduplication, polling fallback), node and edge state on the canvas from real events, a unit counter, fallback reasons, reduced motion and a labelled replay.
- **7.5:** the Runs view (status filter, run detail, admitted snapshot, node outcomes, completed effects, explicit retry, cancel), a node inspector, an evidence inspector with score-kind labels and bounded previews, citations and the protected chunk route.

## API contract used

The client follows `routes_runs.py` and `routes_inspect.py`:

| Need | Route | Client |
|---|---|---|
| Run list | `GET /v1/runs?status=…&limit=…` (status repeats) | `listRuns` |
| Run record | `GET /v1/runs/{id}` | `getRunRecord` |
| Stored result | `GET /v1/runs/{id}/result` (404 = no result) | `getRunResult` returns `null` on 404 |
| Polling | `GET /v1/runs/{id}/events?after_sequence=N&limit=500` | `listRunEvents` |
| Stream | `GET /v1/runs/{id}/events/stream`, `?after=N`; `id:` holds the sequence; ends with `run.end` or `server.closing` | `followRunEvents` |
| Cancel, retry | `POST /v1/runs/{id}/cancel`, `POST /v1/runs/{id}/retry` | `cancelRunRecord`, `retryRun` |
| Full chunk | `GET /v1/collections/{collection}/chunks/{chunk_id}?window=0` | `getChunk` (both segments URL-encoded) |

Event kinds are `EventKind` (`core/pipelines/results.py`) plus `run.status` (`core/workspace/events.py`).
Runner event summaries hold `{message, data, at}`. The `run.status` summary holds `status`, `wall_time_s`, `failed_node`, `error` and `completed_effects`.

## Files

| File | Lines | Purpose |
|---|---|---|
| `src/api/runs.ts` | 178 | Typed run and chunk client. Unsafe run identifiers are refused before fetch. |
| `src/runs/eventClient.ts` | 189 | `followRunEvents`: stream first, polling fallback, sequence deduplication, stop on terminal status. |
| `src/runs/runState.ts` | 158 | Folds events into node, unit, effect and status state. `edgeRunStyle` for edges. |
| `src/runs/useRunMonitor.ts`, `useReducedMotion.ts` | 75, 22 | Hooks. Unmount detaches monitoring only. |
| `src/runs/evidence.ts`, `redact.ts` | 78, 30 | Score-kind labels, 100-row and 4 KiB bounds, evidence search, secret masking. |
| `src/runs/RunsView.tsx`, `RunList.tsx`, `RunDetail.tsx` | 84, 40, 159 | Runs view. |
| `src/runs/RunSnapshot.tsx`, `NodeOutcomes.tsx`, `NodeRunInspector.tsx` | 55, 76, 38 | Snapshot, outcomes, node inspector. |
| `src/runs/EvidenceInspector.tsx`, `EvidenceRows.tsx`, `ChunkViewer.tsx`, `SafeValue.tsx` | 61, 87, 53, 46 | Evidence, rows, chunk text, safe JSON display. |
| `src/runs/ReplayPanel.tsx`, `LiveRunSummary.tsx`, `NodeRunBadge.tsx`, `runs.css` | 98, 45, 18, 215 | Replay, live summary, status badge, styles. |
| `src/canvas/OperationNode.tsx`, `FlowSurface.tsx`, `RunPanel.tsx`, `CanvasView.tsx`, `canvas.css` | | Additive: optional run state per node, edge class and `animated`, live summary slot, monitor wiring, two style rules. |
| `src/App.tsx` | | One branch: `view.id === "runs"` renders `RunsView`. The `DocumentView` branch stays. |
| Tests | | `api/runs.test.ts`, `runs/eventClient.test.ts`, `runs/runState.test.ts`, `runs/evidence.test.ts`, `runs/RunsView.test.tsx`, `runs/EvidenceInspector.test.tsx`, `canvas/CanvasView.live.test.tsx`; helpers `runs/test/fakes.ts`, `runs/test/runServer.ts`. |

## Behaviour

- **Real states only.** A node with no event shows "Not started". Progress events set "Running" and a message. No percentage, rate or estimate is computed.
- **Edges.** An edge is highlighted only while its target node is running. React Flow `animated` is off when `prefers-reduced-motion: reduce` applies; the static highlight and status text stay.
- **Fallback.** A `node_fallback` event shows "Fallback: <reason>" on the node and in the inspector.
- **Units.** "Units: N started, N completed, N failed, N cancelled" counts distinct `unit_id` values from `unit_*` events only. No total is guessed.
- **Reconnect.** The browser reconnects by itself and sends `Last-Event-ID`. A new stream uses `?after=<last sequence>`. Events with a sequence at or below the last delivered one are dropped, in the client and again in the state fold.
- **Fallback to polling.** A closed stream, three errors without a frame, or no `EventSource` starts polling from the last sequence. 401, 403 and 404 stop polling. Other errors retry with a growing delay.
- **Terminal.** `run.end`, `server.closing` or a complete polling page stops monitoring. After `run.end` the client reads the run record again.
- **Live and replay.** An active run shows "Live: …". A finished run shows a "Replay" section: "Replay of recorded events. Nothing runs again." Replay moves only on button presses. A finished run that the canvas restores shows "Recorded run, not live".
- **Timings.** The node inspector shows the node time from the stored result. The run wall time shows apart from it, with "Node times can overlap, so they are not added up."
- **Evidence.** Rank is the delivered position; earlier `dense_rank`, `sparse_rank` and `fused_rank` values show when a row carries them. Labels: Reranker score, RRF score, Dense similarity, Full-text score, "Rank only" (no number) for `sparse_rank_v1`, "Score (<kind>)" for an unknown kind. The view says scores are not comparable and are not probabilities of correctness.
- **Bounds.** At most 100 rows ("Showing the first 100 of N rows.") and 4 KiB of UTF-8 text per preview ("Preview cut at 4 KiB."). "Show full chunk <id>" opens the protected chunk route.
- **Secrets.** The UI shows the server's `[redacted]` value as given. Credential keys always show `[redacted]`; bearer tokens, URL credentials and credential query values in text are masked again. All text renders as text nodes; nothing uses `dangerouslySetInnerHTML`.

## Test-first record

1. First run of `api/runs.test.ts` and the three `runs/*.test.ts` files: **4 files failed** (modules missing). After the implementation: **39 passed**.
2. First run of `canvas/CanvasView.live.test.tsx`: **6 failed** (no event stream opened). After the wiring: **6 passed**.
3. First run of `runs/RunsView.test.tsx` and `runs/EvidenceInspector.test.tsx`: **2 files failed** (modules missing). After the implementation: **13 passed**.
4. `App.test.tsx` then failed once: the Runs view had no `data-testid="empty-state"`. The "No run selected" state now carries it.

## Mutation checks

Script `scratchpad/mut74/mutate.py`. Each check backs up one file, changes one line, runs the named tests, and restores the file.

| Id | Change | Result |
|---|---|---|
| M1 | No sequence deduplication in the event client | 2 failed (reconnect replay, repeated polling page) |
| M2 | Edge animation ignores reduced motion | 2 failed (unit and canvas) |
| M3 | Rank-only kind shows a number | 2 failed (unit and inspector) |
| M4 | No polling fallback on a refused stream | 3 failed (two unit, one canvas) |
| M5 | Credential keys not masked | 2 failed (unit and "never renders a secret") |
| M6 | Previews not bounded at 4 KiB | 2 failed (unit and inspector) |
| M7 | Finished run shown as live | 1 failed (replay test) |

M1 does not fail the canvas reconnect test, because the state fold also drops repeated sequences. That second guard is intended.

## Final results

| Command | Result |
|---|---|
| `npm run lint` | clean |
| `npm run typecheck` | clean |
| `npm test` | 24 files, **212 passed** |
| `npm run build` | built; Vite prints its 500 kB chunk-size warning |

## Open points

1. **Retrieval graph outputs are stored as text.** `to_jsonable` (`core/workspace/artefacts.py`) has no dataclass branch. A graph output of `RankedEvidence` or `ContextBundle` becomes its text form in the stored result, so the evidence inspector finds no rows and says so. Answer outputs (plain dicts) work. Fix (owner of `core/workspace`): convert values with `public_rows()` (or `dataclasses.asdict`, without vectors) before storage, and add a test.
2. **Restored pipeline shows an empty draft.** On a page load with a stored pipeline id and no stored draft, `useDraft` writes an empty draft for that id before `showPipeline` reads it, so the canvas shows an empty graph instead of the revision. The live canvas test opens the pipeline from the Pipeline list instead. Fix (owner of `canvas/useDraft.ts`): skip the first storage write, or let `showPipeline` prefer the revision when the stored draft is empty.
3. **Node times come from the stored result only.** A running node shows "recorded when the run ends". Event timestamps are not subtracted, so no measured time is invented.
4. **Not run:** a browser walk-through at 1280, 768 and 390 px widths in both themes, and a real `omrg web` stream. Vitest uses a fake `EventSource`.

## Lead follow-up (2026-10-13)

1. Search-graph outputs were stored as text. `core/workspace/artefacts.to_jsonable` now converts dataclass port values field by field and uses `public_rows()` when present (vectors still omitted). New test `test_to_jsonable_serialises_graph_port_dataclasses`; with the branch disabled it fails (1 failed, 41 passed), restored 42 passed. Workspace and run tests: 207 passed.
2. Reload showed an empty graph. `canvas/useDraft.ts` no longer saves the empty placeholder shown before a stored pipeline loads. New `canvas/useDraft.test.ts` (3 tests); with the guard removed 1 fails; restored 3 pass.
3. Web gate after both fixes: lint OK, typecheck OK, 25 files / 215 tests passed, build OK.
