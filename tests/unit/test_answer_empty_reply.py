"""Empty or unreadable model replies are generation failures (TDR-036).

Live bug, 2026-10-18: with Ollama ``qwen3:4b`` the first chat answer
worked, and every later answer came back as the literal text
``"Empty Response"`` with status ``generation_unverified``. Ollama's
llama-server ran out of Metal memory (``num_ctx=262144``), and Ollama
still answered ``HTTP 200`` with an empty message whose ``role`` is
``""``. LlamaIndex's Ollama LLM raised a pydantic ``ValidationError``
on that role, and LlamaIndex's refine synthesiser caught it and put
``"Empty Response"`` in place of the answer.

These tests drive the real ``llama_index.llms.ollama.Ollama`` class over
an ``httpx.MockTransport`` that replays those Ollama payloads. No
Ollama server runs.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from ollama import AsyncClient, Client

from omrg.core.answer.stages import (
    FAILURE_STAGE_GENERATION,
    prepare_evidence,
    synthesise_answer,
)
from omrg.core.settings import AnswerBlock
from omrg.engine_answer import server_seam

_BASE_URL = "http://ollama.test:11434"

_ROW = {
    "chunk_id": "c1",
    "source_id": "doc-1",
    "source_version": "v1",
    "source": "/docs/a.md",
    "source_chunk_index": 0,
    "text": "The tower is 300 metres tall.",
    "score": 0.9,
}

#: ``/api/show`` for qwen3:4b. LlamaIndex reads ``context_length`` from it
#: when no ``context_window`` is set, and then sends it as ``num_ctx``.
_SHOW = {
    "modelfile": "FROM qwen3:4b",
    "parameters": "temperature 0.6\ntop_k 20\ntop_p 0.95",
    "template": "{{ .Prompt }}",
    "details": {
        "format": "gguf",
        "family": "qwen3",
        "families": ["qwen3"],
        "parameter_size": "4.0B",
        "quantization_level": "Q4_K_M",
    },
    "model_info": {"general.architecture": "qwen3", "qwen3.context_length": 262144},
    "capabilities": ["completion", "tools", "thinking"],
}

#: A good non-streamed qwen3 reply: thinking plus cited content.
_GOOD_CHAT = {
    "model": "qwen3:4b",
    "created_at": "2026-10-18T18:02:39.901Z",
    "message": {
        "role": "assistant",
        "content": "The tower is 300 metres tall [1].",
        "thinking": "The evidence in source 1 gives the height.",
    },
    "done": True,
    "done_reason": "stop",
    "total_duration": 10_730_126_709,
    "prompt_eval_count": 562,
    "eval_count": 244,
}

#: What Ollama returned after llama-server logged "Insufficient Memory"
#: and "Compute error": HTTP 200, done, and an empty message with an
#: empty role.
_FAILED_CHAT = {
    "model": "qwen3:4b",
    "created_at": "2026-10-18T18:02:53.000Z",
    "message": {"role": "", "content": ""},
    "done": True,
}


class _FakeOllama:
    """MockTransport handler: replies to ``/api/chat`` in a scripted order."""

    def __init__(self, chat_replies: list[dict[str, Any]]) -> None:
        self._chat_replies = list(chat_replies)
        self.chat_bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/show":
            return httpx.Response(200, json=_SHOW)
        if request.url.path == "/api/chat":
            self.chat_bodies.append(json.loads(request.content))
            return httpx.Response(200, json=self._chat_replies.pop(0))
        return httpx.Response(404, json={"error": "not found"})


def _ollama_llm(handler: _FakeOllama) -> Any:
    """Build the real LlamaIndex Ollama LLM over the mock transport."""
    from llama_index.llms.ollama import Ollama

    transport = httpx.MockTransport(handler)
    return Ollama(
        model="qwen3:4b",
        base_url=_BASE_URL,
        request_timeout=5.0,
        client=Client(host=_BASE_URL, transport=transport),
        async_client=AsyncClient(host=_BASE_URL, transport=transport),
    )


def _redact(exc: BaseException) -> str:
    return str(exc)


async def _synthesise(complete: Any) -> Any:
    return await synthesise_answer(
        "How tall is the tower?",
        prepare_evidence([_ROW]),
        complete=complete,
        answer_block=AnswerBlock(),
        error_detail=_redact,
    )


async def test_later_empty_ollama_reply_is_a_generation_failure() -> None:
    """The live sequence: a good answer, then Ollama's empty-role reply."""
    handler = _FakeOllama([_GOOD_CHAT, _FAILED_CHAT])
    seam = server_seam(_ollama_llm(handler))

    first = await _synthesise(seam)
    assert first.error is None
    assert first.text == "The tower is 300 metres tall [1]."

    second = await _synthesise(seam)
    assert second.text is None, f"placeholder leaked as the answer: {second.text!r}"
    assert second.failure_stage == FAILURE_STAGE_GENERATION
    assert second.error is not None
    assert second.error == (
        "Generation failed: the answer model sent a malformed reply. "
        "This often means it ran out of memory. Check the model, then ask again."
    )
    assert "validation error" not in second.error and "ChatMessage" not in second.error
    assert second.completion_calls == 1
    assert len(handler.chat_bodies) == 2


@pytest.mark.parametrize("reply", ["", "   \n"])
async def test_empty_completion_text_is_a_friendly_generation_failure(reply: str) -> None:
    """A seam that returns no text never becomes an "Empty Response" answer."""

    async def complete(prompt: str) -> str:
        return reply

    outcome = await _synthesise(complete)

    assert outcome.text is None
    assert outcome.failure_stage == FAILURE_STAGE_GENERATION
    assert outcome.error == (
        "Generation failed: the answer model returned an empty reply. "
        "Check that the model is running and has enough memory, then ask again."
    )
    assert outcome.completion_calls == 1


@pytest.mark.parametrize("exc", [ValueError("bad reply"), TypeError("bad type")])
async def test_seam_errors_refine_would_swallow_still_fail_generation(
    exc: Exception,
) -> None:
    """LlamaIndex refine catches ValueError and TypeError; the seam must not lose them."""

    async def complete(prompt: str) -> str:
        raise exc

    outcome = await _synthesise(complete)

    assert outcome.text is None
    assert outcome.failure_stage == FAILURE_STAGE_GENERATION
    assert outcome.error == f"Generation failed: {type(exc).__name__}: {exc}"
