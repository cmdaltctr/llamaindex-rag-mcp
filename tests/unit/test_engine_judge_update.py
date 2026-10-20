"""A judge save reaches the next answer, not the one running (add-judge-model-setting 1.7).

``Engine.use_provider_settings`` starts a new generation. The next answer
builds its claim check judge from the new ``answer.verify_model``. An answer
that started earlier keeps the judge it already holds (design D2).
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from omrg.core.settings import AnswerBlock
from omrg.engine import Engine


class NamedJudge:
    """A judge that records each prompt under the model name it was built with."""

    def __init__(self, model: str, calls: list[str]) -> None:
        self.model = model
        self.calls = calls

    async def acomplete(self, prompt: str) -> Any:
        self.calls.append(self.model)
        return MagicMock(text="SUPPORTED")


def _judge_on(effective_settings: Any, model: str) -> Any:
    return effective_settings(answer=AnswerBlock(verify_claims=True, verify_model=model))


def test_next_answer_uses_the_saved_judge_and_a_running_one_keeps_its_own(
    effective_settings: Any,
) -> None:
    calls: list[str] = []
    built: list[str] = []

    def judge_factory(block: Any) -> NamedJudge:
        built.append(block.verify_model)
        return NamedJudge(block.verify_model, calls)

    store = MagicMock()
    store.cache_identity = "test-identity"
    engine = Engine(
        _judge_on(effective_settings, "old-judge"),
        store=store,
        embed_model=MagicMock(model_name="test-model"),
        verify_llm_factory=judge_factory,
    )
    first_started, first_release = asyncio.Event(), asyncio.Event()

    async def fake_answer(query: str, **kwargs: Any) -> dict[str, Any]:
        if query == "first":
            first_started.set()
            await first_release.wait()
        await kwargs["verify_complete"]("prompt")
        return {"status": "ok", "answer": query}

    async def run() -> None:
        running = asyncio.create_task(engine.answer("first", collection_name="docs"))
        await asyncio.wait_for(first_started.wait(), timeout=10)
        engine.use_provider_settings(_judge_on(effective_settings, "new-judge"))
        await engine.answer("second", collection_name="docs")
        first_release.set()
        await running

    with patch("omrg.core.answer.pipeline.answer", side_effect=fake_answer):
        asyncio.run(run())
    engine.close()

    assert built == ["old-judge", "new-judge"]
    assert calls == ["new-judge", "old-judge"]  # the running answer kept the old judge
