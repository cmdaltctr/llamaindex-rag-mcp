"""Read-only Engine accessors used by the web transport (task 6.4 follow-up)."""

from __future__ import annotations

import pytest
from tests.unit.test_engine_pipelines_support import FakeStore, build_engine, chunks


class _Resolver:
    """Stand-in profile resolver identified by object identity."""


def test_store_property_returns_the_owned_store(effective_settings) -> None:
    """``Engine.store`` is the injected store and cannot be reassigned."""
    store = FakeStore(chunks())
    engine = build_engine(effective_settings(), store=store)
    assert engine.store is store
    with pytest.raises(AttributeError):
        engine.store = FakeStore(chunks())  # type: ignore[misc]


def test_store_property_rejects_a_closed_engine(effective_settings) -> None:
    """A closed Engine exposes no store."""
    engine = build_engine(effective_settings())
    engine.close()
    with pytest.raises(RuntimeError):
        _ = engine.store


def test_profile_resolver_is_built_lazily_once(effective_settings) -> None:
    """The resolver comes from its factory on first access, then is cached."""
    calls: list[int] = []

    def factory() -> _Resolver:
        calls.append(1)
        return _Resolver()

    engine = build_engine(effective_settings(), profile_resolver_factory=factory)
    assert calls == []
    first = engine.profile_resolver
    assert isinstance(first, _Resolver)
    assert engine.profile_resolver is first
    assert calls == [1]


def test_profile_resolver_is_none_without_one(effective_settings) -> None:
    """An Engine built with explicit settings and no resolver reports ``None``."""
    assert build_engine(effective_settings()).profile_resolver is None
