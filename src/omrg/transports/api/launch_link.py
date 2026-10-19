"""Private, renewed sign-in link for a login-item server (design D4).

A login-item server has no terminal, so it cannot print its one-time
sign-in link. :class:`RearmingAccessPolicy` writes the link to a file that
only the current user can read, and writes a new link after each sign-in
and after the failed-attempt limit disables the old one.

``security.py`` stays unchanged. The subclass reads and writes the base
class's private secret, counters and lock, so its tests pin that tie.
"""

from __future__ import annotations

import logging
import os
import secrets
import tempfile
from collections.abc import Iterable
from pathlib import Path

from .security import BOOTSTRAP_PREFIX, MAX_BOOTSTRAP_FAILURES, AccessPolicy

logger = logging.getLogger(__name__)

#: Name of the link file inside the workspace folder.
LINK_FILE_NAME = "launch-link"


def write_link_file(path: Path, url: str) -> None:
    """Write *url* as one line to *path*, readable by the current user only.

    The text goes to a temporary file in the same folder first and is then
    renamed into place, so a reader never sees a partial link. ``mkstemp``
    creates the file with mode 0600, so the link is never readable by
    others, not even for a moment.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(url + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


class RearmingAccessPolicy(AccessPolicy):
    """An :class:`AccessPolicy` that keeps a fresh sign-in link in a file."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        bootstrap_secret: str,
        link_file: Path,
        extra_origins: Iterable[str] = (),
    ) -> None:
        """Create a policy that publishes its link to *link_file*."""
        super().__init__(host, port, bootstrap_secret=bootstrap_secret, extra_origins=extra_origins)
        self._link_file = link_file
        #: True while the file holds a spent link because a renewal write failed.
        self._publish_pending = False

    @classmethod
    def for_launch(  # pyright: ignore[reportIncompatibleMethodOverride]
        cls,
        host: str,
        port: int,
        *,
        link_file: Path,
        extra_origins: Iterable[str] = (),
    ) -> RearmingAccessPolicy:
        """Create a policy with a fresh random secret and a link file path."""
        return cls(
            host,
            port,
            bootstrap_secret=BOOTSTRAP_PREFIX + secrets.token_urlsafe(32),
            link_file=link_file,
            extra_origins=extra_origins,
        )

    def publish(self) -> None:
        """Write the current link to the file.

        Raises:
            OSError: The file cannot be written. The caller stops the start-up,
                because without the file nobody can sign in.
        """
        with self._lock:
            write_link_file(self._link_file, self.launch_url())

    def retire(self) -> None:
        """Remove the link file. Safe to call when it is already gone."""
        self._link_file.unlink(missing_ok=True)

    def exchange_bootstrap(self, candidate: str) -> str | None:
        """Exchange the secret as the base class does, then renew it when spent.

        A secret is renewed after a successful sign-in and when the
        failed-attempt limit has disabled it. A single wrong guess changes
        nothing, except that it retries a renewal write that failed earlier.
        """
        token = super().exchange_bootstrap(candidate)
        with self._lock:
            if token is not None or self._bootstrap_failures >= MAX_BOOTSTRAP_FAILURES:
                self._rearm()
            elif self._publish_pending:
                self._write_current()
        return token

    def _rearm(self) -> None:
        """Replace the secret and the file content. The caller holds the lock."""
        self._bootstrap = BOOTSTRAP_PREFIX + secrets.token_urlsafe(32)
        self._bootstrap_used = False
        self._bootstrap_failures = 0
        self._write_current()

    def _write_current(self) -> None:
        """Write the current link. A failure is logged and retried on the next attempt.

        The sign-in that triggered a renewal already succeeded, so a failed
        write must not fail it. Until a later write works, the file keeps
        the spent link. A browser that opens that link posts it, is refused,
        and so triggers the retry; the user then runs 'omrg web open' again.
        """
        try:
            write_link_file(self._link_file, self.launch_url())
        except OSError as exc:
            self._publish_pending = True
            logger.warning("Could not renew the sign-in link file: %s", exc.strerror or exc)
        else:
            self._publish_pending = False
