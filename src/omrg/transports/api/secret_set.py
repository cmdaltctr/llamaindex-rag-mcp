"""Append-only secret set shared by log redaction and routes (design D7).

:class:`SecretSet` lives in its own module so ``security.py`` stays under the
500-line ceiling. ``omrg.transports.api.security`` re-exports it.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from threading import Lock


class SecretSet:
    """An append-only set of secret values, shared by the log filters and routes.

    A saved provider key is added before the key reaches the keychain, and a
    replaced key stays until shutdown, so an old key in a late log line is
    still removed. There is no remove method. ``repr`` hides the values.
    """

    def __init__(self, values: Iterable[str] = ()) -> None:
        """Create the set from *values*; empty values are ignored."""
        self._lock = Lock()
        self._values: list[str] = []
        for value in values:
            self.add(value)

    def add(self, value: str) -> None:
        """Add *value*. An empty or known value changes nothing."""
        with self._lock:
            if value and value not in self._values:
                self._values.append(value)

    def __iter__(self) -> Iterator[str]:
        """Iterate over a snapshot taken now."""
        with self._lock:
            return iter(tuple(self._values))

    def __len__(self) -> int:
        """Return how many secrets the set holds."""
        return len(self._values)

    def __repr__(self) -> str:
        """Show the count only."""
        return f"SecretSet(count={len(self)})"
