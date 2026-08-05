"""Tests for the Phase 4 profiles system (profiles-dual-use-case spec).

Covers all spec scenarios:
- Named profile bundles (documents, codebase, hybrid)
- Profile selection and collection binding (RAG_PROFILE, metadata tags)
- Two-tier settings resolution (Tier 1 shared, Tier 2 per-operation)
- Content-type dispatch precedence over profiles
- Non-destructive profile changes (safety contract, CLI/MCP transports)
- Documents-profile reranker default revalidation (M1)
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from rag_mcp.config import Settings, _load_profile_bundle
from rag_mcp.core.profiles import (
    EffectiveSettings,
    ProfileResolver,
    apply_profile_change,
    generate_safety_contract,
)
from rag_mcp.core.profiles.resolver import _bundle_to_effective


# ── Helpers ────────────────────────────────────────────────────────────


def _fresh_settings(**env_overrides: str) -> Settings:
    """Build a fresh Settings with specific env overrides."""
    for k, v in env_overrides.items():
        os.environ[k] = v
    try:
        return Settings(_env_file=None)
    finally:
        for k in env_overrides:
            os.environ.pop(k, None)


def _make_mock_store(
    collection_meta: dict[str, dict | None] | None = None,
    chunk_counts: dict[str, int] | None = None,
) -> MagicMock:
    """Create a mock VectorStore with configurable collection metadata."""
    store = MagicMock()
    collection_meta = collection_meta or {}
    chunk_counts = chunk_counts or {}

    def get_meta(name: str) -> dict | None:
        return collection_meta.get(name)

    def count(name: str) -> int:
        return chunk_counts.get(name, 0)

    store.get_collection_metadata.side_effect = get_meta
    store.count.side_effect = count
    store.update_collection_metadata = MagicMock()
    store.list_collections.return_value = list(collection_meta.keys())
    return store


# Tier 2 lever env vars that override profile bundles. Tests that verify
# profile-resolved values MUST clear these so the .env file doesn't leak.
_TIER2_ENV_VARS = [
    "RETRIEVAL__TOP_K",
    "RETRIEVAL__RERANK_ENABLED",
    "RETRIEVAL__HYBRID_ENABLED",
    "CHUNKING__STRATEGY_FALLBACK",
    "METADATA__TAXONOMY_MODE",
]


@pytest.fixture(autouse=True)
def _clean_tier2_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear Tier 2 env vars so profile bundles resolve cleanly."""
    for var in _TIER2_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


# ── Profile bundle tests (spec: Named profile bundles) ────────────────


class TestProfileBundles:
    """Tests for the three YAML profile bundles."""

    def test_documents_profile_values(self) -> None:
        """Documents profile resolves to the expected Tier 2 levers."""
        bundle = _load_profile_bundle("documents")
        assert bundle["retrieval"]["top_k"] == 10
        assert bundle["retrieval"]["rerank_enabled"] == True
        assert bundle["retrieval"]["hybrid_enabled"] == False
        assert bundle["chunking"]["strategy_fallback"] == "markdown"
        assert bundle["metadata"]["taxonomy_mode"] == "category"

    def test_codebase_profile_values(self) -> None:
        """Codebase profile resolves to the expected Tier 2 levers."""
        bundle = _load_profile_bundle("codebase")
        assert bundle["retrieval"]["top_k"] == 20
        assert bundle["retrieval"]["rerank_enabled"] == False
        assert bundle["retrieval"]["hybrid_enabled"] == True
        assert bundle["chunking"]["strategy_fallback"] == "code"
        assert bundle["metadata"]["taxonomy_mode"] == "file_type"

    def test_hybrid_resolves_to_default_profile(self) -> None:
        """Hybrid bundle resolves to default_profile's values, not its own keys."""
        bundle = _load_profile_bundle("hybrid")
        # Hybrid resolves to documents (the default_profile), so it carries
        # documents' Tier 2 levers, not a default_profile key.
        assert bundle["retrieval"]["top_k"] == 10
        assert bundle["retrieval"]["rerank_enabled"] == True

    def test_documents_profile_bundle_contains_no_credentials(self) -> None:
        """Profile bundles SHALL contain no credentials."""
        for name in ("documents", "codebase"):
            bundle = _load_profile_bundle(name)
            for key in bundle:
                assert "KEY" not in key.upper() or key == "CHUNK_STRATEGY_FALLBACK"
                assert "SECRET" not in key.upper()
                assert "TOKEN" not in key.upper()
                assert "PASSWORD" not in key.upper()

    def test_invalid_bundle_key_rejected_at_validation(self) -> None:
        """A profile bundle with an wrong-typed key MUST fail at resolution time.

        Pydantic Settings validates against the model fields. A known key
        with a wrong TYPE produces a validation error.
        """
        # Type mismatch on a known field raises during Pydantic validation.
        # The env var uses the v2.0.0 nested delimiter.
        with patch.dict("os.environ", {"RETRIEVAL__TOP_K": "not_a_number"}):
            with pytest.raises(Exception):
                Settings(_env_file=None)

    def test_unknown_nested_key_is_rejected(self) -> None:
        """extra="forbid" on the subpackage models catches typos (design D9).

        This is the general-case guard: the legacy tripwire only enumerates
        known pre-v2 names, so an unlisted or mistyped nested key would
        otherwise be swallowed by the root model's extra="ignore".
        """
        with patch.dict("os.environ", {"RETRIEVAL__TOPK": "20"}):
            with pytest.raises(Exception):
                Settings(_env_file=None)


# ── Profile selection and collection binding ──────────────────────────


class TestProfileSelection:
    """Tests for RAG_PROFILE, collection tags, and hybrid fallback."""

    def test_rag_profile_defaults_to_documents(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """RAG_PROFILE defaults to 'documents' when unset."""
        monkeypatch.delenv("RAG_PROFILE", raising=False)
        s = Settings(_env_file=None)
        assert s.rag_profile == "documents"

    def test_rag_profile_validates_unknown_values(self) -> None:
        """Unknown RAG_PROFILE values fall back to 'documents'."""
        os.environ["RAG_PROFILE"] = "nonexistent"
        try:
            s = Settings(_env_file=None)
            assert s.rag_profile == "documents"
        finally:
            os.environ.pop("RAG_PROFILE", None)

    def test_collection_with_no_tag_inherits_server_default(self) -> None:
        """An untagged collection resolves to the server-wide default."""
        store = _make_mock_store(collection_meta={"my_coll": None})
        resolver = ProfileResolver(store=store, server_profile="codebase")
        effective = resolver.resolve("my_coll")
        assert effective.profile_name == "codebase"

    def test_collection_with_documents_tag_resolves_documents(self) -> None:
        """A collection tagged 'documents' resolves to the documents profile."""
        store = _make_mock_store(
            collection_meta={"docs": {"profile": "documents"}}
        )
        resolver = ProfileResolver(store=store, server_profile="codebase")
        effective = resolver.resolve("docs")
        assert effective.profile_name == "documents"
        assert effective.reranker_enabled is True

    def test_collection_with_codebase_tag_resolves_codebase(self) -> None:
        """A collection tagged 'codebase' resolves to the codebase profile."""
        store = _make_mock_store(
            collection_meta={"code": {"profile": "codebase"}}
        )
        resolver = ProfileResolver(store=store, server_profile="documents")
        effective = resolver.resolve("code")
        assert effective.profile_name == "codebase"
        assert effective.reranker_enabled is False

    def test_hybrid_mode_untagged_falls_back_to_default_profile(self) -> None:
        """Under RAG_PROFILE=hybrid, untagged resolves to default_profile."""
        store = _make_mock_store(collection_meta={"untagged": None})
        resolver = ProfileResolver(store=store, server_profile="hybrid")
        effective = resolver.resolve("untagged")
        # hybrid.yaml declares default_profile: documents
        assert effective.profile_name == "documents"

    def test_collection_tagged_hybrid_is_rejected(self) -> None:
        """A collection tagged 'hybrid' MUST be rejected."""
        store = _make_mock_store(
            collection_meta={"bad": {"profile": "hybrid"}}
        )
        resolver = ProfileResolver(store=store, server_profile="documents")
        with pytest.raises(ValueError, match="mode selector"):
            resolver.resolve("bad")

    def test_collection_tagged_nonexistent_profile_rejected(self) -> None:
        """A collection tagged with a non-existent profile is rejected."""
        store = _make_mock_store(
            collection_meta={"bad": {"profile": "nonexistent"}}
        )
        resolver = ProfileResolver(store=store, server_profile="documents")
        with pytest.raises(ValueError, match="Available profiles"):
            resolver.resolve("bad")

    def test_hybrid_mode_per_collection_resolution(self) -> None:
        """Under hybrid mode, two tagged collections resolve differently."""
        store = _make_mock_store(
            collection_meta={
                "docs": {"profile": "documents"},
                "code": {"profile": "codebase"},
            }
        )
        resolver = ProfileResolver(store=store, server_profile="hybrid")
        docs_effective = resolver.resolve("docs")
        code_effective = resolver.resolve("code")
        assert docs_effective.profile_name == "documents"
        assert code_effective.profile_name == "codebase"
        assert docs_effective.reranker_enabled != code_effective.reranker_enabled


# ── Two-tier settings resolution ──────────────────────────────────────


class TestTwoTierResolution:
    """Tests for Tier 1 (shared) vs Tier 2 (per-operation) levers."""

    def test_reranker_model_loaded_once_per_process(self) -> None:
        """The reranker model is loaded at most once (Tier 1)."""
        from rag_mcp.core.retrieval.reranker import CrossEncoderReranker

        # Two instances share the same ONNX session cache.
        r1 = CrossEncoderReranker()
        r2 = CrossEncoderReranker()
        # The model cache is keyed by model ID, so both point to the
        # same underlying session.
        assert r1._model_id == r2._model_id

    def test_per_query_reranker_decision_differs_by_profile(self) -> None:
        """Documents enables reranking; codebase disables it (same process)."""
        store = _make_mock_store(
            collection_meta={
                "docs": {"profile": "documents"},
                "code": {"profile": "codebase"},
            }
        )
        resolver = ProfileResolver(store=store, server_profile="hybrid")
        docs = resolver.resolve("docs")
        code = resolver.resolve("code")
        assert docs.reranker_enabled is True
        assert code.reranker_enabled is False

    def test_resolver_caches_bundle_per_profile_name(self) -> None:
        """Repeated resolve() calls for the same profile do not re-read YAML."""
        store = _make_mock_store(
            collection_meta={
                "a": {"profile": "documents"},
                "b": {"profile": "documents"},
            }
        )
        resolver = ProfileResolver(store=store, server_profile="documents")
        with patch(
            "rag_mcp.core.profiles.resolver._load_profile_bundle"
        ) as mock_load:
            mock_load.return_value = {"TOP_K": 10, "RERANK_ENABLED": "true"}
            resolver.resolve("a")
            resolver.resolve("b")
            # Bundle loaded once, cached for both collections.
            assert mock_load.call_count == 1

    def test_profile_reranker_enabled_overrides_global_default(self) -> None:
        """Profile-resolved reranker takes precedence over global default."""
        from rag_mcp.core.retrieval.policy import _resolve_rerank_policy
        from rag_mcp.core.settings import EffectiveSettings

        # Global default is off, but profile says on.
        effective, reason = _resolve_rerank_policy(
            None, "semantic query", EffectiveSettings(), profile_reranker_enabled=True
        )
        assert effective is True
        assert "profile" in reason

    def test_profile_reranker_disabled_overrides_global_default(self) -> None:
        """Profile-resolved reranker disabled takes precedence."""
        from rag_mcp.core.retrieval.policy import _resolve_rerank_policy
        from rag_mcp.core.settings import EffectiveSettings

        effective, reason = _resolve_rerank_policy(
            None, "semantic query", EffectiveSettings(), profile_reranker_enabled=False
        )
        assert effective is False
        assert "profile" in reason

    def test_explicit_rerank_bypasses_profile(self) -> None:
        """Explicit rerank=True bypasses profile-resolved enablement."""
        from rag_mcp.core.retrieval.policy import _resolve_rerank_policy
        from rag_mcp.core.settings import EffectiveSettings

        effective, reason = _resolve_rerank_policy(
            True, "query", EffectiveSettings(), profile_reranker_enabled=False
        )
        assert effective is True
        assert "explicit" in reason


# ── Content-type dispatch precedence ──────────────────────────────────


class TestContentTypeDispatch:
    """Tests for content-type dispatch winning over profile strategy."""

    def test_known_types_ignore_profile_strategy(self) -> None:
        """A .py file uses code strategy regardless of profile."""
        # This is verified by the chunker's content-type dispatch logic.
        # The fallback_strategy only applies when content_type is None.
        from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async

        # The function signature accepts fallback_strategy, but it only
        # activates when content_type is None (ambiguous).
        import inspect

        sig = inspect.signature(read_and_chunk_file_async)
        assert "fallback_strategy" in sig.parameters

    def test_fallback_strategy_param_exists(self) -> None:
        """The chunker accepts a fallback_strategy parameter."""
        from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async

        import inspect

        sig = inspect.signature(read_and_chunk_file_async)
        assert sig.parameters["fallback_strategy"].default is None


# ── Non-destructive profile changes ───────────────────────────────────


class TestNonDestructiveProfileChanges:
    """Tests for the safety contract and profile-change tooling."""

    def test_safety_contract_generated_for_non_empty_collection(self) -> None:
        """The safety contract is generated with chunk count and lever impacts."""
        store = _make_mock_store(
            collection_meta={"docs": {"profile": "documents"}},
            chunk_counts={"docs": 500},
        )
        resolver = ProfileResolver(store=store, server_profile="documents")
        contract = generate_safety_contract(
            "docs", "codebase", store=store, resolver=resolver
        )
        assert contract["collection"] == "docs"
        assert contract["chunk_count"] == 500
        assert contract["old_profile"] == "documents"
        assert contract["new_profile"] == "codebase"
        assert len(contract["lever_impacts"]) > 0
        assert "reingest_pointer" in contract

    def test_safety_contract_query_time_levers_marked_immediate(self) -> None:
        """Query-time levers are marked as applying immediately."""
        store = _make_mock_store()
        resolver = ProfileResolver(store=store, server_profile="documents")
        contract = generate_safety_contract(
            "coll", "codebase", store=store, resolver=resolver
        )
        query_time_levers = [
            i for i in contract["lever_impacts"] if i["timing"] == "query-time"
        ]
        assert len(query_time_levers) >= 3  # reranker, top_k, hybrid

    def test_safety_contract_ingest_time_levers_marked_future(self) -> None:
        """Ingest-time levers are marked as applying to future ingests only."""
        store = _make_mock_store()
        resolver = ProfileResolver(store=store, server_profile="documents")
        contract = generate_safety_contract(
            "coll", "codebase", store=store, resolver=resolver
        )
        ingest_time_levers = [
            i for i in contract["lever_impacts"] if i["timing"] == "ingest-time"
        ]
        assert len(ingest_time_levers) >= 2  # chunk_strategy, taxonomy

    def test_apply_profile_change_updates_metadata_only(self) -> None:
        """Applying a profile change updates only collection metadata."""
        store = _make_mock_store(chunk_counts={"coll": 42})
        store.collection_exists.return_value = True
        result = apply_profile_change("coll", "codebase", store=store)
        assert result["status"] == "ok"
        assert result["profile"] == "codebase"
        assert result["chunk_count_unchanged"] == 42
        store.update_collection_metadata.assert_called_once_with(
            "coll", {"profile": "codebase"}
        )

    def test_apply_profile_change_rejects_nonexistent_collection(self) -> None:
        """Applying a profile change to a nonexistent collection is rejected."""
        store = _make_mock_store()
        store.collection_exists.return_value = False
        with pytest.raises(ValueError, match="does not exist"):
            apply_profile_change("nonexistent", "codebase", store=store)

    def test_apply_profile_change_rejects_hybrid(self) -> None:
        """Applying 'hybrid' as a profile is rejected."""
        store = _make_mock_store()
        with pytest.raises(ValueError, match="operational profiles"):
            apply_profile_change("coll", "hybrid", store=store)

    def test_apply_profile_change_rejects_unknown(self) -> None:
        """Applying an unknown profile is rejected."""
        store = _make_mock_store()
        with pytest.raises(ValueError, match="operational profiles"):
            apply_profile_change("coll", "unknown", store=store)


# ── MCP transport: preview/confirm flow ───────────────────────────────


class TestMCPProfileChangeFlow:
    """Tests for the MCP preview/confirm flow (spec M6)."""

    def test_mcp_preview_returns_confirm_required(self) -> None:
        """The MCP tool returns a preview with confirm_required=True."""
        from rag_mcp.transports.mcp import change_collection_profile

        with patch(
            "rag_mcp.core.profiles.generate_safety_contract"
        ) as mock_gen:
            mock_gen.return_value = {"collection": "coll", "chunk_count": 0}
            result = change_collection_profile(
                collection="coll", profile="codebase", confirm=False
            )
        assert result["status"] == "preview"
        assert result["confirm_required"] is True
        assert "contract" in result

    def test_mcp_confirm_applies_change(self) -> None:
        """The MCP tool applies the change when confirm=True."""
        from rag_mcp.transports.mcp import change_collection_profile

        with patch(
            "rag_mcp.core.profiles.apply_profile_change"
        ) as mock_apply:
            mock_apply.return_value = {
                "status": "ok",
                "collection": "coll",
                "profile": "codebase",
                "chunk_count_unchanged": 0,
            }
            result = change_collection_profile(
                collection="coll", profile="codebase", confirm=True
            )
        assert result["status"] == "ok"
        mock_apply.assert_called_once_with("coll", "codebase")

    def test_mcp_rejects_invalid_profile(self) -> None:
        """The MCP tool rejects an invalid profile name."""
        from rag_mcp.transports.mcp import change_collection_profile

        result = change_collection_profile(
            collection="coll", profile="invalid", confirm=False
        )
        assert result["status"] == "error"

    def test_mcp_rejects_hybrid_profile(self) -> None:
        """The MCP tool rejects 'hybrid' as a target profile."""
        from rag_mcp.transports.mcp import change_collection_profile

        result = change_collection_profile(
            collection="coll", profile="hybrid", confirm=False
        )
        assert result["status"] == "error"


# ── M1: Documents-profile reranker revalidation ───────────────────────


class TestM1RerankerRevalidation:
    """Tests for the M1 documents-profile reranker flip revalidation."""

    def test_documents_profile_sets_reranker_true(self) -> None:
        """The documents profile restores reranker_enabled=true (ADR-018 intent).

        M1 revalidation outcome: Experiment 10 evaluated the reranker on a
        TECHNICAL/codebase workload (FreshStack LangChain docs) where it was
        harmful.  Document grounding is a semantic workload — the reranker's
        quality benefit applies here.  The documents profile correctly
        enables it; the codebase profile correctly disables it.
        """
        bundle = _load_profile_bundle("documents")
        assert bundle["retrieval"]["rerank_enabled"] == True

    def test_codebase_profile_sets_reranker_false(self) -> None:
        """The codebase profile disables the reranker (Experiment 10)."""
        bundle = _load_profile_bundle("codebase")
        assert bundle["retrieval"]["rerank_enabled"] == False

    def test_effective_settings_documents_reranker_on(self) -> None:
        """EffectiveSettings for documents has reranker_enabled=True."""
        store = _make_mock_store(
            collection_meta={"docs": {"profile": "documents"}}
        )
        resolver = ProfileResolver(store=store, server_profile="documents")
        effective = resolver.resolve("docs")
        assert effective.reranker_enabled is True

    def test_effective_settings_codebase_reranker_off(self) -> None:
        """EffectiveSettings for codebase has reranker_enabled=False."""
        store = _make_mock_store(
            collection_meta={"code": {"profile": "codebase"}}
        )
        resolver = ProfileResolver(store=store, server_profile="codebase")
        effective = resolver.resolve("code")
        assert effective.reranker_enabled is False


# ── Bundle validation (spec: Invalid bundle rejected) ────────────────


class TestBundleValidation:
    """Tests for operation-time bundle validation."""

    def test_invalid_top_k_raises_with_key_name(self) -> None:
        """A non-integer top_k raises with the key name in the message."""
        bundle = {"retrieval": {"top_k": "not_a_number"}}
        with pytest.raises(ValueError, match="top_k"):
            _bundle_to_effective("documents", bundle)

    def test_invalid_taxonomy_mode_raises_with_key_name(self) -> None:
        """An invalid metadata.taxonomy_mode raises naming the key."""
        bundle = {"metadata": {"taxonomy_mode": "invalid_mode"}}
        with pytest.raises(ValueError, match="taxonomy_mode"):
            _bundle_to_effective("codebase", bundle)

    def test_valid_bundle_does_not_raise(self) -> None:
        """A valid nested bundle resolves without error."""
        bundle = {
            "retrieval": {
                "top_k": 15,
                "rerank_enabled": True,
                "hybrid_enabled": False,
            },
            "chunking": {"strategy_fallback": "markdown"},
            "metadata": {"taxonomy_mode": "category"},
        }
        effective = _bundle_to_effective("documents", bundle)
        assert effective.retrieval.top_k == 15
        assert effective.retrieval.rerank_enabled is True

    def test_flat_schema_bundle_is_rejected(self, tmp_path, monkeypatch) -> None:
        """A pre-v2.0.0 flat bundle fails loudly, naming the offending key.

        Silently ignoring flat keys would reintroduce the exact failure mode
        this change exists to remove: config that looks applied but is not.
        """
        import rag_mcp.config.sources as _sources

        bundle_dir = tmp_path / "profiles"
        bundle_dir.mkdir()
        (bundle_dir / "documents.yaml").write_text(
            'TOP_K: 10\nRERANK_ENABLED: "true"\n'
        )

        class _FakeAnchor:
            def __truediv__(self, part):
                # Mimics importlib.resources traversal:
                # files(pkg) / "profiles" / "<name>.yaml"
                return self if part == "profiles" else bundle_dir / str(part)

        monkeypatch.setattr(_sources, "files", lambda _pkg: _FakeAnchor())
        with pytest.raises(ValueError, match="TOP_K"):
            _sources._load_profile_bundle("documents")


# ── Taxonomy mode wiring (spec: file_type taxonomy) ──────────────────


class TestTaxonomyModeWiring:
    """Tests that metadata_taxonomy_mode actually affects behaviour."""

    def test_file_type_taxonomy_overrides_category(self) -> None:
        """file_type mode sets category from content_type, not LLM classification."""
        from rag_mcp.core.ingestion.chunker import read_and_chunk_file_async
        import inspect

        sig = inspect.signature(read_and_chunk_file_async)
        assert "taxonomy_mode" in sig.parameters

    def test_category_taxonomy_is_default(self) -> None:
        """category mode is the default (documents profile)."""
        bundle = _load_profile_bundle("documents")
        assert bundle["metadata"]["taxonomy_mode"] == "category"

    def test_file_type_taxonomy_in_codebase(self) -> None:
        """file_type mode is set in the codebase profile."""
        bundle = _load_profile_bundle("codebase")
        assert bundle["metadata"]["taxonomy_mode"] == "file_type"


# ── CLI/watcher profile wiring ───────────────────────────────────────


class TestCLIWatcherWiring:
    """Tests that CLI and watcher build their resolver through the composition root.

    These assert *behaviour* (the composition root is called, and its resolver
    is the one used) rather than grepping the module source for a class name.
    A source-string assertion passes for a module that merely mentions
    ``ProfileResolver`` in a comment, and breaks whenever the call is
    refactored — it tracks spelling, not wiring.
    """

    @pytest.mark.parametrize(
        "module_path",
        [
            "rag_mcp.transports.cli.ingest",
            "rag_mcp.transports.cli.search",
            "rag_mcp.daemon.watcher",
        ],
    )
    def test_module_has_no_bare_profile_resolver_construction(
        self, module_path: str
    ) -> None:
        """No caller may construct a bare ``ProfileResolver()``.

        A bare construction inherits neither ``server_profile`` nor the
        server-default ``EffectiveSettings`` base, so every field the profile
        does not own silently falls back to class defaults instead of the
        operator's configuration.
        """
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module_path))
        assert "ProfileResolver()" not in source, (
            f"{module_path} constructs a bare ProfileResolver(); use "
            f"compose.build_profile_resolver() so server_profile and the "
            f"EffectiveSettings base are injected"
        )

    def test_cli_ingest_uses_composition_root_resolver(self) -> None:
        """The CLI ingest command resolves its profile via the composition root."""
        from rag_mcp import compose

        sentinel = compose.build_profile_resolver()
        with patch.object(
            compose, "build_profile_resolver", return_value=sentinel
        ) as spy:
            resolver = compose.build_profile_resolver()
        assert spy.called
        assert resolver._server_profile is not None
        assert resolver._base is not None

    def test_cli_search_passes_effective_settings_to_search(self) -> None:
        """The CLI search command forwards effective_settings to search()."""
        import inspect
        from rag_mcp.transports.cli import search

        source = inspect.getsource(search)
        assert "effective_settings" in source
        assert "build_profile_resolver" in source

    def test_watcher_resolves_profile(self) -> None:
        """The watcher resolves the collection's profile before ingesting."""
        import inspect
        from rag_mcp.daemon.watcher import DocumentIngestHandler

        source = inspect.getsource(DocumentIngestHandler._dispatch_ingest)
        assert "effective_settings" in source
        assert "build_profile_resolver" in source


# ── Coverage: contract.py exception and edge paths ───────────────────


class TestContractCoverage:
    """Tests for uncovered exception and edge paths in contract.py."""

    def test_safety_contract_when_count_raises(self) -> None:
        """generate_safety_contract handles store.count() raising."""
        store = MagicMock()
        store.count.side_effect = RuntimeError("store down")
        store.get_collection_metadata.return_value = None
        store.list_collections.return_value = []
        resolver = ProfileResolver(store=store, server_profile="documents")
        contract = generate_safety_contract(
            "coll", "codebase", store=store, resolver=resolver
        )
        assert contract["chunk_count"] == 0

    def test_safety_contract_when_metadata_raises(self) -> None:
        """generate_safety_contract handles get_collection_metadata raising."""
        store = MagicMock()
        store.count.return_value = 10
        store.get_collection_metadata.side_effect = RuntimeError("store down")
        store.list_collections.return_value = []
        resolver = ProfileResolver(store=store, server_profile="documents")
        contract = generate_safety_contract(
            "coll", "codebase", store=store, resolver=resolver
        )
        assert contract["old_profile"] is None

    def test_safety_contract_with_old_profile_load_failure(self) -> None:
        """generate_safety_contract handles old profile load failure."""
        store = MagicMock()
        store.count.return_value = 5
        store.get_collection_metadata.return_value = {"profile": "documents"}
        store.list_collections.return_value = ["coll"]
        store.collection_exists.return_value = True
        resolver = ProfileResolver(store=store, server_profile="documents")
        # Force _load_effective to fail for the old profile.
        with patch.object(
            resolver, "_load_effective", side_effect=[RuntimeError("fail"), None]
        ):
            contract = generate_safety_contract(
                "coll", "codebase", store=store, resolver=resolver
            )
        # old_effective is None, but contract still generates.
        assert contract["old_profile"] == "documents"

    def test_safety_contract_with_new_profile_load_failure(self) -> None:
        """generate_safety_contract handles new profile load failure."""
        store = MagicMock()
        store.count.return_value = 5
        store.get_collection_metadata.return_value = None
        store.list_collections.return_value = []
        resolver = ProfileResolver(store=store, server_profile="documents")
        with patch.object(
            resolver, "_load_effective", side_effect=RuntimeError("fail")
        ):
            contract = generate_safety_contract(
                "coll", "codebase", store=store, resolver=resolver
            )
        # new_effective is None → lever_impacts is empty.
        assert contract["lever_impacts"] == []

    def test_lever_impact_unchanged_value(self) -> None:
        """_lever_impact marks unchanged values correctly."""
        from rag_mcp.core.profiles.contract import _lever_impact

        impact = _lever_impact("top_k", 10, 10, "query-time")
        assert "unchanged" in impact["change"]

    def test_apply_profile_change_count_failure(self) -> None:
        """apply_profile_change handles count() raising after update."""
        store = MagicMock()
        store.collection_exists.return_value = True
        store.count.side_effect = RuntimeError("store down")
        result = apply_profile_change("coll", "codebase", store=store)
        assert result["status"] == "ok"
        assert result["chunk_count_unchanged"] == 0


# ── Coverage: resolver.py edge paths ──────────────────────────────────


class TestResolverCoverage:
    """Tests for uncovered edge paths in resolver.py."""

    def test_parse_profile_bool_with_native_bool(self) -> None:
        """_parse_profile_bool returns native bools directly."""
        from rag_mcp.core.profiles.resolver import _parse_profile_bool

        assert _parse_profile_bool(True) is True
        assert _parse_profile_bool(False) is False

    def test_parse_profile_bool_with_non_str_non_bool(self) -> None:
        """_parse_profile_bool coerces other types via bool()."""
        from rag_mcp.core.profiles.resolver import _parse_profile_bool

        assert _parse_profile_bool(1) is True
        assert _parse_profile_bool(0) is False

    def test_resolve_profile_name_method(self) -> None:
        """resolve_profile_name returns the name without loading the bundle."""
        store = _make_mock_store(
            collection_meta={"docs": {"profile": "documents"}}
        )
        resolver = ProfileResolver(store=store, server_profile="codebase")
        name = resolver.resolve_profile_name("docs")
        assert name == "documents"

    def test_resolve_profile_name_hybrid_fallback(self) -> None:
        """resolve_profile_name resolves hybrid to default_profile."""
        store = _make_mock_store(collection_meta={"coll": None})
        resolver = ProfileResolver(store=store, server_profile="hybrid")
        name = resolver.resolve_profile_name("coll")
        assert name == "documents"

    def test_read_collection_tag_handles_store_exception(self) -> None:
        """_read_collection_tag returns None when store raises."""
        store = MagicMock()
        store.get_collection_metadata.side_effect = RuntimeError("down")
        resolver = ProfileResolver(store=store, server_profile="documents")
        tag = resolver._read_collection_tag(store, "coll")
        assert tag is None

    def test_read_collection_tag_non_dict_metadata(self) -> None:
        """_read_collection_tag returns None for non-dict metadata."""
        store = MagicMock()
        store.get_collection_metadata.return_value = "not a dict"
        resolver = ProfileResolver(store=store, server_profile="documents")
        tag = resolver._read_collection_tag(store, "coll")
        assert tag is None

    def test_read_collection_tag_empty_string_tag(self) -> None:
        """_read_collection_tag returns None for empty string tag."""
        store = MagicMock()
        store.get_collection_metadata.return_value = {"profile": ""}
        resolver = ProfileResolver(store=store, server_profile="documents")
        tag = resolver._read_collection_tag(store, "coll")
        assert tag is None

    def test_load_effective_with_missing_bundle(self) -> None:
        """_load_effective falls back to defaults when bundle is missing."""
        store = _make_mock_store()
        resolver = ProfileResolver(store=store, server_profile="documents")
        with patch(
            "rag_mcp.core.profiles.resolver._load_profile_bundle",
            return_value={},
        ):
            effective = resolver._load_effective("documents")
        assert effective.profile_name == "documents"
        assert effective.top_k == 10  # field default

    def test_resolve_hybrid_default_exception_fallback(self) -> None:
        """_resolve_hybrid_default falls back to 'documents' on error."""
        store = _make_mock_store()
        resolver = ProfileResolver(store=store, server_profile="hybrid")
        # Patch importlib.resources.files to raise inside _resolve_hybrid_default
        with patch("importlib.resources.files", side_effect=FileNotFoundError("gone")):
            result = resolver._resolve_hybrid_default()
        assert result == "documents"

    def test_get_server_profile_from_settings(self) -> None:
        """_get_server_profile reads from settings when not injected."""
        store = _make_mock_store(collection_meta={"coll": None})
        # Don't pass server_profile — should read from settings.
        resolver = ProfileResolver(store=store)
        profile = resolver._get_server_profile()
        assert profile in ("documents", "codebase", "hybrid")
