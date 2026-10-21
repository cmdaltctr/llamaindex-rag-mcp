"""Live tests for the streaming answer route: client leaves, parallel streams, shutdown.

Task 3.3 of add-answer-stage-progress. The requests run through raw ASGI
calls on the test's own event loop, so a test can hold the Engine mid-answer,
drop the connection and report any ASGI spec version. No model or network
call happens.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

from tests.unit.test_web_answer_stream_support import (  # noqa: E402
    ALL_STAGES,
    COLLECTION,
    RawStream,
    StagedEngine,
    staged_engine,
)
from tests.unit.test_web_documents_support import build_app  # noqa: E402

from omrg.transports.api.lifespan import shutdown_runtime  # noqa: E402
from omrg.transports.api.routes.answer_stream import stream_answer  # noqa: E402
from omrg.transports.api.routes.documents import AnswerBody  # noqa: E402


@pytest.fixture
def engine(tmp_path: Path, effective_settings: Any) -> StagedEngine:
    return staged_engine(tmp_path, effective_settings())


def _token(app: Any) -> str:
    return app.state.access_policy.issue_bearer({"read"}).token


@asynccontextmanager
async def _lifespan(app: Any, engine: StagedEngine) -> AsyncIterator[None]:
    """Run the app lifespan; release a held answer before shutdown.

    Shutdown waits for admitted work, so a failing check inside the block
    would otherwise hang on the held answer instead of failing.
    """
    async with app.router.lifespan_context(app):
        try:
            yield
        finally:
            engine.event("release").set()


def test_closing_the_stream_cancels_the_answer_and_releases_admission(
    tmp_path: Path, engine: StagedEngine
) -> None:
    """The generator's clean-up cancels the producer; the watch never fires here."""
    app, _ = build_app(tmp_path, engine)
    engine.hold_at = 1  # after ``searching``

    async def never_gone() -> bool:
        return False

    async def scenario() -> None:
        async with _lifespan(app, engine):
            runtime = app.state.runtime
            request = SimpleNamespace(app=app, is_disconnected=never_gone)
            response = await stream_answer(
                COLLECTION, AnswerBody(query="q"), request, runtime, None
            )
            frames = response.body_iterator
            first = await asyncio.wait_for(anext(frames), 3)
            assert "event: stage" in first and "searching" in first
            assert runtime.admission.active == 1
            await asyncio.wait_for(frames.aclose(), 3)
            assert engine.event("cancelled").is_set()
            assert runtime.admission.active == 0

    asyncio.run(scenario())


def test_two_streams_hold_only_their_own_stages(tmp_path: Path, engine: StagedEngine) -> None:
    app, _ = build_app(tmp_path, engine)
    engine.script = {"alpha": ALL_STAGES[:3], "beta": ALL_STAGES[:1]}
    engine.hold_at = 1

    async def scenario() -> None:
        async with _lifespan(app, engine):
            token = _token(app)
            alpha = RawStream(app, token, "alpha")
            beta = RawStream(app, token, "beta")
            await alpha.wait_frames(1)
            await beta.wait_frames(1)
            assert app.state.runtime.admission.active == 2  # both run at once
            engine.event("release").set()
            await asyncio.wait_for(asyncio.gather(alpha.task, beta.task), 5)
            for stream, question, stages in (
                (alpha, "alpha", ["searching", "writing", "citing"]),
                (beta, "beta", ["searching"]),
            ):
                stage_data = [data for event, _, data in stream.frames if event == "stage"]
                assert [data["stage"] for data in stage_data] == stages
                assert [data["sequence"] for data in stage_data] == list(range(1, len(stages) + 1))
                assert stream.events()[-1] == "result"
                assert stream.frames[-1][2]["query"] == question
            assert app.state.runtime.admission.active == 0

    asyncio.run(scenario())


@pytest.mark.parametrize("hold_at", [0, 1], ids=["before-first-stage", "after-searching"])
def test_client_leaving_during_a_long_model_call_is_noticed_on_spec_2_4(
    tmp_path: Path, engine: StagedEngine, hold_at: int
) -> None:
    """With ASGI spec 2.4 Starlette only notices a gone client on send; the watch does."""
    app, _ = build_app(tmp_path, engine)
    engine.hold_at = hold_at

    async def scenario() -> None:
        async with _lifespan(app, engine):
            stream = RawStream(app, _token(app), "q", spec_version="2.4")
            await asyncio.wait_for(engine.event("holding").wait(), 3)
            sent_before = len(stream.frames)
            assert sent_before == hold_at
            stream.disconnect()
            await asyncio.wait_for(engine.event("cancelled").wait(), 3)
            await asyncio.wait_for(stream.task, 3)
            assert len(stream.frames) == sent_before  # nothing sent after the client left
            assert "result" not in stream.events()
            assert app.state.runtime.admission.active == 0

    asyncio.run(scenario())


def test_shutdown_waits_for_the_stream_and_the_stream_ends_with_its_result(
    tmp_path: Path, engine: StagedEngine
) -> None:
    app, _ = build_app(tmp_path, engine)
    engine.hold_at = 1

    async def scenario() -> None:
        async with _lifespan(app, engine):
            runtime = app.state.runtime
            stream = RawStream(app, _token(app), "q")
            await stream.wait_frames(1)
            shutdown = asyncio.create_task(shutdown_runtime(runtime))
            await asyncio.sleep(0.1)
            assert not shutdown.done()
            assert not engine.closed
            assert not runtime.admission.is_open
            engine.event("release").set()
            await asyncio.wait_for(stream.task, 5)
            await asyncio.wait_for(shutdown, 5)
            assert stream.events() == ["stage", "stage", "stage", "result"]
            assert stream.frames[-1][2]["status"] == "ok"
            assert engine.closed

    asyncio.run(scenario())
