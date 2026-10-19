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
them unresolved so it stays a leaf (D6). :func:`provider_values_from_file` turns
the current ``omrg.jsonc`` into :class:`ProviderValues`, so the web server
follows page saves and hand edits after launch (D7).
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from .config import Settings, _resolve_effective_embed_provider
from .config.provider_sources import PROVIDER_FIELDS, coerce_field
from .config.rules import SECRET_FIELDS, provider_of
from .config.user_config import SECRETS_DIR

if TYPE_CHECKING:
    from .config.settings_file import SettingsFile
    from .core.settings import EffectiveSettings


logger = logging.getLogger(__name__)

#: ``(launch settings, the same with keychain keys)``, kept while the launch settings object lives.
_resolved: tuple[Settings, Settings] | None = None


@dataclass(frozen=True)
class ProviderValues:
    """Provider values read from ``omrg.jsonc`` and held in memory.

    Keys are ``Settings`` field paths (``ollama_base_url``,
    ``llamacpp_chat_url``, ``openrouter_api_key``, ``answer.provider``,
    ``answer.model``). A blank value counts as unset. ``repr`` shows the
    field names only, because a value can be an API key.

    Attributes:
        values: Value by field path.
        sources: Source word by field path for a value that does not come from
            the code default: ``config-file``, ``keychain`` or ``key-file``.
        key_paths: The key file that a ``key-file`` key was read from, by field path.
        unset: Fields that the file no longer sets and whose default is blank
            (a key, the llama.cpp program or model). Applying resets them.
        key_problems: Reason by provider name when a ``keychain://`` reference
            cannot be used: ``keychain-missing`` or ``keychain-unreadable``.
        keychain_available: Whether a usable system keychain exists.
        keychain_reason: Why no keychain is available, when it is not.
    """

    values: Mapping[str, str] = field(default_factory=dict)
    sources: Mapping[str, str] = field(default_factory=dict)
    key_paths: Mapping[str, str] = field(default_factory=dict)
    unset: frozenset[str] = frozenset()
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
    top: dict[str, Any] = {}
    answer: dict[str, str] = {}
    sources = dict(settings.setting_sources)
    key_paths = dict(settings.key_file_paths)
    for path in PROVIDER_FIELDS:
        if path in locked:
            continue
        if path in values.unset:
            top[path] = ""
            sources.pop(path, None)
            key_paths.pop(path, None)
            continue
        value = (values.values.get(path) or "").strip()
        if not value:
            continue
        if path.startswith("answer."):
            answer[path.removeprefix("answer.")] = value
        elif (typed := coerce_field(path, value)) is not None:
            top[path] = typed
        else:
            continue
        if word := values.sources.get(path):
            sources[path] = word
        else:
            sources.pop(path, None)
        if path in values.key_paths:
            key_paths[path] = values.key_paths[path]
        else:
            key_paths.pop(path, None)
    if answer:
        top["answer"] = settings.answer.model_copy(update=answer)
    top["setting_sources"] = sources
    top["key_file_paths"] = key_paths
    top["config_file_fields"] = frozenset(p for p, w in sources.items() if w == "config-file")
    top["key_file_fields"] = frozenset(p for p, w in sources.items() if w == "key-file")
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


def resolve_launch_settings(base: Settings) -> Settings:
    """Return *base* with each ``keychain://`` key reference resolved (D6).

    ``compose.get_settings`` calls this, so the CLI, the stdio server and the
    web server read the keys that the Settings page saved. Without a reference
    it returns *base* and ``keyring`` is not imported. A missing or unreadable
    entry is logged once by provider name, never by key.
    """
    global _resolved
    if not isinstance(base, Settings) or not base.keychain_refs:
        return base
    if _resolved is not None and _resolved[0] is base:
        return _resolved[1]
    settings, problems = resolve_keychain_references(base)
    for provider, state in sorted(problems.items()):
        logger.warning("The %s key in omrg.jsonc cannot be used: %s.", provider, state)
    _resolved = (base, settings)
    return settings


# ── Values read from omrg.jsonc for the running web server (D7) ─────────

#: Source words of a value that came from the file layer (the file, a key file or the keychain).
FILE_SOURCES = frozenset({"config-file", "key-file", "keychain"})
_CHAT_FIELDS = ("answer.provider", "answer.model")
_NO_KEYCHAIN = "No system keychain is available."


def code_default(path: str) -> str:
    """Return the code default of the provider field *path* as text (``""`` for none)."""
    block, _, leaf = path.rpartition(".")
    if block:
        info = Settings.model_fields[block].annotation.model_fields[leaf]  # type: ignore[union-attr]
    else:
        info = Settings.model_fields[path]
    default = info.default
    return "" if default is None else str(default)


def _secret_from_file(path: str, file: SettingsFile) -> tuple[str, str, str | None] | None:
    """Return ``(key, source word, key file path)`` for a key the file or a key file holds."""
    if path in file.secrets:
        word = "key-file" if path in file.key_paths else "config-file"
        return file.secrets[path], word, file.key_paths.get(path)
    if path in file.key_file:
        found = str(file.directory / SECRETS_DIR / f"{provider_of(path)}.key")
        return file.key_file[path], "key-file", found
    return None


def _explicit(base: Settings) -> frozenset[str]:
    explicit = frozenset(getattr(base, "provider_explicit", ()))
    return explicit | frozenset(_CHAT_FIELDS) if explicit & set(_CHAT_FIELDS) else explicit


def provider_values_from_file(
    base: Settings, file: SettingsFile, keychain: KeychainReader | None
) -> ProviderValues:
    """Return the provider values that *file* sets, over the launch settings *base*.

    Args:
        base: The settings resolved at launch.
        file: What ``omrg.jsonc`` and ``secrets/`` hold now.
        keychain: The keychain to read ``keychain://`` references from, or
            ``None`` for none.

    Returns:
        The values, their sources and the keychain facts. The result holds keys,
        so its ``repr`` shows field names only.
    """
    explicit = _explicit(base)
    values: dict[str, str] = {}
    sources: dict[str, str] = {}
    key_paths: dict[str, str] = {}
    unset: set[str] = set()
    references: dict[str, str] = {}
    for path in PROVIDER_FIELDS:
        if path in explicit:
            continue
        secret = path in SECRET_FIELDS
        if secret and path in file.references:
            references[path] = file.references[path]
        elif secret and (found := _secret_from_file(path, file)) is not None:
            values[path], sources[path] = found[0], found[1]
            if found[2] is not None:
                key_paths[path] = found[2]
        elif not secret and path in file.values:
            values[path], sources[path] = str(file.values[path]), "config-file"
        elif base.setting_sources.get(path) in FILE_SOURCES:
            default = code_default(path)
            if default:
                values[path] = default
            else:
                unset.add(path)
    available = bool(keychain is not None and keychain.available)
    problems: dict[str, str] = {}
    if references and keychain is not None:
        carrier = base.model_copy(update={"keychain_refs": references, "setting_sources": {}})
        resolved, problems = resolve_keychain_references(carrier, store=keychain)
        for path in references:
            key = str(getattr(resolved, path, "") or "")
            if key:
                values[path], sources[path] = key, "keychain"
            else:
                unset.add(path)
    elif references:
        problems = {provider: "keychain-unreadable" for provider in references.values()}
        unset.update(references)
    return ProviderValues(
        values=values,
        sources=sources,
        key_paths=key_paths,
        unset=frozenset(unset),
        key_problems=problems,
        keychain_available=available,
        keychain_reason=None if available else _NO_KEYCHAIN,
    )


def secret_values(values: ProviderValues) -> list[str]:
    """Return the key texts in *values*, for the launch's append-only secret set."""
    return [values.values[path] for path in values.values if path in SECRET_FIELDS]


def current_provider_values(file: SettingsFile, keychain: KeychainReader | None) -> ProviderValues:
    """Return the provider values *file* sets over the launch settings of this process.

    The web transport calls this because it may not read the settings itself.
    """
    from .compose import get_settings

    return provider_values_from_file(get_settings(), file, keychain)
