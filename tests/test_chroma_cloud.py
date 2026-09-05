"""Tests for the add-chroma-cloud-backend change: explicit Chroma Cloud mode.

Covers the chroma-cloud-backend spec scenarios:
- explicit ``CHROMA_MODE`` selection (default local, explicit cloud,
  unknown values rejected at Settings construction time)
- independent embedding-compute and storage axes (all four combinations,
  no ``hybrid`` selector)
- cloud credential validation (API key required, tenant/database paired,
  secrets never echoed in validation errors or summaries)
- ChromaVectorStore client injection (local PersistentClient, cloud
  CloudClient with a heartbeat connection check)
- embedding-identity collection metadata (stamp on first write, merge
  with existing profile tags, mismatch rejection, legacy compatibility)
- local/cloud operation parity through the VectorStore contract
- runtime setup failure leaving the default store unset and re-callable
- the single ``chromadb`` import boundary in production source

New production names (``EmbeddingIdentity``, the cloud factory kwargs,
``chroma_storage_summary``, ``_embedding_identity_from_settings`) are
resolved lazily inside each test so every scenario fails individually
before the implementation lands.
"""

from __future__ import annotations

import re
import traceback
from pathlib import Path
from unittest.mock import patch

import pytest

# Chroma-only suite (task 5.1): skips by design in the base install and
# runs in the chroma-extra CI job.
pytest.importorskip("chromadb", reason="chroma extra not installed (uv sync --extra chroma)")
import chromadb
import pytest
from llama_index.core.schema import TextNode

from omrg.config import Settings
from omrg.core.vectordb import chroma as chroma_mod
from omrg.core.vectordb.chroma import ChromaVectorStore
from omrg.core.vectordb.identity import redact_secret

# Test key chosen so no prefix collides with words that legitimately
# appear in error messages ("CHROMA_MODE=cloud", "tenant", "database").
# Built by concatenation so secret scanners see only low-entropy
# fragments — it is a fixture, never a real credential.
_CLOUD_KEY = "0" * 8 + "-chroma-test-key"

_CHROMA_ENV_VARS = (
    "CHROMA_MODE",
    "CHROMA_CLOUD_API_KEY",
    "CHROMA_CLOUD_TENANT",
    "CHROMA_CLOUD_DATABASE",
)


# ── Helpers ──────────────────────────────────────────────────────────


def _settings(**overrides) -> Settings:
    """Build a fresh Settings without ``.env`` and deterministic provider defaults.

    ``vector_store`` defaults to ``chroma``: this is the Chroma-only suite
    (extra-gated), and the conftest ``_isolate_env`` fixture pins
    ``VECTOR_STORE=lancedb`` for every test — leaving the env default would
    trip the backend-compat validator (task 2.5).
    """
    overrides.setdefault("vector_store", "chroma")
    overrides.setdefault("embed_provider", "local")
    overrides.setdefault("local_backend", "ollama")
    overrides.setdefault("embed_model", "nomic-embed-text")
    return Settings(_env_file=None, **overrides)


def _cloud_settings(**overrides) -> Settings:
    """Build a valid cloud-mode Settings (key present, tenant/database paired)."""
    overrides.setdefault("chroma_mode", "cloud")
    overrides.setdefault("chroma_cloud_api_key", _CLOUD_KEY)
    return _settings(**overrides)


def _clear_chroma_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove ambient Chroma cloud env entries so defaults are observable."""
    for name in _CHROMA_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def _embedding_identity(
    provider: str = "llamacpp",
    model: str = "model-a",
    index_identity: str | None = None,
):
    """Construct an ``EmbeddingIdentity`` lazily (red pre-implementation)."""
    from omrg.core.vectordb.chroma import EmbeddingIdentity

    return EmbeddingIdentity(provider=provider, model=model, index_identity=index_identity)


def _shared_client():
    """Return the shared in-memory Chroma client installed by conftest."""
    return chromadb.EphemeralClient()


def _assert_no_key_material(message: str, key: str) -> None:
    """Assert neither the key nor any prefix of six-plus characters appears."""
    assert key not in message, f"full API key leaked in: {message!r}"
    for size in range(6, len(key) + 1):
        assert key[:size] not in message, f"API key prefix ({size} chars) leaked: {key[:size]!r}"


def _install_persistent_spy(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    """Wrap the conftest-patched PersistentClient with a kwargs recorder."""
    inner = chromadb.PersistentClient
    calls: list[dict] = []

    def _spy(**kwargs):
        calls.append(kwargs)
        return inner(**kwargs)

    monkeypatch.setattr(chromadb, "PersistentClient", _spy)
    return calls


def _forbid_persistent_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make any PersistentClient construction fail the test."""

    def _forbidden(**kwargs):
        raise AssertionError("PersistentClient must not be constructed in cloud mode")

    monkeypatch.setattr(chromadb, "PersistentClient", _forbidden)


# ── Client doubles ───────────────────────────────────────────────────


class _FakeCollection:
    """Minimal Chroma collection double that records queries and metadata writes."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.metadata: dict | None = None
        self.query_calls = 0

    def modify(self, metadata=None, **_kwargs) -> None:
        self.metadata = dict(metadata) if metadata is not None else None

    def count(self) -> int:
        return 0

    def query(self, **_kwargs) -> dict:
        self.query_calls += 1
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}

    def get(self, **_kwargs) -> dict:
        return {"ids": [], "documents": [], "metadatas": []}

    def delete(self, **_kwargs) -> None:
        return None


class _RecordingClient:
    """Chroma ClientAPI double that records every collection operation."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self._collections: dict[str, _FakeCollection] = {}

    def get_or_create_collection(self, name: str, **_kwargs) -> _FakeCollection:
        self.calls.append(("get_or_create_collection", name))
        if name not in self._collections:
            self._collections[name] = _FakeCollection(name)
        return self._collections[name]

    def get_collection(self, name: str) -> _FakeCollection:
        self.calls.append(("get_collection", name))
        if name not in self._collections:
            # ChromaVectorStore._get_collection treats KeyError as "missing".
            raise KeyError(name)
        return self._collections[name]

    def delete_collection(self, name: str) -> None:
        self.calls.append(("delete_collection", name))
        self._collections.pop(name, None)

    def list_collections(self) -> list[_FakeCollection]:
        self.calls.append(("list_collections",))
        return list(self._collections.values())


def _install_fake_cloud_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    backing=None,
    heartbeat_error: Exception | None = None,
    init_error: Exception | None = None,
):
    """Patch ``chromadb.CloudClient`` to a recording fake.

    Args:
        backing: Real client that collection operations delegate to, so
            parity and injection tests exercise the genuine Chroma path.
        heartbeat_error: Exception raised by ``heartbeat()``.
        init_error: Exception raised by the constructor.

    Returns:
        State object with ``construct_calls`` and ``heartbeat_calls``.
    """
    state = type("_CloudSpy", (), {})()
    state.construct_calls: list[dict] = []
    state.heartbeat_calls = 0

    class _FakeCloudClient:
        def __init__(self, **kwargs) -> None:
            state.construct_calls.append(kwargs)
            self._backing = backing
            if init_error is not None:
                raise init_error

        def heartbeat(self) -> None:
            state.heartbeat_calls += 1
            if heartbeat_error is not None:
                raise heartbeat_error

        def __getattr__(self, name: str):
            if self._backing is None:
                raise AttributeError(name)
            return getattr(self._backing, name)

    monkeypatch.setattr(chromadb, "CloudClient", _FakeCloudClient, raising=False)
    return state


# ── Settings: chroma mode selection ─────────────────────────────────


class TestSettingsChromaMode:
    """CHROMA_MODE parsing: default local, explicit cloud, strict rejection."""

    def test_default_mode_is_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An unset CHROMA_MODE resolves to local without any credentials."""
        _clear_chroma_env(monkeypatch)
        assert Settings(_env_file=None).chroma_mode == "local"

    def test_explicit_cloud_via_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CHROMA_MODE=cloud flows from the environment into the model."""
        _clear_chroma_env(monkeypatch)
        monkeypatch.setenv("VECTOR_STORE", "chroma")
        monkeypatch.setenv("CHROMA_MODE", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", _CLOUD_KEY)
        assert Settings(_env_file=None).chroma_mode == "cloud"

    def test_explicit_cloud_via_kwargs(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Explicit instantiation selects cloud mode."""
        _clear_chroma_env(monkeypatch)
        assert _cloud_settings().chroma_mode == "cloud"

    def test_unknown_mode_rejected_listing_accepted_values(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognised mode fails with the accepted values listed."""
        _clear_chroma_env(monkeypatch)
        with pytest.raises(ValueError) as excinfo:
            _settings(chroma_mode="serverless")
        message = str(excinfo.value)
        assert "CHROMA_MODE" in message
        assert "local" in message and "cloud" in message

    def test_unknown_mode_via_env_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The env path validates exactly like the kwargs path."""
        _clear_chroma_env(monkeypatch)
        monkeypatch.setenv("CHROMA_MODE", "hosted")
        with pytest.raises(ValueError, match="CHROMA_MODE"):
            Settings(_env_file=None)

    def test_empty_mode_resets_to_local(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Whitespace-only values are the operator unset idiom, not an error."""
        _clear_chroma_env(monkeypatch)
        assert _settings(chroma_mode="   ").chroma_mode == "local"
        monkeypatch.setenv("CHROMA_MODE", "")
        assert Settings(_env_file=None).chroma_mode == "local"

    def test_hybrid_mode_is_not_a_selector(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """'hybrid' belongs to retrieval, never to storage selection."""
        _clear_chroma_env(monkeypatch)
        with pytest.raises(ValueError, match="CHROMA_MODE"):
            _settings(chroma_mode="hybrid")

    def test_cloud_env_key_is_read_into_the_model(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """CHROMA_CLOUD_API_KEY flows from the environment into the field."""
        _clear_chroma_env(monkeypatch)
        monkeypatch.setenv("VECTOR_STORE", "chroma")
        monkeypatch.setenv("CHROMA_MODE", "cloud")
        monkeypatch.setenv("CHROMA_CLOUD_API_KEY", _CLOUD_KEY)
        assert Settings(_env_file=None).chroma_cloud_api_key == _CLOUD_KEY

    def test_padded_key_is_stored_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A padded key validates but is stored stripped so it authenticates."""
        _clear_chroma_env(monkeypatch)
        settings = _cloud_settings(chroma_cloud_api_key=f"  {_CLOUD_KEY}\t")
        assert settings.chroma_cloud_api_key == _CLOUD_KEY


# ── Settings: cloud credential validation ───────────────────────────


class TestCloudCredentialsValidation:
    """Cloud credentials validate at Settings construction, before any I/O."""

    def test_cloud_mode_without_key_raises_at_construction(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Startup fails before ingestion when the key is missing."""
        _clear_chroma_env(monkeypatch)
        with pytest.raises(ValueError, match="CHROMA_CLOUD_API_KEY"):
            _settings(chroma_mode="cloud")

    def test_cloud_mode_with_whitespace_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A whitespace key is treated as missing, not as a credential."""
        _clear_chroma_env(monkeypatch)
        with pytest.raises(ValueError, match="CHROMA_CLOUD_API_KEY"):
            _settings(chroma_mode="cloud", chroma_cloud_api_key="   ")

    def test_tenant_without_database_raises_naming_both(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A half-supplied tenant/database pair names both variables."""
        _clear_chroma_env(monkeypatch)
        with pytest.raises(ValueError) as excinfo:
            _cloud_settings(chroma_cloud_tenant="solo-tenant")
        message = str(excinfo.value)
        assert "CHROMA_CLOUD_TENANT" in message
        assert "CHROMA_CLOUD_DATABASE" in message

    def test_database_without_tenant_raises_naming_both(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The mirror half-pair fails identically."""
        _clear_chroma_env(monkeypatch)
        with pytest.raises(ValueError) as excinfo:
            _cloud_settings(chroma_cloud_database="solo-db")
        message = str(excinfo.value)
        assert "CHROMA_CLOUD_TENANT" in message
        assert "CHROMA_CLOUD_DATABASE" in message

    def test_tenant_and_database_together_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The full pair constructs cleanly."""
        _clear_chroma_env(monkeypatch)
        settings = _cloud_settings(chroma_cloud_tenant="t-1", chroma_cloud_database="d-1")
        assert settings.chroma_cloud_tenant == "t-1"
        assert settings.chroma_cloud_database == "d-1"

    def test_key_without_tenant_or_database_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The key-only form constructs; the client resolves the rest."""
        _clear_chroma_env(monkeypatch)
        assert _cloud_settings().chroma_mode == "cloud"

    def test_validation_error_does_not_echo_the_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Validation messages never contain the submitted key material."""
        _clear_chroma_env(monkeypatch)
        with pytest.raises(ValueError, match="CHROMA_CLOUD") as excinfo:
            _cloud_settings(chroma_cloud_tenant="solo-tenant")
        _assert_no_key_material(str(excinfo.value), _CLOUD_KEY)


# ── Factory: local mode ─────────────────────────────────────────────


class TestFactoryLocal:
    """Local mode constructs PersistentClient once with the resolved path."""

    def test_local_factory_constructs_persistent_client_once_with_path(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """PersistentClient(path=...) is called exactly once and injected."""
        calls = _install_persistent_spy(monkeypatch)
        store = chroma_mod.build_chroma_vector_store(persist_dir="/x")
        assert calls == [{"path": "/x"}]
        store.create_collection("local_spy_probe")
        # The injected client serves later operations without re-construction.
        assert calls == [{"path": "/x"}]
        assert "local_spy_probe" in store.list_collections()

    def test_local_factory_defaults_to_effective_persist_dir(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without an explicit path, the composition-root default is used."""
        from omrg.core.settings import get_default_effective_settings

        calls = _install_persistent_spy(monkeypatch)
        chroma_mod.build_chroma_vector_store()
        expected = get_default_effective_settings().chroma_persist_dir
        assert calls == [{"path": expected}]


# ── Factory: cloud mode ─────────────────────────────────────────────


class TestFactoryCloud:
    """Cloud mode constructs CloudClient with exact kwargs plus a heartbeat check."""

    def test_cloud_factory_passes_api_key_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without tenant/database the SDK receives exactly the key."""
        state = _install_fake_cloud_client(monkeypatch, backing=_shared_client())
        store = chroma_mod.build_chroma_vector_store(mode="cloud", cloud_api_key=_CLOUD_KEY)
        assert state.construct_calls == [{"api_key": _CLOUD_KEY}]
        assert state.heartbeat_calls == 1
        store.create_collection("cloud_kw_probe")
        # Collection operations do not repeat the connection check.
        assert state.heartbeat_calls == 1
        assert "cloud_kw_probe" in store.list_collections()

    @pytest.mark.parametrize("tenant,database", [(None, None), ("", "")])
    def test_cloud_factory_omits_empty_tenant_database(
        self, monkeypatch: pytest.MonkeyPatch, tenant: str | None, database: str | None
    ) -> None:
        """None or empty tenant/database reduce to the key-only constructor."""
        state = _install_fake_cloud_client(monkeypatch)
        chroma_mod.build_chroma_vector_store(
            mode="cloud",
            cloud_api_key=_CLOUD_KEY,
            cloud_tenant=tenant,
            cloud_database=database,
        )
        assert state.construct_calls == [{"api_key": _CLOUD_KEY}]

    def test_cloud_factory_passes_tenant_and_database(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A supplied pair reaches the SDK constructor verbatim."""
        state = _install_fake_cloud_client(monkeypatch, backing=_shared_client())
        chroma_mod.build_chroma_vector_store(
            mode="cloud",
            cloud_api_key=_CLOUD_KEY,
            cloud_tenant="tenant-1",
            cloud_database="db-1",
        )
        assert state.construct_calls == [
            {"api_key": _CLOUD_KEY, "tenant": "tenant-1", "database": "db-1"}
        ]
        assert state.heartbeat_calls == 1

    def test_cloud_factory_returns_store_bound_to_injected_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Collection operations route to the cloud client, never PersistentClient."""
        backing = _RecordingClient()
        _install_fake_cloud_client(monkeypatch, backing=backing)
        _forbid_persistent_client(monkeypatch)
        store = chroma_mod.build_chroma_vector_store(mode="cloud", cloud_api_key=_CLOUD_KEY)
        store.create_collection("injected_probe")
        store.list_collections()
        assert ("get_or_create_collection", "injected_probe") in backing.calls
        assert any(call[0] == "list_collections" for call in backing.calls)

    def test_cloud_factory_requires_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A missing key fails before any client construction."""
        state = _install_fake_cloud_client(monkeypatch)
        with pytest.raises(ValueError, match="CHROMA_CLOUD_API_KEY"):
            chroma_mod.build_chroma_vector_store(mode="cloud")
        assert state.construct_calls == []

    @pytest.mark.parametrize("fail_at", ["construction", "heartbeat"])
    def test_cloud_failure_wraps_as_runtime_error_without_key(
        self, monkeypatch: pytest.MonkeyPatch, fail_at: str
    ) -> None:
        """Construction or heartbeat failures become actionable, redacted errors."""
        underlying = ConnectionError(f"401 Unauthorized: api_key={_CLOUD_KEY}")
        _install_fake_cloud_client(
            monkeypatch,
            init_error=underlying if fail_at == "construction" else None,
            heartbeat_error=underlying if fail_at == "heartbeat" else None,
        )
        with pytest.raises(RuntimeError, match="CHROMA_MODE=cloud") as excinfo:
            chroma_mod.build_chroma_vector_store(mode="cloud", cloud_api_key=_CLOUD_KEY)
        _assert_no_key_material(str(excinfo.value), _CLOUD_KEY)

    @pytest.mark.parametrize("fail_at", ["construction", "heartbeat"])
    def test_cloud_failure_redacts_tenant_and_database_values(
        self, monkeypatch: pytest.MonkeyPatch, fail_at: str
    ) -> None:
        """Tenant/database identifiers never leak in cloud connection errors.

        Regression for the audit finding that construction failures
        disclosed the configured tenant and database. The RuntimeError
        must carry neither the full values nor any prefix of six-plus
        characters — the same floor ``redact_secret`` applies to the
        API key. Identifiers start with ``acme-`` so no >=6-character
        prefix collides with words that legitimately appear in the
        wrapper message ("CHROMA_CLOUD_TENANT", "database", ...).
        """
        tenant = "acme-tenant-9f"
        database = "acme-database-9f"
        # Truncated echoes (9- and 8-char prefixes) prove prefix-aware
        # redaction, not just whole-value replacement.
        underlying = ConnectionError(
            f"401 unauthorized: tenant={tenant} database={database} "
            f"truncated={tenant[:9]} fragment={database[:8]}"
        )
        _install_fake_cloud_client(
            monkeypatch,
            init_error=underlying if fail_at == "construction" else None,
            heartbeat_error=underlying if fail_at == "heartbeat" else None,
        )
        with pytest.raises(RuntimeError, match="CHROMA_MODE=cloud") as excinfo:
            chroma_mod.build_chroma_vector_store(
                mode="cloud",
                cloud_api_key=_CLOUD_KEY,
                cloud_tenant=tenant,
                cloud_database=database,
            )
        message = str(excinfo.value)
        for label, value in (("tenant", tenant), ("database", database)):
            assert value not in message, f"full {label} identifier leaked in: {message!r}"
            for size in range(6, len(value) + 1):
                assert value[:size] not in message, (
                    f"{label} identifier prefix ({size} chars) leaked in: {message!r}"
                )


# ── Factory: cloud failure traceback redaction ─────────────────────


class TestCloudFactoryTracebackRedaction:
    """Formatted tracebacks of cloud factory failures carry no secrets.

    Regression for the audit finding that ``raise ... from exc`` chained
    the raw SDK exception as ``__cause__``: the wrapper RuntimeError
    message was redacted, yet ``traceback.format_exception`` re-rendered
    the chained SDK message and echoed the configured API key, tenant,
    and database. Any fix that keeps the formatted chain free of key
    material passes — ``from None``, raising outside the ``except``
    block, or chaining a redacted stand-in cause.
    """

    @pytest.mark.parametrize("fail_at", ["construction", "heartbeat"])
    def test_formatted_traceback_contains_no_cloud_secrets(
        self, monkeypatch: pytest.MonkeyPatch, fail_at: str
    ) -> None:
        """``traceback.format_exception`` renders neither the chained raw
        SDK message nor any six-plus-character secret prefix.

        The fabricated SDK failure echoes the full key, tenant, and
        database plus truncated fragments, mirroring real 401 bodies.
        Identifiers keep the ``acme-`` stem so no >=6-character prefix
        collides with words that legitimately appear in the wrapper
        message; frame source lines show variable names only, never
        runtime values, so they cannot collide either.
        """
        tenant = "acme-tenant-tb"
        database = "acme-database-tb"
        underlying = ConnectionError(
            f"401 Unauthorized: api_key={_CLOUD_KEY} tenant={tenant} "
            f"database={database} truncated={_CLOUD_KEY[:9]} "
            f"fragments={tenant[:8]}/{database[:7]}"
        )
        _install_fake_cloud_client(
            monkeypatch,
            init_error=underlying if fail_at == "construction" else None,
            heartbeat_error=underlying if fail_at == "heartbeat" else None,
        )
        with pytest.raises(RuntimeError, match="CHROMA_MODE=cloud") as excinfo:
            chroma_mod.build_chroma_vector_store(
                mode="cloud",
                cloud_api_key=_CLOUD_KEY,
                cloud_tenant=tenant,
                cloud_database=database,
            )
        formatted = "".join(traceback.format_exception(excinfo.value))
        for label, value in (
            ("API key", _CLOUD_KEY),
            ("tenant identifier", tenant),
            ("database identifier", database),
        ):
            assert value not in formatted, (
                f"full {label} leaked in formatted traceback: {formatted!r}"
            )
            for size in range(6, len(value) + 1):
                assert value[:size] not in formatted, (
                    f"{label} prefix ({size} chars) leaked in formatted traceback: {formatted!r}"
                )


# ── Runtime setup: cloud failure semantics ──────────────────────────


class TestCloudRuntimeSetup:
    """A cloud failure leaves no default store and stays re-callable."""

    def test_cloud_failure_leaves_default_store_unset_and_setup_recallable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failed validation registers nothing; a later call re-attempts."""
        from llama_index.core.embeddings import MockEmbedding

        import omrg.compose as compose_mod
        import omrg.core.vectordb as vectordb_mod
        from omrg.compose import ensure_runtime_setup, reset_runtime_setup
        from omrg.core.vectordb import reset_default_store

        cloud_settings = _cloud_settings(
            chroma_cloud_tenant="tenant-r", chroma_cloud_database="db-r"
        )
        mock_model = MockEmbedding(embed_dim=384)
        reset_runtime_setup()
        reset_default_store()
        try:
            _install_fake_cloud_client(
                monkeypatch,
                heartbeat_error=ConnectionError(f"401 api_key={_CLOUD_KEY}"),
            )
            _forbid_persistent_client(monkeypatch)
            with (
                patch("omrg.compose.get_settings", return_value=cloud_settings),
                patch("omrg.compose.build_embed_model", return_value=mock_model),
            ):
                with pytest.raises(RuntimeError, match="CHROMA_MODE=cloud"):
                    ensure_runtime_setup()
                assert vectordb_mod._default_store is None
                assert compose_mod._runtime_setup_done is False

                # Repair the connection; setup must re-run, not stay cached.
                _install_fake_cloud_client(monkeypatch, backing=_shared_client())
                ensure_runtime_setup()
                assert vectordb_mod._default_store is not None
                assert compose_mod._runtime_setup_done is True
        finally:
            reset_runtime_setup()
            reset_default_store()


# ── Runtime summary and secret redaction ────────────────────────────


class TestChromaStorageSummary:
    """chroma_storage_summary exposes identifiers, never key material."""

    def test_local_summary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from omrg.core.vectordb.summary import chroma_storage_summary

        _clear_chroma_env(monkeypatch)
        assert chroma_storage_summary(_settings()) == "chroma mode=local"

    def test_cloud_summary_includes_identifiers_not_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from omrg.core.vectordb.summary import chroma_storage_summary

        _clear_chroma_env(monkeypatch)
        settings = _cloud_settings(chroma_cloud_tenant="tenant-9", chroma_cloud_database="db-9")
        summary = chroma_storage_summary(settings)
        assert summary == "chroma mode=cloud tenant=tenant-9 database=db-9"
        _assert_no_key_material(summary, _CLOUD_KEY)

    def test_cloud_summary_without_tenant_carries_no_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from omrg.core.vectordb.summary import chroma_storage_summary

        _clear_chroma_env(monkeypatch)
        summary = chroma_storage_summary(_cloud_settings())
        assert summary.startswith("chroma mode=cloud")
        _assert_no_key_material(summary, _CLOUD_KEY)


class TestRedactSecret:
    """The module-level redaction helper used by cloud error paths."""

    def test_replaces_every_occurrence(self) -> None:
        message = f"connect failed for {_CLOUD_KEY} at host"
        assert redact_secret(message, _CLOUD_KEY) == "connect failed for *** at host"

    def test_absent_secret_returns_message_unchanged(self) -> None:
        assert redact_secret("plain message", None) == "plain message"
        assert redact_secret("plain message", "") == "plain message"

    # ── Regression: prefix-aware redaction (validated defect, dc3f35e) ──
    # Cloud SDK errors can echo a truncated key (a six-plus-character
    # prefix), not only the full secret.

    def test_redacts_prefix_of_six_or_more_characters(self) -> None:
        """A truncated key echo (prefix only, no full key) is redacted."""
        prefix = _CLOUD_KEY[:12]
        message = f"auth rejected token={prefix} (truncated)"
        redacted = redact_secret(message, _CLOUD_KEY)
        _assert_no_key_material(redacted, _CLOUD_KEY)
        assert "token=***" in redacted

    def test_redacts_full_key_and_prefix_in_same_message(self) -> None:
        """Full and truncated echoes in one message both disappear."""
        message = f"key={_CLOUD_KEY} truncated={_CLOUD_KEY[:8]}"
        redacted = redact_secret(message, _CLOUD_KEY)
        _assert_no_key_material(redacted, _CLOUD_KEY)
        assert "***" in redacted

    def test_prefixes_below_six_characters_are_left_intact(self) -> None:
        """Sub-threshold fragments survive — the redaction floor is six characters."""
        short = _CLOUD_KEY[:5]
        message = f"context around {short} fragment"
        assert redact_secret(message, _CLOUD_KEY) == message


# ── Embedding identity metadata ─────────────────────────────────────


class TestEmbeddingIdentityMetadata:
    """Collection identity guards incompatible embedding reuse (spec scenario)."""

    def test_write_nodes_stamps_identity_metadata(self) -> None:
        """The first identity-bearing write stamps provider and model."""
        store = ChromaVectorStore(
            client=_shared_client(),
            embedding_identity=_embedding_identity(provider="llamacpp", model="model-a"),
        )
        store.write_nodes([TextNode(text="stamp probe")], "ident_stamp")
        metadata = store.get_collection_metadata("ident_stamp")
        assert metadata is not None
        assert metadata["rag_embed_provider"] == "llamacpp"
        assert metadata["rag_embed_model"] == "model-a"

    def test_write_nodes_stamps_index_identity_when_present(self) -> None:
        """A supplied immutable index identity is stamped alongside the model."""
        store = ChromaVectorStore(
            client=_shared_client(),
            embedding_identity=_embedding_identity(model="model-a", index_identity="hash-111"),
        )
        store.write_nodes([TextNode(text="index stamp probe")], "ident_index_stamp")
        metadata = store.get_collection_metadata("ident_index_stamp")
        assert metadata is not None
        assert metadata["rag_index_identity"] == "hash-111"

    def test_second_write_with_same_identity_succeeds(self) -> None:
        """Compatible reuse appends without re-embedding or rejecting."""
        store = ChromaVectorStore(
            client=_shared_client(),
            embedding_identity=_embedding_identity(model="model-a"),
        )
        store.write_nodes([TextNode(text="first write")], "ident_repeat")
        store.write_nodes([TextNode(text="second write")], "ident_repeat")
        assert store.count("ident_repeat") == 2

    def test_existing_profile_metadata_survives_stamping(self) -> None:
        """Stamping merges with profile tags; Chroma modify replaces the map."""
        plain = ChromaVectorStore(client=_shared_client())
        plain.create_collection("ident_merge")
        plain.update_collection_metadata("ident_merge", {"profile": "documents"})
        ident_store = ChromaVectorStore(
            client=_shared_client(),
            embedding_identity=_embedding_identity(model="model-a"),
        )
        ident_store.write_nodes([TextNode(text="merge probe")], "ident_merge")
        metadata = ident_store.get_collection_metadata("ident_merge")
        assert metadata is not None
        assert metadata["profile"] == "documents"
        assert metadata["rag_embed_provider"] == "llamacpp"

    def test_write_with_different_identity_raises_naming_both(self) -> None:
        """Same-dimension models with different identity are rejected on write."""
        shared = _shared_client()
        store_a = ChromaVectorStore(
            client=shared, embedding_identity=_embedding_identity(model="model-a")
        )
        store_b = ChromaVectorStore(
            client=shared, embedding_identity=_embedding_identity(model="model-b")
        )
        store_a.write_nodes([TextNode(text="owner write")], "ident_mismatch")
        with pytest.raises(ValueError, match="ident_mismatch") as excinfo:
            store_b.write_nodes([TextNode(text="usurper write")], "ident_mismatch")
        message = str(excinfo.value)
        assert "model-a" in message
        assert "model-b" in message

    def test_index_identity_mismatch_with_same_model_raises(self) -> None:
        """Same provider/model but a different corpus identity is still incompatible."""
        shared = _shared_client()
        store_a = ChromaVectorStore(
            client=shared,
            embedding_identity=_embedding_identity(model="model-a", index_identity="hash-aaa"),
        )
        store_b = ChromaVectorStore(
            client=shared,
            embedding_identity=_embedding_identity(model="model-a", index_identity="hash-bbb"),
        )
        store_a.write_nodes([TextNode(text="original corpus")], "ident_index")
        with pytest.raises(ValueError, match="ident_index"):
            store_b.write_nodes([TextNode(text="different corpus")], "ident_index")

    def test_missing_active_index_identity_does_not_raise(self) -> None:
        """An active identity without index identity may extend the index."""
        shared = _shared_client()
        store_a = ChromaVectorStore(
            client=shared,
            embedding_identity=_embedding_identity(model="model-a", index_identity="hash-aaa"),
        )
        store_b = ChromaVectorStore(
            client=shared,
            embedding_identity=_embedding_identity(model="model-a", index_identity=None),
        )
        store_a.write_nodes([TextNode(text="indexed corpus")], "ident_extend")
        store_b.write_nodes([TextNode(text="appended chunk")], "ident_extend")
        assert store_b.count("ident_extend") == 2

    def test_query_with_matching_identity_succeeds(self) -> None:
        """Matching identity queries normally."""
        store = ChromaVectorStore(
            client=_shared_client(),
            embedding_identity=_embedding_identity(model="model-a"),
        )
        store.write_nodes([TextNode(text="match one"), TextNode(text="match two")], "ident_match")
        rows = store.query_dense("ident_match", [0.0] * 384, n_results=2)
        assert len(rows) == 2

    def test_query_identity_mismatch_raises_before_querying(self) -> None:
        """The mismatch check fires before the query reaches the collection."""
        client = _RecordingClient()
        collection = client.get_or_create_collection("ident_query")
        collection.metadata = {
            "rag_embed_provider": "llamacpp",
            "rag_embed_model": "model-a",
        }
        store = ChromaVectorStore(
            client=client, embedding_identity=_embedding_identity(model="model-b")
        )
        with pytest.raises(ValueError, match="ident_query"):
            store.query_dense("ident_query", [0.0] * 384, n_results=5)
        assert collection.query_calls == 0

    def test_query_on_legacy_collection_without_identity_succeeds(self) -> None:
        """Pre-identity collections keep working (legacy compatibility)."""
        shared = _shared_client()
        plain = ChromaVectorStore(client=shared)
        plain.write_nodes([TextNode(text="legacy row")], "ident_legacy")
        ident_store = ChromaVectorStore(
            client=shared, embedding_identity=_embedding_identity(model="model-a")
        )
        rows = ident_store.query_dense("ident_legacy", [0.0] * 384, n_results=1)
        assert len(rows) == 1

    def test_identity_none_never_stamps(self) -> None:
        """The default lazy store leaves collection metadata untouched."""
        store = ChromaVectorStore(client=_shared_client())
        store.write_nodes([TextNode(text="unstamped probe")], "ident_none")
        metadata = store.get_collection_metadata("ident_none")
        assert metadata is None or "rag_embed_provider" not in metadata


# ── Injected client ─────────────────────────────────────────────────


class TestClientInjection:
    """An injected client serves every collection operation directly."""

    def test_injected_client_used_for_every_collection_operation(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No lazy construction occurs once a client is injected."""
        _forbid_persistent_client(monkeypatch)
        client = _RecordingClient()
        store = ChromaVectorStore(client=client)
        store.create_collection("inj")
        assert store.collection_exists("inj")
        store.update_collection_metadata("inj", {"profile": "documents"})
        assert store.get_collection_metadata("inj") == {"profile": "documents"}
        store.list_collections()
        assert store.count("missing") == 0
        store.delete_collection("inj")
        assert not store.collection_exists("inj")
        call_names = {call[0] for call in client.calls}
        assert {
            "get_or_create_collection",
            "get_collection",
            "delete_collection",
            "list_collections",
        } <= call_names


# ── Local/cloud operation parity ────────────────────────────────────


def _exercise_store_cycle(store, name: str) -> dict:
    """Run one create/write/query/count/delete cycle, recording observations."""
    from llama_index.core import Settings as LlamaIndexSettings

    observations: dict = {}
    observations["exists_before"] = store.collection_exists(name)
    store.create_collection(name)
    observations["exists_after_create"] = store.collection_exists(name)
    nodes = [TextNode(text=f"parity probe {i}", metadata={"parity": name}) for i in range(2)]
    store.write_nodes(nodes, name)
    embedding = list(LlamaIndexSettings.embed_model.get_query_embedding("parity probe"))
    rows = store.query_dense(name, embedding, n_results=2)
    observations["query_row_keys"] = {frozenset(row) for row in rows}
    observations["count_after_write"] = store.count(name)
    store.delete_where(name, {"parity": name})
    observations["count_after_delete"] = store.count(name)
    store.delete_collection(name)
    observations["exists_after_delete"] = store.collection_exists(name)
    return observations


class TestLocalCloudParity:
    """Cloud and local modes expose the same result shapes (spec scenario)."""

    def test_local_and_cloud_cycles_produce_identical_observations(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path
    ) -> None:
        """The full lifecycle behaves identically across both modes."""
        _install_persistent_spy(monkeypatch)
        _install_fake_cloud_client(monkeypatch, backing=_shared_client())
        local_store = chroma_mod.build_chroma_vector_store(persist_dir=str(tmp_path))
        cloud_store = chroma_mod.build_chroma_vector_store(mode="cloud", cloud_api_key=_CLOUD_KEY)
        local_obs = _exercise_store_cycle(local_store, "parity_local")
        cloud_obs = _exercise_store_cycle(cloud_store, "parity_cloud")
        assert local_obs == cloud_obs
        assert local_obs["query_row_keys"] == {
            frozenset(
                {
                    "id",
                    "document",
                    "metadata",
                    "score",
                    "score_kind",
                    "native_distance",
                }
            )
        }
        assert local_obs["count_after_write"] == 2
        assert local_obs["count_after_delete"] == 0


# ── Four-mode independence ──────────────────────────────────────────


class TestFourModeIndependence:
    """Embedding compute and vector storage resolve on independent axes."""

    @pytest.mark.parametrize("embed_provider", ["local", "cloud"])
    @pytest.mark.parametrize("chroma_mode", ["local", "cloud"])
    def test_all_four_combinations_accepted(
        self,
        monkeypatch: pytest.MonkeyPatch,
        embed_provider: str,
        chroma_mode: str,
    ) -> None:
        """Every compute/storage combination constructs valid Settings."""
        _clear_chroma_env(monkeypatch)
        kwargs: dict = {"embed_provider": embed_provider, "chroma_mode": chroma_mode}
        if chroma_mode == "cloud":
            kwargs["chroma_cloud_api_key"] = _CLOUD_KEY
        settings = _settings(**kwargs)
        assert settings.chroma_mode == chroma_mode
        assert settings.embed_provider == embed_provider

    @pytest.mark.parametrize("embed_provider", ["local", "cloud"])
    @pytest.mark.parametrize("chroma_mode", ["local", "cloud"])
    def test_build_vector_store_passes_mode_from_settings_independently(
        self,
        monkeypatch: pytest.MonkeyPatch,
        embed_provider: str,
        chroma_mode: str,
    ) -> None:
        """The factory receives the storage mode regardless of the embed axis."""
        from omrg.compose import build_vector_store

        _clear_chroma_env(monkeypatch)
        cloud = chroma_mode == "cloud"
        settings = _settings(
            embed_provider=embed_provider,
            chroma_mode=chroma_mode,
            chroma_cloud_api_key=_CLOUD_KEY if cloud else "",
            chroma_cloud_tenant="t-9" if cloud else "",
            chroma_cloud_database="d-9" if cloud else "",
        )
        with patch("omrg.core.vectordb.chroma.build_chroma_vector_store") as mock_build:
            build_vector_store(settings)
        kwargs = mock_build.call_args.kwargs
        assert kwargs["mode"] == chroma_mode
        assert kwargs["persist_dir"] == settings.chroma_persist_dir
        assert kwargs["cloud_api_key"] == (_CLOUD_KEY if cloud else None)
        assert kwargs["cloud_tenant"] == ("t-9" if cloud else None)
        assert kwargs["cloud_database"] == ("d-9" if cloud else None)


# ── compose: embedding identity wiring ──────────────────────────────


class TestComposeEmbeddingIdentity:
    """compose derives the embedding identity from provider settings."""

    @pytest.mark.parametrize(
        ("provider_kwargs", "expected_provider", "expected_model"),
        [
            (
                {
                    "embed_provider": "local",
                    "local_backend": "llamacpp",
                    "llamacpp_embed_model": "t.gguf",
                },
                "llamacpp",
                "t.gguf",
            ),
            (
                {"embed_provider": "ollama", "embed_model": "nomic-embed-text"},
                "ollama",
                "nomic-embed-text",
            ),
            (
                {
                    "embed_provider": "cloud",
                    "cloud_backend": "openrouter",
                    "openrouter_embed_model": "or-embedding",
                },
                "openrouter",
                "or-embedding",
            ),
        ],
    )
    def test_identity_maps_each_provider_to_its_model_field(
        self, provider_kwargs: dict, expected_provider: str, expected_model: str
    ) -> None:
        from omrg.core.vectordb.identity import embedding_identity_from_settings

        identity = embedding_identity_from_settings(_settings(**provider_kwargs))
        assert identity.provider == expected_provider
        assert identity.model == expected_model
        assert identity.index_identity is None

    def test_build_vector_store_passes_embedding_identity(self) -> None:
        """The factory receives the derived identity object."""
        from omrg.compose import build_vector_store

        settings = _settings(
            embed_provider="local",
            local_backend="llamacpp",
            llamacpp_embed_model="t.gguf",
        )
        with patch("omrg.core.vectordb.chroma.build_chroma_vector_store") as mock_build:
            build_vector_store(settings)
        identity = mock_build.call_args.kwargs.get("embedding_identity")
        assert identity is not None
        assert identity.provider == "llamacpp"
        assert identity.model == "t.gguf"


# ── Import boundary ─────────────────────────────────────────────────


class TestUpsertPrecomputed:
    """The precomputed-embedding upsert added for calibration harnesses."""

    def test_upsert_writes_rows_and_stamps_identity(self) -> None:
        """Rows land with caller-computed embeddings and identity metadata."""
        store = ChromaVectorStore(
            client=_shared_client(),
            embedding_identity=_embedding_identity(provider="ollama", model="model-u"),
        )
        store.upsert_precomputed(
            "upsert_probe",
            ids=["u1", "u2"],
            documents=["alpha text", "beta text"],
            metadatas=[{"k": 1}, {"k": 2}],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            embedding_identity=_embedding_identity(provider="ollama", model="model-u"),
        )
        assert store.count("upsert_probe") == 2
        metadata = store.get_collection_metadata("upsert_probe")
        assert metadata is not None
        assert metadata["rag_embed_provider"] == "ollama"

    def test_upsert_rejects_identity_mismatch(self) -> None:
        """A differing identity fails before any row is written."""
        shared = _shared_client()
        first = ChromaVectorStore(
            client=shared, embedding_identity=_embedding_identity(model="model-a")
        )
        first.upsert_precomputed(
            "upsert_guard",
            ids=["x1"],
            documents=["original"],
            metadatas=[{"k": 1}],
            embeddings=[[0.5, 0.5]],
            embedding_identity=_embedding_identity(model="model-a"),
        )
        second = ChromaVectorStore(
            client=shared, embedding_identity=_embedding_identity(model="model-b")
        )
        with pytest.raises(ValueError, match="upsert_guard"):
            second.upsert_precomputed(
                "upsert_guard",
                ids=["x2"],
                documents=["usurper"],
                metadatas=[{"k": 2}],
                embeddings=[[0.5, 0.5]],
                embedding_identity=_embedding_identity(model="model-b"),
            )
        assert first.count("upsert_guard") == 1


class TestFactoryEdges:
    """Factory and lazy-path branches outside the main modes."""

    def test_unknown_mode_rejected_by_factory(self) -> None:
        """The factory repeats Settings validation for direct callers."""
        with pytest.raises(ValueError, match="CHROMA_MODE"):
            chroma_mod.build_chroma_vector_store(mode="remote")

    def test_direct_construction_lazy_local_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """ChromaVectorStore(persist_dir=...) still constructs lazily."""
        inner = chromadb.PersistentClient
        seen: list[dict] = []

        def _spy(**kwargs):
            seen.append(kwargs)
            return inner(**kwargs)

        monkeypatch.setattr(chromadb, "PersistentClient", _spy)
        store = ChromaVectorStore(persist_dir="/lazy/probe")
        store.create_collection("lazy_probe")
        assert seen == [{"path": "/lazy/probe"}]

    def test_update_metadata_on_missing_collection_creates_it(self) -> None:
        """Updating a missing collection creates it with the metadata."""
        store = ChromaVectorStore(client=_shared_client())
        store.update_collection_metadata("created_by_update", {"profile": "codebase"})
        assert store.get_collection_metadata("created_by_update") == {"profile": "codebase"}

    def test_non_positive_page_size_rejected(self) -> None:
        """Page-size validation rejects zero and negative sizes."""
        store = ChromaVectorStore(client=_shared_client())
        store.create_collection("page_size_probe")
        with pytest.raises(ValueError, match="positive integer"):
            list(store.iter_metadatas("page_size_probe", page_size=0))


class TestChromaImportBoundary:
    """The chroma adapter modules stay the only production chromadb import sites."""

    def test_chroma_module_is_the_only_chromadb_import_site(self) -> None:
        """No other production module may import chromadb (spec scenario)."""
        src_root = Path(__file__).resolve().parent.parent / "src" / "omrg"
        allowed = frozenset(
            {
                "core/vectordb/chroma.py",
                # Cloud-connection helper extracted from the adapter; same
                # boundary, one import site per concern.
                "core/vectordb/chroma_cloud.py",
            }
        )
        pattern = re.compile(r"^\s*(?:import chromadb|from chromadb)", re.MULTILINE)
        offenders = sorted(
            path.relative_to(src_root).as_posix()
            for path in src_root.rglob("*.py")
            if "__pycache__" not in path.parts
            and path.relative_to(src_root).as_posix() not in allowed
            and pattern.search(path.read_text(encoding="utf-8"))
        )
        assert offenders == [], f"unexpected chromadb import sites: {offenders}"
        # Guard against vacuous passage: the canonical adapter must still import it.
        adapter_source = (src_root / "core/vectordb/chroma.py").read_text(encoding="utf-8")
        assert pattern.search(adapter_source) is not None
