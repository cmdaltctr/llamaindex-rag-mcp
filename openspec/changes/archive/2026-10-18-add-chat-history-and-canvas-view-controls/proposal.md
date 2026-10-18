# Proposal

## Why

Chat transcripts live in React state. A reload or a tab close loses every conversation, and the spec forbids server storage. Users also cannot group or delete chats. On the Studio canvas, a pipeline can only be read in the layout it was saved in, and the canvas cannot fill the screen.

## What Changes

- Store chats in the workspace database (`workspace.db`, schema version 5). A chat keeps its turns, each with the question, the collection asked and the finished answer. Reopening a chat shows the saved answers and does not ask again.
- Add chat folders. A chat sits in no folder or in one folder. Dragging a chat onto a folder moves it. Folders have one level only.
- Add delete for one chat and for many chats (select, then delete). Deleting a folder deletes the chats inside it. Every delete asks first and names the count.
- Add a citation popover. Pressing a citation chip, or a `[n]` marker in the answer text, opens a popover with the evidence text, the lineage (source, version, chunk position, page, merged chunk ids) and the chunk's stored metadata. The chunk viewer shows the same metadata. No API change.
- Add two buttons at the top left of the Studio canvas: arrange the pipeline horizontally or vertically, and full screen. Full screen shows the canvas, its toolbar and the canvas panel, with an "X" in the toolbar to leave it.
- Add ADR-082 (Accepted on approval) for the storage and delete decisions.
- **BREAKING (spec only):** the rule "Transcripts SHALL NOT be stored server-side" is removed from `workspace-chat`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-chat`: stored chats, folders, drag and drop, single and bulk delete, folder delete, history list placement, and the citation popover with lineage and metadata.
- `workspace-studio`: layout direction button and full screen canvas mode.

## Impact

- `src/omrg/integrations/workspace_sqlite/schema.py`: migration 5 (`chat_folders`, `chats`, `chat_turns`).
- New chat repository protocol in `src/omrg/core/workspace/` and its SQLite implementation in `integrations/workspace_sqlite/`.
- New `transports/api/routes/chats.py` (browser session only), `openapi.yaml`, and web API client functions.
- `web/src/chat/` (history sidebar, folders, selection, dialogs, citation popover), `web/src/components/ChunkViewer.tsx` and a new `components/ui/popover.tsx` (logic moved from `studio/InfoPopover.tsx`), `web/src/studio/FlowSurface.tsx`, `OperationNode.tsx`, `CanvasEditor.tsx`, `graph.ts`, the Python `GraphLayout` model (new optional `direction`), `App.tsx` (full screen hides the shell), `web/src/lib/routes.ts` (chat id).
- The stdio MCP server, the CLI and the watcher do not read chats (ADR-080). No new dependency for the arrange button (layered layout written by hand).
