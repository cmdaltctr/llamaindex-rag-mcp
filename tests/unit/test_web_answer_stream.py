"""Tests for ``POST /v1/collections/{collection}/answer/stream`` (tasks 3.1 and 3.2).

The route answers with ``stage`` frames, then one ``result`` frame. It
follows the blocking answer route for scope, Origin, body validation,
admission, Engine refusal and error shape. Stage frames hold only a stage
name, a sequence number and the elapsed milliseconds. The Engine is a
scripted double; no model or network call happens.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_answer_stream_support import (  # noqa: E402
    ALL_STAGES,
    ANSWER,
    STREAM,
    StagedEngine,
    split_frames,
    staged_engine,
)
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    login,
)


@pytest.fixture
def engine(tmp_path: Path, effective_settings: Any) -> StagedEngine:
    return staged_engine(tmp_path, effective_settings())


# ── Frames ───────────────────────────────────────────────────────────────


def test_stage_frames_then_one_result_frame(tmp_path: Path, engine: StagedEngine) -> None:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(STREAM, json={"query": "q"}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"
    assert "retry:" not in response.text
    frames = split_frames(response.text)
    assert [event for event, _, _ in frames] == ["stage", "stage", "stage", "result"]
    assert [data["stage"] for _, _, data in frames[:3]] == ["searching", "writing", "citing"]
    assert frames[-1][2]["status"] == "ok"
    ((_, _, kwargs),) = engine.calls
    assert callable(kwargs["on_stage"])
    assert kwargs["collection_name"] == "notes"


def test_result_frame_equals_blocking_response(tmp_path: Path, engine: StagedEngine) -> None:
    engine.answer_result = {
        "status": "ok",
        "query": "q",
        "answer": "Chunk zero is first [1].",
        "citations": [{"ordinal": 1, "chunk_id": "chk_1"}],
        "evidence": [],
        "failure_stage": None,
        "error": None,
        "completion_source": "server",
    }
    app, policy = build_app(tmp_path, engine)
    body = {"query": "q", "top_k": 4, "expand_window": 2}
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        blocking = client.post(ANSWER, json=body, headers=ORIGIN)
        streamed = client.post(STREAM, json=body, headers=ORIGIN)
    assert blocking.status_code == streamed.status_code == 200
    assert split_frames(streamed.text)[-1][2] == blocking.json()
    blocking_call, stream_call = engine.calls
    stream_kwargs = {k: v for k, v in stream_call[2].items() if k != "on_stage"}
    assert stream_kwargs == blocking_call[2]


def test_the_diagnostics_flag_reaches_the_engine(tmp_path: Path, engine: StagedEngine) -> None:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        default = client.post(STREAM, json={"query": "q"}, headers=ORIGIN)
        asked = client.post(STREAM, json={"query": "q", "diagnostics": True}, headers=ORIGIN)
    assert (default.status_code, asked.status_code) == (200, 200)
    assert [kwargs["include_diagnostics"] for _, _, kwargs in engine.calls] == [False, True]


def test_any_other_engine_error_ends_with_the_failure_result(
    tmp_path: Path, engine: StagedEngine
) -> None:
    engine.failure = RuntimeError("provider exploded")
    engine.fail_at = 1  # after ``searching``
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        blocking = client.post(ANSWER, json={"query": "q"}, headers=ORIGIN)
        response = client.post(STREAM, json={"query": "q"}, headers=ORIGIN)
    assert response.status_code == 200
    frames = split_frames(response.text)
    assert [event for event, _, _ in frames] == ["stage", "result"]
    result = frames[-1][2]
    assert result == blocking.json()
    assert (result["status"], result["failure_stage"], result["completion_source"]) == (
        "error",
        None,
        "none",
    )
    assert result["error"].startswith("RuntimeError")
    assert "exploded" not in response.text


# ── Refusals before the stream opens ─────────────────────────────────────


def test_engine_value_error_gives_the_blocking_400_and_releases_admission(
    tmp_path: Path, engine: StagedEngine
) -> None:
    engine.failure = ValueError("Profile 'mine' has no saved Answer graph.")
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        blocking = client.post(ANSWER, json={"query": "q"}, headers=ORIGIN)
        response = client.post(STREAM, json={"query": "q"}, headers=ORIGIN)
        active = app.state.runtime.admission.active
    assert response.status_code == blocking.status_code == 400
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == blocking.json()
    assert active == 0


def test_bad_body_gets_the_blocking_error_and_no_stream(
    tmp_path: Path, engine: StagedEngine
) -> None:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        for body in ({"query": "q", "bogus": 1}, {"query": "x" * 4097}):
            blocking = client.post(ANSWER, json=body, headers=ORIGIN)
            streamed = client.post(STREAM, json=body, headers=ORIGIN)
            assert streamed.status_code == blocking.status_code == 400
            assert streamed.json() == blocking.json()
    assert engine.calls == []


def test_closed_admission_gives_503_and_no_stream(tmp_path: Path, engine: StagedEngine) -> None:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        app.state.runtime.admission.close()
        response = client.post(STREAM, json={"query": "q"}, headers=ORIGIN)
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert engine.calls == []


def test_authentication_scope_and_origin(tmp_path: Path, engine: StagedEngine) -> None:
    app, policy = build_app(tmp_path, engine)
    reader = bearer(policy, "read")
    runner = bearer(policy, "run")
    with TestClient(app, base_url=BASE) as client:
        anonymous = client.post(STREAM, json={"query": "q"})
        wrong_scope = client.post(STREAM, json={"query": "q"}, headers=runner)
        login(client, policy)
        foreign = client.post(STREAM, json={"query": "q"}, headers={"Origin": "http://evil.test"})
        assert engine.calls == []
        client.cookies.clear()
        read_ok = client.post(STREAM, json={"query": "q"}, headers=reader)
    assert anonymous.status_code == 401
    assert wrong_scope.status_code == 403
    assert foreign.status_code == 403
    assert read_ok.status_code == 200
    assert split_frames(read_ok.text)[-1][0] == "result"


# ── Content-free stage frames (task 3.2) ─────────────────────────────────


def test_stage_frames_hold_no_question_or_saved_key(tmp_path: Path, engine: StagedEngine) -> None:
    saved = "sk-or-v1-saved-key-0123456789abcdef"
    marker = "MARKER-QUESTION-7f3a"
    engine.default = ALL_STAGES[:2]
    engine.answer_result = {
        "status": "error",
        "answer": None,
        "citations": [],
        "evidence": [],
        "failure_stage": "generation",
        "error": f"AuthError: provider rejected key {saved}",
        "completion_source": "none",
    }
    app, policy = build_app(tmp_path, engine)
    app.state.secrets.add(saved)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(STREAM, json={"query": marker}, headers=ORIGIN)
    assert response.status_code == 200
    frames = split_frames(response.text)
    stage_blocks = [block for event, block, _ in frames if event == "stage"]
    assert len(stage_blocks) == 2
    for block in stage_blocks:
        assert marker not in block
        assert saved not in block
    assert saved not in response.text
    result = frames[-1][2]
    assert result["error"] == "AuthError: provider rejected key ***"
    assert result["query"] == marker


def test_stage_frames_hold_exactly_three_fields_in_order(
    tmp_path: Path, engine: StagedEngine
) -> None:
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(STREAM, json={"query": "q"}, headers=ORIGIN)
    stages = [data for event, _, data in split_frames(response.text) if event == "stage"]
    assert [set(data) for data in stages] == [{"stage", "sequence", "elapsed_ms"}] * 3
    assert [data["sequence"] for data in stages] == [1, 2, 3]
    elapsed = [data["elapsed_ms"] for data in stages]
    assert all(isinstance(value, int) and value >= 0 for value in elapsed)
    assert elapsed == sorted(elapsed)


def test_text_passed_as_a_stage_never_reaches_a_frame(tmp_path: Path, engine: StagedEngine) -> None:
    """A stage value outside the closed vocabulary is dropped, not framed."""
    engine.default = [ALL_STAGES[0], "the question text", ALL_STAGES[1]]  # type: ignore[list-item]
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        response = client.post(STREAM, json={"query": "q"}, headers=ORIGIN)
    assert "the question text" not in response.text
    stages = [data["stage"] for event, _, data in split_frames(response.text) if event == "stage"]
    assert stages == ["searching", "writing"]
