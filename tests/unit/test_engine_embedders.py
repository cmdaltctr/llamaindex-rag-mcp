"""The Engine's embedder set, keyed by (provider, model) (ADR-081, D5)."""

from __future__ import annotations

import threading
import time

import pytest

from omrs.core.vectordb.identity import EmbeddingIdentity
from omrs.engine_embedders import EngineEmbedders

HOST = EmbeddingIdentity(provider="ollama", model="host-model")
OTHER = EmbeddingIdentity(provider="llamacpp", model="other-model")


class _Counter:
    """Factory that records every build."""

    def __init__(self, delay: float = 0.0) -> None:
        self.built: list[tuple[str, str]] = []
        self._delay = delay

    def __call__(self, provider: str, model: str) -> object:
        time.sleep(self._delay)
        self.built.append((provider, model))
        return object()


def test_host_identity_and_none_return_the_host_embedder() -> None:
    host = object()
    factory = _Counter()
    embedders = EngineEmbedders(host, HOST, factory)

    assert embedders.get(None) is host
    assert embedders.get(HOST) is host
    assert factory.built == []


def test_one_pair_builds_once_and_returns_the_same_instance() -> None:
    factory = _Counter()
    embedders = EngineEmbedders(object(), HOST, factory)

    first = embedders.get(OTHER)
    second = embedders.get(EmbeddingIdentity(provider="llamacpp", model="other-model"))

    assert first is second
    assert factory.built == [("llamacpp", "other-model")]


def test_concurrent_gets_build_once() -> None:
    factory = _Counter(delay=0.05)
    embedders = EngineEmbedders(object(), HOST, factory)
    results: list[object] = []

    def worker() -> None:
        results.append(embedders.get(OTHER))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(factory.built) == 1
    assert len({id(r) for r in results}) == 1


def test_release_clears_the_set() -> None:
    factory = _Counter()
    embedders = EngineEmbedders(object(), HOST, factory)
    first = embedders.get(OTHER)

    embedders.release()

    assert embedders.get(None) is None
    with pytest.raises(RuntimeError, match="released"):
        embedders.get(OTHER)
    assert first is not None


def test_a_new_pair_without_a_factory_is_refused() -> None:
    embedders = EngineEmbedders(object(), HOST, None)

    with pytest.raises(ValueError, match="other-model"):
        embedders.get(OTHER)
