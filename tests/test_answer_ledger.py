"""Per-answer completion ledger: reasoning and usage on the answer result.

Covers tasks 3.1 to 3.3 of ``add-chat-reasoning-and-usage`` (design D1, D3).
Real provider readers are not used: each test injects a fake reader or a
fake raw reply, so the tests stay independent of the provider modules.
"""

from __future__ import annotations

import asyncio
import types
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from conftest import build_mcp_server, direct_ctx
from omrs.core.providers.llm.reply import ReplyFacts
from omrs.core.settings import AnswerBlock, EffectiveSettings, MetadataBlock
from omrs.engine_answer import (
    REASONING_CAP_BYTES,
    ClientCompletion,
    CompletionLedger,
    build_verifier,
    collecting,
    recording_answer_llm,
    recording_judge,
    server_seam,
)


class _RawLLM:
    """Fake LLM whose replies carry a ``raw`` payload for the reader."""

    def __init__(self, *raws: Any) -> None:
        self._raws = list(raws)

    async def acomplete(self, prompt: str, **_: Any) -> Any:
        return types.SimpleNamespace(text=f"text for {prompt}", raw=self._raws.pop(0))


def _read(raw: Any) -> ReplyFacts:
    """Fake reader: the raw reply is already a ``ReplyFacts``."""
    return raw


def _run_seam(llm: Any, ledger: CompletionLedger, prompts: list[str]) -> list[str]:
    seam = server_seam(llm, ledger, read_reply=_read)

    async def _go() -> list[str]:
        return [await seam(p) for p in prompts]

    return asyncio.run(_go())


# ── 3.1 Ledger beside the seam ──────────────────────────────────────────


def test_two_replies_sum_usage_and_join_reasoning() -> None:
    ledger = CompletionLedger()
    llm = _RawLLM(
        ReplyFacts("first thought", 10, 4, 1, 0.001),
        ReplyFacts("second thought", 15, 7, 2, 0.002),
    )

    texts = _run_seam(llm, ledger, ["a", "b"])

    assert texts == ["text for a", "text for b"]
    assert ledger.usage() == {
        "input_tokens": 25,
        "output_tokens": 11,
        "reasoning_tokens": 3,
        "cost_usd": pytest.approx(0.003),
        "calls": 2,
    }
    assert ledger.reasoning() == "first thought\n\nsecond thought"


def test_seam_without_ledger_still_returns_text() -> None:
    seam = server_seam(_RawLLM(ReplyFacts()))
    assert asyncio.run(seam("x")) == "text for x"


def test_figure_is_null_unless_every_call_reported_it() -> None:
    ledger = CompletionLedger()
    llm = _RawLLM(ReplyFacts(None, 10, 4, None, 0.001), ReplyFacts(None, 15, 7, 2, None))

    _run_seam(llm, ledger, ["a", "b"])

    assert ledger.usage() == {
        "input_tokens": 25,
        "output_tokens": 11,
        "reasoning_tokens": None,
        "cost_usd": None,
        "calls": 2,
    }
    assert ledger.reasoning() is None


def test_reasoning_is_capped_at_64_kb_with_a_marker() -> None:
    ledger = CompletionLedger()
    _run_seam(_RawLLM(ReplyFacts("é" * 70_000)), ledger, ["a"])

    text = ledger.reasoning()

    assert text is not None
    assert len(text.encode("utf-8")) <= REASONING_CAP_BYTES
    assert text.endswith("[reasoning truncated]")


def test_failing_reader_counts_the_call_with_null_figures() -> None:
    def _broken(_raw: Any) -> ReplyFacts:
        raise KeyError("usage")

    ledger = CompletionLedger()
    seam = server_seam(_RawLLM(object()), ledger, read_reply=_broken)

    assert asyncio.run(seam("a")) == "text for a"
    assert ledger.usage()["calls"] == 1
    assert ledger.usage()["input_tokens"] is None


def test_judge_calls_are_added_to_the_same_ledger(tmp_path: Any) -> None:
    ledger = CompletionLedger()
    _run_seam(_RawLLM(ReplyFacts("answer thought", 10, 4, 0, 0.001)), ledger, ["a"])
    judge = _RawLLM(ReplyFacts("judge thought", 5, 1, 0, 0.0002), ReplyFacts(None, 5, 1, 0, 0.0002))
    effective = _settings(tmp_path, verify_claims=True)

    with patch("omrs.engine_answer.reply_reader", return_value=_read):
        verify, reason = build_verifier(effective, lambda _block: judge, str, ledger)
        assert reason is None
        assert verify is not None

        async def _judge_twice() -> None:
            await verify("c1")
            await verify("c2")

        asyncio.run(_judge_twice())

    usage = ledger.usage()
    assert usage["calls"] == 3
    assert usage["cost_usd"] == 0.0014
    assert usage["input_tokens"] == 20
    # Judge reasoning counts toward usage only; the reasoning box shows the answer's.
    assert ledger.reasoning() == "answer thought"


def test_graph_resources_record_into_the_active_ledger() -> None:
    """The user-profile graph path reaches the same ledger through its resources."""
    answer = recording_answer_llm(lambda: _RawLLM(ReplyFacts("graph thought", 2, 1, 0, 0.5)), "x")
    judge = recording_judge(
        lambda _block: _RawLLM(ReplyFacts("judge", 1, 1, 0, 0.25)), lambda _b: "y"
    )
    ledger = CompletionLedger()

    async def _go() -> None:
        with collecting(ledger):
            await answer().acomplete("a")
            await judge(None).acomplete("c")
        await answer().acomplete("outside")  # No active ledger: nothing recorded.

    with patch("omrs.engine_answer.reply_reader", return_value=_read):
        asyncio.run(_go())

    assert ledger.usage()["calls"] == 2
    assert ledger.usage()["cost_usd"] == 0.75
    assert ledger.reasoning() == "graph thought"


def test_graph_resources_keep_a_missing_model_missing() -> None:
    assert recording_answer_llm(None, "x") is None
    assert recording_judge(None, lambda _b: "y") is None
    assert recording_answer_llm(lambda: None, "x")() is None


# ── 3.2 Engine result shape ─────────────────────────────────────────────


def _settings(tmp_path: Any, **answer: Any) -> EffectiveSettings:
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
        answer=AnswerBlock(**answer),
    )


def _engine(settings: EffectiveSettings, **kwargs: Any) -> Any:
    from omrs.engine import Engine

    store = MagicMock(cache_identity="test-identity")
    return Engine(settings, store=store, embed_model=MagicMock(model_name="m"), **kwargs)


def _core_calling(prompts: int) -> Any:
    """Patch core answer with a fake that calls the answer seam *prompts* times."""

    async def fake_answer(_query: str, **kwargs: Any) -> dict:
        complete = kwargs["complete"]
        for n in range(prompts):
            await complete(f"p{n}")
        return {"status": "ok", "answer": "x", "completion_source": kwargs["completion_source"]}

    return patch("omrs.core.answer.pipeline.answer", side_effect=fake_answer)


def test_server_answer_carries_reasoning_and_usage(tmp_path: Any) -> None:
    llm = _RawLLM(ReplyFacts("The user asks about colour.", 25, 11, 2, 0.00000925))
    engine = _engine(_settings(tmp_path), answer_llm_factory=lambda: llm)

    with _core_calling(1), patch("omrs.engine_answer.reply_reader", return_value=_read):
        result = asyncio.run(engine.answer("q"))

    assert result["answer"] == "x"
    assert result["reasoning"] == "The user asks about colour."
    assert result["usage"] == {
        "input_tokens": 25,
        "output_tokens": 11,
        "reasoning_tokens": 2,
        "cost_usd": 0.00000925,
        "calls": 1,
    }


def test_server_answer_without_reasoning_has_no_reasoning_key(tmp_path: Any) -> None:
    llm = _RawLLM(ReplyFacts(None, 3, 1, None, None))
    engine = _engine(_settings(tmp_path), answer_llm_factory=lambda: llm)

    with _core_calling(1), patch("omrs.engine_answer.reply_reader", return_value=_read):
        result = asyncio.run(engine.answer("q"))

    assert "reasoning" not in result
    assert result["usage"]["cost_usd"] is None
    assert result["usage"]["calls"] == 1


def test_server_answer_with_no_model_call_has_no_usage(tmp_path: Any) -> None:
    engine = _engine(_settings(tmp_path), answer_llm_factory=lambda: _RawLLM())

    with _core_calling(0):
        result = asyncio.run(engine.answer("q"))

    assert "usage" not in result
    assert "reasoning" not in result


def test_client_sampled_answer_has_no_usage(tmp_path: Any) -> None:
    async def client(prompt: str) -> str:
        return "client text"

    engine = _engine(_settings(tmp_path))
    completion = ClientCompletion(complete=client, source="client_mrtr", max_rounds=2)

    with _core_calling(1):
        result = asyncio.run(engine.answer("q", client_completion=completion))

    assert result["completion_source"] == "client_mrtr"
    assert "usage" not in result
    assert "reasoning" not in result


# ── 3.3 MCP flag ────────────────────────────────────────────────────────


_MCP_RESULT = {
    "status": "ok",
    "answer": "x",
    "completion_source": "server",
    "reasoning": "thinking",
    "usage": {
        "input_tokens": 1,
        "output_tokens": 1,
        "reasoning_tokens": None,
        "cost_usd": None,
        "calls": 1,
    },
}


async def _mcp_answer(monkeypatch: pytest.MonkeyPatch, **kwargs: Any) -> dict:
    from omrs.transports.mcp import answer_documents

    async def _fake(*_args: Any, **_kwargs: Any) -> dict:
        return dict(_MCP_RESULT)

    server = build_mcp_server()
    monkeypatch.setattr(server.test_context.engine, "answer", _fake)
    return await answer_documents(query="q", ctx=direct_ctx(server), **kwargs)


async def test_mcp_omits_reasoning_unless_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    result = await _mcp_answer(monkeypatch)

    assert "reasoning" not in result
    assert result["usage"]["calls"] == 1


async def test_mcp_includes_reasoning_when_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    result = await _mcp_answer(monkeypatch, include_reasoning=True)

    assert result["reasoning"] == "thinking"
    assert result["usage"]["calls"] == 1


def test_mcp_description_names_the_flag() -> None:
    from omrs.transports.mcp.answer import DESCRIPTION

    assert "include_reasoning" in DESCRIPTION
