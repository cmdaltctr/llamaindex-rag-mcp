"""Metadata classification uses the supplied store, never a process default.

Regressions for ``repair-modular-core-boundaries`` tasks 3.2 to 3.4
(design D2). Every test captures the real classification prompt through a
fake ``httpx.AsyncClient``, so no model or network call is made. A
poisoned process-default store records any access: a broken
implementation that swallows the poisoned lookup still fails here,
because the assertions check prompt contents and the access log.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest

from omrg.core.settings import EffectiveSettings, MetadataBlock

_PROVIDERS = {
    "ollama": {"local_backend": "ollama"},
    "llamacpp": {"local_backend": "llamacpp"},
    "openrouter": {"metadata_llm_provider": "cloud", "cloud_backend": "openrouter"},
}


class _FakeStore:
    """In-memory store exposing the two ``VectorStore`` reads taxonomy uses."""

    def __init__(self, collections: dict[str, list[dict]], *, broken: set[str] = frozenset()):
        self.collections = collections
        self.broken = broken
        self.calls: list[str] = []

    def list_collections(self) -> list[str]:
        self.calls.append("list_collections")
        return list(self.collections)

    def iter_metadatas(self, name: str, page_size: int | None = None) -> Iterator[dict]:
        self.calls.append(f"iter_metadatas:{name}")
        if name in self.broken:
            raise RuntimeError(f"collection {name} locked")
        # One row per page: later rows are only reachable by paging on.
        yield from self.collections[name]


class _PoisonStore(_FakeStore):
    """Process-default double: records access and offers a poison label."""

    def __init__(self) -> None:
        super().__init__({"poison": [{"category": "poison_label"}]})


class _BrokenStore(_FakeStore):
    """Supplied store whose collection listing fails outright."""

    def __init__(self) -> None:
        super().__init__({})

    def list_collections(self) -> list[str]:
        self.calls.append("list_collections")
        raise RuntimeError("db locked")


def _settings(provider: str = "ollama", mode: str = "local", **metadata: Any) -> EffectiveSettings:
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode=mode, **metadata), **_PROVIDERS[provider]
    )


class _Capture:
    """Fake HTTP client recording each prompt; answers per document marker."""

    def __init__(self, *, fail: bool = False) -> None:
        self.prompts: list[str] = []
        self.fail = fail

    def __call__(self, **_kwargs: Any) -> _Capture:
        return self

    async def __aenter__(self) -> _Capture:
        return self

    async def __aexit__(self, *_exc: Any) -> None:
        return None

    async def post(self, _url: str, **kwargs: Any) -> Any:
        payload = kwargs["json"]
        prompt = payload.get("prompt") or payload["messages"][-1]["content"]
        self.prompts.append(prompt)
        await asyncio.sleep(0)  # yield so concurrent classifications interleave
        if self.fail:
            raise ConnectionError("backend unreachable")
        document = prompt.rsplit("Document:\n", 1)[-1]
        category = document.split()[0].lower() + "_topic"
        return _Response({"category": category, "keywords": ["k"], "summary": "s"})


class _Response:
    def __init__(self, payload: dict) -> None:
        raw = json.dumps(payload)
        self._body = {"response": raw, "choices": [{"message": {"content": raw}}]}

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._body


@pytest.fixture
def capture(monkeypatch: pytest.MonkeyPatch) -> _Capture:
    """Replace ``httpx.AsyncClient`` and every retry sleep with fakes."""
    fake = _Capture()
    monkeypatch.setattr("httpx.AsyncClient", fake)

    async def _no_sleep(_seconds: float) -> None:
        return None

    for target in ("_common", "ollama", "llamacpp"):
        monkeypatch.setattr(f"omrg.core.metadata.{target}._retry_sleep", _no_sleep)
    return fake


@pytest.fixture(params=["absent", "poisoned"])
def default_store(request: pytest.FixtureRequest) -> _PoisonStore | None:
    """Remove the process-default store, or replace it with a poisoned one."""
    from omrg.core.vectordb import get_default_store, reset_default_store, set_default_store

    reset_default_store()
    if request.param == "absent":
        with pytest.raises(RuntimeError):
            get_default_store()
        return None
    poison = _PoisonStore()
    set_default_store(poison)  # type: ignore[arg-type]
    return poison


def _classify(text: str, settings: EffectiveSettings, store: Any = None) -> tuple[dict, bool]:
    from omrg.core.metadata.extractor import extract_metadata_with_status_async

    return asyncio.run(extract_metadata_with_status_async(text, "f.txt", settings, store=store))


def _prompt_categories(prompt: str) -> set[str]:
    section = prompt.split("EXISTING CATEGORIES", 1)[1].split("Document:", 1)[0]
    return {line[2:].strip() for line in section.splitlines() if line.startswith("- ")}


def _assert_untouched(poison: _PoisonStore | None) -> None:
    if poison is not None:
        assert poison.calls == [], "process-default store was consulted"


# ── 3.2 Supplied store reaches every shared prompt provider ──────────────


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
def test_supplied_store_labels_reach_prompt(provider, capture, default_store) -> None:
    """All collections of the supplied store reach each provider's prompt."""
    store = _FakeStore(
        {
            "first": [{"category": "Owned Alpha"}, None, {"category": "ai"}],
            "second": [{"other": 1}, {"category": "owned_beta"}],
        }
    )
    result, degraded = _classify("zenith text", _settings(provider), store)

    assert result == {"category": "zenith_topic", "keywords": ["k"], "summary": "s"}
    assert degraded is False
    cats = _prompt_categories(capture.prompts[0])
    assert {"owned_alpha", "owned_beta", "ai", "biology", "uncategorised"} <= cats
    assert "poison_label" not in cats
    assert store.calls == ["list_collections", "iter_metadatas:first", "iter_metadatas:second"]
    _assert_untouched(default_store)


def test_disjoint_stores_interleaved(capture, default_store) -> None:
    """Concurrent classifications each see only their own store's labels."""
    from omrg.core.metadata.extractor import extract_metadata_with_status_async

    store_a = _FakeStore({"docs": [{"category": "alpha_only"}], "notes": [{"category": "a2"}]})
    store_b = _FakeStore({"docs": [{"category": "beta_only"}]})
    settings_a = _settings(keyword_rules=json.dumps([{"pattern": "x", "category": "seed_a"}]))
    settings_b = _settings(keyword_rules=json.dumps([{"pattern": "y", "category": "seed_b"}]))

    async def _run() -> list:
        return await asyncio.gather(
            extract_metadata_with_status_async("alpha", "a", settings_a, store=store_a),
            extract_metadata_with_status_async("beta", "b", settings_b, store=store_b),
            extract_metadata_with_status_async("beta", "b", settings_b, store=store_b),
            extract_metadata_with_status_async("alpha", "a", settings_a, store=store_a),
        )

    asyncio.run(_run())
    for prompt in capture.prompts:
        cats = _prompt_categories(prompt)
        if prompt.endswith("alpha"):
            assert cats == {"alpha_only", "a2", "seed_a", "uncategorised"}
        else:
            assert cats == {"beta_only", "seed_b", "uncategorised"}
    assert len(capture.prompts) == 4
    _assert_untouched(default_store)


# ── 3.3 Standalone seed-only lookup and supplied-store failures ──────────


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
def test_standalone_without_store_is_seed_only(provider, capture, default_store, caplog) -> None:
    """No store means seeds only: no default lookup, warning or degradation."""
    seeds = json.dumps([{"pattern": "x", "category": "Seed One"}])
    with caplog.at_level(logging.DEBUG, logger="omrg.core.metadata._common"):
        result, degraded = _classify("zenith", _settings(provider, keyword_rules=seeds))

    assert _prompt_categories(capture.prompts[0]) == {"seed one", "uncategorised"}
    assert result["category"] == "zenith_topic"
    assert degraded is False
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]
    _assert_untouched(default_store)


def test_supplied_store_failure_warns_and_uses_seeds(capture, default_store, caplog) -> None:
    """A real failure of the supplied store keeps the warning/seed fallback."""
    store = _BrokenStore()
    with caplog.at_level(logging.WARNING):
        result, degraded = _classify("zenith", _settings(), store)

    assert any("failed to query vector store" in r.message.lower() for r in caplog.records)
    assert _prompt_categories(capture.prompts[0]) >= {"ai", "biology", "uncategorised"}
    assert result == {"category": "zenith_topic", "keywords": ["k"], "summary": "s"}
    assert degraded is False
    assert store.calls == ["list_collections"]
    _assert_untouched(default_store)


def test_collection_failure_keeps_healthy_siblings(capture, default_store) -> None:
    """One unreadable collection is skipped; its siblings still contribute."""
    store = _FakeStore(
        {"bad": [{"category": "never"}], "good": [{"category": "healthy"}]}, broken={"bad"}
    )
    _classify("zenith", _settings(), store)

    cats = _prompt_categories(capture.prompts[0])
    assert "healthy" in cats
    assert "never" not in cats
    _assert_untouched(default_store)


@pytest.mark.parametrize("provider", sorted(_PROVIDERS))
def test_retry_budget_and_degradation_with_store(provider, capture, default_store) -> None:
    """Exhausted retries keep the fallback shape, budget and degraded flag."""
    capture.fail = True
    store = _FakeStore({"docs": [{"category": "owned"}]})
    result, degraded = _classify("zenith", _settings(provider, classify_max_attempts=3), store)

    assert result == {"category": "uncategorised", "keywords": [], "summary": ""}
    assert degraded is True
    assert len(capture.prompts) == 3
    assert all("- owned" in prompt for prompt in capture.prompts)
    assert store.calls.count("list_collections") == 1  # prompt is built once
    _assert_untouched(default_store)


# ── 3.4 LlamaIndex fallback forwarding ───────────────────────────────────


def test_llamaindex_import_fallback_forwards_store(monkeypatch, capture, default_store) -> None:
    """A missing LLM package falls back to local mode with the same store."""

    def _missing(_name: str) -> Any:
        raise ImportError("stub: package not installed")

    monkeypatch.setattr("omrg.core.providers.llm.registry.get", _missing)
    store = _FakeStore({"docs": [{"category": "owned_label"}]})
    result, degraded = _classify("zenith", _settings(mode="llamaindex"), store)

    assert "owned_label" in _prompt_categories(capture.prompts[0])
    assert result["category"] == "zenith_topic"
    assert degraded is True
    _assert_untouched(default_store)


def test_llamaindex_pipeline_fallback_forwards_store(monkeypatch, capture, default_store) -> None:
    """A failing LlamaIndex pipeline falls back to local mode with the same store."""
    monkeypatch.setattr(
        "omrg.core.providers.llm.registry.get", lambda _name: lambda *_a, **_kw: object()
    )
    monkeypatch.setattr("omrg.core.metadata.llamaindex._get_max_chunks", lambda: 0)
    store = _FakeStore({"docs": [{"category": "owned_label"}]})
    result, degraded = _classify("zenith", _settings("llamacpp", mode="llamaindex"), store)

    assert "owned_label" in _prompt_categories(capture.prompts[0])
    assert result["category"] == "zenith_topic"
    assert degraded is True
    _assert_untouched(default_store)


# ── Signature compatibility and modes without category lookup ────────────


def test_registered_strategies_accept_keyword_only_store() -> None:
    """Built-ins keep positional text/file/settings and add keyword-only store."""
    from omrg.core.metadata import registry
    from omrg.core.metadata.extractor import (
        _dispatch_local_extraction,
        extract_metadata_async,
        extract_metadata_with_status_async,
    )

    callables = [registry.get(name) for name in registry.available()]
    callables += [extract_metadata_async, extract_metadata_with_status_async]
    for fn in callables:
        params = inspect.signature(fn).parameters
        positional = [p.name for p in params.values() if p.kind is p.POSITIONAL_OR_KEYWORD]
        assert positional[1:] == ["file_name", "settings"], fn.__qualname__
        assert params["store"].kind is inspect.Parameter.KEYWORD_ONLY, fn.__qualname__
        assert params["store"].default is None, fn.__qualname__
    assert inspect.signature(_dispatch_local_extraction).parameters["store"].default is None


def test_custom_strategy_receives_store_through_dispatch(monkeypatch) -> None:
    """The registry dispatch forwards the store keyword to any strategy."""
    from omrg.core.metadata import registry

    seen: list[Any] = []

    async def _probe(text, file_name="", settings=None, *, store=None) -> dict:
        seen.append(store)
        return {"category": "probe"}

    monkeypatch.setitem(registry._registry, "probe", "unused:unused")
    monkeypatch.setitem(registry._cache, "probe", _probe)
    sentinel = _FakeStore({})
    result, degraded = _classify("text", _settings(mode="probe"), sentinel)

    assert result == {"category": "probe"}
    assert degraded is False
    assert seen == [sentinel]
    assert sentinel.calls == []


@pytest.mark.parametrize("mode", ["keyword", "disabled"])
def test_modes_without_lookup_ignore_store(mode, default_store) -> None:
    """Keyword and disabled modes accept a store but never read it."""
    store = _FakeStore({"docs": [{"category": "owned"}]})
    with_store = _classify("neural network transformer", _settings(mode=mode), store)
    without = _classify("neural network transformer", _settings(mode=mode))

    assert with_store == without
    assert store.calls == []
    _assert_untouched(default_store)


# ── Engine-driven ingestion: two Engines, disjoint stores ────────────────


def _engine(tmp_path, name: str, settings: EffectiveSettings) -> Any:
    from llama_index.core.embeddings import MockEmbedding

    from omrg.core.profiles.resolver import ProfileResolver
    from omrg.core.vectordb.lancedb.store import LanceVectorStore
    from omrg.engine import Engine

    store = LanceVectorStore(uri=str(tmp_path / f"store-{name}"), scan_page_size=1)
    return Engine(
        settings,
        store=store,
        embed_model=MockEmbedding(embed_dim=4),  # 0.5 * sqrt(4): unit norm
        profile_resolver=ProfileResolver(store=store, server_profile="documents", base=settings),
    )


def _write_doc(tmp_path, folder: str, marker: str) -> str:
    docs = tmp_path / folder
    docs.mkdir()
    (docs / "notes.txt").write_text(f"{marker} protocol notes for this corpus.\n", "utf-8")
    return str(docs)


@pytest.mark.parametrize("first", ["a", "b"])
def test_two_engines_interleaved_ingestion_prompts(
    tmp_path, first, capture, default_store, effective_settings
) -> None:
    """Each Engine's prompt holds its own labels from all of its collections.

    Round one classifies ``zenith``/``aurora`` documents into collection
    ``first``; round two ingests into ``second``, so the owning label is
    reachable only by scanning the other collection of the same store.
    """
    settings = effective_settings(
        extraction_mode="local", local_backend="ollama", hybrid_sparse_backend="native"
    )
    engines = {"a": _engine(tmp_path, "a", settings), "b": _engine(tmp_path, "b", settings)}
    markers = {"a": "zenith", "b": "aurora"}
    order = [first, "b" if first == "a" else "a"]

    for round_name in ("first", "second"):
        for key in order:
            path = _write_doc(tmp_path, f"{key}-{round_name}", markers[key])
            asyncio.run(engines[key].ingest(path, collection_name=round_name))

    second_round = capture.prompts[2:]
    assert len(second_round) == 2
    for prompt in second_round:
        own = "zenith" if "Document:\nzenith" in prompt else "aurora"
        other = "aurora" if own == "zenith" else "zenith"
        cats = _prompt_categories(prompt)
        assert f"{own}_topic" in cats, prompt
        assert f"{other}_topic" not in cats, prompt
        assert {"ai", "uncategorised"} <= cats
        assert "poison_label" not in cats
    _assert_untouched(default_store)
    for engine in engines.values():
        engine.close()
