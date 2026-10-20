# Design

## Context

Observed in the code:

- Chat sends one blocking `POST /v1/collections/{collection}/answer` (`answer_collection` in `routes/documents.py`). It holds `admitted(runtime)` for the whole call, calls `runtime.engine.answer(...)`, redacts the `error` text with `_redact_error` and returns JSON. `AssistantTurn.tsx` prints "Waiting for the answer." until the JSON arrives.
- **Direct path** (built-in profiles `documents`, `codebase`): `Engine.answer` calls `core.answer.pipeline.answer`. Its steps run in this order: retrieval in `asyncio.to_thread`, `prepare_evidence`, `synthesise_answer`, `resolve_citations`, `verify_answer`, `answered_result`. Three early returns skip later steps: the master switch (`disabled_result`), an empty evidence list (`no_evidence_result`) and a missing model (`no_provider_result`). `verify_answer` runs the judge only when `answer.verify_claims` is on and the answer is grounded.
- **User-profile path**: `Engine.answer` calls `engine_profiles.answer`. That calls `_run_async`, which calls `engine.run_pipeline({"graph": graph}, inputs=...)`. `run_pipeline` already accepts `on_event: EventSink`. The runner emits ordered `PipelineEvent` values with `node_id`, `sequence` and `kind` (`NODE_STARTED`, `NODE_BYPASSED`, `NODE_SKIPPED` and others). The event carries the node id, not the operation. The graph document (`graph["nodes"]`, each with `id` and `operation`) is in hand inside `_run_async`, so a node-id to operation map is cheap. A disabled node emits `NODE_BYPASSED` and no `NODE_STARTED` (`execution.py`, `_bypass`). Runs on one Engine are serialised.
- The grounded-answer seam (`core/answer/synthesis.py`) returns the whole reply and `stream_complete` raises `NotImplementedError`.
- Existing SSE code: `runs.py` (`_frame`, `STREAM_RETRY_MS`, `API_HEADERS`, `Cache-Control: no-store`, `X-Accel-Buffering: no`) and `logs.py` reuse the same helpers. Both are GET streams with replay.
- A cookie session that posts needs an allowed `Origin` header (`security.py`, `_authenticate`). A bearer credential skips that check. A browser `EventSource` can only send GET, with no body.
- `engine.py` is 489 lines. `pipeline.py` is 356. `engine_profiles.py` is 356. `documents.py` is 221. `mutations.ts` is 235.
- Chats are stored by `useChatSession.onResult`, which receives only the finished `AnswerResult`.

## Goals / Non-Goals

**Goals:**

- Chat shows the current stage of a running answer, on both paths, with one vocabulary.
- The blocking route and the MCP and CLI callers do not change.
- A missing or odd graph step never fails an answer.
- Stage frames are content-free.

**Non-Goals:**

- Token-by-token streaming of the answer text. The model call stays whole-reply. This is a possible follow-up, and it needs its own change because it touches the seam, citation resolution (which needs the whole text) and claim verification.
- A Stop button, resume after reload, and progress for MCP, CLI or Search.
- A stage for the work inside one step (for example per claim in verification).

## Decisions

### D1. Transport: a POST whose response is an event stream, read with `fetch`

Three options were compared.

| | (a) POST makes a job, GET follows it | (b) POST streams its own response | (c) GET with the query in the URL |
|---|---|---|---|
| Browser API | `EventSource` | `fetch` plus a body reader | `EventSource` |
| Auth and Origin | POST has the Origin rule, GET stream is read-only. Needs a job-id check so one session cannot follow another's job. | One route. Same scope (`read`), same session Origin rule as today. | Question text sits in the URL. The guard rejects credential-like query values. URLs reach logs and history. |
| Replay and reconnect | Yes (`Last-Event-ID`) | None. A dropped connection loses the answer, as the blocking call does today. | Yes, but a reconnect would re-run the question. |
| Tab close | Job runs on unless a cancel rule is added. | The server sees the disconnect and can cancel. | Same as (b). |
| Server memory | A job table with a time to live, a cap and clean-up. | None. | None. |
| `admitted(runtime)` | Held by a background task, not by a request. Shutdown must cancel or wait for the task. | Held by the request for its whole life. Same as today. | Same as (b). |
| Saved chats | Unchanged. The page still receives the result and saves it. | Unchanged. | Unchanged. |
| New web code | Small: reuse `EventSource` and `FakeEventSource`. | A frame reader (about 40 lines) and a fake stream for tests. | Small. |
| Query limits | None. | None. | 4,096-character question and `metadata_filter` object do not fit a URL safely. |

**Decision: (b).** It adds no server state, it keeps one admission rule, and it keeps the Origin protection that POST already has. Option (a) buys replay, and replay has no use here. A reload loses the turn anyway, because a turn is saved only when its result reaches the page. Option (c) puts the question in the URL, which breaks the content-free rule and the credential-in-query guard.

The cost of (b) is a hand-written frame reader in the page. Every current browser supports a streamed `fetch` body. The fallback in D7 covers the rest.

The route is a separate path (`.../answer/stream`, operation `streamAnswer`) and not a content-negotiated variant of the blocking route. The blocking route keeps one response type, one OpenAPI entry and no new branch.

### D2. Wire format

The response is `text/event-stream` with the headers of `streamRunEvents` (`API_HEADERS`, `Cache-Control: no-store`, `X-Accel-Buffering: no`). The route sends no `retry:` line, because nothing reconnects. It sends no heartbeat: the connection is on loopback and a browser `fetch` has no idle timeout.

Frames use the existing `_frame` helper:

```
event: stage
data: {"stage":"searching","sequence":1,"elapsed_ms":412}

event: stage
data: {"stage":"writing","sequence":2,"elapsed_ms":2210}

event: result
data: { ...the AnswerResult of the blocking route... }
```

- `stage`: closed schema `AnswerStageEvent` with `stage` (enum `searching`, `writing`, `citing`, `verifying`), `sequence` (integer from 1) and `elapsed_ms` (integer). `elapsed_ms` counts from admission.
- `result`: the blocking route's result, after `_redact_error`. It is always the last frame of a normal stream.
- `failure`: `{"status": <int>, "message": <string>}`. Used only when the Engine raises `ValueError` after the stream opened. The blocking route answers 400 there, and a stream cannot change its status after the first byte. The page turns the frame into an `ApiError` of kind `http`, so `describeError` shows the usual line.

The conformance helper `_check_frames` demands a `retry` hint on the first frame. That rule fits the GET streams only. Task 3.6 limits it to operations without a request body.

### D3. Stage vocabulary and the core callback

New module `src/omrg/core/answer/progress.py`:

- `AnswerStage`, a `StrEnum` with four values in order: `searching`, `writing`, `citing`, `verifying`.
- `StageReporter(callback)`: a small object that the paths call as `reporter.enter(stage)`. It drops a repeat of the current stage and drops a stage that ranks lower than one already sent, so the order is monotonic. It catches and logs any error from the callback, so a broken consumer never fails an answer. With `callback=None` every call does nothing.
- `operation_stage(operation_id) -> AnswerStage | None`, the graph map (D4).

The callback type is `Callable[[AnswerStage], None]`, a plain function called on the event loop. Both paths run on the loop, so no thread hop is needed. The route's callback only calls `put_nowait` on a queue.

`core.answer.pipeline.answer` gains `on_stage: Callable[[AnswerStage], None] | None = None`. It creates the reporter and calls it at four points:

1. `searching` after the master-switch check and before retrieval.
2. `writing` after the evidence and provider checks pass, before `synthesise_answer`.
3. `citing` after a synthesis that gave text, before `resolve_citations`.
4. `verifying` only when `verify_answer` will call the judge: `answer.verify_claims` is on and the citations are grounded. This is the test `verify_answer` applies. The judge may still report `verification_skipped`; the stage then ends at once and the result carries the reason.

The `result` frame ends the stream, so nothing follows `verifying`.

A request rejected by `_validate_request` and a disabled operation report no stage. An empty evidence list reports `searching` only. A missing provider reports `searching` only. A generation failure reports `searching` and `writing`. These match the scenarios in the delta spec.

`Engine.answer` gets the same optional `on_stage` argument and passes it to the core call and to `engine_profiles.answer`. `omrg.Engine` is the public API. The argument is optional and keyword-only, so no caller breaks. `engine.py` has 489 lines. The extra argument, its docstring line and two pass-through lines add about 8, which is close to the 500-line ceiling. Task 2.3 checks the count. If the file goes over 500, the user-profile branch of `Engine.answer` moves into one helper in `engine_profiles.py`.

The seam is untouched. `stream_complete` keeps raising. `on_stage` never receives text.

### D4. User-profile path: map node events to the same stages

`engine_profiles._run_async` gets an optional `on_event` argument and passes it to `engine.run_pipeline`. `engine_profiles.answer` builds the sink:

1. Read the graph that `_run_async` already holds. Build `{node_id: operation}` from `graph["nodes"]`.
2. For each `NODE_STARTED` event, look up the operation and call `operation_stage`. If it returns a stage, call `reporter.enter(stage)`.
3. Ignore every other event kind. `NODE_BYPASSED` and `NODE_SKIPPED` never start a stage, so a disabled `verify.claims` node never shows "Verifying claims".

The map in `operation_stage`:

| Operation id | Stage |
|---|---|
| `retrieve.*`, `combine.*`, `select.*`, `context.*`, `answer.prepare_evidence` | `searching` |
| `answer.synthesise` | `writing` |
| `answer.cite` | `citing` |
| `verify.claims` | `verifying` |
| anything else | no stage |

The map matches by prefix for the retrieval families, so a new retrieval operation needs no edit. It matches by exact id for the other three.

How a user edit degrades:

- **Unknown node** (a new operation, or a plugin step): no stage. The current stage stays on screen.
- **Missing node** (no cite step, no verify step): that stage never appears. The list shows what ran.
- **Reordered or repeated nodes**: `StageReporter` drops repeats and backward steps. The list never shows a stage twice.
- **No node maps to a stage**: the page gets zero `stage` frames and shows "Waiting for the answer." with the counter (D7).
- **A sink error**: the runner logs it and the run continues. The runner already does this (`events.py`).

The runner, `PipelineEvent` and the graph adapters do not change. Runs on one Engine are serialised, so a second graph-path answer waits for the first. Its first `NODE_STARTED` comes late, and the page shows "Waiting for the answer." and the counter until it does.

### D5. The route: producer task, queue, cancel on leave

New module `src/omrg/transports/api/routes/answer_stream.py`, registered next to the other routers in `app.py`. `documents.py` does not change. The new module imports `AnswerBody`, `_redact_error` and `_answer_failure` from `documents.py`, as `logs.py` imports `_frame` from `runs.py`.

Flow:

1. The handler checks scope `read` (`ReadScope`), validates `AnswerBody`, and enters runtime admission before it returns. If admission is closed, it answers 503. Admission is held by an `AsyncExitStack` that the stream generator closes in its `finally`.
2. The generator starts a producer task: `runtime.engine.answer(..., on_stage=enqueue)`. `enqueue` puts an `AnswerStageEvent` on an `asyncio.Queue`. The task puts the result (or the failure) on the queue and then a sentinel.
3. The generator reads the queue and yields frames: `stage`, then `result` or `failure`.
4. In `finally`, if the producer task is not done, the generator cancels it and awaits it with the cancellation suppressed. Then it closes the admission stack.

**Client leaves: cancel, not finish.** An answer costs model time and money, and its result has nowhere to go: the page saves a turn only when the result reaches it. Letting it run on would also double the cost when the user presses Retry. Starlette cancels the generator when the client drops, so the `finally` block runs.

What a cancel does on each path:

- Direct path: the awaiting task is cancelled. The model call is cancelled where the client supports it. A retrieval thread already started in `to_thread` cannot be stopped. It ends and its result is dropped.
- Graph path: `run_pipeline` turns an outer cancel into a cooperative cancel. A node that has started finishes. The model call in flight is therefore not interrupted. Admission stays held until it ends. This matches how shutdown treats started nodes.

Shutdown: the stream holds admission like the blocking route, so graceful shutdown waits for it. The route sends no `server.closing` frame.

Two answers at once: each request has its own queue, task and frames. The direct path runs them in parallel. The graph path serialises them on the Engine.

Memory: one queue of at most six small items per stream. Nothing outlives the request.

### D6. Web client: a `stream` method and a frame reader

- `ApiClient` (`web/src/api/client.ts`) gains `stream(method, path, input)`. It shares `isApiPath`, the headers and the `network` error mapping with `request`. It returns the `Response` when the status is OK and the content type is `text/event-stream`. A non-OK status is parsed as the JSON error envelope and thrown as `ApiError` of kind `http`, exactly as `request` does. `client.ts` is 152 lines, so it has room.
- New `web/src/api/answerStream.ts` holds:
  - `readFrames(body)`: reads a `ReadableStream` of bytes with `TextDecoder`, splits on a blank line, and yields `{event, data}`. It ignores comment lines and unknown events.
  - `answerCollectionStreaming(api, collection, controls, {onStage, signal})`: calls `stream`, handles `stage`, `result` and `failure` frames, and returns the `AnswerResult`.
- The AbortSignal from the mutation cancels the fetch, which is the disconnect that D5 acts on.

### D7. Fallback rules

`answerCollectionStreaming` falls back to `answerCollection` only for these, and only before any frame arrived:

- the browser has no `fetch` body reader (`response.body?.getReader` is missing);
- the stream route answers 404 or 405, or answers 200 with a content type that is not `text/event-stream`.

It does not fall back for 400, 401, 403, 5xx or a network failure. A refusal or an outage would only repeat on the blocking route, and a fallback after a partial stream would start a second paid answer. A stream that ends with no `result` frame throws `ApiError` kind `network`, and `describeError` shows the friendly line with Retry.

Existing ChatView tests use a fake server that answers 404 for unknown routes (`fakeDocumentsServer.ts`). Those tests therefore pass through the fallback unchanged. The new tests cover the stream path.

### D8. The page: hook and display

`useAnswer` in `web/src/api/mutations.ts` keeps its mutation key `ANSWER_MUTATION_KEY`, because `ChatView` counts pending answers through it. It gains a `progress` value in its return: `{ stages: AnswerStage[] }`. It resets the list when `mutate` is called. It adds a stage as each `stage` frame arrives, and drops duplicates.

New component `web/src/chat/AnswerProgress.tsx` (about 70 lines), used by `AssistantTurn` in place of the plain "Waiting" paragraph:

- A `ul` of the stages seen so far, in arrival order. A finished stage has a lucide `Check` icon. The current stage has a lucide `Loader2` icon that spins only under `motion-safe`.
- Labels: "Searching", "Writing the answer", "Checking citations", "Verifying claims". The component keeps no row for a stage that has not started, so it never needs to know whether verification is on.
- A counter in `text-meta text-muted-foreground tabular-nums`, for example "12 s". It starts when the question is sent and uses one `setInterval` that the component clears on unmount. It sits outside the live region and is `aria-hidden`.
- The current stage line is the only `role="status"` element with `aria-live="polite"`, so a screen reader hears each stage once.
- With no stage seen, the component shows today's line, "Waiting for the answer.", with the same counter.
- Colour comes from tokens (`text-muted-foreground`, `text-foreground`). It adds no literal colour and no CSS file. It uses no primitive wrapper because it is text and icons only.
- At 390 px the list stays one column. At 1280 px it sits under the "Answer from <collection>" label at the same width as the answer.

When the result arrives, `AssistantTurn` renders the answer and drops the component. A reopened chat has `saved` set, so it never mounts the component.

### D9. Persistence and safety

- `useChatSession.onResult` still receives only the `AnswerResult`. Stage values live in hook state and are never passed to it. No backend table, route or schema changes.
- Safety: `AnswerStageEvent` has `additionalProperties: false` and three fields. The producer builds it from the stage enum and a counter, never from the request. A test posts a marker question and a failing model whose error text holds a saved key, then asserts that the raw bytes of every `stage` frame hold neither. The `result` frame passes through `_redact_error`, as the blocking route does. The page still shows errors through `describeError`.
- The `failure` frame's message is built from the same `str(exc)` the blocking route puts in its 400 body, so it adds no new text.

### D10. ADR

An ADR is warranted. The next free number is **ADR-087** (the folder ends at 086). It would record: why a streamed POST and not a job plus GET or a GET with the query; cancel on disconnect; the closed content-free frame; and that `on_stage` joins the public `Engine.answer` surface. It would also state that the model call stays whole-reply, so a later token-streaming change has a clear starting point. This proposal does not write the ADR. Task 8.1 writes it at implementation time.

## Risks / Trade-offs

- **No resume.** A dropped connection loses the answer, as the blocking call does today. Accepted. A job table (option a) is the way to add this later.
- **Cancel on the graph path is cooperative.** A started model call finishes and holds admission until it ends. Accepted, and noted in the route docstring.
- **Hand-written frame reader.** It is small, but it is new parsing code. Tests feed it split chunks, a split UTF-8 character and a missing final blank line.
- **`engine.py` near the ceiling.** Handled in task 3.3.
- **Two code paths share one vocabulary.** The core test runs the same question through both paths and asserts the same stage list, so the two cannot drift.
- **Stage names for plugin steps.** A plugin operation maps to no stage. The page shows the previous stage longer. Accepted.
- **Proxies.** The server binds to loopback only, so no proxy buffers the stream. `X-Accel-Buffering: no` is set anyway, as for the run stream.

## Migration Plan

No data migration. The blocking route stays. An older server without the stream route makes the new page fall back to the blocking call. An older page against a newer server never calls the new route. Rollback is a revert of the change.

## Open questions

1. **Cancel or finish when the client leaves?** Recommendation: cancel (D5). Choose "finish" only if you want a future "answers continue in the background" feature, which needs the job table of option (a).
2. **Add a Stop button now?** Recommendation: no. The cancel path will exist, so a button is a small follow-up (abort the fetch). It needs a decision on what the turn shows after Stop.
3. **Should `Engine.answer` get a public `on_stage` argument, or should a private seam carry it?** Recommendation: public, optional, keyword-only. A private seam would force the route to reach into core.
4. **Stage wording.** Recommendation: "Searching", "Writing the answer", "Checking citations", "Verifying claims". Change the strings in one place (`AnswerProgress.tsx`) if you prefer others.
5. **Show "Verifying claims" when the judge is unavailable?** The stage appears briefly, then the result reports `verification_skipped`. Recommendation: accept this. The alternative needs a judge probe before the stage, which adds a call path for little gain.
6. **ADR-087 now or at apply time?** Recommendation: at apply time, as task 8.1, so it records what shipped.
