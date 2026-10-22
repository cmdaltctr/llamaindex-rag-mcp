"""The restart-only snapshot of one ``omrs web`` launch (ADR-087, D7).

``EffectiveSettings`` stays frozen for the life of the process (ADR-037), so a
hand edit of an engine setting in ``omrs.jsonc`` cannot apply live. The server
calls :func:`capture` once at launch and keeps the result on ``app.state``.
:func:`pending` then names each restart-only key whose file value differs, and
``GET /v1/settings/configuration`` marks those keys "Restart to apply".

The restart-only set is derived from the ``Settings`` model (see
``transports.settings_view.restart_only_keys``), so it cannot drift from the
model. A key field is tracked by its reference (``keychain://<provider>``) or
by the word ``set``, never by its value.

This module imports no web framework.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ...config.rules import SECRET_FIELDS
from ...config.settings_file import SettingsFile
from ..settings_view import restart_only_keys


def _token(file: SettingsFile, key: str) -> Any:
    """Return what the file holds for *key*, without any key value."""
    if key in SECRET_FIELDS:
        if key in file.references:
            return f"keychain://{file.references[key]}"
        if key in file.secrets:
            return "set"
        return "key-file" if key in file.key_file else None
    return file.values.get(key)


def capture(settings_file: SettingsFile) -> dict[str, Any]:
    """Return the restart-only values that *settings_file* holds, by dotted key.

    Args:
        settings_file: The file as read at launch.

    Returns:
        One entry for every restart-only key. A key the file does not set maps
        to ``None``.
    """
    return {key: _token(settings_file, key) for key in restart_only_keys()}


def pending(snapshot: Mapping[str, Any], current_file: SettingsFile) -> set[str]:
    """Return the restart-only keys whose file value differs from *snapshot*.

    Args:
        snapshot: The result of :func:`capture` at launch.
        current_file: The file as read now.

    Returns:
        The keys a restart would change. A file that cannot be parsed reports
        none: the problem list names it, and a restart would not read it.
    """
    if current_file.state == "broken":
        return set()
    return {key for key, old in snapshot.items() if _token(current_file, key) != old}
