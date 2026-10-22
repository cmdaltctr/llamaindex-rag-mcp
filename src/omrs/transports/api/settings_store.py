"""The web server's store of settings: ``omrs.jsonc`` (ADR-087, D1, D5, D7).

:class:`SettingsFileStore` is a thin wrapper over ``config.settings_file`` (read)
and ``config.settings_file_write`` (write, with the in-process lock). Every
settings route and the :class:`~.provider_state.ProviderState` go through it,
so no route reads or writes the workspace database for a setting.

The store also reports the file stamp ``(st_mtime_ns, st_size, st_ino)``. A
change of the stamp tells the server that a person edited the file, or that
another save replaced it, and the live values need a re-read (D7).

:func:`refusal_response` maps the write errors to the error envelope. Their
messages name the rule and never hold the refused value.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from fastapi.responses import JSONResponse

from ...config.settings_file import SettingsFile, read_settings_file
from ...config.settings_file_write import (
    SettingsFileConflict,
    SettingsFileError,
    SettingsFileRefused,
    WriteResult,
    write_settings,
)
from ...config.user_config import CONFIG_FILE, parse_jsonc, user_config_dir
from .errors import error_response

#: What the file stamp holds: modification time (ns), size and inode.
Stamp = tuple[int, int, int]


class SettingsFileStore:
    """Read and write ``omrs.jsonc`` in the user config folder.

    Args:
        directory: The user config folder. ``None`` resolves it once, now.
    """

    def __init__(self, directory: Path | None = None) -> None:
        """Fix the folder for the life of the store."""
        self.directory = directory if directory is not None else user_config_dir()

    @property
    def path(self) -> Path:
        """The ``omrs.jsonc`` path."""
        return self.directory / CONFIG_FILE

    def read(self) -> SettingsFile:
        """Return what the file and ``secrets/`` hold now, with the file revision."""
        return read_settings_file(self.directory)

    def stamp(self) -> Stamp | None:
        """Return ``(st_mtime_ns, st_size, st_ino)`` of the file, or ``None`` when absent."""
        try:
            info = os.stat(self.path)
        except OSError:
            return None
        return (info.st_mtime_ns, info.st_size, info.st_ino)

    def write(self, changes: Mapping[str, Any], revision: str | None) -> WriteResult:
        """Set or remove keys. ``None`` or blank removes a key.

        Raises:
            SettingsFileRefused: A key or value is not allowed.
            SettingsFileConflict: The file changed since *revision*, or cannot be parsed.
            SettingsFileWriteError: The disk refused the write.
        """
        return write_settings(changes, revision=revision, directory=self.directory)

    def check_revision(self, revision: str | None) -> None:
        """Raise :class:`SettingsFileConflict` when the file differs from *revision*."""
        if revision is not None:
            self.write({}, revision)

    def raw(self, keys: Mapping[str, Any] | list[str] | tuple[str, ...]) -> dict[str, Any]:
        """Return the raw JSON value of each dotted key, or ``None`` when the file lacks it.

        Used to put a key back after a refused change. A broken file gives ``None`` for all.
        """
        try:
            data: Any = parse_jsonc(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        found: dict[str, Any] = {}
        for key in keys:
            node: Any = data
            for part in key.split("."):
                node = node.get(part) if isinstance(node, dict) else None
            found[key] = node
        return found


def refusal_response(error: SettingsFileError) -> JSONResponse:
    """Return the envelope for a refused write: 400 for a rule, 409 for a conflict, else 500.

    The message names the rule or the cause and never the refused value.
    """
    if isinstance(error, SettingsFileRefused):
        return error_response(400, str(error))
    if isinstance(error, SettingsFileConflict):
        return error_response(409, str(error))
    return error_response(500, str(error))


__all__ = ["SettingsFileStore", "Stamp", "refusal_response"]
