"""SQLite store for chats and chat folders (ADR-082).

This module is an integration leaf. It does not import ``omrg.core``, so the
limits below repeat the values in ``omrg.core.workspace.chats``; a test keeps
them equal.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from omrg.integrations.workspace_sqlite.pipeline_sql import (
    new_id,
    read_connection,
    write_transaction,
)

MAX_TITLE = 200
MAX_FOLDER_NAME = 100
MAX_QUESTION = 10_000
MAX_ANSWER_BYTES = 2 * 1024 * 1024


def _default_clock() -> datetime:
    return datetime.now(UTC)


def _bounded(text: str, limit: int, what: str) -> str:
    """Return *text* stripped, or raise ``ValueError`` when empty or over *limit*."""
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"A {what} cannot be empty.")
    if len(cleaned) > limit:
        raise ValueError(f"A {what} can have at most {limit} characters.")
    return cleaned


def _chat(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "chat_id": row["chat_id"],
        "folder_id": row["folder_id"],
        "title": row["title"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _folder(row: sqlite3.Row) -> dict[str, Any]:
    return {"folder_id": row["folder_id"], "name": row["name"], "created_at": row["created_at"]}


class SqliteChatRepository:
    """Reads and writes chats in an already migrated workspace database.

    Open ``SqliteWorkspaceRepository`` on the same file first, so migration 5
    has run. Each call uses a short-lived connection.

    Args:
        path: The workspace database file.
        clock: Returns the current time; tests inject a fixed clock.
    """

    def __init__(self, path: Path, *, clock: Callable[[], datetime] = _default_clock) -> None:
        """Remember the database file and the clock."""
        self.path = Path(path)
        self._clock = clock

    def _now(self) -> str:
        return self._clock().isoformat()

    # --- reads -----------------------------------------------------------

    def list_chats(self) -> dict[str, list[dict[str, Any]]]:
        """Return all folders (oldest first) and chats (newest first, no turns)."""
        with read_connection(self.path) as conn:
            folders = conn.execute("SELECT * FROM chat_folders ORDER BY created_at, folder_id")
            chats = conn.execute("SELECT * FROM chats ORDER BY updated_at DESC, chat_id")
            return {"folders": [_folder(r) for r in folders], "chats": [_chat(r) for r in chats]}

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        """Return one chat with its turns in order.

        Raises:
            KeyError: If the chat does not exist.
        """
        with read_connection(self.path) as conn:
            row = conn.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
            if row is None:
                raise KeyError(chat_id)
            turns = conn.execute(
                "SELECT * FROM chat_turns WHERE chat_id = ? ORDER BY position", (chat_id,)
            )
            return {
                **_chat(row),
                "turns": [
                    {
                        "position": t["position"],
                        "collection": t["collection"],
                        "question": t["question"],
                        "answer": json.loads(t["answer_json"]),
                        "created_at": t["created_at"],
                    }
                    for t in turns
                ],
            }

    # --- chat writes -----------------------------------------------------

    def create_chat(self, title: str, folder_id: str | None = None) -> dict[str, Any]:
        """Create an empty chat.

        Raises:
            ValueError: If the title is empty or too long.
            KeyError: If *folder_id* does not exist.
        """
        cleaned = _bounded(title, MAX_TITLE, "chat title")
        chat_id, now = new_id(), self._now()
        with write_transaction(self.path) as conn:
            if folder_id is not None:
                self._require_folder(conn, folder_id)
            conn.execute(
                "INSERT INTO chats VALUES (?, ?, ?, ?, ?)", (chat_id, folder_id, cleaned, now, now)
            )
        return {
            "chat_id": chat_id,
            "folder_id": folder_id,
            "title": cleaned,
            "created_at": now,
            "updated_at": now,
        }

    def append_turn(
        self, chat_id: str, collection: str, question: str, answer: dict[str, Any]
    ) -> dict[str, Any]:
        """Add a turn at ``MAX(position) + 1``, chosen inside the write transaction.

        Raises:
            ValueError: If the question is empty or too long, or the answer is too large.
            KeyError: If the chat does not exist.
        """
        cleaned = _bounded(question, MAX_QUESTION, "question")
        encoded = json.dumps(answer, separators=(",", ":"), ensure_ascii=False)
        if len(encoded.encode("utf-8")) > MAX_ANSWER_BYTES:
            raise ValueError("The answer is too large to store.")
        now = self._now()
        with write_transaction(self.path) as conn:
            self._require_chats(conn, [chat_id])
            position = conn.execute(
                "SELECT COALESCE(MAX(position), 0) + 1 FROM chat_turns WHERE chat_id = ?",
                (chat_id,),
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO chat_turns VALUES (?, ?, ?, ?, ?, ?)",
                (chat_id, position, collection, cleaned, encoded, now),
            )
            conn.execute("UPDATE chats SET updated_at = ? WHERE chat_id = ?", (now, chat_id))
        return {"chat_id": chat_id, "position": position, "created_at": now}

    def move_chat(self, chat_id: str, folder_id: str | None) -> dict[str, Any]:
        """Move a chat into a folder, or out with ``None``.

        Raises:
            KeyError: If the chat or the folder does not exist.
        """
        with write_transaction(self.path) as conn:
            self._require_chats(conn, [chat_id])
            if folder_id is not None:
                self._require_folder(conn, folder_id)
            conn.execute("UPDATE chats SET folder_id = ? WHERE chat_id = ?", (folder_id, chat_id))
            return _chat(
                conn.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,)).fetchone()
            )

    def delete_chat(self, chat_id: str) -> dict[str, int]:
        """Delete one chat and its turns.

        Raises:
            KeyError: If the chat does not exist.
        """
        return self.delete_chats([chat_id])

    def delete_chats(self, chat_ids: Sequence[str]) -> dict[str, int]:
        """Delete many chats in one transaction.

        Raises:
            KeyError: If any id does not exist. Nothing is deleted then.
        """
        unique = list(dict.fromkeys(chat_ids))
        with write_transaction(self.path) as conn:
            for chat_id in unique:
                if conn.execute("DELETE FROM chats WHERE chat_id = ?", (chat_id,)).rowcount == 0:
                    raise KeyError(chat_id)  # the rollback undoes the earlier deletes
        return {"chats": len(unique), "folders": 0}

    # --- folder writes ---------------------------------------------------

    def create_folder(self, name: str) -> dict[str, Any]:
        """Create a folder.

        Raises:
            ValueError: If the name is empty or too long.
        """
        cleaned = _bounded(name, MAX_FOLDER_NAME, "folder name")
        folder_id, now = new_id(), self._now()
        with write_transaction(self.path) as conn:
            conn.execute("INSERT INTO chat_folders VALUES (?, ?, ?)", (folder_id, cleaned, now))
        return {"folder_id": folder_id, "name": cleaned, "created_at": now}

    def rename_folder(self, folder_id: str, name: str) -> dict[str, Any]:
        """Rename a folder.

        Raises:
            ValueError: If the name is empty or too long.
            KeyError: If the folder does not exist.
        """
        cleaned = _bounded(name, MAX_FOLDER_NAME, "folder name")
        with write_transaction(self.path) as conn:
            self._require_folder(conn, folder_id)
            conn.execute(
                "UPDATE chat_folders SET name = ? WHERE folder_id = ?", (cleaned, folder_id)
            )
            return _folder(
                conn.execute(
                    "SELECT * FROM chat_folders WHERE folder_id = ?", (folder_id,)
                ).fetchone()
            )

    def delete_folder(self, folder_id: str) -> dict[str, int]:
        """Delete a folder and the chats inside it.

        Raises:
            KeyError: If the folder does not exist.
        """
        with write_transaction(self.path) as conn:
            self._require_folder(conn, folder_id)
            inside = conn.execute(
                "SELECT COUNT(*) FROM chats WHERE folder_id = ?", (folder_id,)
            ).fetchone()[0]
            conn.execute("DELETE FROM chat_folders WHERE folder_id = ?", (folder_id,))
        return {"chats": int(inside), "folders": 1}

    # --- checks ----------------------------------------------------------

    @staticmethod
    def _require_folder(conn: sqlite3.Connection, folder_id: str) -> None:
        found = conn.execute("SELECT 1 FROM chat_folders WHERE folder_id = ?", (folder_id,))
        if found.fetchone() is None:
            raise KeyError(folder_id)

    @staticmethod
    def _require_chats(conn: sqlite3.Connection, chat_ids: Sequence[str]) -> None:
        for chat_id in chat_ids:
            if conn.execute("SELECT 1 FROM chats WHERE chat_id = ?", (chat_id,)).fetchone() is None:
                raise KeyError(chat_id)
