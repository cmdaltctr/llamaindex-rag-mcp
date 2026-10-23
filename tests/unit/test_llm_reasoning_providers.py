"""Reasoning levels and reply reading per Chat provider (add-chat-reasoning-and-usage D2).

Each provider module maps a level to its own request field
(``reasoning_kwargs``) and reads reasoning text and usage from its own raw
reply (``read_reply``). An empty level must leave the request unchanged. A
reader must never raise. Keys in these tests are fake.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any

import httpx
import pytest
from tests.unit.test_connection_summary import make_settings

from omrs.core.providers.llm import (
    anthropic,
    llamacpp,
    ollama,
    openai_compatible,
    openrouter,
    registry,
)
from omrs.core.providers.llm.reply import NO_FACTS, ReplyFacts

OR_KEY = "sk-or-v1-0000aaaa1111bbbb2222cccc3333dddd"  # gitleaks:allow

#: The OpenRouter ``/chat/completions`` reply recorded on 2026-10-23
#: (``z-ai/glm-5.3-flash``, effort ``low``), trimmed to the fields OMRS reads.
OPENROUTER_REPLY: dict[str, Any] = {
    "id": "gen-1761256000-abc",
    "object": "chat.completion",
    "created": 1761256000,
    "model": "z-ai/glm-5.3-flash",
    "provider": "Z.AI",
    "choices": [
        {
            "index": 0,
            "finish_reason": "stop",
            "message": {
                "role": "assistant",
                "content": "The sky is blue [1].",
                "reasoning": "The user asks about colour.",
            },
        }
    ],
    "usage": {
        "prompt_tokens": 25,
        "completion_tokens": 11,
        "total_tokens": 36,
        "cost": 0.00000925,
        "completion_tokens_details": {"reasoning_tokens": 2},
    },
}

OLLAMA_REPLY: dict[str, Any] = {
    "model": "qwen3:0.6b",
    "message": {"role": "assistant", "content": "Hello!", "thinking": "The user greets me."},
    "done": True,
    "prompt_eval_count": 11,
    "eval_count": 106,
}

ANTHROPIC_REPLY: dict[str, Any] = {
    "id": "msg_01",
    "type": "message",
    "role": "assistant",
    "content": [
        {"type": "thinking", "thinking": "First step.", "signature": "sig"},
        {"type": "thinking", "thinking": "Second step.", "signature": "sig"},
        {"type": "text", "text": "The answer."},
    ],
    "usage": {"input_tokens": 40, "output_tokens": 30},
}


def _objects(value: Any) -> Any:
    """Return *value* with every dict turned into an attribute object (a pydantic-like reply)."""
    if isinstance(value, dict):
        return types.SimpleNamespace(**{k: _objects(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_objects(v) for v in value]
    return value


# ── reasoning_kwargs ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("module", "level", "expected"),
    [
        (openrouter, "", None),
        (openrouter, "low", {"extra_body": {"reasoning": {"effort": "low"}}}),
        (openrouter, "none", {"extra_body": {"reasoning": {"effort": "none"}}}),
        (openai_compatible, "", None),
        (openai_compatible, "low", {"reasoning_effort": "low"}),
        (openai_compatible, "none", {"reasoning_effort": "none"}),
        (ollama, "", None),
        (ollama, "low", {"think": "low"}),
        (ollama, "medium", {"think": "medium"}),
        (ollama, "high", {"think": "high"}),
        (ollama, "none", {"think": False}),
        (ollama, "max", {"think": True}),
        (llamacpp, "", None),
        (llamacpp, "low", None),
        (llamacpp, "none", None),
        (anthropic, "", None),
        (anthropic, "low", None),
        (anthropic, "none", None),
    ],
)
def test_reasoning_kwargs(module: types.ModuleType, level: str, expected: Any) -> None:
    assert module.reasoning_kwargs(level) == expected


@pytest.mark.parametrize(
    ("name", "ignores"),
    [
        ("openrouter", False),
        ("openai_compatible", False),
        ("ollama", False),
        ("llamacpp", True),
        ("anthropic", True),
    ],
)
def test_the_registry_knows_who_ignores_the_level(name: str, ignores: bool) -> None:
    assert registry.ignores_reasoning(name) is ignores


# ── read_reply ────────────────────────────────────────────────────────────

_OPENROUTER_FACTS = ReplyFacts(
    reasoning="The user asks about colour.",
    input_tokens=25,
    output_tokens=11,
    reasoning_tokens=2,
    cost_usd=0.00000925,
)


@pytest.mark.parametrize("shape", [lambda r: r, _objects], ids=["dict", "object"])
@pytest.mark.parametrize("name", ["openrouter", "openai_compatible", "llamacpp"])
def test_the_openai_shaped_reply_is_read(name: str, shape: Any) -> None:
    assert registry.reply_reader(name)(shape(OPENROUTER_REPLY)) == _OPENROUTER_FACTS


def test_the_pydantic_chat_completion_is_read() -> None:
    """``CompletionResponse.raw`` from ``OpenAILike`` is the openai ``ChatCompletion`` object."""
    from openai.types.chat import ChatCompletion

    raw = ChatCompletion.model_validate(OPENROUTER_REPLY)
    assert openrouter.read_reply(raw) == _OPENROUTER_FACTS


def test_reasoning_content_is_read_when_reasoning_is_absent() -> None:
    reply = json.loads(json.dumps(OPENROUTER_REPLY))
    message = reply["choices"][0]["message"]
    message["reasoning_content"] = message.pop("reasoning")
    assert llamacpp.read_reply(reply).reasoning == "The user asks about colour."


def test_an_openai_reply_without_reasoning_or_cost_reports_none() -> None:
    reply = {
        "choices": [{"message": {"role": "assistant", "content": "x"}}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 3},
    }
    assert openai_compatible.read_reply(reply) == ReplyFacts(input_tokens=5, output_tokens=3)


@pytest.mark.parametrize("shape", [lambda r: r, _objects], ids=["dict", "object"])
def test_the_ollama_reply_is_read(shape: Any) -> None:
    assert registry.reply_reader("ollama")(shape(OLLAMA_REPLY)) == ReplyFacts(
        reasoning="The user greets me.", input_tokens=11, output_tokens=106
    )


@pytest.mark.parametrize("shape", [lambda r: r, _objects], ids=["dict", "object"])
def test_the_anthropic_reply_is_read(shape: Any) -> None:
    assert registry.reply_reader("anthropic")(shape(ANTHROPIC_REPLY)) == ReplyFacts(
        reasoning="First step.\n\nSecond step.", input_tokens=40, output_tokens=30
    )


_ODD_REPLIES = [
    None,
    "text",
    42,
    [],
    {},
    {"choices": []},
    {"choices": "x"},
    {"choices": [{"message": None}], "usage": "x"},
    {"usage": {"prompt_tokens": "25", "completion_tokens": True, "cost": "cheap"}},
    {"message": 5, "prompt_eval_count": -1},
    {"content": [None, 3, {"type": "thinking"}], "usage": []},
    {"choices": [{"message": {"reasoning": ""}}]},
]


@pytest.mark.parametrize(
    "name", ["openrouter", "openai_compatible", "llamacpp", "ollama", "anthropic"]
)
@pytest.mark.parametrize("raw", _ODD_REPLIES)
def test_a_reader_never_raises_and_invents_nothing(name: str, raw: Any) -> None:
    assert registry.reply_reader(name)(raw) == NO_FACTS


def test_a_reader_survives_an_object_whose_attributes_raise() -> None:
    class Hostile:
        def __getattr__(self, name: str) -> Any:
            raise RuntimeError("boom")

    for name in ("openrouter", "ollama", "anthropic"):
        assert registry.reply_reader(name)(Hostile()) == NO_FACTS


# ── build(): the level reaches the request ────────────────────────────────


def _openrouter(reasoning: str | None) -> Any:
    settings = make_settings(openrouter_api_key=OR_KEY)
    kwargs = {} if reasoning is None else {"reasoning": reasoning}
    return openrouter.build(settings, answer_model="z-ai/glm-5.3-flash", **kwargs)


def _sent_body(llm: Any) -> dict[str, Any]:
    """Run one completion against a stub transport and return the JSON body sent."""
    sent: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        return httpx.Response(200, json=OPENROUTER_REPLY)

    llm._http_client = httpx.Client(transport=httpx.MockTransport(handler))
    completion = llm.complete("Why is the sky blue?")
    assert completion.text == "The sky is blue [1]."
    assert openrouter.read_reply(completion.raw) == _OPENROUTER_FACTS
    return sent[0]


def test_an_empty_level_sends_no_reasoning_field_to_openrouter() -> None:
    assert _openrouter("").additional_kwargs == _openrouter(None).additional_kwargs == {}
    assert "reasoning" not in _sent_body(_openrouter(""))


def test_a_level_reaches_the_openrouter_request_body() -> None:
    body = _sent_body(_openrouter("low"))
    assert body["reasoning"] == {"effort": "low"}
    assert "extra_body" not in body


def test_openai_compatible_sends_reasoning_effort() -> None:
    settings = make_settings(openai_compatible_base_url="http://localhost:1234/v1")
    plain = openai_compatible.build(settings, answer_model="m", reasoning="")
    assert plain.additional_kwargs == {}
    llm = openai_compatible.build(settings, answer_model="m", reasoning="high")
    assert llm.additional_kwargs == {"reasoning_effort": "high"}
    assert _sent_body(llm)["reasoning_effort"] == "high"


def test_llamacpp_sends_nothing_for_a_level() -> None:
    settings = make_settings()
    llm = llamacpp.build(settings, answer_model="m", reasoning="low")
    assert llm.additional_kwargs == {}
    sent = llm._get_model_kwargs()
    assert not {"reasoning", "reasoning_effort", "extra_body"} & set(sent)


@pytest.mark.parametrize(
    ("level", "think"), [("", None), ("low", "low"), ("none", False), ("max", True)]
)
def test_ollama_sends_think(level: str, think: Any) -> None:
    llm = ollama.build(make_settings(), answer_model="qwen3:4b", reasoning=level)
    assert llm.thinking == think
    assert llm.additional_kwargs == {}  # Ollama puts additional_kwargs in options, not the body


def test_anthropic_sends_nothing_for_a_level(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    class StubAnthropic:
        def __init__(self, **kwargs: Any) -> None:
            seen.update(kwargs)

    stub = types.ModuleType("llama_index.llms.anthropic")
    stub.Anthropic = StubAnthropic  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "llama_index.llms.anthropic", stub)
    settings = make_settings(anthropic_api_key="sk-ant-api03-AAAA1111BBBB2222CCCC3333")
    anthropic.build(settings, timeout=9.0, answer_model="claude-x", reasoning="low")
    assert set(seen) == {"model", "api_key", "timeout"}


# ── composition root: one level per role ──────────────────────────────────


class _Recorder:
    """A provider ``build()`` that records the keyword arguments it got."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, settings: Any, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return object()


@pytest.fixture
def recorder(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setitem(registry._cache, "openrouter", rec)
    return rec


def _answer_settings(**answer: Any) -> Any:
    from omrs.config import Settings

    block = {"provider": "openrouter", "model": "a", "verify_provider": "openrouter"}
    return Settings(_env_file=None, answer={**block, **answer})


def test_the_answer_model_gets_the_answer_level(recorder: _Recorder) -> None:
    from omrs.compose_answer import build_answer_llm

    build_answer_llm(_answer_settings(reasoning="high", verify_reasoning=""))
    assert recorder.calls[-1]["reasoning"] == "high"


def test_an_empty_answer_level_passes_nothing(recorder: _Recorder) -> None:
    from omrs.compose_answer import build_answer_llm

    build_answer_llm(_answer_settings(reasoning=""))
    assert "reasoning" not in recorder.calls[-1]


def test_the_judge_gets_its_own_level(recorder: _Recorder) -> None:
    from omrs.compose import settings_to_effective
    from omrs.compose_answer import build_verify_llm

    settings = _answer_settings(reasoning="high", verify_reasoning="", verify_claims=True)
    build_verify_llm(settings, answer_block=settings_to_effective(settings).answer)
    assert "reasoning" not in recorder.calls[-1]
    settings = _answer_settings(reasoning="high", verify_reasoning="low", verify_claims=True)
    build_verify_llm(settings, answer_block=settings_to_effective(settings).answer)
    assert recorder.calls[-1]["reasoning"] == "low"
