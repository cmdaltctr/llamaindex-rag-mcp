"""Saved provider values applied over resolved settings (design D2, D3, D4, D6).

Pure functions and one value object. ``compose.py`` re-exports the public
names because it sits near the 500-line ceiling. The web workspace saves a
provider address, a key or the Chat model; this module lays those saved
values over the ``Settings`` that the environment and ``.env`` resolved.

A value from the environment or ``.env`` always wins and locks its field. A
value from ``omrg.jsonc`` does not lock (ADR-087). The Ollama address also
locks while the embeddings role uses Ollama, because the running embedder
keeps the address it was built with.

This module also resolves ``keychain://`` key references. ``config/`` returns
them unresolved so it stays a leaf (D6).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from .config import _resolve_effective_embed_provider
from .config.provider_sources import PROVIDER_FIELDS, coerce_field

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


#: The Chat choice locks as one unit (design D2).
_CHAT_FIELDS = ("answer.provider", "answer.model")


def locked_fields(
    settings: Settings, explicit: frozenset[str], *, profiles_ollama: bool = False
) -> dict[str, str]:
    """Return the locked editable fields and why each is locked.

    Args:
        settings: Settings as the environment and ``.env`` resolved them.
        explicit: Fields that the environment or ``.env`` set. The Chat
            provider and model lock together when either is set.
        profiles_ollama: Whether any profile selects Ollama embeddings
            (see ``uses_ollama_embeddings``).

    Returns:
        Field path to reason: ``environment`` (the process environment or
        ``.env`` set it) or ``embeddings``. Where the value came from
        (``env`` or ``dotenv``) is in ``settings.setting_sources``. A value
        from ``omrg.jsonc`` is not a reason.
    """
    if any(path in explicit for path in _CHAT_FIELDS):
        explicit = explicit | frozenset(_CHAT_FIELDS)
    locked = {path: "environment" for path in PROVIDER_FIELDS if path in explicit}
    uses_ollama = profiles_ollama or _resolve_effective_embed_provider(settings) == "ollama"
    if "ollama_base_url" not in locked and uses_ollama:
        locked["ollama_base_url"] = "embeddings"
    return locked


def apply_provider_values(
    settings: Settings,
    values: ProviderValues,
    explicit: frozenset[str] | None = None,
    *,
    profiles_ollama: bool = False,
) -> Settings:
    """Return a copy of *settings* with each unlocked saved value in place.

    Args:
        settings: Settings as the environment and ``.env`` resolved them.
        values: Saved values.
        explicit: Fields that the environment or ``.env`` set. ``None``
            reads ``settings.provider_explicit``.
        profiles_ollama: Whether any profile selects Ollama embeddings.

    Returns:
        A new ``Settings``. The input is not changed.
    """
    locked = locked_fields(
        settings,
        settings.provider_explicit if explicit is None else explicit,
        profiles_ollama=profiles_ollama,
    )
    top: dict[str, str | int] = {}
    answer: dict[str, str] = {}
    for path in PROVIDER_FIELDS:
        value = (values.values.get(path) or "").strip()
        if not value or path in locked:
            continue
        if path.startswith("answer."):
            answer[path.removeprefix("answer.")] = value
        elif (typed := coerce_field(path, value)) is not None:
            top[path] = typed
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


class KeychainReader(Protocol):
    """What :func:`resolve_keychain_references` needs from a keychain store.

    ``integrations.keychain.KeychainStore`` fits. A test passes a fake.
    """

    @property
    def available(self) -> bool:
        """Whether a usable system keychain exists."""
        ...

    def read(self, provider: str) -> Any:
        """Return the saved key as an object with ``reveal()``, or ``None`` when absent."""
        ...


def resolve_keychain_references(
    settings: Settings, *, store: KeychainReader | None = None
) -> tuple[Settings, dict[str, str]]:
    """Return *settings* with each ``keychain://`` reference replaced by its key.

    ``config/`` leaves the reference unresolved (``Settings.keychain_refs``) so
    it stays a leaf (D6). The web server, the CLI and the stdio server call
    this one function. ``integrations.keychain`` (and so ``keyring``) loads
    only when a reference exists, so a run with none pays no import cost and
    sees no keychain prompt.

    Args:
        settings: Settings as ``config/`` resolved them.
        store: The keychain to read. ``None`` builds a ``KeychainStore``.

    Returns:
        ``(settings, problems)``. A resolved field takes the source word
        ``keychain`` in ``setting_sources``. *problems* maps a provider name to
        ``keychain-missing`` (no entry) or ``keychain-unreadable`` (no usable
        keychain, or the call failed); that provider has no key. A value from
        the environment or ``.env`` never reaches this function: ``config/``
        drops the reference when one of them sets the field.
    """
    if not settings.keychain_refs:
        return settings, {}
    from .integrations.keychain import (
        STATE_MISSING,
        STATE_UNREADABLE,
        KeychainStore,
        KeychainUnavailableError,
    )

    keychain = store if store is not None else KeychainStore()
    keys: dict[str, str] = {}
    problems: dict[str, str] = {}
    sources = dict(settings.setting_sources)
    available = keychain.available
    for name, provider in settings.keychain_refs.items():
        if not available:
            problems[provider] = STATE_UNREADABLE
            continue
        try:
            secret = keychain.read(provider)
        except KeychainUnavailableError:
            problems[provider] = STATE_UNREADABLE
            continue
        if secret is None:
            problems[provider] = STATE_MISSING
        else:
            keys[name] = secret.reveal()
            sources[name] = "keychain"
    return settings.model_copy(update={**keys, "setting_sources": sources}), problems
