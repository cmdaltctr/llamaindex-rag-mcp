"""System keychain adapter for provider API keys (design D1, D7).

``keyring`` is an optional dependency of the ``web`` extra. It is imported
inside functions only, so the base install and the stdio server never load
it (ADR-024). Each keychain call runs in a worker thread with a time limit,
because a call can block, or wait for a system prompt on macOS.

The keychain counts as unavailable when the backend is the fail or null
keyring, a chainer with no usable backend, a backend from ``keyrings.alt``
(plaintext and file backends), or a backend with priority below 1. There is
no fallback to a plaintext store: a save with no keychain raises and writes
nothing.

One service name, :data:`SERVICE`, with the provider name as the user name.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable
from typing import Any, TypeVar

#: Keychain service name. The user name is the provider name.
SERVICE = "omrg"
#: Seconds a keychain call may run before it counts as failed.
DEFAULT_TIMEOUT = 5.0

#: Field states a key can show (design D1).
STATE_OK = "ok"
STATE_UNSET = "unset"
STATE_MISSING = "keychain-missing"
STATE_UNREADABLE = "keychain-unreadable"

_T = TypeVar("_T")

#: Set once the keyring backend was chosen with the ``recommended`` limit.
_BACKEND_READY = False


class KeychainUnavailableError(RuntimeError):
    """No usable system keychain, or a keychain call failed or timed out."""


class Secret:
    """A key held in memory. Its text forms never show the value."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        """Hold *value*."""
        self._value = value

    def reveal(self) -> str:
        """Return the key. Call only where the key leaves memory for its provider."""
        return self._value

    def __repr__(self) -> str:
        """Hide the key."""
        return "Secret(***)"

    __str__ = __repr__

    def __format__(self, spec: str) -> str:
        """Hide the key in every format string."""
        return "***"

    def __bool__(self) -> bool:
        """Return whether a key is held."""
        return bool(self._value)

    def __eq__(self, other: object) -> bool:
        """Compare two secrets by value."""
        return isinstance(other, Secret) and other._value == self._value

    __hash__ = None  # type: ignore[assignment]


def is_usable_backend(backend: Any) -> bool:
    """Return whether *backend* is a real, encrypted keychain backend."""
    from keyring.backends import fail, null
    from keyring.backends.chainer import ChainerBackend

    if type(backend).__module__.startswith("keyrings.alt"):
        return False
    if isinstance(backend, fail.Keyring | null.Keyring):
        return False
    if isinstance(backend, ChainerBackend):
        try:
            members = list(backend.backends)
        except Exception:
            return False
        return bool(members) and all(is_usable_backend(member) for member in members)
    try:
        return float(backend.priority) >= 1
    except Exception:
        return False


def _run_with_limit(call: Callable[[], _T], timeout: float) -> _T:
    """Run *call* in a daemon worker thread and wait at most *timeout* seconds.

    Raises:
        KeychainUnavailableError: The call raised, or did not finish in time.
    """
    box: dict[str, Any] = {}

    def work() -> None:
        try:
            box["value"] = call()
        except BaseException as exc:
            box["error"] = type(exc).__name__

    thread = threading.Thread(target=work, name="omrg-keychain", daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise KeychainUnavailableError("The system keychain did not answer in time.")
    if "error" in box:
        # Only the error class is kept: a message could echo the key.
        raise KeychainUnavailableError(f"The system keychain call failed ({box['error']}).")
    return box["value"]  # type: ignore[no-any-return]


def _current_backend() -> Any:
    """Choose the backend once (priority 1 or higher), then return it.

    Runs inside the worker thread: backend detection can block on a prompt.
    """
    global _BACKEND_READY
    import keyring
    import keyring.core

    if not _BACKEND_READY:
        keyring.core.init_backend(limit=keyring.core.recommended)
        _BACKEND_READY = True
    return keyring.get_keyring()


class KeychainStore:
    """Saves, reads and deletes provider keys in the system keychain.

    Keys read by :meth:`load` stay in memory as :class:`Secret` values.
    ``repr`` shows provider names only.

    Args:
        timeout: Seconds each keychain call may take.
    """

    def __init__(self, timeout: float = DEFAULT_TIMEOUT) -> None:
        """Create a store with no keys loaded."""
        self.timeout = timeout
        self._keys: dict[str, Secret] = {}

    def __repr__(self) -> str:
        """Name the loaded providers, never their keys."""
        return f"KeychainStore(providers={sorted(self._keys)})"

    @property
    def available(self) -> bool:
        """Whether a usable system keychain exists."""
        try:
            return _run_with_limit(lambda: is_usable_backend(_current_backend()), self.timeout)
        except Exception:
            return False

    def _require(self) -> None:
        if not self.available:
            raise KeychainUnavailableError("No system keychain is available.")

    def save(self, provider: str, key: str) -> None:
        """Save *key* for *provider*.

        Raises:
            KeychainUnavailableError: No usable keychain, or the call failed.
                Nothing is written in that case.
        """
        self._require()
        import keyring

        _run_with_limit(lambda: keyring.set_password(SERVICE, provider, key), self.timeout)
        self._keys[provider] = Secret(key)

    def read(self, provider: str) -> Secret | None:
        """Return the saved key for *provider*, or ``None`` when absent or no keychain.

        Raises:
            KeychainUnavailableError: The call failed or timed out.
        """
        if not self.available:
            return None
        import keyring

        value = _run_with_limit(lambda: keyring.get_password(SERVICE, provider), self.timeout)
        return None if value is None else Secret(value)

    def delete(self, provider: str) -> None:
        """Delete the saved key for *provider*. A missing entry is not an error.

        Raises:
            KeychainUnavailableError: No usable keychain, or the call failed.
        """
        self._require()
        import keyring
        from keyring.errors import PasswordDeleteError

        def remove() -> None:
            try:
                keyring.delete_password(SERVICE, provider)
            except PasswordDeleteError:
                pass

        _run_with_limit(remove, self.timeout)
        self._keys.pop(provider, None)

    def load(self, providers: Iterable[str]) -> dict[str, Secret]:
        """Read the key of each provider into memory. Unreadable entries are skipped."""
        self._keys.clear()
        for provider in providers:
            try:
                secret = self.read(provider)
            except KeychainUnavailableError:
                continue
            if secret is not None:
                self._keys[provider] = secret
        return dict(self._keys)

    def get(self, provider: str) -> Secret | None:
        """Return the key :meth:`load` or :meth:`save` put in memory."""
        return self._keys.get(provider)

    def state(self, provider: str, saved: bool) -> str:
        """Return the field state of *provider*.

        Args:
            provider: Provider name.
            saved: Whether this workspace recorded a saved key
                (``provider.<name>.key_saved_at``).

        Returns:
            ``"ok"`` when the keychain holds a key, ``"keychain-missing"``
            when the flag is set and the entry is gone, ``"keychain-unreadable"``
            when the read failed or no keychain exists for a saved key, and
            ``"unset"`` when there is no key and no flag.
        """
        try:
            secret = self.read(provider)
        except KeychainUnavailableError:
            return STATE_UNREADABLE
        if secret is not None:
            return STATE_OK
        if not saved:
            return STATE_UNSET
        return STATE_MISSING if self.available else STATE_UNREADABLE
