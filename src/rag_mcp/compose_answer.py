"""Answer-model composition — ``compose.build_answer_llm`` implementation.

Lives in a sibling module (re-exported by ``compose.py``) because the
composition root itself sits at the 500-line ceiling and must not grow
inline (task 2.9; the ``storage_summary`` re-export set the precedent).

Resolution policy (task 3.2): ``None`` — never an exception — when
answering is disabled or the provider's optional dependency is missing,
so a retrieval-only deployment stays usable.  An unknown provider name
raises ``ValueError`` (validated fail-fast at startup by
``compose._resolve_active_strategies``, task 3.4).

``build_verify_llm`` (ADR-059) follows the same policy for the claim-
verification judge: ``None`` when verification is disabled or the
optional dependency is missing; credential/configuration ``ImportError``
stays loud for the TRANSPORT to convert into ``verification_skipped``
(the answer itself must never fail behind an unconfigured judge).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .config import Settings


def build_answer_llm(settings: Settings | None = None) -> Any:
    """Construct the answer language model from the answer settings block.

    Resolves through the existing LLM provider registry
    (``core/providers/llm/registry.py`` — the same registry metadata
    extraction uses) with the block's model passed via the
    backwards-compatible ``answer_model`` override, so answering never
    silently reuses the metadata classification model.

    Args:
        settings: Resolved settings (defaults to the singleton).

    Returns:
        A configured LlamaIndex LLM, or ``None`` when answering is
        disabled or the provider's optional dependency is missing.

    Raises:
        ValueError: When ``answer.provider`` names no registered
            provider (fail-fast; also surfaced at startup).
        ImportError: When the provider requires credentials or other
            configuration that is absent — configuration errors are
            deliberately loud, unlike missing optional extras.
    """
    from .config import get_settings
    from .core.providers.llm import registry as llm_registry

    if settings is None:
        settings = get_settings()

    if not settings.answer.enabled:
        return None

    name = settings.answer.provider.strip()
    if name not in llm_registry.available():
        raise ValueError(
            f"ANSWER__PROVIDER={settings.answer.provider!r} is not a registered "
            f"LLM provider. Available: {', '.join(llm_registry.available())}."
        )
    try:
        build = llm_registry.get(name)
        return build(
            settings,
            timeout=settings.answer.timeout,
            answer_model=settings.answer.model,
        )
    except ModuleNotFoundError:
        # Missing optional package. The optional SDK import happens
        # lazily INSIDE the provider builder (registry resolution only
        # imports the provider module, which always ships in the base
        # install), so this signal arrives from the build call.
        # ModuleNotFoundError — raised only by the import machinery —
        # is caught; a manually raised plain ImportError (missing
        # credentials and similar configuration errors) stays loud.
        # A retrieval-only deployment remains usable; the answering
        # tools return the actionable error.
        return None


def _resolve_verify_provider_name(settings: Settings) -> str:
    """Resolve the verify-provider alias to a registry name.

    ``verify_provider`` accepts the same aliases the metadata LLM
    provider uses (ADR-059): ``cloud`` (or empty) resolves to the cloud
    backend, ``local`` to the local backend; anything else is a literal
    registry name.

    Args:
        settings: Resolved settings.

    Returns:
        The concrete LLM-registry provider name.
    """
    raw = settings.answer.verify_provider.strip()
    if raw in ("", "cloud"):
        return settings.cloud_backend
    if raw == "local":
        return settings.local_backend
    return raw


def validate_verify_provider(settings: Settings) -> None:
    """Fail fast at startup on an unknown verify-provider name (ADR-059).

    Mirrors the ANSWER__PROVIDER gate: only validated when the judge is
    actually opted in, so default deployments gain no new failure mode.
    Only the NAME is validated; :func:`build_verify_llm` stays lazy.

    Args:
        settings: Resolved settings.

    Raises:
        ValueError: When the alias-resolved provider name is not in the
            LLM registry, listing the registered names.
    """
    from .core.providers.llm import registry as llm_registry

    if not (settings.answer.enabled and settings.answer.verify_claims):
        return
    name = _resolve_verify_provider_name(settings)
    if name not in llm_registry.available():
        raise ValueError(
            f"ANSWER__VERIFY_PROVIDER={settings.answer.verify_provider!r} is not a "
            f"registered LLM provider (aliases: cloud, local). Available: "
            f"{', '.join(llm_registry.available())}."
        )


def build_verify_llm(
    settings: Settings | None = None,
    *,
    answer_block: Any | None = None,
) -> Any:
    """Construct the claim-verification judge LLM (ADR-059).

    Resolves through the same LLM provider registry as the answer
    model, with ``answer.verify_model`` (empty string → the provider's
    default model, e.g. ``openrouter_llm_model``) passed via the
    ``answer_model`` override.

    Resolution is lazy — ``core/`` and the transports may call it per
    answer without paying an import at startup (retrieval-only
    deployments stay usable).

    Args:
        settings: Resolved settings (defaults to the singleton).
        answer_block: Optional resolved :class:`AnswerBlock`
            (``EffectiveSettings.answer``) carrying the operation's
            final ``verify_*`` values — profile/env precedence already
            applied by the caller.  When given, its ``enabled`` and
            ``verify_*`` fields drive the build so a profile-enabled
            judge is honoured; backends, credentials and timeout still
            come from *settings*.

    Returns:
        A configured LlamaIndex LLM, or ``None`` when verification is
        disabled (``verify_claims`` false) or the provider's optional
        dependency is missing.

    Raises:
        ValueError: When ``verify_provider`` (after alias resolution)
            names no registered provider.  Also surfaced fail-fast at
            startup by ``compose._resolve_active_strategies``.
        ImportError: When the provider requires credentials or other
            configuration that is absent.  Deliberately loud HERE; the
            transport catches it and reports ``verification_skipped``
            naming the error so the answer never fails behind an
            unconfigured judge (spec: graceful degradation).
    """
    from .config import get_settings
    from .core.providers.llm import registry as llm_registry

    if settings is None:
        settings = get_settings()

    block = answer_block if answer_block is not None else settings.answer
    if not (getattr(block, "enabled", True) and getattr(block, "verify_claims", False)):
        return None

    raw = str(getattr(block, "verify_provider", "cloud") or "cloud").strip()
    verify_model = str(getattr(block, "verify_model", "") or "").strip()
    if raw in ("", "cloud"):
        name = settings.cloud_backend
    elif raw == "local":
        name = settings.local_backend
    else:
        name = raw
    if name not in llm_registry.available():
        raise ValueError(
            f"ANSWER__VERIFY_PROVIDER={getattr(block, 'verify_provider', '')!r} is not a "
            f"registered LLM provider (aliases: cloud, local). Available: "
            f"{', '.join(llm_registry.available())}."
        )
    try:
        build = llm_registry.get(name)
        return build(
            settings,
            timeout=settings.answer.timeout,
            answer_model=(verify_model or None),
        )
    except ModuleNotFoundError:
        # Missing optional package — same policy as build_answer_llm:
        # the judge silently does not exist, verification degrades to
        # verification_skipped, retrieval-only startup stays usable.
        return None
