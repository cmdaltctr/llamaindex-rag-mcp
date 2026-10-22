"""Admission counter for the web runtime (design D4 of ``add-web-power-menu``).

:class:`Admission` counts admitted work so shutdown can wait for it. It
lives in its own module because ``lifespan.py`` sits at the 500-line
ceiling. ``lifespan.py`` re-exports both names, so existing imports and
patch targets keep working.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager


class AdmissionClosed(RuntimeError):
    """The server is shutting down and admits no new work."""


class Admission:
    """Counts admitted work so shutdown can wait for it."""

    def __init__(self) -> None:
        """Start open with no active work."""
        self._open = True
        self._active = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._closed = asyncio.Event()

    @property
    def is_open(self) -> bool:
        """Whether new work is admitted."""
        return self._open

    @property
    def active(self) -> int:
        """Number of admitted calls that have not finished (read-only)."""
        return self._active

    @asynccontextmanager
    async def enter(self) -> AsyncIterator[None]:
        """Hold admission for the duration of the block.

        Raises:
            AdmissionClosed: Shutdown has begun.
        """
        if not self._open:
            raise AdmissionClosed("The server is shutting down.")
        self._active += 1
        self._idle.clear()
        try:
            yield
        finally:
            self._active -= 1
            if self._active == 0:
                self._idle.set()

    def close(self) -> None:
        """Stop admitting new work and wake :meth:`wait_closed` waiters."""
        self._open = False
        self._closed.set()

    async def wait_closed(self) -> None:
        """Return when admission closes. Event streams end on this signal."""
        await self._closed.wait()

    async def wait_idle(self) -> None:
        """Return when no admitted work remains."""
        await self._idle.wait()
