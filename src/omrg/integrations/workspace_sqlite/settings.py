"""Typed workspace settings in the ``workspace_settings`` table (design D6).

Only the keys named in :data:`SETTING_KEYS` exist. A stored value that does
not parse reads as unset, so a damaged row never stops the server.

Besides the fixed web-server keys, the table holds the LLM provider choices
of design D1 and D6: ``chat.provider``, ``chat.model``,
``provider.<name>.<field>`` (a saved address or model) and
``provider.<name>.key_saved_at`` (when this workspace saved a key). An API
key never enters this table; it lives in the system keychain
(:mod:`omrg.integrations.keychain`).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path

from omrg.integrations.workspace_sqlite.schema import connect

MCP_HTTP_ENABLED = "mcp_http_enabled"
WEB_PORT = "web_port"
UPLOAD_LIMIT_MIB = "upload_limit_mib"
CHAT_PROVIDER = "chat.provider"
CHAT_MODEL = "chat.model"
KEY_SAVED_AT = "key_saved_at"
#: The fixed keys the table may hold. Provider keys follow :data:`PROVIDER_KEY_PATTERN`.
SETTING_KEYS: frozenset[str] = frozenset(
    {MCP_HTTP_ENABLED, WEB_PORT, UPLOAD_LIMIT_MIB, CHAT_PROVIDER, CHAT_MODEL}
)
#: The only fields a provider row may hold: addresses and whole numbers (the
#: ``url`` and ``int`` fields of the provider connection descriptors), the
#: managed llama.cpp server's program, model and window, and the save time. A secret-looking
#: field such as ``api_key`` is never allowed. A test in ``tests/`` checks this
#: list against the descriptors, because integrations may not import ``core``.
PROVIDER_FIELD_IDS: frozenset[str] = frozenset(
    {
        "base_url",
        "chat_url",
        "context_window",
        "server_binary",
        "server_model",
        KEY_SAVED_AT,
    }
)
#: ``provider.<name>.<field>``: lower-case provider id, one allowed field id.
PROVIDER_KEY_PATTERN = re.compile(
    r"provider\.[a-z][a-z0-9_-]{0,63}\.(?:" + "|".join(sorted(PROVIDER_FIELD_IDS)) + ")"
)
_IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,63}")
#: Longest stored text for a chat or provider value.
MAX_VALUE_CHARS = 2048

#: Saved ports must be unprivileged.
MIN_WEB_PORT = 1024
MAX_WEB_PORT = 65535

#: Allowed per-file upload limit, in whole MiB.
MIN_UPLOAD_LIMIT_MIB = 1
MAX_UPLOAD_LIMIT_MIB = 2048


class UnknownSettingError(KeyError):
    """A key outside the allowed set was read or written."""


def is_known_key(key: str) -> bool:
    """Return whether *key* is a fixed key or a ``provider.<name>.<field>`` key."""
    return key in SETTING_KEYS or PROVIDER_KEY_PATTERN.fullmatch(key) is not None


def provider_key(provider: str, field: str) -> str:
    """Return the settings key for *field* of *provider*.

    Raises:
        UnknownSettingError: The result is not an allowed key.
    """
    key = f"provider.{provider}.{field}"
    if not is_known_key(key):
        raise UnknownSettingError(key)
    return key


def _clean_text(value: str | None) -> str | None:
    """Return *value* when it is short printable single-line text, else ``None``."""
    if value is None or not value.strip() or len(value) > MAX_VALUE_CHARS:
        return None
    if not value.isprintable():
        return None
    return value


def _parse_timestamp(value: str | None) -> str | None:
    """Return *value* when it is an ISO 8601 timestamp, else ``None``."""
    text = _clean_text(value)
    if text is None or len(text) > 64:
        return None
    try:
        datetime.fromisoformat(text)
    except ValueError:
        return None
    return text


def _parse_bounded(value: str | None, low: int, high: int) -> int | None:
    """Return the whole number in *value*, or ``None`` when absent, invalid or out of range."""
    if value is None or not value.isascii() or not value.isdigit():
        return None
    number = int(value)
    return number if low <= number <= high else None


class WorkspaceSettings:
    """Reads and writes the workspace settings of one database file.

    Each call opens a short-lived connection, as the workspace repository
    does. The database must already be migrated (open it with
    ``SqliteWorkspaceRepository`` first).

    Args:
        path: The workspace database file.
    """

    def __init__(self, path: Path) -> None:
        """Remember the database file."""
        self.path = Path(path)

    def get(self, key: str) -> str | None:
        """Return the stored text for *key*, or ``None`` when unset.

        Raises:
            UnknownSettingError: *key* is not a known setting.
        """
        if not is_known_key(key):
            raise UnknownSettingError(key)
        conn = connect(self.path)
        try:
            row = conn.execute("SELECT value FROM workspace_settings WHERE key = ?", (key,))
            found = row.fetchone()
        finally:
            conn.close()
        return None if found is None else str(found["value"])

    def set(self, key: str, value: str | None) -> None:
        """Store *value* for *key*; ``None`` clears it.

        Raises:
            UnknownSettingError: *key* is not a known setting.
        """
        if not is_known_key(key):
            raise UnknownSettingError(key)
        conn = connect(self.path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            if value is None:
                conn.execute("DELETE FROM workspace_settings WHERE key = ?", (key,))
            else:
                conn.execute(
                    "INSERT INTO workspace_settings (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, value),
                )
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def get_valid(self, key: str) -> str | None:
        """Return the stored text for *key*, or ``None`` when unset or damaged.

        Damaged means empty, too long, or not printable single-line text.
        """
        return _clean_text(self.get(key))

    def get_chat_provider(self) -> str | None:
        """Return the saved Chat provider name, or ``None`` when unset or damaged."""
        value = self.get_valid(CHAT_PROVIDER)
        return value if value is not None and _IDENTIFIER.fullmatch(value) else None

    def get_chat_model(self) -> str | None:
        """Return the saved Chat model name, or ``None`` when unset or damaged."""
        return self.get_valid(CHAT_MODEL)

    def set_chat_choice(self, provider: str | None, model: str | None) -> None:
        """Save the Chat provider and model; ``None`` clears each.

        Raises:
            ValueError: A value is not a provider id or printable model text.
        """
        if provider is not None and not _IDENTIFIER.fullmatch(provider):
            raise ValueError("The Chat provider is not a valid provider name.")
        if model is not None and _clean_text(model) is None:
            raise ValueError("The Chat model must be short printable text.")
        self.set(CHAT_PROVIDER, provider)
        self.set(CHAT_MODEL, model)

    def get_key_saved_at(self, provider: str) -> str | None:
        """Return when this workspace saved a key for *provider*, or ``None``."""
        return _parse_timestamp(self.get(provider_key(provider, KEY_SAVED_AT)))

    def set_key_saved_at(self, provider: str, when: str | None) -> None:
        """Record when a key was saved for *provider*; ``None`` clears the record.

        Raises:
            ValueError: *when* is not an ISO 8601 timestamp.
        """
        if when is not None and _parse_timestamp(when) is None:
            raise ValueError("The saved time must be an ISO 8601 timestamp.")
        self.set(provider_key(provider, KEY_SAVED_AT), when)

    def get_mcp_http_enabled(self) -> bool:
        """Return whether MCP over HTTP is on. Off when unset or unreadable."""
        return self.get(MCP_HTTP_ENABLED) == "true"

    def set_mcp_http_enabled(self, enabled: bool) -> None:
        """Store whether MCP over HTTP is on."""
        self.set(MCP_HTTP_ENABLED, "true" if enabled else "false")

    def get_web_port(self) -> int | None:
        """Return the saved web port, or ``None`` when unset or invalid."""
        return _parse_bounded(self.get(WEB_PORT), MIN_WEB_PORT, MAX_WEB_PORT)

    def set_web_port(self, port: int | None) -> None:
        """Save the web port for later launches; ``None`` clears it.

        Raises:
            ValueError: *port* is outside 1024 to 65535.
        """
        if port is not None and not MIN_WEB_PORT <= port <= MAX_WEB_PORT:
            raise ValueError(f"Port must be between {MIN_WEB_PORT} and {MAX_WEB_PORT}.")
        self.set(WEB_PORT, None if port is None else str(port))

    def get_upload_limit_mib(self) -> int | None:
        """Return the saved per-file upload limit in MiB, or ``None`` when unset or invalid."""
        return _parse_bounded(
            self.get(UPLOAD_LIMIT_MIB), MIN_UPLOAD_LIMIT_MIB, MAX_UPLOAD_LIMIT_MIB
        )

    def set_upload_limit_mib(self, mib: int | None) -> None:
        """Save the per-file upload limit in MiB; ``None`` clears it.

        Raises:
            ValueError: *mib* is outside 1 to 2048.
        """
        if mib is not None and not MIN_UPLOAD_LIMIT_MIB <= mib <= MAX_UPLOAD_LIMIT_MIB:
            raise ValueError(
                f"The upload limit must be between {MIN_UPLOAD_LIMIT_MIB} "
                f"and {MAX_UPLOAD_LIMIT_MIB} MiB."
            )
        self.set(UPLOAD_LIMIT_MIB, None if mib is None else str(mib))


def read_saved_web_port(path: Path) -> int | None:
    """Return the saved web port without creating or migrating anything.

    ``omrg web`` calls this before it binds. A missing file, an older schema
    or an unreadable database means no saved port.
    """
    if not Path(path).is_file():
        return None
    try:
        return WorkspaceSettings(path).get_web_port()
    except sqlite3.Error:
        return None
