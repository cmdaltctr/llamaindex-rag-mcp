# Design

## Context

Observed in the code:

- Chat sends one blocking `POST /v1/collections/{collection}/answer` (`answer_collection` in `routes/documents.py`). It holds `admitted(runtime)` for the whole call, calls `runtime.engine.answer(...)`, redacts the `error` text with `_redact_error` and returns JSON. A `ValueError` from the Engine becomes a 400. Any other exception becomes a 200 result in the `_answer_failure` shape. `AssistantTurn.tsx` prints "Waiting for the answer." until the JSON arrives.
- **Shared steps.** `core/answer/stages.py` holds `synthesise_answer`, `resolve_citations` and `verify_answer`. Its docstring says: "Graph adapters call the same functions, so there is one implementation of each step." Both answer paths call these three functions, and only after their own early returns.
- **Direct path** (built-in profiles `documents`, `codebase`): `Engine.answer` calls `core.answer.pipeline.answer`. Its steps run in this order: retrieval in `asyncio.to_thread`, `prepare_evidence`, `synthesise_answer`, `resolve_citations`, `verify_answer`, `answered_result`. Three early returns skip later steps: the master switch (`disabled_result`), an empty evidence list (`no_evidence_result`) and a missing model (`no_provider_result`).
- **Claim check gate.** `verify_answer` returns `NO_VERIFICATION` unless the answer is grounded and `answer.verify_claims` is on. Then it calls `run_verification_stage`, which reports `verification_skipped` at once when the judge seam is `None` (no judge model set, since `add-judge-model-setting`). The judge seam is known before `verify_answer` runs on both paths: `build_verifier` in `Engine.answer`, `_judge_seam` in `verify_claims_adapter`.
- **User-profile path**: `Engine.answer` calls `engine_profiles.answer`, then `_run_async`, then `engine.run_pipeline({"graph": graph}, inputs=...)`. `run_pipeline` accepts `on_event: EventSink`, an async callable (`events.py`). Every node of the Answer graph starts, even when it has no work. `synthesise_adapter` returns the disabled, no-evidence and no-provider results from inside the step. `verify_claims_adapter` checks `answer.verify_claims` inside the step, and the template never disables that node. A stage map built on `NODE_STARTED` events would therefore show "Writing the answer" for a no-evidence answer and "Verifying claims" when verification is off.
- The runner starts each node with `asyncio.create_task` inside the run call (`execution.py`). A task copies the caller's context, so a `ContextVar` set before `run_pipeline` is visible inside every node. Runs on one Engine are serialised by an `asyncio.Lock`.
- **Where `ValueError` comes from.** On both paths, every `ValueError` is raised before any step does work: `refuse_caller_inputs`, `slot_graph` (no saved graph), `apply_request`, and `PipelineValidationError` (a `ValueError`, raised "before any side effect"). A graph run that fails mid-way raises `ProfileRunError`, a `RuntimeError`.
- The grounded-answer seam (`core/answer/synthesis.py`) returns the whole reply and `stream_complete` raises `NotImplementedError`.
- Existing SSE code: `runs.py` (`_frame`, `STREAM_RETRY_MS`, `API_HEADERS`, `Cache-Control: no-store`, `X-Accel-Buffering: no`) and `logs.py` reuse the same helpers. Both are GET streams with replay.
- **Disconnect detection.** Starlette 1.6 `StreamingResponse` watches for `http.disconnect` only when the server reports ASGI spec below 2.4. uvicorn 0.52.1 reports 2.3, so it works today. With spec 2.4 Starlette notices a gone client only when a send fails. The route sends nothing during a 30-second model call, so a later uvicorn would let a closed tab run its answer to the end.
- A cookie session that posts needs an allowed `Origin` header (`security.py`, `_authenticate`). A bearer credential skips that check. A browser `EventSource` can only send GET, with no body.
- `useAnswer` is a TanStack `useMutation`. A mutation gets no `AbortSignal`, and unmounting the component does not stop it.
- `engine.py` is 489 lines. `pipeline.py` is 356. `stages.py` is 290. `engine_profiles.py` is 356. `documents.py` is 221. `client.ts` is 179. `mutations.ts` is 235.
- Chats are stored by `useChatSession.onResult`, which receives only the finished `AnswerResult`.
- ADR numbers 087 and 088 are taken. The next free number is 089.

## Goals / Non-Goals

**Goals:**

- Chat shows the current stage of a running answer, on both paths, with one vocabulary and one rule: a stage shows only when its work starts.
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

The response is `text/event-stream` with the headers of `streamRunEvents` (`API_HEADERS`, `Cache-Control: no-store`, `X-Accel-Buffering: no`). The route sends no `retry:` line, because nothing reconnects. It sends no heartbeat: the connection is on loopback, a browser `fetch` has no idle timeout, and the route watches the client itself (D5).

Frames use the existing `_frame` helper:

```
event: stage
data: {"stage":"searching","sequence":1,"elapsed_ms":412}

event: stage
data: {"stage":"writing","sequence":2,"elapsed_ms":2210}

event: result
data: { ...the AnswerResult of the blocking route... }
```

- `stage`: closed schema `AnswerStageEvent` with `stage` (enum `searching`, `writing`, `citing`, `verifying`), `sequence` (integer from 1) and `elapsed_ms` (integer). `elapsed_ms` counts from admission. The page does not show it. It stays for debugging and for the order test.
- `result`: the blocking route's result, after `_redact_error`. It is always the last frame of a stream.

There is no `failure` frame. Every Engine `ValueError` comes before the first stage (Context), and the route opens the stream only after the first stage or the result is ready (D5). A `ValueError` therefore gets the blocking route's plain 400. Any other Engine error ends the stream with a `result` frame in the `_answer_failure` shape, as the blocking route returns it.

The conformance helper `_check_frames` demands a `retry` hint on the first frame. That rule fits the GET streams only. Task 3.6 limits it to operations without a request body.

### D3. Stage vocabulary and where stages are reported

New module `src/omrg/core/answer/progress.py`:

- `AnswerStage`, a `StrEnum` with four values in order: `searching`, `writing`, `citing`, `verifying`.
- `StageReporter(callback)`: a small object with `enter(stage)`. It drops a repeat of the current stage and a stage that ranks lower than one already sent, so the order is monotonic. It catches and logs any error from the callback, so a broken consumer never fails an answer.
- A module `ContextVar[StageReporter | None]`, default `None`.
- `reporting(on_stage)`: a context manager. With a callback it installs a new reporter and restores the old value on exit. With `None` it does nothing.
- `report_stage(stage)`: calls the active reporter, or does nothing when there is none.

The callback type is `Callable[[AnswerStage], None]`, a plain function called on the event loop. Both paths run on the loop, so no thread hop is needed. The route's callback only calls `put_nowait` on a queue.

**One rule for both paths: a stage is reported where its work starts.** Three of the four reports sit in the shared steps of `stages.py`, so both paths get them from one place:

1. `searching`: direct path, in `pipeline.answer` after the master-switch check and before retrieval. Graph path, see D4.
2. `writing`: first line of `synthesise_answer`. Both paths call it only after the evidence and provider checks pass.
3. `citing`: first line of `resolve_citations`. Both paths call it only after a synthesis that gave text. Citation matching is pure text work, so this stage is short. It stays, because it shows the order and costs nothing.
4. `verifying`: in `verify_answer`, after its gate (grounded and `answer.verify_claims` on) and only when `verify_complete` is not `None`. With no judge model set, no stage shows and the result carries `verification_skipped`, as today.

The `result` frame ends the stream, so nothing follows `verifying`.

A request rejected by `_validate_request` and a disabled operation report no stage. An empty evidence list and a missing provider report `searching` only. A generation failure reports `searching` and `writing`. These match the delta spec.

`Engine.answer` gains an optional keyword-only `on_stage` argument. It wraps both paths in `reporting(on_stage)`. `core.answer.pipeline.answer` gets no new argument: its tests install a reporter with `reporting(...)`. `omrg.Engine` is the public API, and the argument is optional, so no caller breaks. `engine.py` has 489 lines. The argument, its docstring line and the `with` block add about 6. Task 2.3 checks the count. If the file goes over 500, the user-profile branch of `Engine.answer` moves into one helper in `engine_profiles.py`.

Each request runs in its own task, and a task copies its context, so two streams never share a reporter. Callers that do not pass `on_stage` (MCP, CLI, scripts, experiments) install nothing, and `report_stage` does nothing for them.

The seam is untouched. `stream_complete` keeps raising. A callback never receives text.

### D4. User-profile path: the same steps, plus one event for `searching`

The answer adapters call the shared steps of D3, so `writing`, `citing` and `verifying` need no graph code. A skipped step reports nothing, because the adapter returns before it calls the shared step:

- `synthesise_adapter` returns the disabled, no-evidence and no-provider results before `synthesise_answer`, so none of them shows "Writing the answer".
- `cite_adapter` returns at once when there is no answer text, so a failed synthesis shows no "Checking citations".
- `verify_claims_adapter` returns before `verify_answer` when verification is off or the answer is not grounded. With no judge, `verify_answer` reports nothing (D3, point 4). A bypassed node never runs its adapter.

`searching` comes from the first `NODE_STARTED` event of the run, whatever the node. `engine_profiles._run_async` gets an optional `on_event` argument and passes it to `engine.run_pipeline`. `engine_profiles.answer` passes an async sink that calls `report_stage(AnswerStage.SEARCHING)` on `NODE_STARTED` and ignores every other kind. The first node starts only after graph validation, so a `PipelineValidationError` still comes before any stage. The sink reads no node id and no operation. There is no node-to-stage map.

How a user edit degrades:

- **Unknown node** (a new operation, or a plugin step): no stage of its own. The current stage stays on screen.
- **Missing node** (no cite step, no verify step): that stage never appears. The list shows what ran.
- **Reordered or repeated nodes**: `StageReporter` drops repeats and backward steps. The list never shows a stage twice.
- **No answer step at all**: the page sees `searching` only, then the result.
- **A sink error**: the runner logs it and the run continues (`events.py`).

The runner, `PipelineEvent` and the graph adapters do not change. Runs on one Engine are serialised, so a second graph-path answer waits for the first. Its first `NODE_STARTED` comes late, and the page shows "Waiting for the answer." and the counter until it does.

### D5. The route: producer task, queue, client watch

New module `src/omrg/transports/api/routes/answer_stream.py`, registered next to the other routers in `app.py`. `documents.py` does not change. The new module imports `AnswerBody`, `_redact_error` and `_answer_failure` from `documents.py`, as `logs.py` imports `_frame` from `runs.py`.

Flow:

1. The handler checks scope `read` (`ReadScope`) and validates `AnswerBody`. It enters runtime admission through an `AsyncExitStack`. If admission is closed, `admitted` raises 503.
2. It starts a producer task: `runtime.engine.answer(..., on_stage=enqueue)`. `enqueue` puts an `AnswerStageEvent` on an `asyncio.Queue`. The task puts the result, or the exception, on the queue.
3. It starts a watch task that checks `request.is_disconnected()` once a second and cancels the producer when the client has gone. Cancel therefore works whatever ASGI spec version the server reports.
4. The handler waits for the first queue item before it returns a response:
   - a `ValueError`: close the stack and return the blocking route's 400 (`error_response(400, str(exc), error_type="validation")`);
   - any other exception: stream one `result` frame in the `_answer_failure` shape;
   - a stage or a result: return the `StreamingResponse`.
5. The generator yields the first item, then reads the queue and yields frames until the result.
6. In `finally`, the generator cancels and awaits the producer and the watch task with the cancellation suppressed. Then it closes the admission stack. The handler does the same clean-up when it returns before a stream.

**Client leaves: cancel, not finish.** An answer costs model time and money, and its result has nowhere to go: the page saves a turn only when the result reaches it. Letting it run on would also double the cost when the user presses Retry.

What a cancel does on each path:

- Direct path: the awaiting task is cancelled. The model call is cancelled where the client supports it. A retrieval thread already started in `to_thread` cannot be stopped. It ends and its result is dropped.
- Graph path: `run_pipeline` turns an outer cancel into a cooperative cancel. A node that has started finishes. The model call in flight is therefore not interrupted. Admission stays held until it ends. This matches how shutdown treats started nodes.

Shutdown: the stream holds admission like the blocking route, so graceful shutdown waits for it. The route sends no `server.closing` frame.

Two answers at once: each request has its own queue, tasks, reporter and frames. The direct path runs them in parallel. The graph path serialises them on the Engine.

Memory: one queue of at most five small items per stream. Nothing outlives the request.

### D6. Web client: a `stream` method, a frame reader and an abort

- `ApiClient` (`web/src/api/client.ts`) gains `stream(method, path, input, signal)`. It shares `isApiPath`, the headers and the `network` error mapping with `request`. It returns the `Response` when the status is OK and the content type is `text/event-stream`. A non-OK status is parsed as the JSON error envelope and thrown as `ApiError` of kind `http`, exactly as `request` does. `client.ts` is 179 lines, so it has room.
- New `web/src/api/answerStream.ts` holds:
  - `readFrames(body)`: reads a `ReadableStream` of bytes with `TextDecoder`, splits on a blank line, and yields `{event, data}`. It ignores comment lines and unknown events.
  - `answerCollectionStreaming(api, collection, controls, {onStage, signal})`: calls `stream`, handles `stage` and `result` frames, and returns the `AnswerResult`.
- **Abort.** A TanStack mutation gets no `AbortSignal`, so `useAnswer` owns an `AbortController` in a ref. It aborts the old controller and makes a new one on each `mutate`, and it aborts on unmount. Its signal goes to `answerCollectionStreaming`. An abort ends the fetch, and the server's watch (D5) cancels the answer. Leaving a chat or pressing Retry therefore never leaves a paid answer running. An aborted request is not shown as an error, because the turn has gone or a new request has replaced it.

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

### D10. ADR

An ADR is warranted. The next free number is **ADR-089** (087 and 088 are taken). It would record: why a streamed POST and not a job plus GET or a GET with the query; cancel on disconnect, watched by the route; the closed content-free frame; stages reported where their work starts, through a context reporter in the shared steps; and that `on_stage` joins the public `Engine.answer` surface. It would also state that the model call stays whole-reply, so a later token-streaming change has a clear starting point. This proposal does not write the ADR. Task 8.1 writes it at implementation time.

## Risks / Trade-offs

- **No resume.** A dropped connection loses the answer, as the blocking call does today. Accepted. A job table (option a) is the way to add this later.
- **Cancel on the graph path is cooperative.** A started model call finishes and holds admission until it ends. Accepted, and noted in the route docstring.
- **Reports live inside shared steps.** `stages.py` gains three `report_stage` calls, which are side effects in otherwise pure functions. They do nothing without an installed reporter. The parity test in task 2.1 and the mutation checks in group 6 keep them in place.
- **Watch poll.** The route checks the client once a second, so a cancel can lag by up to one second. Accepted.
- **Hand-written frame reader.** It is small, but it is new parsing code. Tests feed it split chunks, a split UTF-8 character and a missing final blank line.
- **`engine.py` near the ceiling.** Handled in task 2.3.
- **Two code paths share one vocabulary.** The engine test runs the same question through both paths and asserts the same stage list, so the two cannot drift.
- **Stage names for plugin steps.** A plugin operation reports no stage. The page shows the previous stage longer. Accepted.
- **Proxies.** The server binds to loopback only, so no proxy buffers the stream. `X-Accel-Buffering: no` is set anyway, as for the run stream.

## Migration Plan

No data migration. The blocking route stays. An older server without the stream route makes the new page fall back to the blocking call. An older page against a newer server never calls the new route. Rollback is a revert of the change.

## Open questions

1. **Cancel or finish when the client leaves?** Recommendation: cancel (D5). Choose "finish" only if you want a future "answers continue in the background" feature, which needs the job table of option (a).
2. **Add a Stop button now?** Recommendation: no. The abort path exists (D6), so a button is a small follow-up. It needs a decision on what the turn shows after Stop.
3. **Should `Engine.answer` get a public `on_stage` argument, or should a private seam carry it?** Recommendation: public, optional, keyword-only. A private seam would force the route to reach into core.
4. **Stage wording.** Recommendation: "Searching", "Writing the answer", "Checking citations", "Verifying claims". Change the strings in one place (`AnswerProgress.tsx`) if you prefer others.
5. **ADR-089 now or at apply time?** Recommendation: at apply time, as task 8.1, so it records what shipped.
