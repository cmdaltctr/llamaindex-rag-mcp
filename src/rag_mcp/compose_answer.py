"""Answer-model composition — ``compose.build_answer_llm`` implementation.

Lives in a sibling module (re-exported by ``compose.py``) because the
composition root itself sits at the 500-line ceiling and must not grow
inline (task 2.9; the ``storage_summary`` re-export set the precedent).

Resolution policy (task 3.2): ``None`` — never an exception — when
answering is disabled or the provider's optional dependency is missing,
so a retrieval-only deployment stays usable.  An unknown provider name
raises ``ValueError`` (validated fail-fast at startup by
``compose._resolve_active_strategies``, task 3.4).
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
