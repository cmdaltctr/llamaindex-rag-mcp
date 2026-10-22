"""The durable MCP token (design D4).

At most one token exists. Only its SHA-256 hash is stored; the value is
returned once, when it is created. A random 256-bit token needs no slow
hash. Comparison is constant-time.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import sqlite3
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from omrs.integrations.workspace_sqlite.schema import connect

#: Prefix that lets log redaction match the token.
MCP_TOKEN_PREFIX = "omrs_mcp_"  # noqa: S105 - a public prefix, not a secret


@dataclass(frozen=True)
class CreatedToken:
    """A newly created token. This is the only place its value exists.

    Attributes:
        token: The token value; show it once.
        created_at: ISO 8601 creation time.
    """

    token: str
    created_at: str


def hash_token(token: str) -> str:
    """Return the hex SHA-256 digest stored in place of the token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _default_clock() -> datetime:
    return datetime.now(UTC)


class McpTokenStore:
    """Creates, revokes and verifies the MCP token of one workspace database.

    Args:
        path: The workspace database file, already migrated.
        clock: Returns the current time; injected for deterministic tests.
    """

    def __init__(self, path: Path, *, clock: Callable[[], datetime] = _default_clock) -> None:
        """Remember the database file."""
        self.path = Path(path)
        self._clock = clock

    def create(self) -> CreatedToken:
        """Create a token, replacing any existing one, in one transaction.

        Returns:
            The new token. Its value is not stored.
        """
        token = MCP_TOKEN_PREFIX + secrets.token_urlsafe(32)
        created_at = self._clock().isoformat()
        conn = connect(self.path)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM mcp_tokens")
            conn.execute(
                "INSERT INTO mcp_tokens (token_id, token_hash, created_at) VALUES (?, ?, ?)",
                (uuid.uuid4().hex, hash_token(token), created_at),
            )
            conn.execute("COMMIT")
        except sqlite3.Error:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        return CreatedToken(token=token, created_at=created_at)

    def revoke(self) -> bool:
        """Delete the token. Returns whether one existed."""
        conn = connect(self.path)
        try:
            return conn.execute("DELETE FROM mcp_tokens").rowcount > 0
        finally:
            conn.close()

    def describe(self) -> dict[str, bool | str | None]:
        """Return ``{exists, created_at}`` without the token value."""
        conn = connect(self.path)
        try:
            row = conn.execute("SELECT created_at FROM mcp_tokens").fetchone()
        finally:
            conn.close()
        return {"exists": row is not None, "created_at": None if row is None else row[0]}

    def verify(self, candidate: str) -> bool:
        """Return whether *candidate* is the current token (constant-time)."""
        if not candidate:
            return False
        conn = connect(self.path)
        try:
            row = conn.execute("SELECT token_hash FROM mcp_tokens").fetchone()
        finally:
            conn.close()
        if row is None:
            return False
        return hmac.compare_digest(hash_token(candidate), row[0])
