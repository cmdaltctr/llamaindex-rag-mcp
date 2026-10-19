"""The Engine owns credential redaction (design D9 of add-mcp-http-transport)."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

from omrg.core.settings import AnswerBlock, EffectiveSettings, MetadataBlock

_KEY = "0" * 8 + "-chroma-test-key"
_TENANT = "9" * 8 + "-tenant"
_DATABASE = "8" * 8 + "-database"
_OPENROUTER = "sk-or-" + "4" * 12


def _secrets() -> Any:
    from omrg.core.vectordb.identity import RedactionSecrets

    return RedactionSecrets(
        chroma_cloud_api_key=_KEY,
        chroma_cloud_tenant=_TENANT,
        chroma_cloud_database=_DATABASE,
        provider_keys=(_OPENROUTER,),
    )


def test_redaction_secrets_remove_every_value_and_long_prefixes() -> None:
    text = f"key={_KEY} prefix={_KEY[:12]} tenant={_TENANT} db={_DATABASE} or={_OPENROUTER[:10]}"
    out = _secrets().redact(text)
    for leaked in (_KEY, _KEY[:12], _TENANT, _DATABASE, _OPENROUTER[:10]):
        assert leaked not in out


def test_empty_redaction_secrets_change_nothing() -> None:
    from omrg.core.vectordb.identity import RedactionSecrets

    assert RedactionSecrets().redact("plain text") == "plain text"


def test_engine_redact_uses_the_injected_secrets(tmp_path: Any) -> None:
    from omrg.engine import Engine

    engine = Engine(
        EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled")),
        store=MagicMock(cache_identity="i"),
        embed_model=MagicMock(),
        redaction=_secrets(),
    )
    assert _TENANT not in engine.redact(f"tenant {_TENANT}")


def test_engine_without_secrets_redacts_nothing() -> None:
    from omrg.engine import Engine

    engine = Engine(
        EffectiveSettings(metadata=MetadataBlock(extraction_mode="disabled")),
        store=MagicMock(cache_identity="i"),
        embed_model=MagicMock(),
    )
    assert engine.redact("tenant abc") == "tenant abc"


def test_verifier_error_with_chroma_tenant_is_redacted() -> None:
    from omrg.engine import Engine

    def factory(_block: Any) -> Any:
        raise RuntimeError(f"401 for tenant={_TENANT}")

    captured: dict[str, Any] = {}

    async def fake_answer(_q: str, **kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "ok"}

    engine = Engine(
        EffectiveSettings(
            metadata=MetadataBlock(extraction_mode="disabled"),
            answer=AnswerBlock(verify_claims=True),
        ),
        store=MagicMock(cache_identity="i"),
        embed_model=MagicMock(),
        verify_llm_factory=factory,
        redaction=_secrets(),
    )
    with patch("omrg.core.answer.pipeline.answer", side_effect=fake_answer):
        asyncio.run(engine.answer("q"))

    assert _TENANT not in captured["verify_unavailable_reason"]
    assert "RuntimeError" in captured["verify_unavailable_reason"]


def test_build_engine_fills_redaction_from_settings() -> None:
    from llama_index.core.embeddings import MockEmbedding

    from omrg import compose
    from omrg.config import Settings

    cloud = Settings(
        _env_file=None,
        chroma_mode="cloud",
        chroma_cloud_api_key=_KEY,
        chroma_cloud_tenant=_TENANT,
        chroma_cloud_database=_DATABASE,
        openrouter_api_key=_OPENROUTER,
        vector_store="chroma",
        embed_provider="local",
        local_backend="ollama",
        embed_model="nomic-embed-text",
    )
    with (
        patch("omrg.compose.get_settings", return_value=cloud),
        patch("omrg.compose.build_embed_model", return_value=MockEmbedding(embed_dim=384)),
        patch("omrg.compose.build_vector_store", return_value=MagicMock(cache_identity="i")),
        patch("omrg.compose.build_reranker", return_value=None),
    ):
        engine = compose.build_engine()
    try:
        out = engine.redact(f"{_KEY} {_TENANT} {_DATABASE} {_OPENROUTER}")
        for leaked in (_KEY, _TENANT, _DATABASE, _OPENROUTER):
            assert leaked not in out
    finally:
        engine.close()
