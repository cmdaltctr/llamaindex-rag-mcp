"""The checks of ``PUT /v1/settings/configuration`` (edit-settings-from-configuration-page D3).

The Configuration section saves one or more settings in one request. Every
change is checked before anything is written, in the contract order, and the
first failure wins:

1. a key the page may not write (read-only, a key field, not one plain value,
   or no setting at all): 400;
2. a key that ``env`` or ``.env`` sets: 409, naming the variable;
3. a value that breaks its rule (type, bounds, choices, address): 400;
4. a PDF reader that is not installed: 400, the same answer as Settings >
   Document reading gives.

The file checks (stale revision, broken file, disk error) belong to the writer.

This module imports no web framework. No message holds a submitted value.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from ...config.rules import FILE_ONLY, document_reading_problem
from ...config.settings_file import check_setting
from ...config.settings_file_write import read_only_reason
from ..settings_view import LOCKING_SOURCES, env_lock_reason, source_word
from .document_reading import reader_refusal

if TYPE_CHECKING:
    from ...config import Settings

NOT_WRITABLE = "{key} is not a setting that can be changed here."


def launch_source(launch: Settings, key: str, overrides: Mapping[str, tuple[Any, str]]) -> str:
    """Return where the launch took *key* from; a file-only key reads *overrides*."""
    if key in FILE_ONLY:
        return overrides[key][1] if key in overrides else "default"
    return source_word(launch, key)


def value_rule(key: str, value: Any) -> str | None:
    """Return the rule that *value* breaks for *key*, or ``None``. ``None`` always passes."""
    if value is None:
        return None
    rule = document_reading_problem(key, value)  # blank text is refused for these keys
    return rule if rule is not None else check_setting(key, value)[1]


def update_refusal(
    changes: Mapping[str, Any],
    launch: Settings,
    overrides: Mapping[str, tuple[Any, str]] | None = None,
) -> tuple[int, str] | None:
    """Run checks 1 to 4 of a save and return ``(status, message)``, or ``None``.

    Args:
        changes: The ``changes`` member of the request.
        launch: The launch ``Settings``, which say where each value came from.
        overrides: ``(value, source)`` by file-only key, for a value the launch
            fixed (``WEB_MAX_UPLOAD_MIB`` is ``env``).

    Returns:
        The status and message of the first failure, or ``None`` when every
        change passes. The message names the key and the rule, never the value.
    """
    fixed = overrides or {}
    for key in changes:
        if read_only_reason(key) is not None:
            return 400, NOT_WRITABLE.format(key=key)
    for key in changes:
        if launch_source(launch, key, fixed) in LOCKING_SOURCES:
            return 409, env_lock_reason(key)
    for key, value in changes.items():
        rule = value_rule(key, value)
        if rule is not None:
            return 400, f"{key}: {rule}"
    return reader_refusal(changes)
