"""Server log routes (design D13).

Both routes need the browser session (`manage` scope): a bearer credential
never reads the server log. Records are redacted before they enter the
buffer (see ``log_buffer``). The stream replays after a sequence, like the
run event stream, and ends when the server stops admitting requests.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import Response, StreamingResponse

from ..engine_access import RuntimeDep
from ..errors import API_HEADERS
from ..lifespan import WebRuntime
from ..log_buffer import LogBuffer
from .experiments import ManageScope
from .graphs import ok
from .runs import STREAM_RETRY_MS, _frame, _start_sequence

router = APIRouter(prefix="/v1")

#: Seconds between looks at the buffer while a stream waits for a record.
POLL_SECONDS = 0.2


def _buffer(request: Request) -> LogBuffer:
    return request.app.state.log_buffer


@router.get("/logs", operation_id="getLogs")
async def get_logs(
    _: ManageScope,
    request: Request,
    after: Annotated[int, Query(ge=0)] = 0,
) -> Response:
    """Return the buffered records after a sequence, oldest first.

    `last_seq` is the newest sequence, which is 0 when nothing was logged.
    A client that holds a copy asks again with `after=<last_seq>`.
    """
    buffer = _buffer(request)
    return ok({"records": buffer.records(after), "last_seq": buffer.last_seq})


async def _log_stream(runtime: WebRuntime, buffer: LogBuffer, after: int) -> AsyncIterator[str]:
    """Yield SSE frames until admission closes or the client leaves."""
    closed = asyncio.ensure_future(runtime.admission.wait_closed())
    try:
        yield f"retry: {STREAM_RETRY_MS}\n\n"
        cursor = after
        while not closed.done():
            for record in buffer.records(cursor):
                cursor = record["seq"]
                yield _frame("log", record, record["seq"])
            await asyncio.wait({closed}, timeout=POLL_SECONDS)
        yield _frame("server.closing", {"reason": "The server is shutting down."})
    finally:
        closed.cancel()


@router.get("/logs/stream", operation_id="streamLogs")
async def stream_logs(
    _: ManageScope,
    request: Request,
    runtime: RuntimeDep,
    after: Annotated[int | None, Query(ge=0)] = None,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> Response:
    """Stream new records as `text/event-stream`, with replay after a sequence.

    `Last-Event-ID` wins over `after`. The stream ends with
    `event: server.closing` when the server stops.
    """
    start = _start_sequence(last_event_id, after)
    if isinstance(start, Response):
        return start
    headers = {**API_HEADERS, "Cache-Control": "no-store", "X-Accel-Buffering": "no"}
    return StreamingResponse(
        _log_stream(runtime, _buffer(request), start),
        media_type="text/event-stream",
        headers=headers,
    )
