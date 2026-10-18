# Tasks

Work in the sibling worktree `llamaindex-rag-mcp-feat-add-chat-history-and-canvas-view-controls` on `feat/add-chat-history-and-canvas-view-controls`, forked from `integration/core-web` (the user approved the plan and the worktree on 2026-10-18). Verify `git rev-parse --show-toplevel` and `git branch --show-current` before any command that changes state. Commit with `uv run git commit`.

## 1. Chat storage (backend)

- [x] 1.1 Write failing tests for migration 5: a v4 file with profiles migrates, a backup file appears, the three tables and two indexes exist, and a folder delete cascades to chats and turns. Then add migration 5 in `integrations/workspace_sqlite/schema.py`. Verify: the new tests pass, and the cascade test fails with `ON DELETE CASCADE` removed.
- [x] 1.2 Write failing tests, then add the `ChatRepository` protocol in `core/workspace/` and its SQLite implementation in `integrations/workspace_sqlite/chats.py`: create, append turn (server-assigned position), list, get, move, delete one, delete many (all or nothing), folder create, rename and delete. Verify: the new repository tests pass; the all-or-nothing test fails when the transaction is removed.
- [x] 1.3 Wire the repository in `compose`, then add `transports/api/routes/chats.py` with the D4 routes, body limits, `require_session("read")` and `require_session("manage")` for deletes. Verify: route tests cover each route, the 413 limit, the count in delete responses, and a bearer token refused on `GET /v1/chats`.
- [x] 1.4 Add the chat routes to `openapi.yaml`. Verify: `uv run pytest tests/test_openapi_conformance.py tests/test_contract_coverage.py` passes.
- [x] 1.5 Run the backend gate. Verify: `uv run lint-imports` and `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q` pass, including the 500-line ceiling.

## 2. Chat history (web)

- [ ] 2.1 Add API client functions, query keys and mutations for chats and folders in `web/src/api/`. Verify: the new unit tests in `web/src/api` pass.
- [ ] 2.2 Add the chat id to the chat route (`#/chat/<collection>/<chat-id>`) in `web/src/lib/routes.ts`. Verify: route parse and format tests pass, and an unknown chat id test shows a new empty chat.
- [ ] 2.3 Write failing tests, then store turns: `AssistantTurn` renders a saved result without calling `useAnswer`; the view creates the chat on the first usable answer, saves each usable answer, skips error results, and ignores a 404 for a deleted chat. Verify: the reload scenario test passes, and fails when the save call is removed.
- [ ] 2.4 Add the history list (left column from `lg`, History sheet below `lg`) with folders: create, rename, drag a chat onto a folder or onto "No folder", and a "Move to" menu. Verify: tests for drop, keyboard move and folder rename pass.
- [ ] 2.5 Add Select mode, bulk delete, single delete and folder delete, each with a count confirmation. Verify: tests for the delete scenarios, delete of the open chat, and cancel pass.
- [ ] 2.6 Move the popover positioning and dismissal from `studio/InfoPopover.tsx` into `components/ui/popover.tsx`, and make `InfoPopover` use it. Verify: `InfoPopover.test.tsx` passes unchanged, and new primitive tests cover Escape, outside click and focus return.
- [ ] 2.7 Write failing tests, then add `ChunkMetadata.tsx` (Lineage and Metadata sections, cut values with "Show all") and use it in `ChunkViewer`. Verify: `ChunkViewer.test.tsx` shows the metadata keys and the cut, and fails when the section is removed.
- [ ] 2.8 Write failing tests, then add `CitationPopover.tsx` and open it from the chips and from `[n]` markers that match a citation ordinal. Verify: tests cover the popover content, a merged citation listing both chunk ids, a marker with no citation staying plain text, Escape closing with focus return, and a 404 chunk keeping the saved evidence text.
- [ ] 2.9 Update the chat section of `docs/guides/` to describe stored chats, folders and delete. Verify: `grep -rni "not stored\|transcript.*lost" docs/guides` finds no stale statement.

## 3. Canvas view controls (web)

- [ ] 3.1 Add the optional `direction` field to the layout in all four places (TS types, `fromDocument`/`toLayout`, Python `GraphLayout`, `openapi.yaml`). Verify: a round-trip test keeps `direction` through `toLayout(fromDocument(...))`, a Python test accepts it, and a layout without it reads as horizontal.
- [ ] 3.2 Write failing tests, then add `web/src/studio/arrange.ts`: layering by longest path, both directions, and the cycle fallback. Verify: the unit tests pass, and fail when the layering is replaced by input order.
- [ ] 3.3 Make `OperationNode` handles follow the direction. Verify: a node test checks Left/Right for horizontal and Top/Bottom for vertical.
- [ ] 3.4 Add `ViewToolbar.tsx` (top-left `Panel`) with the arrange button. Verify: tests show positions change, no revision call is made, and a read-only canvas sends no layout call.
- [ ] 3.5 Add full screen: the context flag in `App.tsx`, the overlay in `CanvasEditor`, the "X" button, Escape, focus moves, and reset on leaving the canvas. Verify: tests for enter, "X", Escape, Escape in a text field, and kept selection pass.
- [ ] 3.6 Update the Studio section of `docs/guides/` for the toolbar. Verify: the guide names both buttons.
- [ ] 3.7 Check chat and canvas in a browser at 1280 px and 390 px with Chrome DevTools. Verify: no sideways scroll; screenshots saved under `docs/guides/images/web-workspace/`.

## 4. Close

- [ ] 4.1 Run `./scripts/local_ci.sh`, the web gate (lint, typecheck, tests, build) and `openspec validate --all --strict`. Verify: all pass.
- [ ] 4.2 After review, set ADR-082 to Accepted in the file and in `docs/adr/ADR_README.md`, then archive the change.
