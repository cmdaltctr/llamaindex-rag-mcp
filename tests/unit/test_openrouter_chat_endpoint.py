"""The OpenRouter Chat model is called through the chat endpoint (TDR-037).

``OpenAILike`` defaults to ``is_chat_model=False``, which sends every
answer to the legacy ``/completions`` endpoint. A reasoning model then
writes its reasoning into the answer text. The test key is fake.
"""

from __future__ import annotations

from typing import Any

import pytest
from llama_index.core.base.llms.types import ChatMessage, ChatResponse, MessageRole
from llama_index.llms.openai import OpenAI
from tests.unit.test_connection_summary import make_settings

from omrs.core.providers.llm import registry

OR_KEY = "sk-or-v1-FAKE0123456789abcdef"  # gitleaks:allow


def test_openrouter_build_declares_a_chat_model() -> None:
    llm = registry.get("openrouter")(make_settings(openrouter_api_key=OR_KEY), answer_model="m-x")
    assert llm.is_chat_model is True
    assert llm.metadata.is_chat_model is True


@pytest.mark.asyncio
async def test_openrouter_acomplete_uses_the_chat_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    async def fake_achat(self: Any, messages: Any, **kwargs: Any) -> ChatResponse:
        calls.append("chat")
        return ChatResponse(message=ChatMessage(role=MessageRole.ASSISTANT, content="ok"))

    async def fake_acomplete(self: Any, prompt: str, **kwargs: Any) -> Any:
        calls.append("completions")
        raise AssertionError("the legacy /completions endpoint was called")

    monkeypatch.setattr(OpenAI, "_achat", fake_achat)
    monkeypatch.setattr(OpenAI, "_acomplete", fake_acomplete)
    llm = registry.get("openrouter")(make_settings(openrouter_api_key=OR_KEY), answer_model="m-x")

    reply = await llm.acomplete("question")

    assert calls == ["chat"]
    assert reply.text == "ok"
