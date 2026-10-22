"""Workspace-managed upload storage (design D8).

Uploaded files go to ``<workspace>/uploads/<upload id>/<file name>``. A
request streams into ``uploads/.partial/<id>.part`` first; the file moves
to its final place only after the whole body arrived within the limit.
Any failure, cancellation or over-limit body removes the partial file.

The type check uses the ingestible extension set that the caller passes in
from resolved settings (``ingestion.ingest_extensions``). This module keeps
no list of its own. Content detection (Magika) still runs at ingestion,
unchanged. Archives are never extracted and URL names are refused.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import re
import secrets
import shutil
import unicodedata
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any

from ...integrations.workspace_sqlite.schema import make_private_dirs

#: One mebibyte in bytes.
MIB = 1024 * 1024
#: Default per-file limit: 50 MiB.
DEFAULT_MAX_UPLOAD_BYTES = 50 * MIB

_PARTIAL = ".partial"
_URL = re.compile(r"^[a-z][a-z0-9+.\-]*:", re.IGNORECASE)
_ID = re.compile(r"^[0-9a-f]{32}$")


class UploadRejected(Exception):
    """An upload failed a check. ``status_code`` is the HTTP status to send."""

    def __init__(self, status_code: int, message: str) -> None:
        """Record the HTTP status and the client-safe message."""
        super().__init__(message)
        self.status_code = status_code
        self.message = message


def _check_name(name: str) -> str:
    """Return the NFC form of a plain file name, or refuse it."""
    name = unicodedata.normalize("NFC", name)
    if _URL.match(name) or "://" in name:
        raise UploadRejected(400, "URL ingestion is not supported. Upload the file itself.")
    if not name or name in {".", ".."} or name.startswith("."):
        raise UploadRejected(400, "The file name is empty or hidden.")
    if any(ch in name for ch in "/\\") or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise UploadRejected(400, "The file name must not contain path separators.")
    if len(name.encode("utf-8")) > 255:
        raise UploadRejected(400, "The file name is longer than 255 bytes.")
    return name


def _too_large(limit: int) -> str:
    return f"The file is larger than the {limit} byte upload limit."


class UploadStore:
    """Managed upload storage inside one workspace."""

    def __init__(self, directory: Path, *, max_bytes: int = DEFAULT_MAX_UPLOAD_BYTES) -> None:
        """Create the store. Call :meth:`prepare` before use.

        Args:
            directory: The ``uploads`` directory inside the workspace.
            max_bytes: The per-file size limit.
        """
        self.directory = directory
        self.max_bytes = max_bytes

    @property
    def _partial_dir(self) -> Path:
        return self.directory / _PARTIAL

    def prepare(self) -> None:
        """Create the private directories and remove leftovers of a crash."""
        make_private_dirs(self._partial_dir)
        self.purge_partials()

    def purge_partials(self) -> None:
        """Delete every partial file left by an interrupted upload."""
        if not self._partial_dir.is_dir():
            return
        for leftover in self._partial_dir.iterdir():
            if leftover.is_dir() and not leftover.is_symlink():
                shutil.rmtree(leftover, ignore_errors=True)
            else:
                leftover.unlink(missing_ok=True)

    def preflight(
        self,
        name: str,
        size: int | None,
        extensions: Iterable[str],
        max_bytes: int | None = None,
    ) -> str:
        """Check a file name, declared size and type before any byte is stored.

        Args:
            name: The client file name.
            size: The declared size in bytes, or ``None`` when unknown.
            extensions: The ingestible extension set from resolved settings.
            max_bytes: The limit to check against; ``None`` uses the current one.

        Returns:
            The normalised file name.

        Raises:
            UploadRejected: Invalid name (400), unsupported type (415) or
                declared size over the limit (413).
        """
        name = _check_name(name)
        suffix = Path(name).suffix.lower()
        allowed = sorted({ext.lower() for ext in extensions})
        if suffix not in allowed:
            shown = suffix or "(none)"
            raise UploadRejected(
                415,
                f"File type {shown} is not supported for upload. "
                f"Supported types: {', '.join(allowed)}. Archives are not extracted.",
            )
        if size is not None and size < 0:
            raise UploadRejected(400, "The declared size is negative.")
        limit = self.max_bytes if max_bytes is None else max_bytes
        if size is not None and size > limit:
            raise UploadRejected(413, _too_large(limit))
        return name

    async def receive(
        self,
        name: str,
        chunks: AsyncIterator[bytes],
        size: int | None,
        extensions: Iterable[str],
    ) -> dict[str, Any]:
        """Stream an upload into managed storage.

        Args:
            name: The client file name.
            chunks: The request body.
            size: The declared size, or ``None``.
            extensions: The ingestible extension set from resolved settings.

        Returns:
            ``{"id", "name", "size", "sha256"}`` for the stored file.

        The limit is read once, at the start. A change to :attr:`max_bytes`
        during the upload applies to later uploads only.

        Raises:
            UploadRejected: A preflight check failed or the body passed the limit.
        """
        limit = self.max_bytes
        name = self.preflight(name, size, extensions, limit)
        make_private_dirs(self._partial_dir)
        upload_id = secrets.token_hex(16)
        partial = self._partial_dir / f"{upload_id}.part"
        digest = hashlib.sha256()
        received = 0
        fd = os.open(partial, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as handle:
                async for chunk in chunks:
                    received += len(chunk)
                    if received > limit:
                        raise UploadRejected(413, _too_large(limit))
                    handle.write(chunk)
                    digest.update(chunk)
            final_dir = self.directory / upload_id
            make_private_dirs(final_dir)
            os.replace(partial, final_dir / name)
        except BaseException:
            # Covers failures, client disconnects and task cancellation.
            partial.unlink(missing_ok=True)
            with contextlib.suppress(OSError):
                (self.directory / upload_id).rmdir()
            raise
        return {"id": upload_id, "name": name, "size": received, "sha256": digest.hexdigest()}

    def path_for(self, upload_id: str) -> Path:
        """Return the stored file for *upload_id*.

        Raises:
            UploadRejected: Malformed or unknown identifier (404).
        """
        if not _ID.match(upload_id):
            raise UploadRejected(404, "Unknown upload.")
        folder = self.directory / upload_id
        files = [p for p in folder.iterdir() if p.is_file()] if folder.is_dir() else []
        if len(files) != 1:
            raise UploadRejected(404, "Unknown upload.")
        return files[0]
