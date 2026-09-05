"""Engine construction — ``compose.build_engine`` implementation.

Lives in a sibling module (re-exported by ``compose.py``) because the
composition root itself sits at the 500-line ceiling and must not grow
inline (following the ``compose_answer.py`` precedent).

``build_engine()`` is the single construction path: it resolves
``Settings`` from the environment (the sole ``get_settings()`` caller
outside sanctioned siblings), runs the shared startup validation,
constructs the embedder, store, reranker and profile resolver, derives
``EffectiveSettings``, and returns an ``Engine`` owning those
dependencies. It installs NO process-global state —
``ensure_runtime_setup()`` is the installer over this builder.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Settings

#: Profile Tier 2 levers whose environment overrides are captured once,
#: at composition time: a constructed engine must never observe later
#: environment changes (resolver would otherwise read live ``os.environ``
#: at operation time).
_PROFILE_ENV_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "RETRIEVAL__TOP_K",
        "RETRIEVAL__RERANK_ENABLED",
        "RETRIEVAL__HYBRID_ENABLED",
        "CHUNKING__STRATEGY_FALLBACK",
        "METADATA__TAXONOMY_MODE",
        "INGESTION__INGEST_EXTENSIONS",
        "ANSWER__VERIFY_CLAIMS",
        "ANSWER__VERIFY_MODEL",
        "ANSWER__VERIFY_PROVIDER",
    }
)


def _snapshot_profile_env() -> dict[str, str]:
    """Capture the applicable profile env overrides at composition time."""
    return {key: os.environ[key] for key in _PROFILE_ENV_OVERRIDE_KEYS if key in os.environ}


def build_engine(settings: Settings | None = None) -> Any:
    """Construct an :class:`Engine` from resolved settings.

    The single production construction path. Resolves ``Settings`` from
    the environment (the sole ``get_settings()`` caller), runs the
    shared startup validation (active strategies, norm-guard state) and
    the environment-based safeguards (legacy flat env vars, recognised
    legacy Chroma data) BEFORE constructing any dependency, constructs
    the embedder, store, reranker and profile resolver, derives
    ``EffectiveSettings``, and returns an ``Engine`` owning those
    dependencies. No process-global state is installed.

    Args:
        settings: Resolved settings (defaults to ``get_settings()``).
            Explicit settings skip the environment-only safeguards
            (legacy env-var tripwire, legacy Chroma-data protection)
            but still run the shared strategy validation.

    Returns:
        An :class:`omrg.Engine` owning its composed dependencies.

    Raises:
        ValueError: Invalid provider, store or strategy name; legacy
            flat env var present; recognised legacy Chroma data without
            an explicit backend choice.
        ImportError: Missing optional dependency for a configured provider.
    """
    # Lazy imports so test patches on ``omrg.compose.*`` propagate:
    # module-level imports would capture the original reference and
    # ``patch("omrg.compose.build_embed_model")`` would be a no-op.
    # ``get_settings`` resolves through the compose module attribute for
    # the same reason — the composition root's bound reference is the
    # single patchable settings seam (see test_compose.py, test_chroma_cloud.py).
    from .compose import (
        _log_norm_guard_state,
        _resolve_active_strategies,
        build_embed_model,
        build_profile_resolver,
        build_reranker,
        build_vector_store,
        get_settings,
        settings_to_effective,
    )
    from .config import check_legacy_env_vars

    environment_based = settings is None
    if environment_based:
        # Fail fast on pre-v2.0.0 flat env vars before resolving
        # anything, so an unmigrated .env produces a naming error rather
        # than silent defaults. Environment-based construction only:
        # explicit-settings callers resolved their own configuration.
        check_legacy_env_vars()
        settings = get_settings()
    # Disabled norm guard is an explicit operator decision: make its
    # consequence visible at construction (spec: guard configuration
    # is explicit) on both construction routes.
    _log_norm_guard_state(settings)
    if environment_based:
        # Fail closed on recognised legacy Chroma data when no explicit
        # backend was selected (task 4, design D6) — before any store
        # construction so ingestion/retrieval can never touch the
        # untouched directory.
        from .core.vectordb.legacy import evaluate_legacy_chroma_data

        evaluate_legacy_chroma_data(
            settings.chroma_persist_dir,
            settings.vector_store,
            settings.vector_store_provenance,
        )
    # Resolve the configured strategies so a bad import string fails
    # fast on BOTH construction routes, before any dependency is
    # constructed (shared validation, not installer-only).
    _resolve_active_strategies(settings)

    embed_model = build_embed_model(settings)
    store = build_vector_store(settings)
    effective = settings_to_effective(settings)
    # Snapshot the profile env overrides NOW: the resolver is built
    # lazily, but an already-constructed engine must never observe
    # later environment changes.
    profile_env = _snapshot_profile_env()

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
        profile_resolver_factory=lambda: build_profile_resolver(
            settings, store=store, env_overrides=profile_env
        ),
        answer_llm_factory=lambda: _build_answer_llm(settings),
        verify_llm_factory=lambda block: _build_verify_llm(settings, block),
    )


def configured_vector_store() -> str:
    """Return the configured vector-store adapter name.

    Composition-root surface for transports that need the adapter name
    without calling ``get_settings()`` directly (the settings-resolution
    boundary forbids ``get_settings()`` outside ``compose`` siblings).
    """
    from .config import get_settings

    return get_settings().vector_store


def _build_answer_llm(settings: Any) -> Any:
    """Build the answer LLM; the availability policy lives in compose_answer.

    ``build_answer_llm`` returns ``None`` when answering is disabled or
    the optional dependency is missing; ``ValueError`` (unknown provider)
    and ``ImportError`` (missing credentials) propagate to the first
    ``engine.answer()`` call carrying the actionable message.
    """
    from .compose_answer import build_answer_llm

    return build_answer_llm(settings)


def _build_verify_llm(settings: Any, answer_block: Any) -> Any:
    """Build the verify LLM without swallowing configuration errors.

    The ENGINE converts a construction failure into a redacted
    ``verification_skipped`` reason (ADR-059: the answer itself must
    never fail behind an unconfigured judge).
    """
    from .compose_answer import build_verify_llm

    return build_verify_llm(settings, answer_block=answer_block)
