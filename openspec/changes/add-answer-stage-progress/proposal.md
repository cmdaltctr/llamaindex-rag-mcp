# Proposal

## Why

An answer takes 30 to 60 seconds. During that time Chat prints one line, "Waiting for the answer.", and nothing else. The user cannot tell whether the system is searching, writing, checking citations or verifying claims. A stuck call and a slow call look the same.

The server already knows the stage at every moment. Both answer paths call the same step functions in `core/answer/stages.py`, in a fixed order. Nothing carries that knowledge to the page.

## What Changes

- Chat shows the current stage while an answer runs: **Searching**, **Writing the answer**, **Checking citations** and, only when claim verification runs with a judge model, **Verifying claims**. Finished stages stay in view with a tick. A seconds counter runs beside them.
- New route `POST /v1/collections/{collection}/answer/stream`. It takes the body of `POST .../answer` and answers with server-sent events: `stage` frames, then one `result` frame that carries the same answer result as the blocking route. A request the Engine rejects gets the blocking route's 400, because the stream opens only after the first stage. The page reads the stream with `fetch`.
- `Engine.answer` gains an optional `on_stage` callback. One rule serves both paths: a stage is reported where its work starts. The shared steps in `stages.py` report writing, citing and verifying. A step that skips its work reports nothing. Searching comes from the direct pipeline, or from the first graph step that starts. The runner does not change, and there is no node-to-stage map.
- An unknown or missing graph node never fails an answer. The stage list shows only what ran.
- The existing `POST .../answer` stays as it is. It is the fallback when the stream is unavailable, and it serves the MCP-adjacent and script callers.
- A closed browser tab, a chat the user leaves, a Retry or a cancelled request cancels the answer on the server and frees its admission. The route watches the client itself, so this does not depend on the server's ASGI version.
- Stage frames carry a stage name, a sequence number and elapsed milliseconds. They never carry question text, passage text, answer text, model names, keys or error detail.
- Saved chats are unchanged. Only the finished result is stored, as today.
- Docs and OpenAPI follow. A new ADR (ADR-089) is recommended; the design explains why. It is not written in this change.

## Non-goals

- Token-by-token text streaming. The model call stays whole-reply. The grounded-answer seam still refuses streaming and does not change. This is a possible follow-up.
- A Stop button. Cancel on disconnect is in scope; a button that cancels is a follow-up.
- Resuming an answer after a page reload or a dropped connection.
- Stage progress for MCP clients, the CLI or Search.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `workspace-chat`: the running turn shows its stage and a seconds counter; the fallback to the blocking call; stage events are never stored.
- `local-web-workspace`: the new streaming answer route, its scope and Origin rules, its closed frame schema, its content-free rule and its behaviour when the client leaves.
- `grounded-answer-synthesis`: the optional stage callback of the answer operation, its order, and the rule that the model call stays whole-reply.

## Impact

- Code (backend): new `src/omrg/core/answer/progress.py` (stage names, a reporter and a context reporter), one report call each in `synthesise_answer`, `resolve_citations` and `verify_answer` (`src/omrg/core/answer/stages.py`), one in `src/omrg/core/answer/pipeline.py`, an `on_stage` argument in `src/omrg/engine.py`, a small event sink in `src/omrg/engine_profiles.py`, and a new route module `src/omrg/transports/api/routes/answer_stream.py`. `engine.py` sits at 489 lines, so the design names a split if the change goes over 500.
- Code (web): `web/src/api/client.ts` gains a `stream` method, a new `web/src/api/answerStream.ts` holds the frame reader and the fallback, `useAnswer` in `web/src/api/mutations.ts` reports progress and aborts its request on unmount and on Retry, and `web/src/chat/AssistantTurn.tsx` shows it through a new small `AnswerProgress` component.
- API: one route added to `openapi.yaml`.
- Docs: `docs/guides/web-workspace.md` (Chat). `docs/guides/mcp-tools.md` does not change, because MCP tools are not touched.
- Tests: new backend and web tests; the clean-base tripwire counts in `tests/test_clean_base_tripwire.py` change.
- No new dependency. No change to the saved chat format, the workspace database or the settings.
- Security: the new POST route has the same scope (`read`) and the same session Origin rule as `POST .../answer`. The stage frames are content-free.
