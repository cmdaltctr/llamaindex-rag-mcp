"""Saved LLM provider values of one web launch (design D3, D6, D7).

:class:`ProviderState` reads the saved addresses, the Chat choice and the
keychain keys into a :class:`~omrg.compose_providers.ProviderValues`, hands
them to the Engine factory as its ``provider_source`` and applies each save
in the order of design D6: keychain (keys only), database, runtime values,
``engine.use_provider_settings``. When the Engine refuses, the database row
(and a changed key) go back and the previous values return.

The module also holds the address and key rules, which name the rule and
never repeat the value.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from ...compose_providers import ProviderValues, provider_effective_settings
from ...core.providers.llm import registry
from ...core.providers.llm.connection import ConnectionDescriptor, ConnectionField
from ...integrations.keychain import KeychainUnavailableError
from ...integrations.workspace_sqlite.settings import WorkspaceSettings, provider_key

logger = logging.getLogger(__name__)

#: Longest provider address.
MAX_ADDRESS_CHARS = 2048
#: Saved key length bounds.
MIN_KEY_CHARS = 8
MAX_KEY_CHARS = 512
KEY_RULE = "The key must be 8 to 512 printable characters with no spaces."
ADDRESS_RULE = (
    "The address must be an absolute http or https URL with a host, at most 2,048 "
    "characters, and no user name, password, query or fragment."
)
_CONTROL = re.compile(r"[\x00-\x20\x7f]")


class EngineRefused(RuntimeError):
    """The Engine refused the new provider values; the save was rolled back."""


def validate_address(value: str) -> str | None:
    """Return the rule a provider address breaks, or ``None`` when it is valid.

    The result never contains *value*.
    """
    if not value or len(value) > MAX_ADDRESS_CHARS or _CONTROL.search(value):
        return ADDRESS_RULE
    if "?" in value or "#" in value:
        return ADDRESS_RULE
    try:
        parts = urlsplit(value)
        parts.port  # noqa: B018 - raises ValueError on a bad port
    except ValueError:
        return ADDRESS_RULE
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return ADDRESS_RULE
    if parts.username is not None or parts.password is not None:
        return ADDRESS_RULE
    return None


def valid_key(value: str) -> bool:
    """Return whether *value* is a key the rule allows."""
    return (
        MIN_KEY_CHARS <= len(value) <= MAX_KEY_CHARS
        and value.isprintable()
        and not any(ch.isspace() for ch in value)
    )


def descriptor_of(provider: str) -> ConnectionDescriptor | None:
    """Return the connection descriptor of a registered *provider*, or ``None``."""
    return registry.describe_all().get(provider)


def field_of(descriptor: ConnectionDescriptor, field_id: str) -> ConnectionField | None:
    """Return the field of *descriptor* with id *field_id*, or ``None``."""
    return next((spec for spec in descriptor.fields if spec.id == field_id), None)


def overlay(values: ProviderValues, typed: Mapping[str, str]) -> ProviderValues:
    """Return *values* with the typed ``Settings`` fields laid over them (nothing saved)."""
    return replace(values, values={**values.values, **typed})


class ProviderState:
    """Saved provider values, the stores behind them and the secret set.

    Args:
        settings: Workspace settings store (the database is already prepared).
        keychain: A :class:`~omrg.integrations.keychain.KeychainStore` or a
            stand-in with the same methods.
        secrets: The launch's append-only secret set.
    """

    def __init__(self, settings: WorkspaceSettings, keychain: Any, secrets: Any) -> None:
        """Create the state with no values loaded; call :meth:`load`."""
        self.settings = settings
        self.keychain = keychain
        self.secrets = secrets
        self.values = ProviderValues()
        #: Serialises saves so two requests never interleave their writes.
        self.lock = asyncio.Lock()

    def source(self) -> ProviderValues:
        """Return the current values. The Engine factories call this at build time."""
        return self.values

    def load(self) -> ProviderValues:
        """Read the keychain keys and the database rows; add each key to the secret set."""
        providers = list(registry.describe_all())
        for secret in self.keychain.load(providers).values():
            self.secrets.add(secret.reveal())
        self.values = self.build()
        return self.values

    def build(self) -> ProviderValues:
        """Build values from the database rows and the keys now in memory."""
        values: dict[str, str] = {}
        saved_at: dict[str, str] = {}
        problems: dict[str, str] = {}
        for provider, descriptor in registry.describe_all().items():
            self._provider_values(provider, descriptor, values)
            stamp = self.settings.get_key_saved_at(provider)
            if stamp is not None:
                saved_at[provider] = stamp
                if self.keychain.get(provider) is None:
                    problems[provider] = self._problem(provider)
        chat_provider = self.settings.get_chat_provider()
        chat_model = self.settings.get_chat_model()
        if chat_provider:
            values["answer.provider"] = chat_provider
        if chat_model:
            values["answer.model"] = chat_model
        available = bool(self.keychain.available)
        return ProviderValues(
            values=values,
            key_saved_at=saved_at,
            key_problems=problems,
            keychain_available=available,
            keychain_reason=None if available else "No system keychain is available.",
        )

    def _provider_values(
        self, provider: str, descriptor: ConnectionDescriptor, values: dict[str, str]
    ) -> None:
        for spec in descriptor.fields:
            if spec.kind == "secret":
                secret = self.keychain.get(provider)
                if secret is not None:
                    values[spec.settings_field] = secret.reveal()
                continue
            saved = self.settings.get_valid(provider_key(provider, spec.id))
            if saved:
                values[spec.settings_field] = saved

    def _problem(self, provider: str) -> str:
        """Return ``keychain-missing`` or ``keychain-unreadable`` for a saved key not loaded."""
        return str(self.keychain.state(provider, True))

    # ── Saves (design D6 order) ──────────────────────────────────────────

    def _commit(self, engine: Any, restore: Callable[[], None]) -> None:
        """Rebuild the runtime values and give them to the Engine, or roll back."""
        previous = self.values
        self.values = self.build()
        try:
            engine.use_provider_settings(provider_effective_settings(self.source))
        except (ValueError, RuntimeError):
            restore()
            self.values = previous
            logger.info("The engine refused new provider values; the save was rolled back.")
            raise EngineRefused from None

    def save_fields(self, engine: Any, provider: str, updates: Mapping[str, str | None]) -> None:
        """Save or clear addresses (field id to value or ``None``).

        Raises:
            EngineRefused: The Engine refused; the rows are restored.
        """
        keys = {fid: provider_key(provider, fid) for fid in updates}
        old = {fid: self.settings.get(key) for fid, key in keys.items()}
        for fid, value in updates.items():
            self.settings.set(keys[fid], value)

        def restore() -> None:
            for fid, value in old.items():
                self.settings.set(keys[fid], value)

        self._commit(engine, restore)

    def save_chat(
        self, engine: Any, choice: tuple[str, str] | None, previous: tuple[Any, Any]
    ) -> None:
        """Save or clear the Chat provider and model and apply them with every saved value.

        Args:
            engine: The running Engine.
            choice: ``(provider, model)``, or ``None`` to clear the choice.
            previous: The ``(provider, model)`` rows to restore when the Engine refuses.

        Raises:
            EngineRefused: The Engine refused; the rows are restored.
        """
        self.settings.set_chat_choice(*(choice or (None, None)))
        self._commit(engine, lambda: self.settings.set_chat_choice(*previous))

    def save_key(self, engine: Any, provider: str, key: str) -> None:
        """Save *key* to the keychain, record the save time and apply it.

        The caller adds *key* to the secret set first.

        Raises:
            KeychainUnavailableError: The keychain call failed; nothing is written.
            EngineRefused: The Engine refused; the row and the key are restored.
        """
        previous = self.keychain.get(provider)
        old_stamp = self.settings.get_key_saved_at(provider)
        self.keychain.save(provider, key)
        self.settings.set_key_saved_at(provider, datetime.now(UTC).isoformat(timespec="seconds"))

        def restore() -> None:
            self.settings.set_key_saved_at(provider, old_stamp)
            self._put_back(provider, previous)

        self._commit(engine, restore)

    def delete_key(self, engine: Any, provider: str) -> None:
        """Remove the key from the keychain and clear the save time.

        Raises:
            KeychainUnavailableError: The keychain call failed; nothing changed.
            EngineRefused: The Engine refused; the row and the key are restored.
        """
        previous = self.keychain.get(provider)
        old_stamp = self.settings.get_key_saved_at(provider)
        self.keychain.delete(provider)
        self.settings.set_key_saved_at(provider, None)

        def restore() -> None:
            self.settings.set_key_saved_at(provider, old_stamp)
            self._put_back(provider, previous)

        self._commit(engine, restore)

    def _put_back(self, provider: str, previous: Any) -> None:
        """Best effort: return the keychain entry of *provider* to *previous*."""
        try:
            if previous is None:
                self.keychain.delete(provider)
            else:
                self.keychain.save(provider, previous.reveal())
        except KeychainUnavailableError:
            logger.warning("The keychain entry for %s could not be restored.", provider)


def typed_settings(descriptor: ConnectionDescriptor, typed: Mapping[str, str]) -> dict[str, str]:
    """Map typed field ids to ``Settings`` field paths; blank values are dropped."""
    out: dict[str, str] = {}
    for fid, value in typed.items():
        spec = field_of(descriptor, fid)
        if spec is not None and value.strip():
            out[spec.settings_field] = value.strip()
    return out


def build_engine(engine_factory: Callable[..., Any], provider_source: Any) -> Any:
    """Call *engine_factory*, passing ``provider_source`` only when it names that parameter.

    Test fakes take no argument and keep working.
    """
    try:
        accepts = "provider_source" in inspect.signature(engine_factory).parameters
    except (TypeError, ValueError):
        accepts = False
    return engine_factory(provider_source=provider_source) if accepts else engine_factory()


def load_providers(app: Any, mcp_http: Any) -> ProviderState | None:
    """Read the saved provider values and keychain keys after the database is prepared.

    Keys join the launch's secret set so logs and answer errors never show
    them. Returns ``None`` when the app has no workspace settings store.
    """
    if mcp_http is None:
        return None
    state = ProviderState(mcp_http.settings, app.state.keychain, app.state.secrets)
    state.load()
    return state
