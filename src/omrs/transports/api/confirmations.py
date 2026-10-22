"""Preview-bound confirmations for destructive actions (design D8).

A preview observes the store and issues a single-use confirmation
token. The token is bound to the action, the collection, the selector,
the observed validity token and an expiry time. A confirmation is
accepted only when all of these still match; any rejection spends the
token, so the client must preview again.

The validity token comes from the store's durable data version
(``get_data_version``) when the backend offers one. Otherwise it falls
back to the process-local generation counter plus the row count, and
the preview carries :data:`PROCESS_LOCAL_WARNING`: a write by another
process after the preview can go undetected.
"""

from __future__ import annotations

import json
import secrets
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any

#: Seconds a preview stays valid.
DEFAULT_TTL_SECONDS = 300.0
#: Unredeemed previews kept per launch; the oldest go first.
MAX_PENDING = 256
#: ``app.state`` attribute that holds the confirmation book.
CONFIRMATIONS_STATE = "omrs_confirmations"

PROCESS_LOCAL_WARNING = (
    "This vector store reports only a process-local validity token. A change "
    "made by another process (for example the watch daemon or a CLI ingest) "
    "after this preview is not always detected. Run the preview again if "
    "another process can write to this collection."
)


@dataclass(frozen=True)
class ObservedState:
    """The store state a preview saw.

    Attributes:
        token: Opaque validity token for the collection.
        guarantee: ``"durable"`` or ``"process_local"``.
    """

    token: str
    guarantee: str


def observe(store: Any, collection: str, extra: str = "") -> ObservedState:
    """Return the validity token the store reports for *collection*.

    Args:
        store: The Engine's vector store.
        collection: Collection the action targets.
        extra: Further observed state to bind, such as the profile tag.

    Returns:
        The durable token when available, else the process-local one.
    """
    suffix = f"|{extra}" if extra else ""
    durable = store.get_data_version(collection)
    if durable is not None:
        return ObservedState(f"durable:{durable}{suffix}", "durable")
    local = f"local:{store.get_generation(collection)}:{store.count(collection)}"
    return ObservedState(local + suffix, "process_local")


def selector_key(selector: Mapping[str, Any]) -> str:
    """Return a canonical text form of *selector* for exact comparison."""
    return json.dumps(selector, sort_keys=True, separators=(",", ":"), default=str)


class ConfirmationRejected(Exception):
    """A confirmation does not match its preview.

    Attributes:
        status_code: HTTP status to return.
        message: Actionable message for the user.
    """

    def __init__(self, status_code: int, message: str) -> None:
        """Store the status and message."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


@dataclass(frozen=True)
class _Pending:
    action: str
    collection: str
    selector: str
    state: str
    expires_at: float


class ConfirmationBook:
    """Issued, unredeemed confirmations for one launch."""

    def __init__(
        self,
        *,
        ttl: float = DEFAULT_TTL_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Create an empty book.

        Args:
            ttl: Seconds a preview stays valid.
            clock: Wall-clock source in seconds (tests inject a fake).
        """
        self._ttl = ttl
        self._clock = clock
        self._pending: OrderedDict[str, _Pending] = OrderedDict()
        self._lock = Lock()

    def issue(
        self,
        action: str,
        collection: str,
        selector: Mapping[str, Any],
        state: ObservedState,
    ) -> dict[str, Any]:
        """Record a preview and return its confirmation description."""
        token = "cf_" + secrets.token_urlsafe(24)
        expires_at = self._clock() + self._ttl
        entry = _Pending(action, collection, selector_key(selector), state.token, expires_at)
        with self._lock:
            self._pending[token] = entry
            while len(self._pending) > MAX_PENDING:
                self._pending.popitem(last=False)
        return {
            "token": token,
            "expires_at": datetime.fromtimestamp(expires_at, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "expires_in": self._ttl,
            "validity": state.guarantee,
            "warning": PROCESS_LOCAL_WARNING if state.guarantee == "process_local" else None,
        }

    def redeem(
        self,
        token: str | None,
        action: str,
        collection: str,
        selector: Mapping[str, Any],
        state: ObservedState,
    ) -> None:
        """Accept *token* for this exact action, or raise.

        The token is spent on every call, accepted or not.

        Raises:
            ConfirmationRejected: 428 without a token; 409 for an unknown,
                used, expired, altered or stale confirmation.
        """
        if not token:
            raise ConfirmationRejected(
                428,
                "This action needs a confirmed preview. Send the request with "
                "dry_run or without confirm first, then repeat it with the "
                "confirmation_token from the preview.",
            )
        with self._lock:
            pending = self._pending.pop(token, None)
        if pending is None:
            raise ConfirmationRejected(
                409, "Unknown or already used confirmation. Run the preview again."
            )
        if self._clock() > pending.expires_at:
            raise ConfirmationRejected(409, "The confirmation expired. Run the preview again.")
        if (pending.action, pending.collection, pending.selector) != (
            action,
            collection,
            selector_key(selector),
        ):
            raise ConfirmationRejected(
                409,
                "The request does not match the previewed action, collection or "
                "selection. Run the preview again for the new selection.",
            )
        if pending.state != state.token:
            raise ConfirmationRejected(
                409,
                "The collection changed after the preview. Run the preview again "
                "to see the current effect.",
            )


def confirmation_book(app_state: Any) -> ConfirmationBook:
    """Return the application's confirmation book, created on first use."""
    book = getattr(app_state, CONFIRMATIONS_STATE, None)
    if book is None:
        book = ConfirmationBook()
        setattr(app_state, CONFIRMATIONS_STATE, book)
    return book
