"""Tests for the MRTR machinery split into ``transports/mcp/answer_mrtr.py``.

Regression tests for the review findings in the MCP transport's
multi-round-trip request flow:

* F2 — the per-request retrieval cache must survive the whole MRTR
  flow (one retrieval per answer, no stale entries after the body).
* F3 — resolver-era failures surface as structured results, never as
  raw tool errors.
* F4 — ``ANSWER__ENABLED=false`` gates every completion path,
  including client sampling.
* F5 — client rounds are capped by ``_MAX_MRTR_ROUNDS`` and an
  exhausted client seam never replays silently.
* F11 — diagnostics report honest retrieval/generation timings and
  completion counts on the client path.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from mcp.client import Client
from mcp.types import CreateMessageResult, SamplingCapability, TextContent

from conftest import build_mcp_server, direct_ctx
from omrs.core.ingestion import ingest_path_async
from omrs.transports.mcp import answer_documents
from omrs.transports.mcp.answer_mrtr import (
    _MAX_MRTR_ROUNDS,
    _client_seam,
    _outstanding_payloads,
)

_COLLECTION = "answer_mrtr_docs"
_DOC_TEXT = "The quantum lantern array is calibrated at station one every Tuesday. " * 40
_QUERY = "quantum lantern calibration"
_GROUNDED_REPLY = "The array is calibrated at station one [1]."


async def _ingest_collection(tmp_path: Path) -> None:
    """Ingest one document into the module's collection."""
    source = tmp_path / "mrtr-doc.txt"
    source.write_text(_DOC_TEXT, encoding="utf-8")
    result = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert result["status"] == "ok", result


def _extract_result(result: Any) -> dict[str, Any]:
    """Extract the data payload from a CallToolResult."""
    if hasattr(result, "structured_content") and result.structured_content:
        return result.structured_content.get("result", result.structured_content)
    import json

    return json.loads(result.content[0].text)


def _counting_search(server: Any, *, delay: float = 0.0) -> list[int]:
    """Wrap the Engine's search (the resolver-side retrieval) with a counter."""
    engine = server.test_context.engine
    real_search = engine.search
    calls: list[int] = []

    def _counting(*args: Any, **kwargs: Any) -> list[dict]:
        calls.append(1)
        if delay:
            time.sleep(delay)
        return real_search(*args, **kwargs)

    engine.search = _counting  # the engine is private to this test's server
    return calls


def _settings_with(**answer: Any) -> Any:
    """Return the default settings with an overridden answer block."""
    from omrs.core.settings import AnswerBlock, get_default_effective_settings

    return get_default_effective_settings().model_copy(update={"answer": AnswerBlock(**answer)})


def _scripted_planner(
    monkeypatch: pytest.MonkeyPatch, prompts_for_rounds: dict[int, str] | None = None
) -> list[str]:
    """Patch the resolver-side planner with a scripted round count.

    ``prompts_for_rounds`` maps ``len(previous_replies) -> prompt``; a
    round whose reply count is absent ends the chain (``None``).  The
    default asks exactly one round.
    """
    from omrs.transports.mcp import answer_mrtr

    if prompts_for_rounds is None:
        prompts_for_rounds = {0: "planned prompt round 1"}
    seen: list[str] = []

    async def _planner(query, nodes, *, previous_replies, **kwargs: Any):
        prompt = prompts_for_rounds.get(len(previous_replies))
        if prompt is not None:
            seen.append(prompt)
        return prompt

    monkeypatch.setattr(answer_mrtr, "plan_next_prompt", _planner)
    return seen


def _sampling_callback(seen_prompts: list[str], reply: str = _GROUNDED_REPLY, delay: float = 0.0):
    """Build a client sampling callback that records prompts."""

    async def _callback(context: Any, params: Any) -> CreateMessageResult:
        block = params.messages[-1].content
        seen_prompts.append(getattr(block, "text", ""))
        if delay:
            time.sleep(delay)
        return CreateMessageResult(
            role="assistant",
            model="client-model",
            content=TextContent(type="text", text=reply),
        )

    return _callback


# ── F2: one retrieval per MRTR answer, cache evicted by the body ─────────


async def test_mrtr_answer_performs_exactly_one_retrieval(
    mcp_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An N-round MRTR answer searches exactly once; no cache entry survives."""
    await _ingest_collection(tmp_path)
    calls = _counting_search(mcp_server)
    _scripted_planner(monkeypatch)  # single client round (N = 1)
    seen_prompts: list[str] = []

    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback(seen_prompts),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {"query": _QUERY, "collection": _COLLECTION, "similarity_threshold": 0.0},
        )

    data = _extract_result(result)
    assert data["status"] == "ok", data
    assert len(seen_prompts) == 1
    assert len(calls) == 1, f"the whole MRTR flow must run search() exactly once, ran {len(calls)}"
    assert _outstanding_payloads() == 0, "no cache entry may remain after the body returns"


async def test_mrtr_multi_round_answer_performs_exactly_one_retrieval(
    mcp_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A two-round MRTR answer still searches exactly once."""
    await _ingest_collection(tmp_path)
    calls = _counting_search(mcp_server)
    _scripted_planner(
        monkeypatch,
        {0: "round-1 prompt", 1: "round-2 prompt"},  # asks exactly two rounds
    )
    seen_prompts: list[str] = []

    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback(seen_prompts),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {"query": _QUERY, "collection": _COLLECTION, "similarity_threshold": 0.0},
        )

    data = _extract_result(result)
    assert data["status"] == "ok", data
    assert len(seen_prompts) == 2
    assert len(calls) == 1, f"every MRTR round must share one retrieval, ran {len(calls)}"
    assert _outstanding_payloads() == 0


# ── F3: resolver failures surface as structured results ──────────────────


async def test_resolver_retrieval_failure_returns_structured_error(
    mcp_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A retrieval failure inside the resolver chain never escapes raw."""
    await _ingest_collection(tmp_path)

    def _boom(*args: Any, **kwargs: Any) -> list[dict]:
        raise RuntimeError("collection missing")

    monkeypatch.setattr(mcp_server.test_context.engine, "search", _boom)
    seen_prompts: list[str] = []

    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback(seen_prompts),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {"query": _QUERY, "collection": _COLLECTION, "similarity_threshold": 0.0},
        )

    data = _extract_result(result)
    assert data["status"] == "error", data
    assert data["failure_stage"] == "retrieval"
    assert "collection missing" in (data["error"] or "")
    for key in ("query", "answer", "citations", "evidence", "failure_stage", "error"):
        assert key in data, f"error result is missing the standard key {key!r}"
    assert seen_prompts == [], "no Sample may be issued after a retrieval failure"
    assert _outstanding_payloads() == 0


async def test_resolver_planning_failure_returns_structured_generation_error(
    mcp_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A planning failure inside the resolver chain reports generation."""
    await _ingest_collection(tmp_path)
    from omrs.transports.mcp import answer_mrtr

    async def _boom(*args: Any, **kwargs: Any) -> str:
        raise RuntimeError("planner exploded")

    monkeypatch.setattr(answer_mrtr, "plan_next_prompt", _boom)
    seen_prompts: list[str] = []

    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback(seen_prompts),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {"query": _QUERY, "collection": _COLLECTION, "similarity_threshold": 0.0},
        )

    data = _extract_result(result)
    assert data["status"] == "error", data
    assert data["failure_stage"] == "generation"
    assert "planner exploded" in (data["error"] or "")
    assert seen_prompts == []
    assert _outstanding_payloads() == 0


# ── F4: the master switch gates client sampling ──────────────────────────


async def test_disabled_modern_session_never_samples_the_client(
    tmp_path: Path,
) -> None:
    """``ANSWER__ENABLED=false``: no Sample issued, actionable error."""
    await _ingest_collection(tmp_path)
    server = build_mcp_server(
        effective=_settings_with(enabled=False), profile_resolver_factory=None
    )
    seen_prompts: list[str] = []
    async with Client(
        server,
        sampling_callback=_sampling_callback(seen_prompts),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {"query": _QUERY, "collection": _COLLECTION, "similarity_threshold": 0.0},
        )

    data = _extract_result(result)
    assert data["status"] == "error", data
    assert "ANSWER__ENABLED" in (data["error"] or "")
    assert seen_prompts == [], "the client model must not be called when disabled"
    assert _outstanding_payloads() == 0


async def test_disabled_server_path_returns_disabled_error_before_the_model(
    tmp_path: Path,
) -> None:
    """Disabled direct call: error before the server model is resolved."""
    await _ingest_collection(tmp_path)

    class _NeverLLM:
        calls = 0

        async def acomplete(self, prompt: str, **kwargs: Any) -> Any:
            _NeverLLM.calls += 1
            raise AssertionError("the server model must not run when disabled")

    def _never_built() -> Any:
        raise AssertionError("the server model must not even be built when disabled")

    server = build_mcp_server(
        effective=_settings_with(enabled=False),
        profile_resolver_factory=None,
        answer_llm_factory=_never_built,
    )
    result = await answer_documents(
        query=_QUERY,
        collection=_COLLECTION,
        similarity_threshold=0.0,
        ctx=direct_ctx(server),
    )

    assert result["status"] == "error"
    assert "ANSWER__ENABLED" in (result["error"] or "")
    assert _NeverLLM.calls == 0


# ── F5: bounded client rounds, exhausted seam never replays ──────────────


async def test_client_seam_exhaustion_raises_instead_of_replaying() -> None:
    """The client seam must not silently replay the last reply."""
    seam = _client_seam(["first reply"])

    assert await seam("prompt 1") == "first reply"
    with pytest.raises(RuntimeError, match="exhausted"):
        await seam("prompt 2")


async def test_client_rounds_are_capped_by_the_chain_depth(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``max_rounds`` above the chain depth still serves at most 4 rounds."""
    await _ingest_collection(tmp_path)
    mcp_server = build_mcp_server(
        effective=_settings_with(max_rounds=8), profile_resolver_factory=None
    )
    seen_prompts: list[str] = []
    # The planner asks forever: every reply triggers another round plan.
    _scripted_planner(monkeypatch, {i: f"round-{i + 1} prompt" for i in range(16)})
    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback(seen_prompts),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {
                "query": _QUERY,
                "collection": _COLLECTION,
                "similarity_threshold": 0.0,
                "diagnostics": True,
            },
        )

    data = _extract_result(result)
    assert data["status"] == "ok", data
    assert _MAX_MRTR_ROUNDS == 4
    assert len(seen_prompts) == _MAX_MRTR_ROUNDS, (
        "the client must answer at most _MAX_MRTR_ROUNDS times"
    )
    assert data["diagnostics"]["completion_calls"] == _MAX_MRTR_ROUNDS, (
        "diagnostics must report the rounds actually served, not the cap"
    )


async def test_exhausted_client_seam_is_a_generation_error(
    mcp_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Synthesis outliving the client replies is an honest generation error."""
    from omrs.core.answer import pipeline as answer_pipeline

    await _ingest_collection(tmp_path)
    # Planning asks two rounds; the body's synthesis demands three seam
    # calls while only two client replies exist.
    _scripted_planner(monkeypatch, {0: "round-1 prompt", 1: "round-2 prompt"})

    async def _thirsty_synthesis(query, nodes, *, seam, **kwargs: Any):
        first = await seam("prompt a")
        second = await seam("prompt b")
        third = await seam("prompt c")  # exhausted: only two replies exist
        return f"{first} {second} {third}", 3

    monkeypatch.setattr(answer_pipeline, "run_synthesis", _thirsty_synthesis)
    seen_prompts: list[str] = []

    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback(seen_prompts),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {
                "query": _QUERY,
                "collection": _COLLECTION,
                "similarity_threshold": 0.0,
                "diagnostics": True,
            },
        )

    data = _extract_result(result)
    assert data["status"] == "error", data
    assert data["failure_stage"] == "generation"
    assert "exhausted" in (data["error"] or "")
    assert data["evidence"], "evidence must be retained on the failure"
    assert data["diagnostics"]["completion_calls"] == 2, (
        "the failure must report the client rounds actually served"
    )


# ── F11: honest timings and counts on the client path ────────────────────


async def test_client_path_diagnostics_report_real_timings(
    mcp_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retrieval_ms and generation_ms include the real work's wall-time."""
    await _ingest_collection(tmp_path)
    _counting_search(mcp_server, delay=0.08)
    _scripted_planner(monkeypatch)
    seen_prompts: list[str] = []

    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback(seen_prompts, delay=0.08),
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {
                "query": _QUERY,
                "collection": _COLLECTION,
                "similarity_threshold": 0.0,
                "diagnostics": True,
            },
        )

    data = _extract_result(result)
    assert data["status"] == "ok", data
    diagnostics = data["diagnostics"]
    assert diagnostics["retrieval_ms"] >= 40.0, (
        f"retrieval_ms must include the resolver's real retrieval, got "
        f"{diagnostics['retrieval_ms']}"
    )
    assert diagnostics["generation_ms"] >= 40.0, (
        f"generation_ms must include the client sampling latency, got "
        f"{diagnostics['generation_ms']}"
    )
    assert diagnostics["completion_calls"] == len(seen_prompts) == 1
