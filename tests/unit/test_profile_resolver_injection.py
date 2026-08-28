"""Tests for ProfileResolver dependency injection and overlay semantics.

Guards two failure modes found in review of groups 1-4:

* **H-7** — ``_bundle_to_effective`` constructed a *fresh* ``EffectiveSettings``
  from class defaults instead of overlaying the profile levers onto the
  server-default base, silently discarding the operator's configuration for
  every field the profile does not own.
* **H-8** — ``server_profile`` was never injected by any production call site,
  so the settings-singleton fallback was the only live path.

Also covers the ``effective_settings`` conftest factory, which previously
discarded flat overrides — including the example in its own docstring.
"""

from __future__ import annotations

import pytest

from rag_mcp.core.profiles.resolver import ProfileResolver, _bundle_to_effective
from rag_mcp.core.settings import EffectiveSettings, RetrievalBlock


# ── H-7: overlay must inherit non-lever fields ──────────────────────────


def test_bundle_overlay_inherits_non_lever_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Profile levers overlay onto the base; everything else is inherited."""
    # Tier 2 env vars legitimately win over the bundle; clear them so this
    # test exercises the bundle→base overlay rather than env precedence.
    for var in ("RETRIEVAL__TOP_K", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__HYBRID_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    base = EffectiveSettings(
        chroma_persist_dir="/operator/path",
        embed_model="operator-model",
        collection_name="operator_collection",
        retrieval=RetrievalBlock(similarity_threshold=0.42),
    )

    effective = _bundle_to_effective(
        "codebase",
        {"retrieval": {"top_k": 20, "rerank_enabled": False, "hybrid_enabled": True}},
        base,
    )

    # Profile-owned levers are applied.
    assert effective.profile_name == "codebase"
    assert effective.retrieval.top_k == 20
    assert effective.retrieval.rerank_enabled is False
    assert effective.retrieval.hybrid_enabled is True

    # Everything the profile does NOT own is inherited from the base.
    assert effective.chroma_persist_dir == "/operator/path"
    assert effective.embed_model == "operator-model"
    assert effective.collection_name == "operator_collection"
    # Including a sibling field inside an overlaid block.
    assert effective.retrieval.similarity_threshold == 0.42


def test_bundle_overlay_does_not_mutate_base(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Resolving a profile must leave the shared base instance untouched."""
    monkeypatch.delenv("RETRIEVAL__TOP_K", raising=False)
    base = EffectiveSettings(retrieval=RetrievalBlock(top_k=10))
    _bundle_to_effective("codebase", {"retrieval": {"top_k": 20}}, base)
    assert base.retrieval.top_k == 10


def test_two_profiles_from_one_base_are_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two collections on different profiles must not observe each other."""
    for var in ("RETRIEVAL__TOP_K", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__HYBRID_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    base = EffectiveSettings(chroma_persist_dir="/shared")

    docs = _bundle_to_effective(
        "documents", {"retrieval": {"top_k": 10, "rerank_enabled": True}}, base
    )
    code = _bundle_to_effective(
        "codebase", {"retrieval": {"top_k": 20, "rerank_enabled": False}}, base
    )

    assert docs.retrieval.top_k == 10
    assert docs.retrieval.rerank_enabled is True
    assert code.retrieval.top_k == 20
    assert code.retrieval.rerank_enabled is False
    # Both still carry the operator's cross-cutting configuration.
    assert docs.chroma_persist_dir == "/shared"
    assert code.chroma_persist_dir == "/shared"


# ── H-8: injection must be wired, not fall back to the singleton ────────


def test_resolver_uses_injected_server_profile_without_touching_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An injected server_profile must be used without reading config.settings."""
    import rag_mcp.config as config_module

    def _boom(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError(
            "ProfileResolver read the settings singleton despite injection"
        )

    monkeypatch.setattr(config_module, "settings", property(_boom), raising=False)

    resolver = ProfileResolver(server_profile="codebase")
    assert resolver._get_server_profile() == "codebase"


def test_resolver_passes_base_through_to_resolved_settings() -> None:
    """The injected base reaches the EffectiveSettings the resolver returns."""
    base = EffectiveSettings(chroma_persist_dir="/injected")
    resolver = ProfileResolver(server_profile="documents", base=base)

    effective = resolver._load_effective("documents")
    assert effective.chroma_persist_dir == "/injected"


def test_build_profile_resolver_injects_both_dependencies() -> None:
    """compose.build_profile_resolver must supply server_profile AND base."""
    from rag_mcp import compose

    resolver = compose.build_profile_resolver()
    assert resolver._server_profile is not None, "server_profile was not injected"
    assert resolver._base is not None, "base EffectiveSettings was not injected"


# ── H-6: the conftest factory must not swallow overrides ────────────────


def test_effective_settings_fixture_routes_flat_override(effective_settings) -> None:
    """The documented flat form must actually apply (it silently did not)."""
    settings = effective_settings(top_k=20)
    assert settings.retrieval.top_k == 20


def test_effective_settings_fixture_routes_dotted_override(effective_settings) -> None:
    """The dotted form must apply."""
    settings = effective_settings(**{"retrieval.top_k": 30})
    assert settings.retrieval.top_k == 30


def test_effective_settings_fixture_accepts_root_field(effective_settings) -> None:
    """Root-level EffectiveSettings fields still work."""
    settings = effective_settings(chroma_persist_dir="/x")
    assert settings.chroma_persist_dir == "/x"


def test_effective_settings_fixture_rejects_unknown_override(
    effective_settings,
) -> None:
    """An unknown key must raise, never be silently discarded."""
    with pytest.raises(TypeError, match="unknown override"):
        effective_settings(definitely_not_a_field=1)


def test_effective_settings_fixture_rejects_unknown_block(effective_settings) -> None:
    """An unknown dotted block must raise."""
    with pytest.raises(TypeError, match="unknown block"):
        effective_settings(**{"nosuchblock.field": 1})
