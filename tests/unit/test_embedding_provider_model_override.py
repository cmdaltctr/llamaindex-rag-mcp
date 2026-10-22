"""Contract: each embedding provider ``build`` accepts a model override.

A profile can name its own embedding model (ADR-081). The provider builder
replaces only the model name. URL, key and batch size still come from
``Settings``. Without the keyword the builder keeps today's model.
"""

from __future__ import annotations

import pytest

from omrs.config import Settings
from omrs.core.ingestion.settings import IngestionSettings
from omrs.core.providers.embeddings import llamacpp, ollama, openrouter

try:  # pragma: no cover - exercised implicitly by the skip decision
    import llama_index.embeddings.openai_like  # noqa: F401
except ImportError:
    _OPENAI_LIKE = False
else:
    _OPENAI_LIKE = True

requires_openai_like = pytest.mark.skipif(
    not _OPENAI_LIKE,
    reason="llama-index-embeddings-openai-like not installed",
)

BATCH = 42


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        embed_model="host-ollama-model",
        ollama_base_url="http://ollama.example:11434",
        llamacpp_embed_model="host-llamacpp-model",
        llamacpp_embed_url="http://llama.example:8081/v1",
        openrouter_api_key="sk-test",
        openrouter_embed_model="host/openrouter-model",
        ingestion=IngestionSettings(embed_batch_size=BATCH),
    )


def test_ollama_build_model_override_keeps_connection_settings() -> None:
    embedder = ollama.build(_settings(), model="m2")
    assert embedder.model_name == "m2"
    assert embedder.base_url == "http://ollama.example:11434"
    assert embedder.embed_batch_size == BATCH


def test_ollama_build_without_override_keeps_host_model() -> None:
    assert ollama.build(_settings()).model_name == "host-ollama-model"


@requires_openai_like
def test_llamacpp_build_model_override_keeps_connection_settings() -> None:
    embedder = llamacpp.build(_settings(), model="m2")
    assert embedder.model_name == "m2"
    assert embedder.api_base == "http://llama.example:8081/v1"
    assert embedder.embed_batch_size == BATCH


@requires_openai_like
def test_llamacpp_build_without_override_keeps_host_model() -> None:
    assert llamacpp.build(_settings()).model_name == "host-llamacpp-model"


@requires_openai_like
def test_openrouter_build_model_override_keeps_connection_settings() -> None:
    embedder = openrouter.build(_settings(), model="vendor/m2")
    assert embedder.model_name == "vendor/m2"
    assert embedder.api_key == "sk-test"
    assert embedder.api_base == "https://openrouter.ai/api/v1"
    assert embedder.embed_batch_size == BATCH


@requires_openai_like
def test_openrouter_build_without_override_keeps_host_model() -> None:
    assert openrouter.build(_settings()).model_name == "host/openrouter-model"
