"""Move saved workspace rows into ``omrg.jsonc`` once (ADR-087, D8).

Before this change the Settings page kept its values in the workspace
database. The file is the store now, so :func:`run_handover` copies each valid
row into ``omrg.jsonc`` where the file does not set that key, adds a
``keychain://<provider>`` reference for each saved key that is in the
keychain, and deletes the rows it handled. The table stays, empty, so no
schema migration destroys data and an older build still opens the database.

Rules:

- The file wins. A key that the file holds (even with an invalid value) keeps
  its file value and the row is deleted. The Chat provider and model move as
  a unit, so a file that sets either one keeps both.
- A row that breaks its rule reads as unset already, so it is deleted without
  a copy.
- If the file cannot be written (the folder is not writable, or the file
  cannot be parsed), every row stays and :class:`HandoverResult` carries the
  notice for ``GET /v1/settings/configuration``. The next start tries again.
- An unavailable keychain leaves the key rows in place: the entry may exist.
- A key never reaches the file. The result and the log hold no value.

Only ``omrg web`` calls this function (root gotcha 17). The CLI, the stdio
MCP server and the watcher never touch the rows.
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ...compose_providers import KeychainReader
from ...config.settings_file import SettingsFile, check_setting, read_settings_file
from ...config.settings_file_write import SettingsFileError, write_settings
from ...config.user_config import display_path, parse_jsonc, user_config_dir
from ...core.providers.llm import registry
from ...core.providers.llm.llamacpp_rules import LLAMACPP_SERVER_FIELDS
from ...integrations.keychain import KeychainUnavailableError
from ...integrations.workspace_sqlite.settings import (
    CHAT_MODEL,
    CHAT_PROVIDER,
    KEY_SAVED_AT,
    MCP_HTTP_ENABLED,
    UPLOAD_LIMIT_MIB,
    WEB_PORT,
    WorkspaceSettings,
    provider_key,
)

logger = logging.getLogger(__name__)

#: Row kinds.
_TEXT, _INT, _BOOL, _KEY = "text", "int", "bool", "key"
#: The Chat choice moves as one unit.
_CHAT_FILE_KEYS = ("answer.provider", "answer.model")


@dataclass(frozen=True)
class HandoverResult:
    """What the handover did, for ``GET /v1/settings/configuration``. It holds no value.

    Attributes:
        pending: Saved rows could not be moved and stay in the database.
        folder: The config folder to name in the notice, when *pending*.
        moved: File keys that the handover wrote.
    """

    pending: bool
    folder: str | None
    moved: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Row:
    """One workspace row and the file key that replaces it."""

    row_key: str
    file_key: str | None
    kind: str
    provider: str | None = None


def _plan() -> list[_Row]:
    """Return every row the old Settings page could write, with its file key."""
    rows = [
        _Row(WEB_PORT, "web_port", _INT),
        _Row(UPLOAD_LIMIT_MIB, "web_max_upload_mib", _INT),
        _Row(MCP_HTTP_ENABLED, "mcp_http_enabled", _BOOL),
        _Row(CHAT_PROVIDER, "answer.provider", _TEXT),
        _Row(CHAT_MODEL, "answer.model", _TEXT),
    ]
    for provider, descriptor in registry.describe_all().items():
        secret_field = None
        for spec in descriptor.fields:
            if spec.kind == "secret":
                secret_field = spec.settings_field
                continue
            kind = _INT if spec.kind == "int" else _TEXT
            rows.append(_Row(provider_key(provider, spec.id), spec.settings_field, kind))
        rows.append(_Row(provider_key(provider, KEY_SAVED_AT), secret_field, _KEY, provider))
    for spec in LLAMACPP_SERVER_FIELDS:
        kind = _INT if spec.kind == "int" else _TEXT
        rows.append(_Row(provider_key("llamacpp", spec.id), spec.settings_field, kind))
    return rows


def _typed(rows: WorkspaceSettings, row: _Row) -> Any | None:
    """Return the row value as a typed, rule-checked value, or ``None`` when unusable."""
    if row.file_key is None:
        return None
    text = rows.get_chat_provider() if row.row_key == CHAT_PROVIDER else rows.get_valid(row.row_key)
    if text is None:
        return None
    if row.kind == _BOOL:
        value: Any = {"true": True, "false": False}.get(text)
    elif row.kind == _INT:
        value = int(text) if text.isascii() and text.isdigit() else None
    else:
        value = text
    if value is None:
        return None
    checked, rule = check_setting(row.file_key, value)
    return checked if rule is None else None


def _held_by_file(file: SettingsFile) -> frozenset[str]:
    """Return every dotted key the file holds with a non-blank value, valid or not.

    The reader drops an invalid value, and a reference to a missing variable
    leaves no trace in it, so this reads the keys from the text. A person who
    typed a key keeps it.
    """
    try:
        data = parse_jsonc(file.path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    held: set[str] = set()

    def present(value: Any) -> bool:
        return value is not None and not (isinstance(value, str) and not value.strip())

    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, dict):
                held.update(f"{key}.{leaf}" for leaf, item in value.items() if present(item))
            elif present(value):
                held.add(key)
    return frozenset(held)


def _keychain_has(keychain: KeychainReader | None, provider: str) -> bool | None:
    """Return whether the keychain holds a key for *provider*; ``None`` when unknown."""
    if keychain is None or not keychain.available:
        return None
    try:
        return keychain.read(provider) is not None
    except KeychainUnavailableError:
        return None


def _decide(
    rows: WorkspaceSettings, keychain: KeychainReader | None, file: SettingsFile
) -> tuple[dict[str, Any], list[str]]:
    """Return ``(changes, handled)``: file changes to write and the row keys to delete."""
    held = _held_by_file(file)
    chat_held = any(key in held for key in _CHAT_FILE_KEYS)
    changes: dict[str, Any] = {}
    handled: list[str] = []
    for row in _plan():
        if rows.get(row.row_key) is None:
            continue
        if row.kind == _KEY:
            exists = _keychain_has(keychain, row.provider or "")
            if exists is None:
                continue  # unknown: keep the row for the next start
            if exists and row.file_key is not None and row.file_key not in held:
                changes[row.file_key] = f"keychain://{row.provider}"
        elif row.file_key is not None and not (
            row.file_key in held or (row.file_key in _CHAT_FILE_KEYS and chat_held)
        ):
            value = _typed(rows, row)
            if value is not None:
                changes[row.file_key] = value
        handled.append(row.row_key)
    return changes, handled


def _folder_text(directory: Path | None) -> str:
    return display_path(directory or user_config_dir())


def run_handover(
    workspace_settings: WorkspaceSettings,
    keychain: KeychainReader | None,
    directory: Path | None = None,
) -> HandoverResult:
    """Copy the saved workspace rows into ``omrg.jsonc``, then delete them.

    The web lifespan calls this once, before ``ProviderState`` starts.

    Args:
        workspace_settings: The workspace settings rows.
        keychain: The system keychain, or a fake. ``None`` counts as unavailable.
        directory: The user config folder (default: the resolved one).

    Returns:
        ``pending=False`` when every row was handled or none existed.
        ``pending=True`` with the folder to name when the file could not be
        written; the rows stay. The function never raises.
    """
    try:
        if not Path(workspace_settings.path).is_file():
            return HandoverResult(False, None)
        file = read_settings_file(directory)
        changes, handled = _decide(workspace_settings, keychain, file)
    except sqlite3.Error:
        logger.warning("The saved settings could not be read; the handover is skipped.")
        return HandoverResult(False, None)
    if not handled:
        return HandoverResult(False, None)
    if changes:
        try:
            write_settings(changes, revision=file.revision, directory=directory)
        except SettingsFileError:
            logger.warning("Saved settings could not be moved to omrg.jsonc; the rows stay.")
            return HandoverResult(True, _folder_text(directory))
    try:
        for row_key in handled:
            workspace_settings.set(row_key, None)
    except sqlite3.Error:
        logger.warning("Saved settings were copied but some rows could not be deleted.")
        return HandoverResult(False, None, tuple(changes))
    if changes:
        logger.info("Moved %d saved setting(s) into omrg.jsonc.", len(changes))
    return HandoverResult(False, None, tuple(changes))
