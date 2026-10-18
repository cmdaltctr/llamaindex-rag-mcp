# Design

## Context

Chat today: `ChatView` holds `turns` in `useState`. `AssistantTurn` calls `useAnswer` on mount, so a remount re-asks the question. The route is `#/chat/<collection>`, and a second segment parses to Home. The workspace database (`workspace.db`, schema version 4) holds profiles, pipelines and runs. Only `omrg web` writes to it (ADR-080). `schema.connect` already sets `PRAGMA foreign_keys = ON`. Other processes open the file read-only and refuse a schema version newer than they know.

Canvas today: `CanvasEditor` renders `FlowSurface` (React Flow) and the right panel. Node positions live in the draft layout. The layout reaches the server only through the "Save layout" action (`PUT /v1/pipelines/{id}/layout`), which never creates a revision. `toLayout` and `fromDocument` copy only `positions`, `viewport` and `selection`. The route stores the layout dict as given, but the Python `GraphLayout` model uses `extra="forbid"`. `OperationNode` fixes handles to Left and Right. `App.tsx` already switches the shell on `onCanvas`.

Auth: bearer tokens (notebook and MCP clients) hold `graph`, `read` and `run`. `require_session(scope)` admits the browser session only, and destructive routes use `require_session("manage")`.

## Goals / Non-Goals

**Goals:** chats survive reload and restart; folders, drag and drop, single and bulk delete; arrange button; full screen.

**Non-Goals:** sending earlier turns to the model (each question still answers alone); chat rename, search, export, sharing; nested folders; undo or trash for deletes; reading chats from the CLI, MCP or a bearer token; a layout library; saving the full screen state; drag and drop on touch screens (the "Move to" menu covers touch).

## Decisions

**D1. Store chats in `workspace.db`, migration 5.** Tables:

- `chat_folders(folder_id TEXT PK, name TEXT NOT NULL, created_at)`
- `chats(chat_id TEXT PK, folder_id TEXT NULL REFERENCES chat_folders ON DELETE CASCADE, title TEXT NOT NULL, created_at, updated_at)`
- `chat_turns(chat_id TEXT REFERENCES chats ON DELETE CASCADE, position INTEGER, collection TEXT, question TEXT, answer_json TEXT, created_at, PRIMARY KEY (chat_id, position))`
- index `chats_by_folder`, `chats_by_updated`.

`connect` already enforces foreign keys, so a folder delete removes its chats and their turns in one statement. The existing migrate step backs up the file first. Alternatives: browser IndexedDB (lost in a new browser, invisible to the server, not the "persistent chat db" the user asked for); a separate SQLite file (a second file to back up and migrate).

**D2. Store the finished answer, not only the question.** `AssistantTurn` takes an optional saved result. With one, it renders the body and skips `useAnswer`. Without one, it asks, and the view then posts the turn. Alternative: store questions and re-ask on open. Rejected: it costs model calls and gives different answers.

**D3. The client saves a turn when a usable answer arrives.** "Usable" means the call succeeded and `result.status !== "error"`. A Retry that then succeeds saves the turn at that point. The first usable answer of a new chat creates the chat (`POST /v1/chats` with the title), then posts the turn. The server assigns `position` as `MAX(position)+1` inside the write transaction, so two tabs never collide. If the chat was deleted while the answer was pending, the server returns 404 and the client drops the turn without a notice. A reload during a pending answer loses that one turn. Accepted.

**D4. API, browser session only.** Saved answers carry evidence text from private documents, and a bearer token for an MCP or notebook client must not read or delete them. All chat routes use `require_session("read")`. The delete routes use `require_session("manage")`, the same as other destructive routes.

| Route | Purpose |
| --- | --- |
| `GET /v1/chats` | folders and chats (no turns), newest chat first |
| `POST /v1/chats` | create a chat: `title`, optional `folder_id` |
| `GET /v1/chats/{chat_id}` | one chat with its turns in order |
| `PATCH /v1/chats/{chat_id}` | move: `folder_id` or `null` |
| `POST /v1/chats/{chat_id}/turns` | append a turn: `collection`, `question`, `answer` |
| `DELETE /v1/chats/{chat_id}` | delete one chat |
| `POST /v1/chats/delete` | delete many: `chat_ids` (1 to 500) |
| `POST /v1/chat-folders` | create a folder: `name` |
| `PATCH /v1/chat-folders/{folder_id}` | rename |
| `DELETE /v1/chat-folders/{folder_id}` | delete the folder and its chats |

Delete responses return `{"chats": n, "folders": m}`. Bulk delete is all or nothing: an unknown id fails the request and deletes nothing. Body limits: title 1 to 200 characters, folder name 1 to 100, question 1 to 10,000, answer JSON at most 2 MiB after encoding (413 above it). Ids are server-made UUIDs. Routes delegate to a `ChatRepository` protocol in `core/workspace/`, built in `compose`; no logic in routes (invariant 3). `openapi.yaml` gains the contract.

**D5. Hard delete.** The user asked for delete, and the confirmation states the count. No trash.

**D6. Drag and drop with native HTML5 events.** No new dependency. Each chat row is `draggable`; each folder row and the "No folder" row are drop targets. A "Move to" menu on each chat gives the same action by keyboard and on touch (WCAG 2.5.7). Bulk select uses a Select mode with checkboxes and a "Delete selected (n)" action. One level of folders keeps the list simple.

**D7. Route.** `#/chat/<collection>/<chatId>`. A route without a chat id shows a new empty chat. Opening a stored chat from the history list routes to the collection of its last turn. Selecting another knowledge base keeps the chat id. A chat id the server does not know shows a short notice and a new empty chat.

**D8. History layout.** From `lg` up: history column on the left (16rem), transcript in the centre, knowledge base panel on the right. Below `lg`: a "History" button above the transcript opens the list in a sheet. The composer stays docked as today.

**D9. Arrange = layered layout, written by hand.** Each node's layer is the longest path from a node with no incoming edge. A cycle or a lone node falls back to input order in layer 0. Layers go along the main axis, and the nodes of a layer go across it, using measured sizes and fixed gaps. The direction (`horizontal` or `vertical`) is a new optional `direction` field on the layout. That needs four edits, because each one would drop or refuse the field otherwise: the TS `GraphLayout` and `DraftLayout` types, `fromDocument` and `toLayout`, the Python `GraphLayout` model (`extra="forbid"`), and the `openapi.yaml` layout schema. Absent means horizontal, so stored layouts stay valid. Arranging changes the draft layout. It reaches the server through the existing "Save layout" action, so it behaves like a drag. `OperationNode` reads the direction from node data and sets handle positions (Left/Right or Top/Bottom). After arranging, the view calls `fitView`. Alternative: dagre or elkjs. Rejected: a dependency for graphs of about ten nodes (CLAUDE.md asks before new dependencies).

**D10. Full screen = a context flag, CSS overlay.** A `CanvasFullScreen` context in `App.tsx` lets `Shell` render only `<main>`. `CanvasEditor` then renders only the surface, the toolbar and an "X" button, as a fixed overlay that fills the window. Not the browser Fullscreen API: Escape and the "X" then behave the same, and tests run in jsdom. `FlowSurface` stays mounted, so selection and viewport are kept. On entry, focus moves to the "X". On exit, focus returns to the full screen button (`useReturnFocus`). The Escape handler ignores the key when focus is in a text field or a menu is open. The flag resets when the route leaves the canvas. It is not stored.

**D11. Toolbar placement.** A React Flow `Panel position="top-left"` in a new `ViewToolbar.tsx`. The zoom controls stay at the bottom left. An empty graph shows no surface, so it shows no toolbar.

**D12. Citation popover.** Today the chips and the evidence rows open the chunk viewer dialog. `GET .../chunks/{id}` already returns the full stored `metadata`, but `ChunkViewer` does not render it. Inline `[n]` markers are plain text. Decisions:

- Markers: split the answer text on `/\[(\d+)\]/`. A marker becomes a button only when its number is in `citations[].ordinal`. Other markers stay text, so no citation is invented (the rule the current code comment states). The text stays plain text, never markup.
- Popover: move the positioning and dismissal logic of `studio/InfoPopover.tsx` (portal on the body, Escape, outside click, focus return) into a `components/ui/popover.tsx` primitive. `InfoPopover` then uses it, so there is one implementation. `CitationPopover.tsx` in `web/src/chat/` renders the content.
- Data: the evidence text, score and lineage come from the answer result (`Evidence` matches `Citation` by ordinal), so they show at once and work for stored chats. The Metadata section loads the chunk with the existing chunk query when the popover opens. A 404 shows "The stored chunk is not available" and keeps the evidence text.
- Grouping: Lineage holds the five lineage keys, `page_label` and `chunk_ids`. Metadata holds every other key, sorted by name, as `key: value`. Arrays and objects show as compact JSON. Values over 200 characters are cut with "Show all". The stored index does not record which keys a chunk got from its source document. The UI therefore does not label keys as inherited. It shows what is stored, and document-level keys (file name, title, author, extracted keywords) appear in Metadata.
- `ChunkViewer` gets the same two sections through a shared `ChunkMetadata.tsx`.
- No API change.

## Risks / Trade-offs

- [Stored answers hold evidence text from private documents] → owner-only file (`touch_private`), session-only routes (D4); ADR-082 records it.
- [Migration 5 on a user's real file] → existing backup-before-migrate; a test migrates a v4 file with profiles in it.
- [An older `omrg` (for example a stdio MCP server from another install) opens the v5 file and refuses the newer version] → the same trade-off as migration 4; ADR-082 names it.
- [A deleted source still has evidence text in saved chats] → stated in ADR-082; the user deletes the chat.
- [`FlowSurface.tsx` is 231 lines] → toolbar and layout maths go in `ViewToolbar.tsx` and `arrange.ts`.
- [Metadata can hold an absolute file path or a long extracted summary] → it is the user's own local index, read only by the browser session; long values are cut.
- [Moving `InfoPopover` logic could change Studio help popovers] → the existing `InfoPopover.test.tsx` must pass unchanged.
- [`ChatView.tsx` would pass 200 lines] → split into `ChatHistory.tsx`, `ChatFolderRow.tsx`, `DeleteChatsDialog.tsx` and `useChatSession.ts`.

## Migration Plan

Migration 5 runs when `omrg web` opens the workspace. Rollback: restore the `workspace.db.v4-to-v5.*.bak` file that the migrate step writes, then run the previous version.
