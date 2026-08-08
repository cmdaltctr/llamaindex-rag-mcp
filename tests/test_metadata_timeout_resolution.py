"""Tests for the per-provider classify/pipeline timeout resolvers.

Covers openspec/changes/fix-silent-metadata-degradation/ task groups 2
and 3: ``_resolve_classify_timeout`` / ``_resolve_pipeline_timeout`` in
``core/metadata/_common.py``, and their wiring into the direct-chat
backends (llamacpp, ollama, openrouter) and the llamaindex pipeline.

All six overrides default to ``None``, so a passing suite could hide a
broken resolver if it only ever exercised the default path — every
resolver test below is parametrised over override-set AND override-unset
per provider (design.md Risk: "No behaviour change is easy to
under-test").
"""

from __future__ import annotations

import asyncio

import pytest

from rag_mcp.core.settings import EffectiveSettings, MetadataBlock


# ── Task 2.2: resolver unit tests ───────────────────────────────────────


class TestResolveClassifyTimeout:
    """``_resolve_classify_timeout(resolved, provider)``."""

    @pytest.mark.parametrize(
        "provider,field",
        [
            ("llamacpp", "llamacpp_classify_timeout"),
            ("ollama", "ollama_classify_timeout"),
            ("openrouter", "openrouter_classify_timeout"),
        ],
    )
    def test_override_honoured(self, provider: str, field: str) -> None:
        """A set override wins over the shared classify_timeout."""
        from rag_mcp.core.metadata._common import _resolve_classify_timeout

        settings = EffectiveSettings(
            metadata=MetadataBlock(classify_timeout=30.0, **{field: 99.0})
        )
        assert _resolve_classify_timeout(settings, provider) == 99.0

    @pytest.mark.parametrize("provider", ["llamacpp", "ollama", "openrouter"])
    def test_unset_falls_back_to_shared(self, provider: str) -> None:
        """An unset override (None, the default) falls back to classify_timeout."""
        from rag_mcp.core.metadata._common import _resolve_classify_timeout

        settings = EffectiveSettings(metadata=MetadataBlock(classify_timeout=42.0))
        assert _resolve_classify_timeout(settings, provider) == 42.0

    def test_unknown_provider_falls_back_to_shared(self) -> None:
        """A provider name with no matching field behaves like an unset override."""
        from rag_mcp.core.metadata._common import _resolve_classify_timeout

        settings = EffectiveSettings(metadata=MetadataBlock(classify_timeout=17.0))
        assert _resolve_classify_timeout(settings, "made_up_provider") == 17.0


class TestResolvePipelineTimeout:
    """``_resolve_pipeline_timeout(resolved, provider)``."""

    @pytest.mark.parametrize(
        "provider,field",
        [
            ("llamacpp", "llamacpp_pipeline_timeout"),
            ("ollama", "ollama_pipeline_timeout"),
            ("openrouter", "openrouter_pipeline_timeout"),
        ],
    )
    def test_override_honoured(self, provider: str, field: str) -> None:
        """A set override wins over the shared pipeline_timeout."""
        from rag_mcp.core.metadata._common import _resolve_pipeline_timeout

        settings = EffectiveSettings(
            metadata=MetadataBlock(pipeline_timeout=180.0, **{field: 300.0})
        )
        assert _resolve_pipeline_timeout(settings, provider) == 300.0

    @pytest.mark.parametrize("provider", ["llamacpp", "ollama", "openrouter"])
    def test_unset_falls_back_to_shared(self, provider: str) -> None:
        """An unset override (None, the default) falls back to pipeline_timeout."""
        from rag_mcp.core.metadata._common import _resolve_pipeline_timeout

        settings = EffectiveSettings(metadata=MetadataBlock(pipeline_timeout=210.0))
        assert _resolve_pipeline_timeout(settings, provider) == 210.0

    def test_unknown_provider_falls_back_to_shared(self) -> None:
        """A provider name with no matching field behaves like an unset override."""
        from rag_mcp.core.metadata._common import _resolve_pipeline_timeout

        settings = EffectiveSettings(metadata=MetadataBlock(pipeline_timeout=99.0))
        assert _resolve_pipeline_timeout(settings, "made_up_provider") == 99.0


# ── Task 3.4: wiring into the direct-chat classify path ─────────────────


class _FakeAsyncClient:
    """Records the ``timeout=`` kwarg httpx.AsyncClient is constructed with.

    ``post`` always raises so no real network call is attempted; the
    backend's own retry-exhaustion path then returns the fallback dict.
    """

    captured: dict = {}

    def __init__(self, **kwargs) -> None:
        _FakeAsyncClient.captured.update(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info) -> None:
        return None

    async def post(self, *args, **kwargs):
        raise RuntimeError("stub client — no real request")


@pytest.fixture
def fake_httpx_client(monkeypatch):
    """Install ``_FakeAsyncClient`` in place of ``httpx.AsyncClient``."""
    _FakeAsyncClient.captured = {}
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    return _FakeAsyncClient


class TestClassifyTimeoutWiring:
    """Each direct-chat backend passes its resolved timeout to httpx."""

    def test_llamacpp_uses_override(self, fake_httpx_client) -> None:
        from rag_mcp.core.metadata.llamacpp import _extract_llamacpp_chat_async

        settings = EffectiveSettings(
            metadata=MetadataBlock(
                classify_timeout=30.0,
                classify_max_attempts=1,
                llamacpp_classify_timeout=45.0,
            )
        )
        asyncio.run(_extract_llamacpp_chat_async("text", "file.txt", settings))
        assert fake_httpx_client.captured["timeout"] == 45.0

    def test_llamacpp_unset_uses_shared(self, fake_httpx_client) -> None:
        from rag_mcp.core.metadata.llamacpp import _extract_llamacpp_chat_async

        settings = EffectiveSettings(
            metadata=MetadataBlock(classify_timeout=30.0, classify_max_attempts=1)
        )
        asyncio.run(_extract_llamacpp_chat_async("text", "file.txt", settings))
        assert fake_httpx_client.captured["timeout"] == 30.0

    def test_ollama_uses_override(self, fake_httpx_client) -> None:
        from rag_mcp.core.metadata.ollama import _extract_ollama_async

        settings = EffectiveSettings(
            metadata=MetadataBlock(
                classify_timeout=30.0,
                classify_max_attempts=1,
                ollama_classify_timeout=55.0,
            )
        )
        asyncio.run(_extract_ollama_async("text", "file.txt", settings))
        assert fake_httpx_client.captured["timeout"] == 55.0

    def test_ollama_unset_uses_shared(self, fake_httpx_client) -> None:
        from rag_mcp.core.metadata.ollama import _extract_ollama_async

        settings = EffectiveSettings(
            metadata=MetadataBlock(classify_timeout=30.0, classify_max_attempts=1)
        )
        asyncio.run(_extract_ollama_async("text", "file.txt", settings))
        assert fake_httpx_client.captured["timeout"] == 30.0

    def test_openrouter_uses_override(self, fake_httpx_client) -> None:
        from rag_mcp.core.metadata.openrouter import _extract_openrouter_chat_async

        settings = EffectiveSettings(
            metadata=MetadataBlock(
                classify_timeout=30.0,
                classify_max_attempts=1,
                openrouter_classify_timeout=65.0,
            )
        )
        asyncio.run(_extract_openrouter_chat_async("text", "file.txt", settings))
        assert fake_httpx_client.captured["timeout"] == 65.0

    def test_openrouter_unset_uses_shared(self, fake_httpx_client) -> None:
        from rag_mcp.core.metadata.openrouter import _extract_openrouter_chat_async

        settings = EffectiveSettings(
            metadata=MetadataBlock(classify_timeout=30.0, classify_max_attempts=1)
        )
        asyncio.run(_extract_openrouter_chat_async("text", "file.txt", settings))
        assert fake_httpx_client.captured["timeout"] == 30.0


# ── Task 3.4: wiring into the llamaindex pipeline path ───────────────────


class TestPipelineTimeoutWiring:
    """The llamaindex pipeline passes its resolved timeout to provider build().

    ``_llm_get(backend)`` is stubbed to raise ``ImportError`` immediately
    after recording the timeout it was called with — this exercises the
    resolver without needing a real LLM package or network access, and
    lands in the already-covered ImportError fallback branch.
    ``_dispatch_local_extraction`` is stubbed too so that fallback never
    reaches a real backend.
    """

    def _run(self, monkeypatch, settings: EffectiveSettings) -> dict:
        recorded: dict = {}

        def _fake_llm_get(name):
            def _build(resolved, *, timeout=None):
                recorded["backend"] = name
                recorded["timeout"] = timeout
                raise ImportError("stub — short-circuits before real construction")

            return _build

        monkeypatch.setattr(
            "rag_mcp.core.providers.llm.registry.get", _fake_llm_get
        )

        async def _fake_dispatch(text, settings, file_name):
            return {"category": "uncategorised", "keywords": [], "summary": ""}

        monkeypatch.setattr(
            "rag_mcp.core.metadata.extractor._dispatch_local_extraction",
            _fake_dispatch,
        )

        from rag_mcp.core.metadata.llamaindex import _extract_llamaindex_async

        asyncio.run(_extract_llamaindex_async("text", "file.txt", settings))
        return recorded

    def test_llamacpp_pipeline_override_reaches_build(self, monkeypatch) -> None:
        settings = EffectiveSettings(
            local_backend="llamacpp",
            metadata_llm_provider="local",
            metadata=MetadataBlock(
                pipeline_timeout=180.0, llamacpp_pipeline_timeout=300.0
            ),
        )
        recorded = self._run(monkeypatch, settings)
        assert recorded["backend"] == "llamacpp"
        assert recorded["timeout"] == 300.0

    def test_llamacpp_pipeline_unset_uses_shared(self, monkeypatch) -> None:
        settings = EffectiveSettings(
            local_backend="llamacpp",
            metadata_llm_provider="local",
            metadata=MetadataBlock(pipeline_timeout=180.0),
        )
        recorded = self._run(monkeypatch, settings)
        assert recorded["timeout"] == 180.0

    def test_ollama_pipeline_override_reaches_build(self, monkeypatch) -> None:
        settings = EffectiveSettings(
            local_backend="ollama",
            metadata_llm_provider="local",
            metadata=MetadataBlock(
                pipeline_timeout=180.0, ollama_pipeline_timeout=250.0
            ),
        )
        recorded = self._run(monkeypatch, settings)
        assert recorded["backend"] == "ollama"
        assert recorded["timeout"] == 250.0

    def test_openrouter_pipeline_unset_uses_shared(self, monkeypatch) -> None:
        """Scenario: 'Each timeout falls back to its shared default when unset'."""
        settings = EffectiveSettings(
            metadata_llm_provider="cloud",
            cloud_backend="openrouter",
            metadata=MetadataBlock(pipeline_timeout=180.0, classify_timeout=30.0),
        )
        recorded = self._run(monkeypatch, settings)
        assert recorded["backend"] == "openrouter"
        assert recorded["timeout"] == 180.0

        from rag_mcp.core.metadata._common import _resolve_classify_timeout

        assert _resolve_classify_timeout(settings, "openrouter") == 30.0

    def test_openrouter_pipeline_override_reaches_build(self, monkeypatch) -> None:
        settings = EffectiveSettings(
            metadata_llm_provider="cloud",
            cloud_backend="openrouter",
            metadata=MetadataBlock(
                pipeline_timeout=180.0, openrouter_pipeline_timeout=400.0
            ),
        )
        recorded = self._run(monkeypatch, settings)
        assert recorded["backend"] == "openrouter"
        assert recorded["timeout"] == 400.0


class TestOllamaClassifyTimeoutNameReclaimed:
    """``METADATA__OLLAMA_CLASSIFY_TIMEOUT`` was a retired v2 nested name.

    It was tripwired because the knob it named governed ALL metadata LLM
    backends despite its Ollama-specific name (see the ADR-037 "Update"
    note and ``rename-classify-settings``). This change adds a genuinely
    Ollama-specific ``ollama_classify_timeout`` override field, whose env
    var is the identical fully-qualified name — pydantic-settings' nested
    delimiter gives every field ``METADATA__<FIELD_NAME_UPPER>`` for free.
    Leaving the old tripwire entry in place would permanently block the
    new field, so it was removed from ``_RETIRED_ENV_VARS`` (config/legacy.py).
    """

    def test_no_longer_in_retired_map(self) -> None:
        from rag_mcp.config.legacy import _RETIRED_ENV_VARS

        assert "METADATA__OLLAMA_CLASSIFY_TIMEOUT" not in _RETIRED_ENV_VARS

    def test_no_longer_trips_the_startup_tripwire(self) -> None:
        from rag_mcp.config.legacy import check_legacy_env_vars

        # Must not raise.
        check_legacy_env_vars({"METADATA__OLLAMA_CLASSIFY_TIMEOUT": "45.0"})

    def test_env_var_resolves_into_the_new_field(self, monkeypatch) -> None:
        """End-to-end: the env var reaches ``Settings.metadata.ollama_classify_timeout``."""
        from rag_mcp.config import Settings

        monkeypatch.setenv("METADATA__OLLAMA_CLASSIFY_TIMEOUT", "45.0")
        settings = Settings(_env_file=None)
        assert settings.metadata.ollama_classify_timeout == 45.0

    def test_unrelated_flat_name_is_still_retired(self) -> None:
        """The pre-v2.0.0 FLAT ``OLLAMA_CLASSIFY_TIMEOUT`` is unaffected.

        It is a different, unrelated retirement (pre-v2.0.0 flat name
        moved into a nested block) and must keep tripwiring — pydantic
        cannot detect flat names on its own.
        """
        from rag_mcp.config.legacy import check_legacy_env_vars

        with pytest.raises(ValueError, match="METADATA__CLASSIFY_TIMEOUT"):
            check_legacy_env_vars({"OLLAMA_CLASSIFY_TIMEOUT": "45.0"})
