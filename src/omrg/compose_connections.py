"""Provider connection summary and test targets (design D5, D13).

Pure functions over resolved ``Settings`` and the LLM provider registry.
``compose.connection_summary`` and ``compose.connection_targets`` are the
thin entries that read the settings; this module lives beside ``compose.py``
because that file sits near the 500-line ceiling.

Each registered provider gets one entry built from its ``CONNECTION``
descriptor (``core/providers/llm/connection.py``), so this module names no
provider. Roles follow the startup rules (``compose._resolve_active_strategies``
and ``compose_answer``). The key value never enters the summary: a key field
holds a flag, a source, a save time and at most the last four characters.
Only :func:`build_connection_targets` carries the key, for the server's own
test request.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

from .compose_providers import ProviderValues, locked_fields
from .config import Settings, _resolve_effective_embed_provider
from .config.user_config import config_file_reason, display_path
from .core.profiles.catalogue import uses_ollama_embeddings
from .core.providers.llm import registry
from .core.providers.llm.connection import ConnectionDescriptor, ConnectionField, ConnectionTarget

__all__ = [
    "ConnectionTarget",
    "build_connection_summary",
    "build_connection_targets",
]

#: Metadata extraction modes that pick a backend from ``metadata_llm_provider``.
_ALIAS_MODES = frozenset({"llamaindex", "local"})
#: A key shows its last four characters only at this length or longer.
_LAST4_MIN_LENGTH = 16


def __getattr__(name: str) -> Any:
    """Serve ``PROVIDERS``, the registered provider names, for older importers."""
    if name == "PROVIDERS":
        return tuple(registry.describe_all())
    raise AttributeError(name)


def _backend(settings: Settings, alias: str) -> str:
    """Resolve the ``cloud`` and ``local`` aliases; other names stay literal."""
    value = (alias or "cloud").strip()
    if value in ("", "cloud"):
        return settings.cloud_backend
    if value == "local":
        return settings.local_backend
    return value


def _metadata_provider(settings: Settings) -> str | None:
    """Return the provider metadata extraction calls, or ``None`` for no LLM call.

    Follows ``core.metadata.extractor``: ``keyword`` and ``disabled`` never
    call a model, ``ollama``, ``llamacpp`` and ``openrouter`` name their
    provider, and ``llamaindex`` and ``local`` resolve the alias.
    """
    mode = settings.metadata.extraction_mode.lower()
    if mode in registry.describe_all():
        return mode
    if mode not in _ALIAS_MODES:
        return None
    if settings.metadata_llm_provider == "cloud":
        return settings.cloud_backend
    return settings.local_backend


def _role_providers(settings: Settings) -> dict[str, str | None]:
    """Return the provider name each role uses, or ``None`` when the role is off."""
    answer = settings.answer
    return {
        "embeddings": _resolve_effective_embed_provider(settings),
        "answers": answer.provider.strip() if answer.enabled else None,
        "metadata": _metadata_provider(settings),
        "verification": (
            _backend(settings, answer.verify_provider)
            if answer.enabled and answer.verify_claims
            else None
        ),
    }


def _installed(descriptor: ConnectionDescriptor) -> bool:
    try:
        return importlib.util.find_spec(descriptor.requires_module) is not None
    except (ImportError, ValueError):
        return False


def _dotted(spec: ConnectionField) -> str:
    """Return the ``Settings`` path of a field, as ``PROVIDER_FIELDS`` spells it."""
    return spec.settings_field


_KEY_FILE_REASON = (
    "Set from the key file (read-only here). Saving a key in the keychain overrides it."
)


def _locked(
    spec: ConnectionField, locks: dict[str, str], settings: Settings
) -> tuple[bool, str | None]:
    reason = locks.get(_dotted(spec))
    if reason == "config-file":
        return True, config_file_reason(settings.user_config_dir)
    if reason == "environment":
        return (
            True,
            f"Set from the environment or .env. Remove {spec.env_var} there to edit it here.",
        )
    if reason == "embeddings":
        return True, "Embeddings use this address, so it cannot change while the server runs."
    return False, None


def _lock_source(reason: str) -> str:
    """Return the field ``source`` of a lock reason."""
    return "config-file" if reason == "config-file" else "env"


def _plain_field(
    spec: ConnectionField, settings: Settings, values: ProviderValues, locks: dict[str, str]
) -> dict[str, Any]:
    """Return the entry of an address (``url``) or whole-number (``int``) field."""
    value = getattr(settings, spec.settings_field)
    saved = (values.values.get(spec.settings_field) or "").strip()
    locked, lock_reason = _locked(spec, locks, settings)
    if locks.get(spec.settings_field) in ("environment", "config-file"):
        source = _lock_source(locks[spec.settings_field])
    elif saved and not locked:
        source = "saved"
    else:
        source = "default"
    return {
        "id": spec.id,
        "label": spec.label,
        "kind": spec.kind,
        "required": spec.required,
        "min": spec.minimum,
        "max": spec.maximum,
        "value": value,
        "source": source,
        "locked": locked,
        "lock_reason": lock_reason,
        "set": bool(value),
        "last4": None,
        "saved_at": None,
        "state": None,
    }


def _secret_field(
    spec: ConnectionField,
    provider: str,
    settings: Settings,
    values: ProviderValues,
    locks: dict[str, str],
) -> dict[str, Any]:
    key = str(getattr(settings, spec.settings_field) or "").strip()
    locked, lock_reason = _locked(spec, locks, settings)
    lock = locks.get(spec.settings_field)
    from_environment = lock in ("environment", "config-file")
    state = None if from_environment else values.key_problems.get(provider)
    saved = bool((values.values.get(spec.settings_field) or "").strip())
    if from_environment:
        source = _lock_source(str(lock))
    elif key and not saved and spec.settings_field in settings.key_file_fields:
        source, lock_reason = "key-file", _KEY_FILE_REASON
    elif key:
        source = "keychain"
    else:
        source = "none"
    if not locked and not values.keychain_available:
        locked = True
        lock_reason = (
            f"No system keychain is available. Set {spec.env_var} in the environment or .env."
        )
    return {
        "id": spec.id,
        "label": spec.label,
        "kind": "secret",
        "required": spec.required,
        "min": None,
        "max": None,
        "value": None,
        "source": source,
        "locked": locked,
        "lock_reason": lock_reason,
        "set": bool(key),
        "last4": key[-4:] if len(key) >= _LAST4_MIN_LENGTH else None,
        "saved_at": None if from_environment else values.key_saved_at.get(provider),
        "state": state,
    }


def _fields(
    provider: str,
    descriptor: ConnectionDescriptor,
    settings: Settings,
    values: ProviderValues,
    profiles_ollama: bool = False,
) -> list[dict[str, Any]]:
    locks = locked_fields(settings, settings.provider_explicit, profiles_ollama=profiles_ollama)
    return [
        _secret_field(spec, provider, settings, values, locks)
        if spec.kind == "secret"
        else _plain_field(spec, settings, values, locks)
        for spec in descriptor.fields
    ]


def build_connection_summary(
    settings: Settings,
    config_dir: Path,
    values: ProviderValues | None = None,
    catalogue: Any = None,
) -> dict[str, Any]:
    """Return the provider summary for ``GET /v1/connections``.

    Args:
        settings: Settings in use, with any saved values already applied.
        config_dir: The working directory whose ``.env`` the settings read.
        values: Saved values and keychain facts. ``None`` means none saved
            and no keychain.
        catalogue: The profile catalogue, or ``None``. The Ollama address
            locks while any profile in it selects Ollama embeddings.

    Returns:
        ``{"config_dir": str, "user_config_dir": str, "keychain": "available" | "unavailable",
        "connections": [entry, ...]}``, one entry per registered provider.
        An entry has ``provider``, ``display_name``, ``locality``,
        ``installed``, ``install_hint``, ``fields``, ``read_only`` and
        ``roles``. No key value is included.
    """
    values = values or ProviderValues()
    profiles_ollama = uses_ollama_embeddings(catalogue)
    by_role = _role_providers(settings)
    entries = []
    for provider, descriptor in registry.describe_all().items():
        installed = _installed(descriptor)
        entries.append(
            {
                "provider": provider,
                "display_name": descriptor.display_name,
                "locality": descriptor.locality,
                "installed": installed,
                "install_hint": (
                    None
                    if installed or descriptor.extra is None
                    else f"uv sync --extra {descriptor.extra}"
                ),
                "fields": _fields(provider, descriptor, settings, values, profiles_ollama),
                "read_only": [
                    {"label": row.label, "value": row.value}
                    for row in descriptor.read_only(settings)
                ],
                "roles": [role for role, name in by_role.items() if name == provider],
            }
        )
    return {
        "config_dir": str(config_dir),
        "user_config_dir": display_path(settings.user_config_dir),
        "keychain": "available" if values.keychain_available else "unavailable",
        "connections": entries,
    }


def build_connection_targets(settings: Settings) -> dict[str, ConnectionTarget]:
    """Return the connection-test request of each registered provider.

    A provider with nothing to contact (no key, blank address) has no URL,
    so its test reports ``not-configured`` and sends nothing.
    """
    return {name: d.test_targets(settings) for name, d in registry.describe_all().items()}
