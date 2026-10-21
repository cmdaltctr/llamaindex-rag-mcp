# ADR-089: Answer Stage Progress over a Streamed POST

- **Date:** 2026-10-21
- **Status:** Proposed
- **Deciders:** Dr Muhammad Aizat Bin Md Hawari
- **Related:** [ADR-059](059-claim-verification-stage.md) (claim verification stage), [ADR-077](077-web-workspace-client-foundation.md) (web client), [ADR-080](080-profiles-own-pipelines.md) (profiles own pipelines), [ADR-082](082-chats-live-in-the-workspace-database.md) (chats in the workspace database)
- **Change:** `openspec/changes/add-answer-stage-progress/` (design D1 to D10)

## Context

An answer takes 30 to 60 seconds. Chat sent one blocking
`POST /v1/collections/{collection}/answer` and printed "Waiting for the
answer." until the JSON arrived. A stuck call and a slow call looked the same.

The server knows the stage at every moment. Both answer paths (the direct
pipeline of the built-in profiles and the Answer graph of a user profile) call
the same step functions in `core/answer/stages.py`. Nothing carried that
knowledge to the page.

A browser `EventSource` can send only GET, with no body. A cookie session that
posts needs an allowed `Origin`. The question can be 4,096 characters, and the
request guard refuses credential-like values in a query string.

## Decision

1. **Transport: a POST that streams its own response.** A new route,
   `POST /v1/collections/{collection}/answer/stream`, takes the body of the
   blocking route and answers with `text/event-stream`. The page reads it with
   `fetch` and a small frame reader. The route has the same scope (`read`) and
   the same session Origin rule as the blocking route. The blocking route does
   not change.
2. **Closed, content-free frames.** A `stage` frame holds `stage` (one of
   `searching`, `writing`, `citing`, `verifying`), `sequence` (from 1) and
   `elapsed_ms`. Its schema is closed. One `result` frame ends the stream and
   holds the blocking route's result, after the same error redaction. There is
   no `retry:` line, no heartbeat and no failure frame.
3. **Open only after the first item.** The route waits for the first stage or
   the result before it sends a response. Every Engine `ValueError` comes before
   the first stage, so a refused request gets the blocking route's 400 and no
   stream.
4. **Stages are reported where their work starts.** `core/answer/progress.py`
   holds the stage enum, a reporter that drops repeats and backward steps, and a
   `ContextVar`. The shared steps report `writing`, `citing` and `verifying`;
   the direct pipeline reports `searching`, and the graph path reports it on
   the first `NODE_STARTED` event. A step that skips its work reports nothing.
   There is no node-to-stage map, and the graph runner does not change.
   With answering switched off, the graph path attaches no sink, so it
   reports no stage, as the direct path does.
5. **`on_stage` joins the public `Engine.answer` surface** as an optional,
   keyword-only callback. Callers that do not pass it (MCP, CLI, scripts,
   experiments) see no change.
6. **Cancel on disconnect, watched by the route.** A watch task checks
   `request.is_disconnected()` once a second and cancels the answer when the
   client has gone. This does not depend on the ASGI spec version the server
   reports. The page aborts its request when the turn leaves the page and before
   a Retry.
7. **The model call stays whole-reply.** The grounded-answer seam still refuses
   streaming. A stage callback never receives text.

## Consequences

### Positive

- Chat shows Searching, Writing the answer, Checking citations and, when claim
  checks run with a judge, Verifying claims, with a seconds counter.
- One vocabulary and one rule serve both answer paths. A user edit to the
  Answer graph never fails an answer; the list shows only what ran.
- A closed tab or a Retry no longer leaves a paid answer running on the direct
  path.
- No server state, no job table and no new admission rule.

### Negative

- No resume. A dropped connection loses the answer, as the blocking call did.
- Cancel on the graph path is cooperative. A started model call finishes and
  holds admission until it ends.
- The watch polls once a second, so a cancel can lag by up to one second.
- `stages.py` gains three `report_stage` calls, which are side effects in
  otherwise pure steps. They do nothing without an installed reporter.
- The page has a hand-written frame reader.

### Neutral

- Saved chats are unchanged. Only the finished result is stored.
- Older servers without the stream route make the page fall back to the
  blocking route (404 or 405 before any frame).

## Alternatives Considered

- **POST creates a job, GET follows it with `EventSource`.** Gives replay and
  reconnect. Needs a job table with a time to live, a check that one session
  cannot follow another's job, and a background task that holds admission.
  Replay has no use here, because a turn is saved only when its result reaches
  the page. Rejected.
- **GET with the question in the query string.** Puts question text in URLs,
  logs and history, breaks the content-free rule and the credential-in-query
  guard, and a reconnect would re-run the question. Rejected.
- **Content negotiation on the blocking route.** Gives one route two response
  types and a new branch. Rejected for a separate path and operation
  (`streamAnswer`).
- **Map graph node starts to stages.** A `NODE_STARTED` map would show "Writing
  the answer" for a no-evidence answer and "Verifying claims" when verification
  is off, because every node starts. Rejected for reports inside the shared
  steps.
- **Token-by-token streaming.** Touches the seam, citation resolution (which
  needs the whole text) and claim checks. Left for a later change; this ADR is
  its starting point.

## References

- `src/omrg/core/answer/progress.py`
- `src/omrg/core/answer/stages.py`, `src/omrg/core/answer/pipeline.py`
- `src/omrg/engine.py`, `src/omrg/engine_profiles.py`
- `src/omrg/transports/api/routes/answer_stream.py`
- `src/omrg/transports/api/openapi.yaml` (`streamAnswer`, `AnswerStageEvent`)
- `web/src/api/answerStream.ts`, `web/src/chat/AnswerProgress.tsx`
- `docs/guides/web-workspace.md` (Answer progress)
