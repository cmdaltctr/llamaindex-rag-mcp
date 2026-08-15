"""Contract: OpenRouter embedding provider must accept arbitrary model IDs.

OpenRouter serves embedding models under provider-prefixed, non-OpenAI IDs
(``qwen/qwen3-embedding-4b``, ``openai/text-embedding-3-small``).  The
provider constructs LlamaIndex ``OpenAILikeEmbedding`` — the adapter that
forwards any ``model_name`` string unchanged — while preserving the
OpenRouter API base, API key, and ingestion batch size.

The six construction tests require ``llama-index-embeddings-openai-like``
(``uv sync --extra openrouter``); they skip on a base install and run in
the floors and coverage jobs where the extra is installed. The
missing-dependency test below stays base-install-safe on purpose.
"""

from __future__ import annotations

import sys

import pytest

from rag_mcp.compose import build_embed_model
from rag_mcp.config import Settings
from rag_mcp.core.ingestion.settings import IngestionSettings

# IDs an OpenRouter deployment actually uses: a third-party model and an
# OpenAI model behind the provider prefix. Both sit outside OpenAI's
# embedding enum, so ``OpenAIEmbedding`` rejects both at construction.
ARBITRARY_MODEL_IDS = ["qwen/qwen3-embedding-4b", "openai/text-embedding-3-small"]

# 42 matches no plausible default or hardcode, so a wiring bug cannot pass.
NON_DEFAULT_BATCH_SIZE = 42

try:  # pragma: no cover - exercised implicitly by the skip decision
    import llama_index.embeddings.openai_like  # noqa: F401
except ImportError:  # Base install without the openrouter/llamacpp extra.
    _OPENAI_LIKE_AVAILABLE = False
else:
    _OPENAI_LIKE_AVAILABLE = True

requires_openai_like = pytest.mark.skipif(
    not _OPENAI_LIKE_AVAILABLE,
    reason="llama-index-embeddings-openai-like not installed (uv sync --extra openrouter)",
)


def _cloud_settings(
    *,
    embed_model: str = "qwen/qwen3-embedding-4b",
    embed_batch_size: int = NON_DEFAULT_BATCH_SIZE,
) -> Settings:
    """Build cloud/openrouter Settings wired for the adapter contract.

    Args:
        embed_model: The OpenRouter embedding model ID to construct with.
        embed_batch_size: Batch size injected via the ingestion block.

    Returns:
        Settings selecting the openrouter cloud embedding provider.
    """
    return Settings(
        _env_file=None,
        embed_provider="cloud",
        cloud_backend="openrouter",
        openrouter_api_key="sk-red-phase",
        openrouter_embed_model=embed_model,
        embed_model="nomic-embed-text",
        ingestion=IngestionSettings(embed_batch_size=embed_batch_size),
    )


# ── Arbitrary model IDs (the core regression) ──────────────────────────────


@requires_openai_like
@pytest.mark.parametrize("model_id", ARBITRARY_MODEL_IDS)
def test_openrouter_embed_accepts_arbitrary_model_ids(model_id: str) -> None:
    """Any OpenRouter model ID must survive provider construction unchanged.

    ``OpenAIEmbedding`` validates against OpenAI's fixed enum and raises
    ``ValueError`` for provider-prefixed IDs; ``OpenAILikeEmbedding``
    forwards the string untouched.
    """
    embedding = build_embed_model(_cloud_settings(embed_model=model_id))
    assert embedding.model_name == model_id


@requires_openai_like
def test_openrouter_embed_builds_openai_like_adapter() -> None:
    """The provider must return ``OpenAILikeEmbedding``, not ``OpenAIEmbedding``.

    Asserted via the concrete class name rather than ``isinstance`` for two
    reasons: the ``llama-index-embeddings-openai-like`` package is absent
    during the red phase so it cannot be imported here, and
    ``OpenAILikeEmbedding`` subclasses ``OpenAIEmbedding`` — an isinstance
    check against the base class would pass before and after the swap and
    prove nothing.
    """
    embedding = build_embed_model(_cloud_settings())
    assert type(embedding).__name__ == "OpenAILikeEmbedding"


# ── Connection settings preserved through the swap ─────────────────────────


@requires_openai_like
def test_openrouter_embed_preserves_api_base() -> None:
    """The adapter must keep pointing at OpenRouter's API base."""
    embedding = build_embed_model(_cloud_settings())
    assert embedding.api_base == "https://openrouter.ai/api/v1"


@requires_openai_like
def test_openrouter_embed_preserves_api_key() -> None:
    """The API key from settings must reach the adapter unchanged."""
    embedding = build_embed_model(_cloud_settings())
    assert embedding.api_key == "sk-red-phase"


@requires_openai_like
def test_openrouter_embed_preserves_batch_size() -> None:
    """The ingestion batch size must be wired through, not defaulted."""
    embedding = build_embed_model(_cloud_settings(embed_batch_size=NON_DEFAULT_BATCH_SIZE))
    assert embedding.embed_batch_size == NON_DEFAULT_BATCH_SIZE


# ── Optional-dependency contract follows the new import path ───────────────


def test_openrouter_embed_missing_openai_like_dep_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unimportable ``openai_like`` module must raise ImportError naming the extra.

    The provider must import from ``llama_index.embeddings.openai_like``
    after the swap, so the missing-dependency guard has to fire on that
    import path. A plain OpenAI enum-valid model ID is used here so the
    only red/green signal is the import path, not model validation.
    """
    # Simulate the adapter package being absent by poisoning sys.modules.
    monkeypatch.setitem(sys.modules, "llama_index.embeddings.openai_like", None)
    settings = _cloud_settings(embed_model="text-embedding-3-small")
    with pytest.raises(ImportError, match="uv sync --extra openrouter"):
        build_embed_model(settings)
