# Tasks

Run every command from the worktree root. Check `git branch --show-current` first. Every task that adds a test follows this order: write the test, run it, confirm it fails for the right reason, then implement.

## 1. Stage reporter and the direct path

- [ ] 1.1 Test first: `tests/unit/test_answer_progress.py` covers `StageReporter` and `operation_stage`. Cases: stages arrive in order, a repeat is dropped, a backward stage is dropped, a raising callback is logged and swallowed, and `callback=None` does nothing. A table test maps `retrieve.dense`, `retrieve.sparse`, `retrieve.prepare_query`, `combine.rrf`, `select.rerank`, `select.threshold`, `context.assemble` and `answer.prepare_evidence` to `searching`. It maps the other three answer operations to their stage and `prepare.chunk` and an invented id to `None`. Verify: the tests fail before `progress.py` exists.
- [ ] 1.2 Add `src/omrg/core/answer/progress.py` with `AnswerStage`, `StageReporter` and `operation_stage`. Verify: task 1.1 passes and `uv run lint-imports` reports 0 broken.
- [ ] 1.3 Test first: `tests/unit/test_answer_pipeline_stages.py` runs `core.answer.pipeline.answer` with a recording callback. Cases: full answer with verification (four stages), verification off (three), no evidence (`searching` only), no provider (`searching` only), master switch off (none), request over the limit (none), generation failure (`searching`, `writing`), and a raising callback. One case checks that the result dict equals the result of a run with no callback. Verify: the tests fail before the hook exists.
- [ ] 1.4 Add `on_stage` to `answer()` in `src/omrg/core/answer/pipeline.py` and call the reporter at the four points in design D3. Verify: task 1.3 passes, the existing answer tests pass, and `pipeline.py` stays under 500 lines.
- [ ] 1.5 Test first: the callback receives `AnswerStage` values only, and `stream_complete` on the seam still raises `NotImplementedError`. Verify: the stage assertion fails if a test double passes text to the callback; the seam test passes with no change to `synthesis.py`.

## 2. Engine and the user-profile path

- [ ] 2.1 Test first: `tests/unit/test_engine_answer_stages.py` runs `Engine.answer` on a collection that follows a user profile with the default Answer graph. Cases: four stages in order; `verify.claims` disabled in the graph gives three; a graph with an extra unknown step answers normally; a graph with no cite step lists only what ran; a graph with dense, sparse and rerank steps gives `searching` once. A parity case runs one question through a built-in profile and a user profile and asserts the same stage list. Verify: the tests fail before the argument exists.
- [ ] 2.2 Add `on_event` to `_run_async` and the node-to-stage sink to `engine_profiles.answer` in `src/omrg/engine_profiles.py`. Add the optional keyword `on_stage` to `Engine.answer` and pass it to both paths. Verify: task 2.1 passes. `src/omrg/core/pipelines/` has no diff.
- [ ] 2.3 Check `wc -l src/omrg/engine.py`. If it is over 500, move the user-profile branch of `Engine.answer` into one helper in `engine_profiles.py`. Verify: `tests/test_file_size_ceiling.py` passes.
- [ ] 2.4 Test first: `Engine.answer` without `on_stage` returns the same result as before for both paths, and a client completion or pre-fetched rows still raise for a user profile. Verify: the existing Engine answer tests pass with no edit.

## 3. The streaming route and the contract

- [ ] 3.1 Test first: `tests/unit/test_web_answer_stream.py` posts to `/v1/collections/{collection}/answer/stream` with a fake Engine. Cases from the delta spec: stage frames then one `result` frame; the `result` equals the blocking route's JSON; 401 with no credential; 403 for a session cookie with a foreign Origin; a bearer with `read` passes; a bearer without `read` gets 403; an unknown body field is refused as the blocking route refuses it; 503 when admission is closed; a `ValueError` after the stream opened gives one `failure` frame; any other Engine error gives a `result` frame in the `_answer_failure` shape. The blocking route's existing tests stay unchanged. Verify: all new tests fail before the route exists.
- [ ] 3.2 Test first: a content test posts a marker question, uses a model that fails with an error text that holds a saved key, and asserts that no `stage` frame holds the marker or the key. It asserts the `result` frame holds the redacted text. A schema test asserts each `stage` frame has exactly `stage`, `sequence` and `elapsed_ms`, with sequence 1, 2, 3 and elapsed times that do not fall. Verify: the tests fail before the route exists.
- [ ] 3.3 Test first: a disconnect test drives the stream generator, reads one frame, then closes it. It asserts the producer task is cancelled and `runtime.admission.active` returns to 0. A second case runs two streams at once and asserts each holds only its own stages. A third case uses a raw ASGI call with an `http.disconnect` message to confirm that Starlette cancels the generator. Verify: the tests fail before the route exists.
- [ ] 3.4 Add `src/omrg/transports/api/routes/answer_stream.py`: scope `read`, admission held from before the first byte, producer task, queue, cancel in `finally`, headers as in `streamRunEvents`. Register it in `app.py`. Reuse `AnswerBody`, `_redact_error` and `_answer_failure` from `documents.py`. Verify: tasks 3.1 to 3.3 pass, the file is under 500 lines, and `documents.py` has no diff.
- [ ] 3.5 Add the route to `src/omrg/transports/api/openapi.yaml`: operation `streamAnswer`, security `sessionCookie` and `bearerToken` with `read`, `x-omrg-scopes: [read]`, `x-omrg-sse-events` for `stage`, `result` and `failure`, and schemas `AnswerStageEvent` (closed) and `AnswerStreamFailure`. Verify: the OpenAPI conformance tests pass.
- [ ] 3.6 Update `tests/unit/test_web_openapi_conformance_support.py`: add `streamAnswer` to a family, and apply the `retry` rule of `_check_frames` only to operations without a request body. Verify: the conformance tests pass, and they fail when `streamAnswer` is removed from the YAML.

## 4. Web client

- [ ] 4.1 Test first: `web/src/api/answerStream.test.ts` tests `readFrames` with frames split across chunks, a multi-byte character split across chunks, comment lines, an unknown event, a final frame with no trailing blank line, and CRLF line ends. Verify: the tests fail before the file exists.
- [ ] 4.2 Test first: tests for `answerCollectionStreaming`. Cases: `onStage` fires in frame order; the `result` frame returns an `AnswerResult`; a `failure` frame throws `ApiError` kind `http`; the fallback runs once for a missing body reader, for 404, for 405 and for a non-stream content type; there is no fallback for 400, 403 and 503; a stream that ends with no result throws kind `network` and does not call the blocking route; an abort stops the read. Verify: the tests fail before the function exists.
- [ ] 4.3 Add `stream` to `ApiClient` in `web/src/api/client.ts` and create `web/src/api/answerStream.ts`. Verify: tasks 4.1 and 4.2 pass, plus the existing `client.test.ts`.
- [ ] 4.4 Test first: `useAnswer` returns `progress.stages`, resets on `mutate`, drops duplicates, and keeps `ANSWER_MUTATION_KEY`. Then change `useAnswer` in `web/src/api/mutations.ts` to call `answerCollectionStreaming`. Verify: the test fails before the change, then passes with the existing `mutations.test.tsx` cases.

## 5. The page

- [ ] 5.1 Load the `omrg-design` skill and read `web/DESIGN.md` and `web/src/AGENTS.md`. Verify: the new files use no literal colour and no hand-written CSS.
- [ ] 5.2 Test first: `web/src/chat/AnswerProgress.test.tsx` and a streaming case in the `AssistantTurn` or `ChatView` tests, using a fake streamed `Response`. Cases: stages appear in order with ticks; the counter advances with fake timers and is `aria-hidden`; only the stage line is `role="status"`; no "Verifying claims" row without a `verifying` frame; no "Writing the answer" row for a no-evidence run; no stage within 10 s shows "Waiting for the answer." and "10 s"; the answer replaces the progress; Retry clears the old stages; a saved turn never mounts the component. Verify: the tests fail before the component exists.
- [ ] 5.3 Add `web/src/chat/AnswerProgress.tsx` and use it in `web/src/chat/AssistantTurn.tsx`. Use lucide `Check` and `Loader2` (spin under `motion-safe` only), token colours and the existing text utilities. Verify: task 5.2 passes, and `ChatView` tests that use the blocking route still pass through the fallback.
- [ ] 5.4 Test first: a `ChatView` test sends a streamed question and asserts that the stored-turn request body holds only `collection`, `question` and `answer`, and that a reload shows the saved answer with no stage line. Verify: the test passes only when stage values never reach `useChatSession.onResult`. Make it fail by passing stages to `onResult`, then restore.
- [ ] 5.5 Run `npm run lint`, `npm run typecheck` and `npm test` in `web/`. Verify: all pass and every file stays under 500 lines.

## 6. Mutation checks

Do each check, confirm the named test fails, then restore the code.

- [ ] 6.1 Swap `writing` and `citing` in `pipeline.py`. Verify: task 1.3 fails.
- [ ] 6.2 Map `verify.claims` to `searching` in `operation_stage`. Verify: tasks 1.1 and 2.1 fail.
- [ ] 6.3 Remove the producer cancel from the generator `finally`. Verify: task 3.3 fails.
- [ ] 6.4 Add the question to the `stage` frame. Verify: task 3.2 fails.
- [ ] 6.5 Remove the duplicate filter in `useAnswer`, and separately make the fallback also run on 403. Verify: tasks 4.2 and 4.4 fail.
- [ ] 6.6 Move the verifying call before `resolve_citations`. Verify: task 1.3 fails.

## 7. Docs

- [ ] 7.1 Update the Chat section of `docs/guides/web-workspace.md`: the stage list, the seconds counter, the fallback line, the stream route in the API table and the rule that stages are not stored. Use British English and short steps. Verify: grep the guide for "Waiting for the answer" and fix stale text.
- [ ] 7.2 Check `docs/guides/mcp-tools.md` and `docs/guides/architecture.md` for text that says the web answer is one blocking call. Verify: edit only a line that is now wrong. MCP tool text does not change.

## 8. Records and counts

- [ ] 8.1 Write `docs/adr/087-answer-stage-progress.md` and add it to the ADR index, as design D10 describes. Verify: the index lists 087.
- [ ] 8.2 Measure the new test counts with the fast suite, with and without the web extra. Update `_BASE_EXECUTED` and `_WEB_EXTRA_CASES` in `tests/test_clean_base_tripwire.py`, and add one comment line that names this change, as `add-web-power-menu` did. Verify: `uv run pytest tests/test_clean_base_tripwire.py -q` passes.

## 9. Gates

Warn before the heavy runs and the browser run.

- [ ] 9.1 Run `uv run pytest -n auto -m "not slow" --deselect tests/test_clean_base_tripwire.py -q`, then `./scripts/local_ci.sh`, `uv run ruff check`, `uv run ruff format --check` and `uv run lint-imports`. Verify: all pass. Run the suite with `env -u OPENROUTER_API_KEY` as well, so a real provider key in the shell does not hide a failure.
- [ ] 9.2 Run `npm run lint`, `npm run typecheck`, `npm test` and `npm run build` in `web/`. Verify: all pass.
- [ ] 9.3 Run `openspec validate add-answer-stage-progress --strict` and `openspec validate --all --strict`. Verify: both pass.
- [ ] 9.4 Browser check against a scratch workspace (never the real login item or port 8765). Use a stub model that waits 8 seconds in each stage. Check at 1280 px and 390 px, in the light and dark theme: the stage list, the counter, the fallback line (stream route blocked) and the final answer. Verify: no sideways scroll at 390 px, the tick and spinner use token colours, and a screen reader tool reports one status region.
- [ ] 9.5 Commit each group with `uv run git commit` and a Conventional Commit message. Verify: the working tree is clean.
