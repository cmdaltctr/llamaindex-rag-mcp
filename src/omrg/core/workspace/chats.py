"""Repository contract for stored chats and their folders (ADR-082).

Composition injects an implementation. Chats hold the finished answers of the
web workspace, so a reload shows them again without a model call. Records are
plain dictionaries that match the JSON the HTTP routes return.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol, runtime_checkable

#: Longest chat title, in characters.
MAX_TITLE = 200
#: Longest folder name, in characters.
MAX_FOLDER_NAME = 100
#: Longest question, in characters.
MAX_QUESTION = 10_000
#: Largest encoded answer, in bytes (2 MiB).
MAX_ANSWER_BYTES = 2 * 1024 * 1024
#: Most chats one bulk delete may name.
MAX_BULK_DELETE = 500


@runtime_checkable
class ChatRepository(Protocol):
    """Persistence for chats, their turns and chat folders.

    An unknown chat or folder raises ``KeyError``. A value over a limit raises
    ``ValueError``. Delete methods return ``{"chats": n, "folders": m}``.
    """

    def list_chats(self) -> dict[str, list[dict[str, Any]]]:
        """Return ``{"folders": [...], "chats": [...]}``; chats come newest first, without turns."""
        ...

    def create_chat(self, title: str, folder_id: str | None = None) -> dict[str, Any]:
        """Create an empty chat."""
        ...

    def get_chat(self, chat_id: str) -> dict[str, Any]:
        """Return one chat with its ``turns`` in order."""
        ...

    def append_turn(
        self, chat_id: str, collection: str, question: str, answer: dict[str, Any]
    ) -> dict[str, Any]:
        """Add a turn at the next position, chosen inside the write transaction."""
        ...

    def move_chat(self, chat_id: str, folder_id: str | None) -> dict[str, Any]:
        """Move a chat into a folder, or out of any folder with ``None``."""
        ...

    def delete_chat(self, chat_id: str) -> dict[str, int]:
        """Delete one chat and its turns."""
        ...

    def delete_chats(self, chat_ids: Sequence[str]) -> dict[str, int]:
        """Delete many chats. An unknown id fails the call and deletes nothing."""
        ...

    def create_folder(self, name: str) -> dict[str, Any]:
        """Create a folder."""
        ...

    def rename_folder(self, folder_id: str, name: str) -> dict[str, Any]:
        """Rename a folder."""
        ...

    def delete_folder(self, folder_id: str) -> dict[str, int]:
        """Delete a folder and every chat inside it."""
        ...
