# Gap fixes: canvas reasons, reconnect refresh, navigation and theme tests

Date: 2026-10-13. Worktree `llamaindex-rag-mcp-v3-feat-add-local-web-pipeline-workspace`, branch `feat/add-local-web-pipeline-workspace`, uncommitted on `879145a`.
Source: `evidence/verification.md` section A items 3, 5 and 6, and the two pipeline-canvas test gaps in section B.
No npm dependency added. No commit made.

## Item 6: the core bypass event carries its reason

Change: `src/omrg/core/pipelines/execution.py` `_bypass`. The `node_bypassed` event now has a message and data:

- message: `Disabled in the graph; passes its 'evidence' input through unchanged.` When no input value reached the node, the message says `has no 'evidence' input to pass through`.
- data: `reason` (`"disabled in the graph"`), `input_port`, `output_port`, `forwarded` (bool).

`NodeOutcome` is unchanged, so the result schema and OpenAPI stay the same. The reason travels in the event only.

Test: `tests/unit/test_pipeline_runner.py::test_bypass_event_carries_its_reason` (runner level, scripted catalogue).

| Step | Result |
|---|---|
| Before the fix | FAILED: `assert '' == 'Disabled in ...gh unchanged.'` |
| After the fix | `tests/unit/test_pipeline_runner*.py`: 39 passed |
| Mutation: `"reason": ""` | FAILED, file restored, then 2 passed |

## Item 5: the canvas node shows "Bypassed" with the reason

Two cases now show "Bypassed" with a reason on the canvas node card, in the Runs outcome badge and in the node inspector ("Bypass reason: ...").

1. Node bypass toggle: `node_bypassed` shows `Bypassed: <core message>`.
2. Reranker `enabled` lever set to Off: the node runs and reports `reranked: false` with `reason` in its completion summary. The canvas now shows `Bypassed: disabled by node parameter`, not "Completed".

Rules (`web/src/runs/runState.ts`):

- `displayStatus` returns `bypassed` for a succeeded node whose summary has `reranked: false` and no fallback. A fallback still shows "Fallback: <reason>".
- `bypassReason` returns the core message for a bypassed node, or `summary.reason` for a pass-through node.
- A bypass with no reason shows `Bypassed: input passed through unchanged`.

Files: `runState.ts`, `NodeRunBadge.tsx`, `NodeRunInspector.tsx`.

Limit: a finished run opened in Runs with no live events uses the stored `NodeOutcome`, which has no summary. That row still says "Completed" for the reranker lever case. Replay of the run shows the reason.

## Item 3: re-read the run record on every reconnect

Change: `web/src/runs/eventClient.ts` takes `onRefresh(run)`. The client reads `GET /v1/runs/{id}` again after each reconnect:

- the stream opens again after an error (browser reconnect);
- the client switches from the stream to polling;
- polling succeeds after one or more failed polls.

The first connection reads nothing, because the monitor reads the record just before it follows events. A failed re-read goes to `onError`; event following continues.

`web/src/runs/useRunMonitor.ts` folds the record into the view with `reconcileRun` (`runState.ts`). It sets the run status from the record. It ignores a record whose `last_sequence` is lower than the last applied event, so a slow read never moves the status back. Node states come from the events that each reconnect replays from the last sequence. The run record has no per-node fields.

## Section B: navigation and theme tests

New file `web/src/canvas/CanvasView.workspace.test.tsx` renders the full `App` with the canvas fake server as global `fetch` and the fake `EventSource`.

1. "keeps the selected node and the submitted run after Canvas, Runs, Canvas": submit a run, add a node, select `prepare_query`, open Runs, return to Canvas. Asserts the selection (`aria-pressed`), the added node, "Submitted run" with `run1` and Revision 1, and the unsaved-draft notice.
2. "keeps canvas edits and the selection when the theme changes": add two nodes, select one, change the theme to dark then light. Asserts both nodes, the selection and the open node inspector.

These are test-only gaps. Both tests passed on first run, as expected. The mutations below show that they fail when the behaviour breaks.

## Test-first record (Vitest)

| Test | Before the fix |
|---|---|
| `canvas/CanvasView.live.test.tsx` 3 new tests (bypass reason, reranker lever Off, reconnect re-read) | 3 failed |
| `runs/eventClient.test.ts` 4 new tests ("authoritative refresh on reconnect": stream reopen with a fake `EventSource` that drops twice and reconnects, switch to polling, polling recovery, failed re-read) | 4 failed |
| `runs/runState.test.ts` 6 new tests (pass-through, completed, fallback precedence, core reason, reconcile, stale record) | 5 failed (fallback precedence already held) |
| After the fixes | 6 files, 60 passed |

## Mutation checks (Vitest)

Script: `scratchpad/mutgap/mutate.py`. Each check edits one file (two for F11), runs the named tests, then restores the file. `git diff --stat` was the same before and after.

| Id | Change | Result |
|---|---|---|
| F1 | Badge drops the bypass reason | 2 failed (both live bypass tests) |
| F2 | Pass-through node shown as completed | 2 failed |
| F3 | No re-read when the stream reopens | 3 failed (live reconnect, client reopen, failed re-read) |
| F4 | No re-read on switch to polling | 1 failed |
| F5 | No re-read when polling recovers | 1 failed |
| F6 | Monitor ignores the re-read record | 1 failed (live reconnect) |
| F7 | Stale record moves the status back | 1 failed |
| F8 | Session forgets the submitted run | 1 failed (navigation test) |
| F9 | Stored draft loses its selection | 1 failed (navigation test) |
| F10 | Theme change remounts the canvas, storage intact | 2 passed: edits come back from storage, which meets the scenario |
| F11 | Theme change remounts the canvas and drafts are not read back | 2 failed |

## Final results

| Command | Result |
|---|---|
| `PYTHONPATH=src PDF_READER=pypdf .venv/bin/python -m pytest -q -p no:cacheprovider tests/unit/test_pipeline_runner*.py` | 39 passed |
| Same, all `tests/unit/test_pipeline_*.py` and `test_web_run*.py` (`-m "not slow"`) | 244 passed |
| `.venv/bin/ruff check` and `ruff format --check` (`core/pipelines`, runner test) | clean |
| `PYTHONPATH=src .venv/bin/lint-imports` | 17 kept, 0 broken |
| `npm run lint` | clean |
| `npm run typecheck` | clean |
| `npm test` | 33 files, 286 passed |
| `npm run build` | built; Vite prints its 500 kB chunk-size warning |

## Open points

1. Stored outcome rows have no node summary. A finished run opened in Runs shows the reranker lever case as "Completed" until replay. To close it, the run result must keep the node summary or a pass-through flag. This needs `NodeOutcome` and the OpenAPI schema (owner: backend).
2. The pass-through rule keys on the reranker summary field `reranked: false`. A future pass-through operation needs the same field, or a shared summary flag set by the core.
3. The spec text issue in `verification.md` (pipeline-canvas, "bypass" covers two mechanisms) is still open. The UI now labels both as "Bypassed" with different reasons.
