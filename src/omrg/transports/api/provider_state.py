"""LLM provider values of one web launch (ADR-087, design D3, D6, D7).

:class:`ProviderState` reads the provider addresses, the Chat choice and the
keys from ``omrg.jsonc`` (and the keychain behind a ``keychain://`` reference)
into a :class:`~omrg.compose_providers.ProviderValues`, hands them to the
Engine factory as its ``provider_source`` and applies each save in this order:
keychain (keys only), the file, runtime values, ``engine.use_provider_settings``.
When the Engine refuses, the file keys (and a changed key) go back and the
previous values return. A hand edit of the file applies through :meth:`reload`.

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
from typing import Any
from urllib.parse import urlsplit

from ...compose_providers import (
    ProviderValues,
    current_provider_values,
    provider_effective_settings,
)
from ...config.rules import SECRET_FIELDS
from ...config.settings_file import ABSENT, SettingsFile
from ...config.settings_file_write import SettingsFileError, WriteResult
from ...config.user_config import KEYCHAIN_PREFIX
from ...core.providers.llm import registry
from ...core.providers.llm.connection import ConnectionDescriptor, ConnectionField
from ...integrations.keychain import KeychainUnavailableError
from .settings_store import SettingsFileStore, Stamp

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


def int_rule(spec: ConnectionField) -> str:
    """Return the rule text of a whole-number field. It names the range, never a value."""
    return f"The value must be a whole number from {spec.minimum} to {spec.maximum}."


def validate_int(spec: ConnectionField, value: object) -> tuple[str | None, str | None]:
    """Check a whole-number *value* against the range of *spec*.

    Returns:
        ``(text, None)`` when the value is a whole number in range, else
        ``(None, rule)``. A boolean, a fraction or other text is refused.
    """
    number: int | None = None
    if isinstance(value, int) and not isinstance(value, bool):
        number = value
    elif isinstance(value, str) and value.strip().isascii() and value.strip().isdigit():
        number = int(value.strip())
    low, high = spec.minimum, spec.maximum
    if number is None or (low is not None and number < low) or (high is not None and number > high):
        return None, int_rule(spec)
    return str(number), None


def check_field(spec: ConnectionField, value: object) -> tuple[str | None, str | None]:
    """Check a value to save for an address or whole-number field.

    Returns:
        ``(text, None)`` to save *text*, ``(None, None)`` to clear the saved
        value (*value* is ``None``), or ``(None, rule)`` when the value breaks
        a rule. The rule never contains the value.
    """
    if value is None:
        return None, None
    if spec.kind == "int":
        return validate_int(spec, value)
    if not isinstance(value, str):
        return None, ADDRESS_RULE
    text = value.strip()
    rule = validate_address(text)
    return (None, rule) if rule else (text, None)


def valid_key(value: str) -> bool:
    """Return whether *value* is a key the rule allows."""
    return (
        MIN_KEY_CHARS <= len(value) <= MAX_KEY_CHARS
        and value.isprintable()
        and not any(ch.isspace() for ch in value)
    )


def secret_texts(values: ProviderValues) -> list[str]:
    """Return the key texts in *values*, for the launch's append-only secret set."""
    return [text for path, text in values.values.items() if path in SECRET_FIELDS and text]


def descriptor_of(provider: str) -> ConnectionDescriptor | None:
    """Return the connection descriptor of a registered *provider*, or ``None``."""
    return registry.describe_all().get(provider)


def field_of(descriptor: ConnectionDescriptor, field_id: str) -> ConnectionField | None:
    """Return the field of *descriptor* with id *field_id*, or ``None``."""
    return next((spec for spec in descriptor.fields if spec.id == field_id), None)


def overlay(values: ProviderValues, typed: Mapping[str, str]) -> ProviderValues:
    """Return *values* with the typed ``Settings`` fields laid over them (nothing saved)."""
    return replace(values, values={**values.values, **typed}, unset=values.unset - set(typed))


class ProviderState:
    """Provider values read from ``omrg.jsonc``, the keychain and the secret set.

    The file is the store (ADR-087). ``load`` reads it, ``reload`` follows a
    change made behind the server's back (a hand edit), and each save writes
    the file first and then reloads, so the values in force always come from
    the file.

    Args:
        store: The ``omrg.jsonc`` store.
        keychain: A :class:`~omrg.integrations.keychain.KeychainStore` or a
            stand-in with the same methods.
        secrets: The launch's append-only secret set.
    """

    def __init__(self, store: SettingsFileStore, keychain: Any, secrets: Any) -> None:
        """Create the state with no values loaded; call :meth:`load`."""
        self.store = store
        self.keychain = keychain
        self.secrets = secrets
        self.values = ProviderValues()
        #: Revision (content hash) of the file the values were read from.
        self.revision = ABSENT
        #: Stamp of the file at that read (D7).
        self.stamp: Stamp | None = None
        #: Serialises saves so two requests never interleave their writes.
        self.lock = asyncio.Lock()

    def source(self) -> ProviderValues:
        """Return the current values. The Engine factories call this at build time."""
        return self.values

    def load(self) -> ProviderValues:
        """Read the file and the keychain keys; add each key to the secret set."""
        self._adopt(self.store.stamp(), self.store.read())
        return self.values

    def _adopt(self, stamp: Stamp | None, file: SettingsFile) -> bool:
        """Take *file* as the current state. Return whether the provider values changed."""
        try:
            values = current_provider_values(file, self.keychain)
        except ValueError:  # the settings cannot be resolved; the Engine build reports why
            logger.warning("The settings cannot be resolved; no values from omrg.jsonc apply.")
            values = ProviderValues()
        for key in secret_texts(values):
            self.secrets.add(key)
        changed = values != self.values
        self.values, self.revision, self.stamp = values, file.revision, stamp
        return changed

    def file_changed(self) -> bool:
        """Return whether the file stamp differs from the last read (D7)."""
        return self.store.stamp() != self.stamp

    def reload(self, engine: Any) -> SettingsFile:
        """Re-read the file and give changed values to the Engine. A refusal keeps the old values.

        Returns:
            The file that was read, for the settings that are not provider values.
        """
        stamp, file = self.store.stamp(), self.store.read()
        previous = (self.values, self.revision, self.stamp)
        if self._adopt(stamp, file):
            try:
                engine.use_provider_settings(provider_effective_settings(self.source))
            except (ValueError, RuntimeError):
                self.values = previous[0]
                logger.info("The engine refused values from omrg.jsonc; they apply at restart.")
        return file

    # ── Saves ────────────────────────────────────────────────────────────

    def save_fields(
        self, engine: Any, changes: Mapping[str, Any], revision: str | None
    ) -> WriteResult:
        """Write *changes* to ``omrg.jsonc`` and apply them. A value of ``None`` removes its key.

        Raises:
            SettingsFileError: The write was refused (rule, conflict or disk).
            EngineRefused: The Engine refused; the file is put back.
        """
        before = self.store.raw(list(changes))
        result = self.store.write(changes, revision)
        stamp, file = self.store.stamp(), self.store.read()
        previous = self.values
        self._adopt(stamp, file)
        if self.values != previous:
            try:
                engine.use_provider_settings(provider_effective_settings(self.source))
            except (ValueError, RuntimeError):
                self._put_file_back(before, result)
                self.values = previous
                logger.info("The engine refused new provider values; the save was rolled back.")
                raise EngineRefused from None
        return result

    def _put_file_back(self, before: Mapping[str, Any], result: WriteResult) -> None:
        """Best effort: return the saved keys to their earlier raw values."""
        try:
            self.store.write(before, result.revision)
            self._adopt(self.store.stamp(), self.store.read())
        except SettingsFileError:
            logger.warning("omrg.jsonc could not be restored after the engine refused a change.")

    def save_chat(
        self, engine: Any, choice: tuple[str, str] | None, revision: str | None
    ) -> WriteResult:
        """Save or clear the Chat provider and model and apply them.

        Raises:
            SettingsFileError: The write was refused.
            EngineRefused: The Engine refused; the file is put back.
        """
        provider, model = choice if choice is not None else (None, None)
        return self.save_fields(
            engine, {"answer.provider": provider, "answer.model": model}, revision
        )

    def save_judge(
        self, engine: Any, choice: tuple[str, str] | None, revision: str | None
    ) -> WriteResult:
        """Save or clear the claim check judge provider and model and apply them.

        Raises:
            SettingsFileError: The write was refused.
            EngineRefused: The Engine refused; the file is put back.
        """
        provider, model = choice if choice is not None else (None, None)
        return self.save_fields(
            engine, {"answer.verify_provider": provider, "answer.verify_model": model}, revision
        )

    def save_key(
        self, engine: Any, provider: str, field: str, key: str, revision: str | None
    ) -> WriteResult:
        """Save *key* to the keychain and write ``keychain://<provider>`` to the file.

        The caller adds *key* to the secret set first. The revision is checked
        before the keychain is touched.

        Raises:
            SettingsFileError: The write was refused. The keychain keeps its old entry.
            KeychainUnavailableError: The keychain call failed; nothing is written.
            EngineRefused: The Engine refused; the file and the key are put back.
        """
        self.store.check_revision(revision)
        previous = self.keychain.read(provider)
        self.keychain.save(provider, key)
        try:
            return self.save_fields(engine, {field: f"{KEYCHAIN_PREFIX}{provider}"}, revision)
        except BaseException:
            self._put_back(provider, previous)
            raise

    def delete_key(
        self, engine: Any, provider: str, field: str, revision: str | None
    ) -> WriteResult:
        """Remove the keychain entry and the ``keychain://`` reference. Other references stay.

        Raises:
            SettingsFileError: The write was refused. The keychain keeps its entry.
            KeychainUnavailableError: The keychain call failed; nothing changed.
            EngineRefused: The Engine refused; the file and the key are put back.
        """
        self.store.check_revision(revision)
        reference = self.store.raw([field])[field]
        previous = self.keychain.read(provider)
        self.keychain.delete(provider)
        ours = isinstance(reference, str) and reference.startswith(KEYCHAIN_PREFIX)
        try:
            return self.save_fields(engine, {field: None} if ours else {}, revision)
        except BaseException:
            self._put_back(provider, previous)
            raise

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
    """Read the provider values and keychain keys after the database is prepared.

    Keys join the launch's secret set so logs and answer errors never show
    them. Returns ``None`` when the app has no settings store.
    """
    if mcp_http is None:
        return None
    state = ProviderState(mcp_http.store, app.state.keychain, app.state.secrets)
    state.load()
    return state
