"""Shared helpers for the streaming answer route tests (add-answer-stage-progress).

Not a test module: it holds a scripted Engine that reports stages through
``on_stage``, a raw ASGI client that can report any ASGI spec version and
leave mid-stream, and a frame splitter. No model, LLM or network call
happens.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_documents_support import RecordingEngine, lance_store  # noqa: E402

from omrg.core.answer.progress import AnswerStage  # noqa: E402

COLLECTION = "notes"
ANSWER = f"/v1/collections/{COLLECTION}/answer"
STREAM = f"/v1/collections/{COLLECTION}/answer/stream"

ALL_STAGES: tuple[AnswerStage, ...] = tuple(AnswerStage)


class StagedEngine(RecordingEngine):
    """A real Engine whose ``answer`` reports a scripted list of stages.

    Attributes:
        script: Stages to report, per question; ``default`` for the rest.
        hold_at: Index in the script where the answer waits on ``release``
            (``0`` holds before any stage; ``None`` never holds).
        fail_at: Index where ``failure`` is raised (``0`` before any stage).
        cancelled: Set when the answer task is cancelled.
        holding: Set when the answer reaches ``hold_at``.
        closed: Whether the lifespan closed the Engine.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.answer_result = {"status": "ok", "query": "q", "answer": "A [1]."}
        self.script: dict[str, Sequence[AnswerStage]] = {}
        self.default: Sequence[AnswerStage] = ALL_STAGES[:3]
        self.hold_at: int | None = None
        self.fail_at = 0
        self.failure: BaseException | None = None
        self.closed = False
        self._loop_events: dict[str, asyncio.Event] = {}

    def event(self, name: str) -> asyncio.Event:
        """Return a loop-local event, made on first use inside the loop."""
        if name not in self._loop_events:
            self._loop_events[name] = asyncio.Event()
        return self._loop_events[name]

    async def answer(self, question: str, **kwargs: Any) -> dict:  # type: ignore[override]
        self.calls.append(("answer", (question,), kwargs))
        on_stage = kwargs.get("on_stage")
        stages = list(self.script.get(question, self.default))
        try:
            for index in range(len(stages) + 1):
                if index == self.fail_at and self.failure is not None:
                    raise self.failure
                if index == self.hold_at:
                    self.event("holding").set()
                    await self.event("release").wait()
                if index == len(stages):
                    break
                if on_stage is not None:
                    on_stage(stages[index])
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            self.event("cancelled").set()
            raise
        return {**self.answer_result, "query": question}

    def close(self) -> None:
        self.closed = True
        super().close()


def staged_engine(tmp_path: Path, settings: Any) -> StagedEngine:
    """Return a :class:`StagedEngine` over an empty isolated store."""
    return StagedEngine(settings, store=lance_store(tmp_path), embed_model=object())


def split_frames(text: str) -> list[tuple[str, str, Any]]:
    """Split an event-stream body into ``(event, raw block, decoded data)``."""
    frames = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event, data = "", None
        for line in block.splitlines():
            name, _, value = line.partition(": ")
            if name == "event":
                event = value
            elif name == "data":
                data = json.loads(value)
        frames.append((event, block, data))
    return frames


class RawStream:
    """One ``POST .../answer/stream`` request driven through raw ASGI calls.

    Args:
        app: The application.
        token: A bearer credential with the ``read`` scope.
        question: The question to post.
        spec_version: The ASGI HTTP spec version the fake server reports.
    """

    def __init__(self, app: Any, token: str, question: str, spec_version: str = "2.3") -> None:
        self.frames: list[tuple[str, str, Any]] = []
        self.status: int | None = None
        self.got_frame = asyncio.Event()
        self._leave = asyncio.Event()
        self._sent_request = False
        self._body = json.dumps({"query": question}).encode()
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": spec_version},
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": STREAM,
            "raw_path": STREAM.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"127.0.0.1:8765"),
                (b"authorization", f"Bearer {token}".encode()),
                (b"content-type", b"application/json"),
                (b"content-length", str(len(self._body)).encode()),
            ],
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8765),
        }
        self.task = asyncio.create_task(app(scope, self._receive, self._send))

    async def _receive(self) -> dict[str, Any]:
        if not self._sent_request:
            self._sent_request = True
            return {"type": "http.request", "body": self._body, "more_body": False}
        await self._leave.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message.get("body"):
            self.frames += split_frames(message["body"].decode())
            self.got_frame.set()

    def disconnect(self) -> None:
        """Simulate the browser closing the connection."""
        self._leave.set()

    async def wait_frames(self, count: int, timeout: float = 5.0) -> None:
        """Wait until at least *count* frames arrived."""

        async def poll() -> None:
            while len(self.frames) < count:
                self.got_frame.clear()
                await self.got_frame.wait()

        await asyncio.wait_for(poll(), timeout)

    def events(self) -> list[str]:
        """Return the event names received so far."""
        return [event for event, _, _ in self.frames]
