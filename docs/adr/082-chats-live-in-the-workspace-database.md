# ADR-082: Chats Live in the Workspace Database

- **Date:** 2026-10-18
- **Status:** Accepted
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-080](080-profiles-own-pipelines.md) (the web server owns the workspace), [ADR-081](081-per-profile-embedding-models.md) (schema version 4)
- **Change:** `openspec/changes/add-chat-history-and-canvas-view-controls/` (design D1 to D6)

## Context

Chat transcripts lived in React state. A reload lost them. The `workspace-chat` spec said transcripts must not be stored server-side. The user now needs chats to persist, to be grouped, and to be deleted.

## Decision

1. **Store chats in `workspace.db` (schema version 5).** Tables `chat_folders`, `chats` and `chat_turns`. The same file, backup-before-migrate and owner-only rules apply as for profiles.
2. **Store the finished answer with each turn.** Opening a chat never calls the model again.
3. **Folders have one level.** A chat is in one folder or none.
4. **Delete is permanent.** A confirmation states the count. Deleting a folder deletes its chats through `ON DELETE CASCADE`.
5. **Only the browser session of `omrg web` reads or writes chats** (ADR-080). The routes use `require_session`, so a bearer token for an MCP or notebook client is refused even with the `read` scope. Deletes need the `manage` scope, as other destructive routes do. The CLI, the stdio MCP server and the watcher do not read chats.
6. **The spec rule "Transcripts SHALL NOT be stored server-side" is removed.**
7. **The user sets the folder order (schema version 6, 2026-10-23).** Migration 6 adds `chat_folders.position` and numbers existing folders in creation order. `PUT /v1/chat-folders/order` takes every folder id once. A new folder goes to the end.

## Consequences

- Answers contain evidence text from the user's documents. They sit in the same owner-only file as other workspace records. A user who deletes a source still has the old evidence text in saved chats until the chat is deleted.
- A reload during a pending answer loses that one turn.
- Each later change to the chat tables needs a numbered migration.
- An older `omrg` install that opens the version 5 file refuses it as newer than it supports. Migration 4 had the same effect. An `omrs` install from before migration 6 refuses a version 6 file in the same way.

## Alternatives considered

- **Browser storage (IndexedDB).** Lost in a new browser, invisible to the server.
- **A separate SQLite file.** A second file to back up and migrate.
- **Store questions only and re-ask.** Costs model calls and changes answers.
- **Trash with undo.** More state and screens. Not requested.
