"""Run-scoped cooperative cancellation.

One :class:`RunCancellation` belongs to one run. The runner gives the same
token to every adapter as ``context.cancellation``, so sibling and later
work see the same request. Cancellation is cooperative:

* The runner stops scheduling. Nodes that have not started are cancelled.
* The runner checks the token immediately before it starts a node, so a
  protected source commit that has not started does not start.
* The runner never interrupts a node that has started. A protected commit
  that has started finishes its write, verification and cleanup. A blocking
  provider call finishes, and the run stays ``cancelling`` until it does.
* An adapter can stop at its own safe boundary with
  :meth:`RunCancellation.raise_if_cancelled`.

Call :meth:`RunCancellation.cancel` on the event-loop thread of the run.
From another thread, use ``loop.call_soon_threadsafe(token.cancel)``.
"""

from __future__ import annotations

import asyncio

from .adapters import CancellationFlag, CancellationToken


class PipelineCancelledError(Exception):
    """Raised by an adapter that stops at a safe boundary after cancellation.

    The runner reports the node as cancelled, not failed.
    """


class RunCancellation(CancellationFlag):
    """Cancellation token for one run, with an awaitable signal.

    Args:
        parent: Optional host token. When the parent reports cancellation,
            this token reports it too. The runner sees a parent request at
            its next scheduling point; it is not woken by it.
    """

    def __init__(self, parent: CancellationToken | None = None) -> None:
        """Create an unset token, optionally linked to ``parent``."""
        super().__init__()
        self._parent = parent
        self._event = asyncio.Event()
        self.reason: str | None = None

    @property
    def cancelled(self) -> bool:
        """Return whether this run or its parent requested cancellation."""
        return self._cancelled or (self._parent is not None and self._parent.cancelled)

    def cancel(self, reason: str | None = None) -> None:
        """Request cancellation. A second request keeps the first reason.

        Args:
            reason: Short, safe explanation, for example ``"user request"``.
        """
        if self._cancelled:
            return
        self._cancelled = True
        self.reason = reason
        self._event.set()

    async def wait(self) -> None:
        """Wait until :meth:`cancel` is called on this token."""
        await self._event.wait()

    def raise_if_cancelled(self) -> None:
        """Stop at a safe boundary when cancellation was requested.

        Raises:
            PipelineCancelledError: If the run is cancelled.
        """
        if self.cancelled:
            detail = f": {self.reason}" if self.reason else ""
            raise PipelineCancelledError(f"The run was cancelled{detail}.")


def run_cancellation(token: CancellationToken | None) -> RunCancellation:
    """Return a :class:`RunCancellation` for ``token``.

    A :class:`RunCancellation` is used as it is. Any other token becomes the
    parent of a new run token. ``None`` gives a new, unlinked token.
    """
    if isinstance(token, RunCancellation):
        return token
    return RunCancellation(parent=token)
