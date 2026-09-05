"""Engine construction — ``compose.build_engine`` implementation.

Lives in a sibling module (re-exported by ``compose.py``) because the
composition root itself sits at the 500-line ceiling and must not grow
inline (following the ``compose_answer.py`` precedent).

``build_engine()`` is the single construction path: it resolves
``Settings`` from the environment (the sole ``get_settings()`` caller
outside sanctioned siblings), constructs the embedder, store, reranker
and profile resolver, derives ``EffectiveSettings``, and returns an
``Engine`` owning those dependencies. It installs NO process-global
state — ``ensure_runtime_setup()`` is the installer over this builder.
"""

from __future__ import annotations

from typing import Any


def build_engine(settings: Any = None) -> Any:
    """Construct an :class:`Engine` from resolved settings.

    The single production construction path. Resolves ``Settings`` from
    the environment (the sole ``get_settings()`` caller), constructs the
    embedder, store, reranker and profile resolver, derives
    ``EffectiveSettings``, and returns an :class:`Engine` owning those
    dependencies. No process-global state is installed.

    Args:
        settings: Resolved settings (defaults to ``get_settings()``).

    Returns:
        An :class:`omrg.Engine` owning its composed dependencies.

    Raises:
        ValueError: Invalid provider, store or strategy name.
        ImportError: Missing optional dependency for a configured provider.
    """
    # Lazy imports so test patches on ``omrg.compose.*`` propagate:
    # module-level imports would capture the original reference and
    # ``patch("omrg.compose.build_embed_model")`` would be a no-op.
    from .compose import (
        build_embed_model,
        build_profile_resolver,
        build_reranker,
        build_vector_store,
        settings_to_effective,
    )
    from .config import get_settings

    if settings is None:
        settings = get_settings()

    embed_model = build_embed_model(settings)
    store = build_vector_store(settings)
    effective = settings_to_effective(settings)

    # Reranker construction is best-effort: a missing optional dependency
    # (ONNX Runtime) degrades to None, and search() falls back to building
    # a fresh instance. The engine owns the reference when construction
    # succeeds so two engines do not share a reranker instance.
    try:
        reranker = build_reranker(settings)
    except Exception:
        reranker = None

    from .engine import Engine

    return Engine(
        effective,
        store=store,
        embed_model=embed_model,
        reranker=reranker,
        profile_resolver_factory=lambda: build_profile_resolver(settings),
        answer_llm_factory=lambda: _build_answer_llm_safe(settings),
        verify_llm_factory=lambda block: _build_verify_llm_safe(settings, block),
    )


def configured_vector_store() -> str:
    """Return the configured vector-store adapter name.

    Composition-root surface for transports that need the adapter name
    without calling ``get_settings()`` directly (the settings-resolution
    boundary forbids ``get_settings()`` outside ``compose`` siblings).
    """
    from .config import get_settings

    return get_settings().vector_store


def _build_answer_llm_safe(settings: Any) -> Any:
    """Build the answer LLM, returning None when unavailable."""
    from .compose_answer import build_answer_llm

    try:
        return build_answer_llm(settings)
    except Exception:
        return None


def _build_verify_llm_safe(settings: Any, answer_block: Any) -> Any:
    """Build the verify LLM, returning None when unavailable."""
    from .compose_answer import build_verify_llm

    try:
        return build_verify_llm(settings, answer_block=answer_block)
    except Exception:
        return None
