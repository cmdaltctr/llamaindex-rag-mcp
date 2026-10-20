"""Persistent workspace sign-in secret, delivered by the page (persistent-web-auth-token).

The server keeps one secret in ``<workspace>/.auth-token`` (mode 0600) and
reuses it on every start. It puts the secret into the application page,
but only for a page load of its own origin (:func:`page_may_carry_secret`).
The page posts the secret to ``POST /v1/session`` on load and again after
any 401, so a restart no longer signs an open tab out.

The secret has the bootstrap prefix, so the existing log redaction and the
query-string guard in :mod:`.security` cover it. Any program that runs as
the user can read the file; ADR-088 records that trust level.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import stat
import tempfile
from collections.abc import Mapping
from pathlib import Path

from ...integrations.workspace_sqlite.schema import make_private_dirs
from .security import BOOTSTRAP_PREFIX, AccessPolicy

logger = logging.getLogger(__name__)

#: Name of the secret file inside the workspace folder.
PAGE_SECRET_FILE_NAME = ".auth-token"  # noqa: S105 - a file name, not a secret
#: ``name`` of the ``<meta>`` tag that carries the secret in the page.
PAGE_SECRET_META = "omrg-page-secret"  # noqa: S105 - a tag name, not a secret

_VALID = re.compile(re.escape(BOOTSTRAP_PREFIX) + r"[A-Za-z0-9_-]{43,}")
_OWN_SITES = frozenset({"none", "same-origin"})


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8")).digest()


class PageSecret:
    """The workspace sign-in secret. ``repr`` hides the value."""

    def __init__(self, value: str) -> None:
        """Hold *value*, a secret read from or written to the workspace."""
        self._value = value
        self._digest = _digest(value)

    @property
    def value(self) -> str:
        """The secret, for the served page only."""
        return self._value

    def matches(self, candidate: str) -> bool:
        """Compare *candidate* with the secret in constant time."""
        return hmac.compare_digest(_digest(candidate), self._digest)

    def __repr__(self) -> str:
        """Show the type only."""
        return "PageSecret(***)"

    @classmethod
    def load_or_create(cls, workspace: Path) -> PageSecret:
        """Read the secret of *workspace*, or create it on the first start.

        A missing workspace folder is created with mode 0700. A file with a
        looser mode than 0600 is tightened when the user owns it; otherwise a
        warning is logged. A file without a valid secret is replaced.

        Args:
            workspace: The workspace folder of this server.

        Returns:
            The secret.

        Raises:
            OSError: The file cannot be read or written, or it is a symbolic link.
        """
        make_private_dirs(workspace)
        path = workspace / PAGE_SECRET_FILE_NAME
        value = _read(path)
        if value is None:
            value = BOOTSTRAP_PREFIX + secrets.token_urlsafe(32)
            _write(path, value)
        return cls(value)


def _read(path: Path) -> str | None:
    """Return the secret in *path*, or ``None`` when it is missing or not valid."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    with os.fdopen(fd, encoding="utf-8") as handle:
        _check_mode(path, os.fstat(handle.fileno()))
        text = handle.read(256).strip()
    if _VALID.fullmatch(text) is None:
        logger.warning("The sign-in secret file %s is not a valid secret. Writing a new one.", path)
        return None
    return text


def _check_mode(path: Path, info: os.stat_result) -> None:
    """Warn about a mode looser than 0600, and tighten it when the user owns the file."""
    mode = stat.S_IMODE(info.st_mode)
    if not mode & 0o077:
        return
    if info.st_uid == os.getuid():
        os.chmod(path, 0o600)
        logger.warning("The sign-in secret file %s had mode %o. Set it to 0600.", path, mode)
    else:
        logger.warning(
            "The sign-in secret file %s has mode %o and another owner. Make it 0600.", path, mode
        )


def _write(path: Path, value: str) -> None:
    """Write *value* to *path* atomically; ``mkstemp`` gives the file mode 0600."""
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(value + "\n")
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def page_may_carry_secret(policy: AccessPolicy, headers: Mapping[str, str]) -> bool:
    """Return whether a page request may receive the secret (design D2).

    The ``Host`` must be the server's own (the DNS-rebinding guard; the
    request guard has already refused any other). An ``Origin``, when sent,
    must be the server's own or approved. The fetch metadata must show a
    same-origin request or a navigation. A foreign page cannot read a
    cross-origin response, so a navigation from elsewhere leaks nothing.

    Args:
        policy: The launch access policy.
        headers: The request headers (case-insensitive mapping).

    Returns:
        ``True`` when the page may carry the secret.
    """
    if not policy.host_allowed(headers.get("host")):
        return False
    origin = headers.get("origin")
    if origin is not None and not policy.origin_allowed(origin):
        return False
    site = headers.get("sec-fetch-site")
    return site is None or site in _OWN_SITES or headers.get("sec-fetch-mode") == "navigate"


def inject_page_secret(page: str, secret: PageSecret) -> str:
    """Return *page* with the secret in a ``<meta>`` tag before ``</head>``.

    A page without ``</head>`` is returned unchanged, so it signs in only
    with a launch link.
    """
    head = page.find("</head>")
    if head < 0:
        return page
    tag = f'<meta name="{PAGE_SECRET_META}" content="{html.escape(secret.value)}">'
    return page[:head] + tag + page[head:]
