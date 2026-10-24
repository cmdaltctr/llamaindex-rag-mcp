"""Every setting with its value in force and its source (ADR-087, D10, D11).

``GET /v1/settings/configuration`` and ``omrs config show`` list the same
rows, so the row builder lives here, below both transports. This module
imports no web framework, so the CLI can use it without the ``web`` extra.

A setting either applies at once (``live``) or only at the next launch
(``restart``). The live set is the provider fields (addresses, keys, Chat
choice, context windows, llama.cpp server values) plus the upload limit and
the MCP switch. Every other setting is restart-only. The restart-only set is
derived from the ``Settings`` model, so a new setting is restart-only without
an edit here.

A key field never leaves this module as a value: the row holds ``None`` and
the last four characters, and only when the key has at least eight
characters.

Each row also describes its control (edit-settings-from-configuration-page
D2): whether the page may write it, why not, its kind, choices, bounds and
whether it takes ``null``. A value that ``env`` or ``.env`` sets locks its row.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import PurePath
from typing import TYPE_CHECKING, Any

from ..config.provider_sources import PROVIDER_FIELDS
from ..config.rules import FILE_ONLY, SECRET_FIELDS
from ..config.setting_shapes import setting_shape
from ..config.settings_file import SettingsFile, setting_paths
from ..config.settings_file_write import read_only_reason

if TYPE_CHECKING:
    from ..config import Settings

APPLIES_LIVE = "live"
APPLIES_RESTART = "restart"

#: Settings that apply at once, with no restart.
LIVE_KEYS: frozenset[str] = frozenset({*PROVIDER_FIELDS, "web_max_upload_mib", "mcp_http_enabled"})
#: Values of the file-only keys when neither the file nor the launch sets them.
#: ``tests/unit/test_settings_view.py`` pins them to ``cli/web.py`` and ``uploads.py``.
FILE_ONLY_DEFAULTS: Mapping[str, Any] = {
    "web_port": 8765,
    "web_max_upload_mib": 50,
    "mcp_http_enabled": False,
}
#: Sources that win over the file, so a file edit changes nothing.
OUTRANKS_FILE: frozenset[str] = frozenset({"init", "env", "dotenv"})
#: Sources that lock a row: the page may not write the key while they set it.
LOCKING_SOURCES: frozenset[str] = frozenset({"env", "dotenv"})
#: A key shorter than this shows no characters at all.
MIN_KEY_CHARS_FOR_LAST4 = 8


def applies(path: str) -> str:
    """Return ``live`` when the setting *path* applies at once, else ``restart``."""
    return APPLIES_LIVE if path in LIVE_KEYS else APPLIES_RESTART


def env_name(key: str) -> str:
    """Return the environment name of *key* (``retrieval.top_k`` gives ``RETRIEVAL__TOP_K``)."""
    return key.upper().replace(".", "__")


def env_lock_reason(key: str) -> str:
    """Return the lock text of a key that ``env`` or ``.env`` sets. It names the variable."""
    return f"Remove {env_name(key)} from the environment or .env to edit it here."


def edit_refusal(key: str, source: str) -> str | None:
    """Return why the page may not write *key* now, or ``None`` when it may.

    A read-only reason wins over the lock of an ``env`` or ``dotenv`` source.
    """
    reason = read_only_reason(key)
    if reason is None and source in LOCKING_SOURCES:
        return env_lock_reason(key)
    return reason


def restart_only_keys() -> tuple[str, ...]:
    """Return every setting key that applies only at the next launch, in model order."""
    return tuple(path for path in setting_paths() if applies(path) == APPLIES_RESTART)


@dataclass(frozen=True)
class SettingView:
    """One row of the configuration list. ``repr`` hides the value.

    Attributes:
        key: Dotted setting key (``retrieval.top_k``).
        value: Value in force as plain JSON data. ``None`` for a key field.
        source: ``init``, ``env``, ``dotenv``, ``config-file``, ``key-file``,
            ``keychain`` or ``default``.
        applies: ``live`` or ``restart``.
        restart_pending: The file now holds another value that a restart applies.
        last4: Only for a key field that is set: its last four characters, or an
            empty string when the key is too short to show any.
        saved: The value ``omrs.jsonc`` holds now as plain JSON data, or
            ``None`` when the file lacks it. ``None`` for a key field.
        editable: The page may write this key now.
        read_only_reason: Why the page may not, or ``None`` when it may.
        kind: ``bool``, ``int``, ``float``, ``text`` or ``choice``; ``None``
            for a setting that is not one plain value.
        choices: The accepted values of a ``choice`` row, else ``None``.
        min: The inclusive lower bound of a number, else ``None``.
        max: The inclusive upper bound of a number, else ``None``.
        nullable: The setting takes ``None``, so Clear restores its default.
    """

    key: str
    value: Any
    source: str
    applies: str
    restart_pending: bool
    last4: str | None = None
    saved: Any = None
    editable: bool = False
    read_only_reason: str | None = None
    kind: str | None = None
    choices: tuple[str, ...] | None = None
    min: int | float | None = None
    max: int | float | None = None
    nullable: bool = False

    def __repr__(self) -> str:
        return f"SettingView(key={self.key}, source={self.source}, applies={self.applies})"


def plain(value: Any) -> Any:
    """Return *value* as plain JSON data (paths and enums become text)."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return plain(value.value)
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (set, frozenset)):
        return sorted((plain(item) for item in value), key=str)
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return str(value)


def last_four(key: str) -> str:
    """Return the last four characters of *key*, or ``""`` when *key* is too short to show."""
    return key[-4:] if len(key) >= MIN_KEY_CHARS_FOR_LAST4 else ""


def _lookup(settings: Settings, path: str) -> Any:
    node: Any = settings
    for part in path.split("."):
        node = getattr(node, part, None)
    return node


def source_word(settings: Settings, path: str) -> str:
    """Return the source word of *path*; defaults from YAML and code read ``default``."""
    word = settings.setting_sources.get(path, "default")
    return "default" if word == "yaml" else word


def _file_only(
    path: str,
    kind: str,
    file: SettingsFile,
    snapshot: Mapping[str, Any],
    overrides: Mapping[str, tuple[Any, str]],
) -> tuple[Any, str]:
    """Return ``(value, source)`` of a file-only key."""
    if path in overrides:
        return overrides[path]
    held = file.values if kind == APPLIES_LIVE else snapshot
    if held.get(path) is not None:
        return held[path], "config-file"
    return FILE_ONLY_DEFAULTS[path], "default"


def describe_settings(
    *,
    launch: Settings,
    live: Settings,
    file: SettingsFile,
    snapshot: Mapping[str, Any],
    pending: Collection[str],
    overrides: Mapping[str, tuple[Any, str]] | None = None,
) -> list[SettingView]:
    """List every setting with its value in force and its source.

    Args:
        launch: ``Settings`` as the process launched. Restart-only rows read it.
        live: ``Settings`` as resolved now, with ``keychain://`` references
            already resolved. Live rows read it.
        file: The current ``omrs.jsonc``. File-only live keys read it.
        snapshot: Restart-only file values captured at launch.
        pending: Keys whose file value differs from *snapshot*.
        overrides: ``(value, source)`` by file-only key, for a value the launch
            fixed (``--port``, ``WEB_MAX_UPLOAD_MIB``).

    Returns:
        One row per setting key, in model order. A row never holds a key
        value: key fields give ``value=None``, ``saved=None`` and the last four
        characters. A row whose restart is pending names the source of the
        value a restart applies: ``config-file``, or ``default`` when the file
        no longer holds the key.
    """
    fixed = overrides or {}
    rows: list[SettingView] = []
    for path in setting_paths():
        kind = applies(path)
        settings = live if kind == APPLIES_LIVE else launch
        last4: str | None = None
        if path in FILE_ONLY:
            value, source = _file_only(path, kind, file, snapshot, fixed)
        elif path in SECRET_FIELDS:
            secret = str(_lookup(settings, path) or "")
            value, source = None, source_word(settings, path)
            if secret:
                last4 = last_four(secret)
            else:
                source = "default"
        else:
            value, source = plain(_lookup(settings, path)), source_word(settings, path)
        waiting = path in pending and source not in OUTRANKS_FILE
        if waiting and path not in SECRET_FIELDS:
            # The value after a restart comes from the file now, so the source says so.
            source = "config-file" if file.values.get(path) is not None else "default"
        refusal = edit_refusal(path, source)
        shape = setting_shape(path)
        rows.append(
            SettingView(
                key=path,
                value=value,
                source=source,
                applies=kind,
                restart_pending=waiting,
                last4=last4,
                saved=None if path in SECRET_FIELDS else plain(file.values.get(path)),
                editable=refusal is None,
                read_only_reason=refusal,
                kind=shape.kind,
                choices=shape.choices,
                min=shape.min,
                max=shape.max,
                nullable=shape.nullable,
            )
        )
    return rows
