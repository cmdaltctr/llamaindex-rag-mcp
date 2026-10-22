"""The profile resolver reports the embedding model a collection's profile names (ADR-081)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from omrs.core.profiles.resolver import ProfileResolver
from omrs.core.vectordb.identity import EmbeddingIdentity


class _Store:
    def __init__(self, metadata: dict[str, dict[str, Any]]) -> None:
        self._metadata = metadata

    def get_collection_metadata(self, name: str) -> dict[str, Any] | None:
        return self._metadata.get(name)


class _Catalogue:
    def __init__(self, records: dict[str, dict[str, Any]]) -> None:
        self._records = records

    def get_profile(self, profile_id: str) -> Mapping[str, Any] | None:
        return self._records.get(profile_id)

    def list_profiles(self) -> Sequence[Mapping[str, Any]]:
        return list(self._records.values())

    def slot_revision(self, profile_id: str, slot: str) -> None:
        return None

    def slot_document(self, profile_id: str, slot: str) -> None:
        return None


def _record(profile_id: str, **embed: Any) -> dict[str, Any]:
    return {"profile_id": profile_id, "base_profile": "documents", "archived_at": None, **embed}


def _resolver(effective_settings, tags: dict[str, str | None]) -> ProfileResolver:
    metadata = {name: ({"profile": tag} if tag else {}) for name, tag in tags.items()}
    catalogue = _Catalogue(
        {
            "papers-b": _record("papers-b", embed_provider="llamacpp", embed_model="model-b"),
            "plain": _record("plain", embed_provider=None, embed_model=None),
        }
    )
    return ProfileResolver(
        store=_Store(metadata),  # type: ignore[arg-type]
        server_profile="documents",
        base=effective_settings(),
        env_overrides={},
        catalogue=catalogue,
    )


def test_user_profile_with_a_model_returns_its_identity(effective_settings) -> None:
    resolver = _resolver(effective_settings, {"c": "papers-b"})

    assert resolver.embedding_choice("c") == EmbeddingIdentity(provider="llamacpp", model="model-b")


def test_binding_carries_the_same_choice(effective_settings) -> None:
    resolver = _resolver(effective_settings, {"c": "papers-b"})

    assert resolver.binding("c").embedding == resolver.embedding_choice("c")


def test_empty_choice_returns_none(effective_settings) -> None:
    assert _resolver(effective_settings, {"c": "plain"}).embedding_choice("c") is None


def test_built_in_profile_returns_none(effective_settings) -> None:
    assert _resolver(effective_settings, {"c": "codebase"}).embedding_choice("c") is None


def test_missing_tag_returns_none(effective_settings) -> None:
    assert _resolver(effective_settings, {"c": None}).embedding_choice("c") is None
