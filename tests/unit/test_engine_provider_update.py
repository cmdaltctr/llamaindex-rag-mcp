"""``Engine.use_provider_settings``: new LLM provider values in a running Engine (task 5.1).

The Engine swaps a whole "generation" (server-default settings, answer
model slot, judge cache, profile resolver). A call that already started
keeps the generation it captured. Embedding settings never change.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from tests.unit.test_engine_pipelines_support import (
    Factory,
    FakeLLM,
    FakeResolver,
    answer_graph,
    build_engine,
)

from omrg.core.pipelines import RunStatus
from omrg.core.settings import AnswerBlock


class SlowLLM(FakeLLM):
    """Answer model that waits for the test before it replies."""

    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def acomplete(self, prompt: str) -> Any:
        self.started.set()
        await self.release.wait()
        return await super().acomplete(prompt)


def _with(effective_settings, **overrides):
    return effective_settings(**overrides)


def test_next_answer_builds_a_new_model_and_never_reuses_the_old(effective_settings) -> None:
    old, new = FakeLLM(), FakeLLM()
    models = iter([old, new])
    engine = build_engine(effective_settings(), answer_llm_factory=lambda: next(models))

    async def run() -> None:
        first = await engine.run_pipeline(answer_graph(), inputs={"query": "text"})
        assert first.status == RunStatus.SUCCEEDED
        engine.use_provider_settings(
            effective_settings(answer=AnswerBlock(provider="openrouter", model="new-name"))
        )
        second = await engine.run_pipeline(answer_graph(), inputs={"query": "text"})
        assert second.status == RunStatus.SUCCEEDED
        third = await engine.run_pipeline(answer_graph(), inputs={"query": "text"})
        assert third.status == RunStatus.SUCCEEDED

    asyncio.run(run())
    assert len(old.prompts) == 1
    assert len(new.prompts) == 2
    assert engine.resolve_settings().answer.model == "new-name"


def test_next_ingest_resolves_settings_with_the_new_key(effective_settings) -> None:
    engine = build_engine(effective_settings(openrouter_api_key="old-key"))
    assert engine.resolve_settings().openrouter_api_key == "old-key"
    engine.use_provider_settings(effective_settings(openrouter_api_key="new-key"))
    assert engine.resolve_settings().openrouter_api_key == "new-key"
    effective, binding = engine._resolve_bound("documents")
    assert effective.openrouter_api_key == "new-key" and binding is None


def test_profile_resolver_is_rebuilt_from_its_factory(effective_settings) -> None:
    resolvers = Factory()
    seen: list[str] = []

    def make() -> Any:
        resolvers.calls += 1
        key = f"key-{resolvers.calls}"
        seen.append(key)
        return FakeResolver({"documents": effective_settings(openrouter_api_key=key)})

    engine = build_engine(effective_settings(), profile_resolver_factory=make)
    assert engine.resolve_settings("documents").openrouter_api_key == "key-1"
    engine.resolve_settings("documents")
    assert resolvers.calls == 1
    engine.use_provider_settings(effective_settings(openrouter_api_key="ignored"))
    assert engine.resolve_settings("documents").openrouter_api_key == "key-2"
    assert seen == ["key-1", "key-2"]


def test_graph_judge_cache_starts_empty_after_the_change(effective_settings) -> None:
    judge = Factory(object())
    engine = build_engine(effective_settings(), verify_llm_factory=judge)
    block = effective_settings().answer
    before = engine._graph_host(None).resources["verify_llm"]
    before(block)
    before(block)
    assert judge.calls == 1
    engine.use_provider_settings(effective_settings(openrouter_api_key="new-key"))
    after = engine._graph_host(None).resources["verify_llm"]
    after(block)
    assert judge.calls == 2
    # The host captured before the change still serves its own cache.
    before(block)
    assert judge.calls == 2


class _Box:
    """Stands for the saved provider values: the source the composition root reads."""

    def __init__(self, value: str) -> None:
        self.value = value

    def snapshot(self) -> str:
        return self.value


class _ModelNamed(FakeLLM):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


class _SlowNamed(SlowLLM):
    def __init__(self, name: str) -> None:
        super().__init__()
        self.name = name


def test_answer_in_flight_keeps_the_old_model_and_the_next_uses_the_new(
    effective_settings,
) -> None:
    box = _Box("old")
    built: dict[str, Any] = {}

    def make(snapshot: str) -> Any:
        built[snapshot] = _SlowNamed(snapshot) if snapshot == "old" else _ModelNamed(snapshot)
        return built[snapshot]

    engine = build_engine(
        effective_settings(), answer_llm_factory=make, snapshot_source=box.snapshot
    )

    async def run() -> tuple[Any, Any]:
        running = asyncio.create_task(engine.run_pipeline(answer_graph(), inputs={"query": "text"}))
        while "old" not in built:
            await asyncio.sleep(0)
        await asyncio.wait_for(built["old"].started.wait(), timeout=10)
        box.value = "new"
        engine.use_provider_settings(effective_settings(openrouter_api_key="new-key"))
        built["old"].release.set()
        finished = await running
        later = await engine.run_pipeline(answer_graph(), inputs={"query": "text"})
        return finished, later

    finished, later = asyncio.run(run())
    assert finished.status == RunStatus.SUCCEEDED and later.status == RunStatus.SUCCEEDED
    assert len(built["old"].prompts) == 1
    assert len(built["new"].prompts) == 1


def test_generation_that_builds_after_the_swap_still_uses_its_own_snapshot(
    effective_settings,
) -> None:
    box = _Box("old")
    engine = build_engine(
        effective_settings(),
        answer_llm_factory=lambda snapshot: _ModelNamed(snapshot),
        snapshot_source=box.snapshot,
    )
    host = engine._graph_host(None)
    box.value = "new"
    engine.use_provider_settings(effective_settings(openrouter_api_key="new-key"))
    # The old generation builds its model only now, after the swap.
    assert host.resources["answer_llm"]().name == "old"
    assert engine._graph_host(None).resources["answer_llm"]().name == "new"


def test_judge_and_resolver_of_an_old_generation_use_its_snapshot(effective_settings) -> None:
    box = _Box("old")
    seen: list[tuple[str, str]] = []

    def judge(block: Any, snapshot: str) -> Any:
        seen.append(("judge", snapshot))
        return object()

    def resolver(snapshot: str) -> Any:
        seen.append(("resolver", snapshot))
        return FakeResolver({"documents": effective_settings()})

    engine = build_engine(
        effective_settings(),
        verify_llm_factory=judge,
        profile_resolver_factory=resolver,
        snapshot_source=box.snapshot,
    )
    old_gen = engine._gen
    host = engine._graph_host(None)
    box.value = "new"
    engine.use_provider_settings(effective_settings(openrouter_api_key="new-key"))
    host.resources["verify_llm"](effective_settings().answer)
    old_gen.get_resolver()
    assert sorted(seen) == [("judge", "old"), ("resolver", "old")]


@pytest.mark.parametrize(
    "change",
    [
        {"embed_model": "other-model"},
        {"embed_provider": "openrouter", "embed_model": "nomic"},
        {"llamacpp_embed_url": "http://elsewhere:8080/v1"},
        {"openrouter_embed_model": "or-embed"},
    ],
)
def test_embedding_change_raises_and_keeps_the_settings(effective_settings, change) -> None:
    engine = build_engine(effective_settings(embed_model="nomic"))
    before = engine.resolve_settings()
    with pytest.raises(ValueError, match="embedding"):
        engine.use_provider_settings(effective_settings(**{"embed_model": "nomic", **change}))
    assert engine.resolve_settings() is before


def test_ollama_address_change_raises_while_embeddings_use_ollama(effective_settings) -> None:
    engine = build_engine(effective_settings(embed_provider="ollama", embed_model="nomic"))
    before = engine.resolve_settings()
    with pytest.raises(ValueError, match="embedding"):
        engine.use_provider_settings(
            effective_settings(
                embed_provider="ollama", embed_model="nomic", ollama_base_url="http://other:11434"
            )
        )
    assert engine.resolve_settings() is before


def test_ollama_address_change_is_accepted_when_embeddings_use_another_provider(
    effective_settings,
) -> None:
    engine = build_engine(effective_settings(embed_provider="openrouter"))
    engine.use_provider_settings(
        effective_settings(embed_provider="openrouter", ollama_base_url="http://other:11434")
    )
    assert engine.resolve_settings().ollama_base_url == "http://other:11434"


def test_any_other_difference_is_refused_and_the_message_holds_no_value(
    effective_settings,
) -> None:
    engine = build_engine(effective_settings())
    with pytest.raises(ValueError, match="collection_name") as caught:
        engine.use_provider_settings(effective_settings(collection_name="secret-collection"))
    assert "secret-collection" not in str(caught.value)


def test_embedder_store_and_reranker_stay_the_same_objects(effective_settings) -> None:
    reranker = object()
    engine = build_engine(effective_settings(), reranker=reranker)
    store, embed_model, embedders = engine._store, engine._embed_model, engine._embedders
    engine.use_provider_settings(effective_settings(openrouter_api_key="new-key"))
    assert engine._store is store
    assert engine._embed_model is embed_model
    assert engine._embedders is embedders
    assert engine._reranker is reranker


def test_redaction_follows_the_new_key(effective_settings) -> None:
    from omrg.core.vectordb.identity import RedactionSecrets

    engine = build_engine(
        effective_settings(openrouter_api_key="old-key-0123456789"),
        redaction=RedactionSecrets(openrouter_api_key="old-key-0123456789"),
    )
    engine.use_provider_settings(effective_settings(openrouter_api_key="new-key-0123456789"))
    assert "new-key-0123456789" not in engine.redact("fail new-key-0123456789")
    # A call in flight with the old key can still fail with it in the text.
    assert "old-key-0123456789" not in engine.redact("fail old-key-0123456789")
    third_key = "third-key-0123456789"  # gitleaks:allow
    engine.use_provider_settings(effective_settings(openrouter_api_key=third_key))
    assert "old-key-0123456789" not in engine.redact("fail old-key-0123456789")
    assert "new-key-0123456789" not in engine.redact("fail new-key-0123456789")
    assert "third-key-0123456789" not in engine.redact("fail third-key-0123456789")


def test_closed_engine_refuses_the_change(effective_settings) -> None:
    engine = build_engine(effective_settings())
    engine.close()
    with pytest.raises(RuntimeError, match="closed"):
        engine.use_provider_settings(effective_settings())


class _ProfileCatalogue:
    def __init__(self, provider: str) -> None:
        self.provider = provider

    def list_profiles(self) -> list[dict[str, Any]]:
        return [{"profile_id": "p", "embed_provider": self.provider, "embed_model": "m"}]


class _ResolverWithCatalogue(FakeResolver):
    def __init__(self, provider: str) -> None:
        super().__init__({})
        self.catalogue = _ProfileCatalogue(provider)


def test_ollama_address_change_raises_when_a_profile_uses_ollama_embeddings(
    effective_settings,
) -> None:
    engine = build_engine(
        effective_settings(embed_provider="openrouter"),
        profile_resolver=_ResolverWithCatalogue("ollama"),
    )
    before = engine._gen.effective
    with pytest.raises(ValueError, match="ollama_base_url"):
        engine.use_provider_settings(
            effective_settings(embed_provider="openrouter", ollama_base_url="http://other:11434")
        )
    assert engine._gen.effective is before


def test_ollama_address_change_is_allowed_when_no_profile_uses_ollama(effective_settings) -> None:
    engine = build_engine(
        effective_settings(embed_provider="openrouter"),
        profile_resolver=_ResolverWithCatalogue("openrouter"),
    )
    engine.use_provider_settings(
        effective_settings(embed_provider="openrouter", ollama_base_url="http://other:11434")
    )
    assert engine._gen.effective.ollama_base_url == "http://other:11434"
