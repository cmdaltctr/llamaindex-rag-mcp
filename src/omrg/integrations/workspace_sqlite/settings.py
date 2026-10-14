"""Typed workspace settings in the ``workspace_settings`` table (design D6).

Only the keys named in :data:`SETTING_KEYS` exist. A stored value that does
not parse reads as unset, so a damaged row never stops the server. Provider
settings stay in ``.env``; this table holds web-server choices only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from omrg.integrations.workspace_sqlite.schema import connect

MCP_HTTP_ENABLED = "mcp_http_enabled"
WEB_PORT = "web_port"
#: The only keys the table may hold.
SETTING_KEYS: frozenset[str] = frozenset({MCP_HTTP_ENABLED, WEB_PORT})

#: Saved ports must be unprivileged.
MIN_WEB_PORT = 1024
MAX_WEB_PORT = 65535


class UnknownSettingError(KeyError):
    """A key outside :data:`SETTING_KEYS` was read or written."""


def _parse_port(value: str | None) -> int | None:
    """Return the port in *value*, or ``None`` when it is absent or invalid."""
    if value is None or not value.isascii() or not value.isdigit():
        return None
    port = int(value)
    return port if MIN_WEB_PORT <= port <= MAX_WEB_PORT else None


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
        if key not in SETTING_KEYS:
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
        if key not in SETTING_KEYS:
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

    def get_mcp_http_enabled(self) -> bool:
        """Return whether MCP over HTTP is on. Off when unset or unreadable."""
        return self.get(MCP_HTTP_ENABLED) == "true"

    def set_mcp_http_enabled(self, enabled: bool) -> None:
        """Store whether MCP over HTTP is on."""
        self.set(MCP_HTTP_ENABLED, "true" if enabled else "false")

    def get_web_port(self) -> int | None:
        """Return the saved web port, or ``None`` when unset or invalid."""
        return _parse_port(self.get(WEB_PORT))

    def set_web_port(self, port: int | None) -> None:
        """Save the web port for later launches; ``None`` clears it.

        Raises:
            ValueError: *port* is outside 1024 to 65535.
        """
        if port is not None and not MIN_WEB_PORT <= port <= MAX_WEB_PORT:
            raise ValueError(f"Port must be between {MIN_WEB_PORT} and {MAX_WEB_PORT}.")
        self.set(WEB_PORT, None if port is None else str(port))


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
