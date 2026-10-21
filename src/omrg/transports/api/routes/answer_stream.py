"""Streaming answer route: stage frames, then the answer result.

``POST /v1/collections/{collection}/answer/stream`` (operation
``streamAnswer``) takes the body of ``answerCollection`` and answers with
server-sent events (add-answer-stage-progress, design D1, D2 and D5):
``stage`` frames as the Engine enters each stage, then one ``result``
frame with the result the blocking route returns, then the end. There is
no ``retry`` line and no heartbeat, because nothing reconnects.

The route holds runtime admission from before the first byte until the
answer ends, so graceful shutdown waits for it. It opens the stream only
when the first stage or the result is ready: an Engine ``ValueError``
always comes before the first stage, so it gets the blocking route's 400.

A client that leaves cancels its answer. The route watches the client
itself, because with ASGI spec 2.4 Starlette notices a gone client only
when a send fails, and nothing is sent during a long model call. On the
direct path the cancel stops the awaiting task (a retrieval thread that
already started runs to its end). On the graph path the cancel is
cooperative: a node that started finishes, and admission stays held until
it does.

Stage frames are content-free: a stage name from the closed vocabulary, a
sequence number and the elapsed milliseconds since admission.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack
from typing import Any

from fastapi import APIRouter, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from ....core.answer.progress import AnswerStage
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import API_HEADERS, error_response
from ..lifespan import WebRuntime
from ..security import redact
from .documents import AnswerBody, _answer_failure, _redact_error
from .runs import _frame

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

#: How often the route checks that its client is still there, in seconds.
WATCH_INTERVAL_S = 1.0
#: Status for a client that left before the stream opened. Nobody reads it.
CLIENT_GONE = 499

_HEADERS = {**API_HEADERS, "Cache-Control": "no-store", "X-Accel-Buffering": "no"}

#: Clean-ups that outlive a cancelled response, held so they are not collected.
_CLEANUPS: set[asyncio.Task[None]] = set()


class _AnswerStream:
    """One streamed answer: admission, producer task, client watch and queue.

    Queue items are ``(kind, data)``: ``stage`` (frame data), ``result``
    (answer result), ``invalid`` (Engine ``ValueError``) or ``gone`` (the
    producer was cancelled).
    """

    def __init__(
        self, runtime: WebRuntime, request: Request, collection: str, body: AnswerBody
    ) -> None:
        self._runtime = runtime
        self._request = request
        self._collection = collection
        self._body = body
        self._queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._stack = AsyncExitStack()
        self._sequence = 0
        self._admitted_at = 0.0
        self._producer: asyncio.Task[None] | None = None
        self._watch: asyncio.Task[None] | None = None
        self._cleanup: asyncio.Task[None] | None = None

    async def open(self) -> tuple[str, Any]:
        """Admit the work, start the answer and its watch, and wait for the first item.

        Raises:
            HTTPException: 503 when shutdown has begun.
        """
        await self._stack.enter_async_context(admitted(self._runtime))
        self._admitted_at = time.monotonic()
        self._producer = asyncio.create_task(self._produce())
        self._watch = asyncio.create_task(self._watch_client(self._producer))
        return await self._queue.get()

    def _on_stage(self, stage: Any) -> None:
        """Queue one stage frame. Only a known stage value is ever framed."""
        try:
            name = AnswerStage(stage).value
        except ValueError:
            logger.warning("Answer stream dropped a value outside the stage vocabulary.")
            return
        self._sequence += 1
        elapsed_ms = int((time.monotonic() - self._admitted_at) * 1000)
        frame = {"stage": name, "sequence": self._sequence, "elapsed_ms": elapsed_ms}
        self._queue.put_nowait(("stage", frame))

    async def _produce(self) -> None:
        body = self._body
        try:
            result = await self._runtime.engine.answer(
                body.query,
                top_k=body.top_k,
                similarity_threshold=body.similarity_threshold,
                rerank=body.rerank,
                hybrid=body.hybrid,
                expand_window=body.expand_window,
                collection_name=self._collection,
                metadata_filter=body.metadata_filter,
                on_stage=self._on_stage,
            )
        except asyncio.CancelledError:
            self._queue.put_nowait(("gone", None))
            raise
        except ValueError as exc:
            self._queue.put_nowait(("invalid", exc))
        except Exception as exc:
            logger.warning("Web answer stream failed: %s", redact(repr(exc)))
            self._queue.put_nowait(("result", _answer_failure(body.query, exc)))
        else:
            self._queue.put_nowait(("result", result))

    async def _watch_client(self, producer: asyncio.Task[None]) -> None:
        """Cancel the producer when the client has gone."""
        while not producer.done():
            if await self._request.is_disconnected():
                producer.cancel()
                return
            await asyncio.sleep(WATCH_INTERVAL_S)

    def _result_frame(self, result: Any) -> str:
        secrets = getattr(self._request.app.state, "secrets", None)
        return _frame("result", jsonable_encoder(_redact_error(result, secrets)))

    async def frames(self, first: tuple[str, Any]) -> AsyncIterator[str]:
        """Yield frames from *first* until the result, then clean up."""
        try:
            kind, data = first
            while kind == "stage":
                yield _frame("stage", data)
                kind, data = await self._queue.get()
            if kind == "result":
                yield self._result_frame(data)
            elif kind == "invalid":  # not expected after a stage; keep the error shape
                yield self._result_frame(_answer_failure(self._body.query, data))
        finally:
            await self.close()

    async def _release(self) -> None:
        tasks = [task for task in (self._watch, self._producer) if task is not None]
        for task in tasks:
            task.cancel()
        for task in tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        await self._stack.aclose()

    async def close(self) -> None:
        """Cancel the producer and the watch, then release admission. Safe to repeat.

        The work runs in its own task. A cancelled response (the client
        left) stops waiting for it, and the task still finishes.
        """
        if self._cleanup is None:
            self._cleanup = asyncio.ensure_future(self._release())
            _CLEANUPS.add(self._cleanup)
            self._cleanup.add_done_callback(_CLEANUPS.discard)
        await asyncio.shield(self._cleanup)


class _AnswerStreamResponse(StreamingResponse):
    """Event-stream response that always releases its stream.

    A send can fail before the body iterator starts, and then the
    iterator's own clean-up never runs.
    """

    def __init__(self, stream: _AnswerStream, first: tuple[str, Any]) -> None:
        super().__init__(stream.frames(first), media_type="text/event-stream", headers=_HEADERS)
        self._stream = stream

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            await self._stream.close()


@router.post("/collections/{collection}/answer/stream", operation_id="streamAnswer")
async def stream_answer(
    collection: str,
    body: AnswerBody,
    request: Request,
    runtime: RuntimeDep,
    _: ReadScope,
) -> Response:
    """Answer a question and stream its stages as server-sent events.

    Same scope, Origin rule, body and result as ``answerCollection``.
    """
    stream = _AnswerStream(runtime, request, collection, body)
    try:
        first = await stream.open()
    except BaseException:
        await stream.close()
        raise
    kind, data = first
    if kind == "invalid":
        await stream.close()
        return error_response(400, str(data), error_type="validation")
    if kind == "gone":
        await stream.close()
        return Response(status_code=CLIENT_GONE)
    return _AnswerStreamResponse(stream, first)
