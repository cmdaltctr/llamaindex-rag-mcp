"""Per-collection profile isolation and end-to-end lever observability.

Tasks 11.4-11.6. These cover the spec scenarios that the DI refactor exists
to make true: two operations in one process each honour their own settings,
and a profile's levers are observable end-to-end without any global mutation.

Before the refactor these properties could not be tested at all — behaviour
was driven by a process-wide singleton, so "two different configurations at
once" was not expressible.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from omrg.core.profiles.resolver import ProfileResolver
from omrg.core.settings import EffectiveSettings, RetrievalBlock


@pytest.fixture(autouse=True)
def _clean_tier2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Env overrides win over bundles by design; clear them here."""
    for var in (
        "RETRIEVAL__TOP_K",
        "RETRIEVAL__RERANK_ENABLED",
        "RETRIEVAL__HYBRID_ENABLED",
        "CHUNKING__STRATEGY_FALLBACK",
        "METADATA__TAXONOMY_MODE",
    ):
        monkeypatch.delenv(var, raising=False)


def _store_with(tags: dict[str, str]) -> MagicMock:
    """A fake VectorStore whose collections carry the given profile tags."""
    store = MagicMock()
    store.get_collection_metadata.side_effect = lambda name: (
        {"profile": tags[name]} if name in tags else None
    )
    store.count.return_value = 1
    return store


# ── 11.4 Nested profile bundles resolve to their documented levers ──────


class TestNestedBundles:
    """Each shipped profile resolves to the lever set its YAML documents."""

    def test_documents_profile_levers(self) -> None:
        resolver = ProfileResolver(server_profile="documents", base=EffectiveSettings())
        effective = resolver._load_effective("documents")
        assert effective.retrieval.top_k == 10
        assert effective.retrieval.rerank_enabled is True
        assert effective.retrieval.hybrid_enabled is False
        assert effective.chunking.strategy_fallback == "markdown"
        assert effective.metadata.taxonomy_mode == "category"

    def test_codebase_profile_levers(self) -> None:
        resolver = ProfileResolver(server_profile="codebase", base=EffectiveSettings())
        effective = resolver._load_effective("codebase")
        assert effective.retrieval.top_k == 20
        assert effective.retrieval.rerank_enabled is False
        assert effective.retrieval.hybrid_enabled is True
        assert effective.chunking.strategy_fallback == "code"
        assert effective.metadata.taxonomy_mode == "file_type"


# ── 11.5 Two operations, two settings, one process ──────────────────────


class TestPerCollectionIsolation:
    """Concurrent operations must not observe each other's configuration."""

    def test_two_collections_resolve_independently(self) -> None:
        """Collections on different profiles get different levers."""
        store = _store_with({"docs": "documents", "code": "codebase"})
        resolver = ProfileResolver(store=store, server_profile="hybrid", base=EffectiveSettings())

        docs = resolver.resolve("docs")
        code = resolver.resolve("code")

        assert docs.retrieval.top_k == 10
        assert code.retrieval.top_k == 20
        assert docs.retrieval.hybrid_enabled is False
        assert code.retrieval.hybrid_enabled is True
        # Resolving the second must not have mutated the first.
        assert docs.retrieval.top_k == 10

    def test_resolution_does_not_mutate_the_shared_base(self) -> None:
        """The injected base is shared; resolving must leave it untouched."""
        base = EffectiveSettings(retrieval=RetrievalBlock(top_k=7))
        store = _store_with({"docs": "documents", "code": "codebase"})
        resolver = ProfileResolver(store=store, server_profile="hybrid", base=base)

        resolver.resolve("docs")
        resolver.resolve("code")

        assert base.retrieval.top_k == 7

    def test_settings_are_frozen_so_operations_cannot_leak(self) -> None:
        """An operation cannot mutate the settings it was handed."""
        resolver = ProfileResolver(server_profile="documents", base=EffectiveSettings())
        effective = resolver._load_effective("documents")
        with pytest.raises(Exception):
            effective.retrieval.top_k = 999  # type: ignore[misc]


# ── 11.6 Profile difference is observable without global mutation ───────


class TestNoGlobalMutation:
    """The documents/codebase difference must not touch process-wide state."""

    def test_profile_difference_leaves_the_default_untouched(self) -> None:
        """Resolving profiles must not rewrite the composition-root default."""
        from omrg.core.settings import get_default_effective_settings

        before = get_default_effective_settings()
        store = _store_with({"docs": "documents", "code": "codebase"})
        resolver = ProfileResolver(store=store, server_profile="hybrid", base=EffectiveSettings())

        docs = resolver.resolve("docs")
        code = resolver.resolve("code")
        after = get_default_effective_settings()

        assert docs.retrieval.top_k != code.retrieval.top_k, (
            "the two profiles must actually differ, or this proves nothing"
        )
        assert after is before
        assert after.retrieval.top_k == before.retrieval.top_k

    def test_untagged_collection_inherits_the_server_profile(self) -> None:
        """No tag means inherit, not fall back to class defaults."""
        store = _store_with({})
        resolver = ProfileResolver(store=store, server_profile="codebase", base=EffectiveSettings())
        effective = resolver.resolve("untagged")
        assert effective.retrieval.top_k == 20
