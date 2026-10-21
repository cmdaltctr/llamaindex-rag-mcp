# Tasks

Run every command from the worktree root. Check `git branch --show-current` first. Every task that adds a test follows this order: write the test, run it, confirm it fails for the right reason, then implement.

## 1. Stage reporter and the direct path

- [x] 1.1 Test first: `tests/unit/test_answer_progress.py` covers `StageReporter`, `reporting` and `report_stage`. Cases: stages arrive in order, a repeat is dropped, a backward stage is dropped, a raising callback is logged and swallowed, `reporting(None)` installs nothing, `report_stage` with no reporter does nothing, and a nested `reporting` restores the outer reporter on exit. Verify: the tests fail before `progress.py` exists.
- [x] 1.2 Add `src/omrg/core/answer/progress.py` with `AnswerStage`, `StageReporter`, the context variable, `reporting` and `report_stage`. Verify: task 1.1 passes and `uv run lint-imports` reports 0 broken.
- [x] 1.3 Test first: `tests/unit/test_answer_pipeline_stages.py` runs `core.answer.pipeline.answer` inside `reporting(recorder)`. Cases: full answer with verification and a judge seam (four stages), verification off (three), verification on with no judge seam (three, and the result has `verification_skipped`), no evidence (`searching` only), no provider (`searching` only), master switch off (none), request over the limit (none), generation failure (`searching`, `writing`), and a raising callback. One case checks that the result dict equals the result of a run with no reporter. Verify: the tests fail before the report calls exist.
- [x] 1.4 Add `report_stage` calls: `searching` in `pipeline.answer` after the master switch, `writing` at the start of `synthesise_answer`, `citing` at the start of `resolve_citations`, and `verifying` in `verify_answer` after its gate when `verify_complete` is not `None` (design D3). Verify: task 1.3 passes, the existing answer tests pass, and `pipeline.py` and `stages.py` stay under 500 lines.
- [x] 1.5 Guard test: the callback receives `AnswerStage` values only, and `stream_complete` on the seam still raises `NotImplementedError`. This test passes at once; it guards against a later change. Verify: it fails if a test double makes `report_stage` pass text, and `synthesis.py` has no diff.

## 2. Engine and the user-profile path

- [x] 2.1 Test first: `tests/unit/test_engine_answer_stages.py` runs `Engine.answer` with `on_stage` on a collection that follows a user profile with the default Answer graph. Cases: with verification on and a judge set, four stages in order; verification off in the settings gives three (the claim step starts but reports nothing); `verify.claims` disabled in the graph gives three; no evidence gives `searching` only (the synthesis step starts but reports nothing); a graph with an extra unknown step answers normally; a graph with no cite step lists only what ran; a graph with dense, sparse and rerank steps gives `searching` once; a graph with no saved Answer graph raises `ValueError` before any stage. A parity case runs one question through a built-in profile and a user profile and asserts the same stage list. Verify: the tests fail before the argument exists.
- [x] 2.2 Add the optional keyword `on_stage` to `Engine.answer` and wrap both paths in `reporting(on_stage)`. Add `on_event` to `_run_async` in `src/omrg/engine_profiles.py`, and pass an async sink from `engine_profiles.answer` that reports `searching` on `NODE_STARTED` and ignores every other event. Verify: task 2.1 passes. `src/omrg/core/pipelines/` and `src/omrg/core/answer/graph_adapters.py` have no diff.
- [x] 2.3 Check `wc -l src/omrg/engine.py`. If it is over 500, move the user-profile branch of `Engine.answer` into one helper in `engine_profiles.py`. Verify: `tests/test_file_size_ceiling.py` passes.
- [x] 2.4 Test first: `Engine.answer` without `on_stage` returns the same result as before for both paths, and a client completion or pre-fetched rows still raise for a user profile. Verify: the existing Engine answer tests pass with no edit.

## 3. The streaming route and the contract

- [x] 3.1 Test first: `tests/unit/test_web_answer_stream.py` posts to `/v1/collections/{collection}/answer/stream` with a fake Engine. Cases from the delta spec: stage frames then one `result` frame; the `result` equals the blocking route's JSON; 401 with no credential; 403 for a session cookie with a foreign Origin; a bearer with `read` passes; a bearer without `read` gets 403; an unknown body field is refused as the blocking route refuses it; 503 when admission is closed; an Engine `ValueError` gives the blocking route's 400 body, no stream, and admission back to 0; any other Engine error gives a `result` frame in the `_answer_failure` shape. The blocking route's existing tests stay unchanged. Verify: all new tests fail before the route exists.
- [x] 3.2 Test first: a content test posts a marker question, uses a model that fails with an error text that holds a saved key, and asserts that no `stage` frame holds the marker or the key. It asserts the `result` frame holds the redacted text. A schema test asserts each `stage` frame has exactly `stage`, `sequence` and `elapsed_ms`, with sequence 1, 2, 3 and elapsed times that do not fall. Verify: the tests fail before the route exists.
- [x] 3.3 Test first: a disconnect test drives the stream generator, reads one frame, then closes it. It asserts the producer task is cancelled and `runtime.admission.active` returns to 0. A second case runs two streams at once and asserts each holds only its own stages. A third case makes a raw ASGI call whose scope reports `spec_version` `"2.4"`, holds the fake model call open, then delivers `http.disconnect`, and asserts the producer is cancelled within 3 seconds with no frame sent. A fourth case starts graceful shutdown during a stream and asserts that shutdown waits, the Engine stays open, and the stream still ends with its `result` frame. Verify: the tests fail before the route exists, and the third case fails when the watch task is removed.
- [x] 3.4 Add `src/omrg/transports/api/routes/answer_stream.py`: scope `read`, admission held from before the first byte, producer task, queue, a watch task on `request.is_disconnected()`, the wait for the first item before the response (design D5), cancel in `finally`, headers as in `streamRunEvents`. Register it in `app.py`. Reuse `AnswerBody`, `_redact_error` and `_answer_failure` from `documents.py`. Verify: tasks 3.1 to 3.3 pass, the file is under 500 lines, and `documents.py` has no diff.
- [x] 3.5 Add the route to `src/omrg/transports/api/openapi.yaml`: operation `streamAnswer`, security `sessionCookie` and `bearerToken` with `read`, `x-omrg-scopes: [read]`, `x-omrg-sse-events` for `stage` and `result`, a `400` response with the error envelope, and the closed schema `AnswerStageEvent`. Verify: the OpenAPI conformance tests pass.
- [x] 3.6 Update `tests/unit/test_web_openapi_conformance_support.py`: add `streamAnswer` to a family, and apply the `retry` rule of `_check_frames` only to operations without a request body. Verify: the conformance tests pass, and they fail when `streamAnswer` is removed from the YAML.

## 4. Web client

- [x] 4.1 Test first: `web/src/api/answerStream.test.ts` tests `readFrames` with frames split across chunks, a multi-byte character split across chunks, comment lines, an unknown event, a final frame with no trailing blank line, and CRLF line ends. Verify: the tests fail before the file exists.
- [x] 4.2 Test first: tests for `answerCollectionStreaming`. Cases: `onStage` fires in frame order; the `result` frame returns an `AnswerResult`; a 400 response throws `ApiError` kind `http` with the server message; the fallback runs once for a missing body reader, for 404, for 405 and for a non-stream content type; there is no fallback for 400, 403 and 503; a stream that ends with no result throws kind `network` and does not call the blocking route; an abort stops the read. Verify: the tests fail before the function exists.
- [x] 4.3 Add `stream` to `ApiClient` in `web/src/api/client.ts` and create `web/src/api/answerStream.ts`. Verify: tasks 4.1 and 4.2 pass, plus the existing `client.test.ts`.
- [x] 4.4 Test first: `useAnswer` returns `progress.stages`, resets on `mutate`, drops duplicates, and keeps `ANSWER_MUTATION_KEY`. It aborts the open request on unmount and before each new `mutate`, and an aborted request sets no error. Then change `useAnswer` in `web/src/api/mutations.ts` to call `answerCollectionStreaming`. Verify: the test fails before the change, then passes with the existing `mutations.test.tsx` cases.

## 5. The page

- [x] 5.1 Load the `omrg-design` skill and read `web/DESIGN.md` and `web/src/AGENTS.md`. Verify: the new files use no literal colour and no hand-written CSS.
- [x] 5.2 Test first: `web/src/chat/AnswerProgress.test.tsx` and a streaming case in the `AssistantTurn` or `ChatView` tests, using a fake streamed `Response`. Cases: stages appear in order with ticks; the counter advances with fake timers and is `aria-hidden`; only the stage line is `role="status"`; no "Verifying claims" row without a `verifying` frame; no "Writing the answer" row for a no-evidence run; no stage within 10 s shows "Waiting for the answer." and "10 s"; the answer replaces the progress; Retry clears the old stages; a saved turn never mounts the component. Verify: the tests fail before the component exists.
- [x] 5.3 Add `web/src/chat/AnswerProgress.tsx` and use it in `web/src/chat/AssistantTurn.tsx`. Use lucide `Check` and `Loader2` (spin under `motion-safe` only), token colours and the existing text utilities. Verify: task 5.2 passes, and `ChatView` tests that use the blocking route still pass through the fallback.
- [x] 5.4 Test first: a `ChatView` test sends a streamed question and asserts that the stored-turn request body holds only `collection`, `question` and `answer`, and that a reload shows the saved answer with no stage line. Verify: the test passes only when stage values never reach `useChatSession.onResult`. Make it fail by passing stages to `onResult`, then restore.
- [x] 5.5 Run `npm run lint`, `npm run typecheck` and `npm test` in `web/`. Verify: all pass and every file stays under 500 lines.

## 6. Mutation checks

Do each check, confirm the named test fails, then restore the code.

- [x] 6.1 Swap the `writing` and `citing` values in `stages.py`. Verify: tasks 1.3 and 2.1 fail.
- [x] 6.2 Move the `writing` report from `synthesise_answer` to the start of `synthesise_adapter`. Verify: the no-evidence case of task 2.1 fails.
- [x] 6.3 Remove the `verify_complete is not None` check before the `verifying` report. Verify: the no-judge case of task 1.3 fails.
- [x] 6.4 Remove the producer cancel from the generator `finally`, and separately remove the watch task. Verify: task 3.3 fails each time.
- [x] 6.5 Add the question to the `stage` frame. Verify: task 3.2 fails.
- [x] 6.6 Remove the duplicate filter in `useAnswer`, separately make the fallback also run on 403, and separately drop the abort on unmount. Verify: tasks 4.2 and 4.4 fail each time.

## 7. Docs

- [x] 7.1 Update the Chat section of `docs/guides/web-workspace.md`: the stage list, the seconds counter, the fallback line, the stream route in the API table and the rule that stages are not stored. Use British English and short steps. Verify: grep the guide for "Waiting for the answer" and fix stale text.
- [x] 7.2 Check `docs/guides/mcp-tools.md` and `docs/guides/architecture.md` for text that says the web answer is one blocking call. Verify: edit only a line that is now wrong. MCP tool text does not change.

## 8. Records and counts

- [x] 8.1 Write `docs/adr/089-answer-stage-progress.md` and add it to the ADR index, as design D10 describes. Check first that 089 is still free. Verify: the index lists 089.
- [x] 8.2 Measure the new test counts with the fast suite, with and without the web extra. Update `_BASE_EXECUTED` and `_WEB_EXTRA_CASES` in `tests/test_clean_base_tripwire.py`, and add one comment line that names this change, as `add-web-power-menu` did. Verify: `uv run pytest tests/test_clean_base_tripwire.py -q` passes.

## 9. Gates

Warn before the heavy runs and the browser run.

- [x] 9.1 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, then `./scripts/local_ci.sh`, `uv run ruff check`, `uv run ruff format --check` and `uv run lint-imports`. Verify: all pass.
- [x] 9.2 Run `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` in `web/`. Verify: all pass.
- [x] 9.3 Run `openspec validate add-answer-stage-progress --strict` and `openspec validate --all --strict`. Verify: both pass.
- [ ] 9.4 Browser check against a scratch workspace (never the real login item or port 8765). Use a stub model that waits 8 seconds in each stage. Check at 1280 px and 390 px, in the light and dark theme: the stage list, the counter, the fallback line (stream route blocked) and the final answer. Verify: no sideways scroll at 390 px, the tick and spinner use token colours, and a screen reader tool reports one status region.
- [x] 9.5 Commit each group with `uv run git commit` and a Conventional Commit message. Verify: the working tree is clean.
