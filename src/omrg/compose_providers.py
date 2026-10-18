"""Saved provider values applied over resolved settings (design D2, D3, D4).

Pure functions and one value object. ``compose.py`` re-exports the public
names because it sits near the 500-line ceiling. The web workspace saves a
provider address, a key or the Chat model; this module lays those saved
values over the ``Settings`` that the environment and ``.env`` resolved.

A value from the environment or ``.env`` always wins and locks its field.
The Ollama address also locks while the embeddings role uses Ollama, because
the running embedder keeps the address it was built with.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .config import _resolve_effective_embed_provider
from .config.provider_sources import PROVIDER_FIELDS

if TYPE_CHECKING:
    from .config import Settings
    from .core.settings import EffectiveSettings


@dataclass(frozen=True)
class ProviderValues:
    """Saved provider values held in memory.

    Keys are ``Settings`` field paths (``ollama_base_url``,
    ``llamacpp_chat_url``, ``openrouter_api_key``, ``answer.provider``,
    ``answer.model``). A blank value counts as unset. ``repr`` shows the
    field names only, because a value can be an API key.

    Attributes:
        values: Saved value by field path.
        key_saved_at: ISO save time by provider name, for providers whose
            key the workspace database records.
        key_problems: Reason by provider name when the database records a
            key that cannot be used: ``keychain-missing`` or
            ``keychain-unreadable``.
        keychain_available: Whether a usable system keychain exists.
        keychain_reason: Why no keychain is available, when it is not.
    """

    values: Mapping[str, str] = field(default_factory=dict)
    key_saved_at: Mapping[str, str] = field(default_factory=dict)
    key_problems: Mapping[str, str] = field(default_factory=dict)
    keychain_available: bool = False
    keychain_reason: str | None = None

    def __repr__(self) -> str:
        return f"ProviderValues(fields={sorted(self.values)})"


def locked_fields(settings: Settings, explicit: frozenset[str]) -> dict[str, str]:
    """Return the locked editable fields and why each is locked.

    Args:
        settings: Settings as the environment and ``.env`` resolved them.
        explicit: Fields that the environment or ``.env`` set.

    Returns:
        Field path to reason: ``environment`` or ``embeddings``.
    """
    locked = {path: "environment" for path in PROVIDER_FIELDS if path in explicit}
    if "ollama_base_url" not in locked and _resolve_effective_embed_provider(settings) == "ollama":
        locked["ollama_base_url"] = "embeddings"
    return locked


def apply_provider_values(
    settings: Settings, values: ProviderValues, explicit: frozenset[str] | None = None
) -> Settings:
    """Return a copy of *settings* with each unlocked saved value in place.

    Args:
        settings: Settings as the environment and ``.env`` resolved them.
        values: Saved values.
        explicit: Fields that the environment or ``.env`` set. ``None``
            reads ``settings.provider_explicit``.

    Returns:
        A new ``Settings``. The input is not changed.
    """
    locked = locked_fields(settings, settings.provider_explicit if explicit is None else explicit)
    top: dict[str, str] = {}
    answer: dict[str, str] = {}
    for path in PROVIDER_FIELDS:
        value = (values.values.get(path) or "").strip()
        if not value or path in locked:
            continue
        if path.startswith("answer."):
            answer[path.removeprefix("answer.")] = value
        else:
            top[path] = value
    if answer:
        top["answer"] = settings.answer.model_copy(update=answer)  # type: ignore[assignment]
    return settings.model_copy(update=top)


def provider_settings(source: Callable[[], ProviderValues]) -> Settings:
    """Return the resolved ``Settings`` with the saved values from *source* applied."""
    from .compose import get_settings

    return apply_provider_values(get_settings(), source())


def provider_effective_settings(source: Callable[[], ProviderValues]) -> EffectiveSettings:
    """Return server-default ``EffectiveSettings`` with the saved values applied.

    The web runtime passes the result to ``Engine.use_provider_settings()``
    after each save.
    """
    from .compose import settings_to_effective

    return settings_to_effective(provider_settings(source))
