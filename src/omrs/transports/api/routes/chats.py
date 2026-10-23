"""Chat routes: stored chats and their folders (ADR-082, add-chat-history design D4).

Saved answers carry evidence text from private documents. Every route needs the
browser session (``require_session``), so a bearer token for a notebook or MCP
client never reads them. The delete routes also need the ``manage`` scope. The
routes delegate to :class:`omrs.core.workspace.chats.ChatRepository` and hold no
chat logic.

* ``GET /v1/chats`` lists folders and chats, newest chat first, without turns.
* ``POST /v1/chats`` creates a chat. ``GET``, ``PATCH`` and ``DELETE`` on
  ``/v1/chats/{chat_id}`` read, move and delete one.
* ``POST /v1/chats/{chat_id}/turns`` saves one finished answer.
* ``POST /v1/chats/delete`` deletes many chats, all or nothing.
* ``/v1/chat-folders`` creates, renames and deletes folders. A folder delete
  removes its chats. ``PUT /v1/chat-folders/order`` sets the folder order.
"""

from __future__ import annotations

import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....core.workspace.chats import (
    MAX_ANSWER_BYTES,
    MAX_BULK_DELETE,
    MAX_FOLDER_NAME,
    MAX_FOLDERS,
    MAX_QUESTION,
    MAX_TITLE,
)
from ..engine_access import RuntimeDep, admitted, require_session
from ..errors import error_response
from ..security import Principal
from .graphs import ok

router = APIRouter(prefix="/v1")

ReadSession = Annotated[Principal, Depends(require_session("read"))]
ManageSession = Annotated[Principal, Depends(require_session("manage"))]


class CreateChatBody(BaseModel):
    """Body of ``POST /v1/chats`` (schema ``ChatCreateRequest``)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=MAX_TITLE)
    folder_id: str | None = Field(default=None, max_length=128)


class MoveChatBody(BaseModel):
    """Body of ``PATCH /v1/chats/{chat_id}`` (schema ``ChatMoveRequest``)."""

    model_config = ConfigDict(extra="forbid")

    folder_id: str | None = Field(max_length=128)


class AppendTurnBody(BaseModel):
    """Body of ``POST /v1/chats/{chat_id}/turns`` (schema ``ChatTurnRequest``)."""

    model_config = ConfigDict(extra="forbid")

    collection: str = Field(min_length=1, max_length=512)
    question: str = Field(min_length=1, max_length=MAX_QUESTION)
    answer: dict[str, Any]


class DeleteChatsBody(BaseModel):
    """Body of ``POST /v1/chats/delete`` (schema ``ChatBulkDeleteRequest``)."""

    model_config = ConfigDict(extra="forbid")

    chat_ids: list[str] = Field(min_length=1, max_length=MAX_BULK_DELETE)


class FolderBody(BaseModel):
    """Body of ``POST /v1/chat-folders`` and ``PATCH /v1/chat-folders/{folder_id}``."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=MAX_FOLDER_NAME)


class FolderOrderBody(BaseModel):
    """Body of ``PUT /v1/chat-folders/order`` (schema ``ChatFolderOrderRequest``)."""

    model_config = ConfigDict(extra="forbid")

    folder_ids: list[Annotated[str, Field(max_length=128)]] = Field(
        min_length=1, max_length=MAX_FOLDERS
    )


def get_chats(runtime: RuntimeDep) -> Any:
    """Route dependency returning the launch's chat store.

    Raises:
        HTTPException: 503 when the server has no chat store.
    """
    if runtime.chats is None:
        raise HTTPException(503, "Stored chats are not available in this server.")
    return runtime.chats


ChatsDep = Annotated[Any, Depends(get_chats)]


def _unknown(runtime: RuntimeDep, exc: KeyError) -> Response:
    return error_response(
        404, "That chat or folder does not exist.", redactor=runtime.engine.redact
    )


def _invalid(runtime: RuntimeDep, exc: ValueError) -> Response:
    return error_response(400, str(exc), error_type="validation", redactor=runtime.engine.redact)


async def _call(runtime: Any, fn: Any, *args: Any) -> Any:
    async with admitted(runtime):
        return await run_in_threadpool(fn, *args)


@router.get("/chats", operation_id="listChats")
async def list_chats(_: ReadSession, runtime: RuntimeDep, chats: ChatsDep) -> Response:
    """List folders and chats; chats come newest first and carry no turns."""
    return ok(await _call(runtime, chats.list_chats))


@router.post("/chats", status_code=201, operation_id="createChat")
async def create_chat(
    _: ReadSession, body: CreateChatBody, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Create an empty chat, optionally inside a folder."""
    try:
        chat = await _call(runtime, chats.create_chat, body.title, body.folder_id)
    except KeyError as exc:
        return _unknown(runtime, exc)
    except ValueError as exc:
        return _invalid(runtime, exc)
    return ok({"chat": chat}, 201)


@router.post("/chats/delete", operation_id="deleteChats")
async def delete_chats(
    _: ManageSession, body: DeleteChatsBody, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Delete many chats. An unknown id fails the request and deletes nothing."""
    try:
        counts = await _call(runtime, chats.delete_chats, body.chat_ids)
    except KeyError as exc:
        return _unknown(runtime, exc)
    return ok(counts)


@router.get("/chats/{chat_id}", operation_id="getChat")
async def get_chat(_: ReadSession, chat_id: str, runtime: RuntimeDep, chats: ChatsDep) -> Response:
    """Return one chat with its turns in order."""
    try:
        chat = await _call(runtime, chats.get_chat, chat_id)
    except KeyError as exc:
        return _unknown(runtime, exc)
    return ok({"chat": chat})


@router.patch("/chats/{chat_id}", operation_id="moveChat")
async def move_chat(
    _: ReadSession, chat_id: str, body: MoveChatBody, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Move a chat into a folder, or out of any folder with ``null``."""
    try:
        chat = await _call(runtime, chats.move_chat, chat_id, body.folder_id)
    except KeyError as exc:
        return _unknown(runtime, exc)
    return ok({"chat": chat})


@router.delete("/chats/{chat_id}", operation_id="deleteChat")
async def delete_chat(
    _: ManageSession, chat_id: str, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Delete one chat and its turns."""
    try:
        counts = await _call(runtime, chats.delete_chat, chat_id)
    except KeyError as exc:
        return _unknown(runtime, exc)
    return ok(counts)


@router.post("/chats/{chat_id}/turns", status_code=201, operation_id="appendChatTurn")
async def append_turn(
    _: ReadSession, chat_id: str, body: AppendTurnBody, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Save one finished answer. The server picks the turn position."""
    encoded = json.dumps(body.answer, separators=(",", ":"), ensure_ascii=False)
    if len(encoded.encode("utf-8")) > MAX_ANSWER_BYTES:
        return error_response(413, "The answer is too large to store.")
    try:
        turn = await _call(
            runtime, chats.append_turn, chat_id, body.collection, body.question, body.answer
        )
    except KeyError as exc:
        return _unknown(runtime, exc)
    except ValueError as exc:
        return _invalid(runtime, exc)
    return ok({"turn": turn}, 201)


@router.post("/chat-folders", status_code=201, operation_id="createChatFolder")
async def create_folder(
    _: ReadSession, body: FolderBody, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Create a chat folder."""
    try:
        folder = await _call(runtime, chats.create_folder, body.name)
    except ValueError as exc:
        return _invalid(runtime, exc)
    return ok({"folder": folder}, 201)


@router.patch("/chat-folders/{folder_id}", operation_id="renameChatFolder")
async def rename_folder(
    _: ReadSession, folder_id: str, body: FolderBody, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Rename a chat folder."""
    try:
        folder = await _call(runtime, chats.rename_folder, folder_id, body.name)
    except KeyError as exc:
        return _unknown(runtime, exc)
    except ValueError as exc:
        return _invalid(runtime, exc)
    return ok({"folder": folder})


@router.put("/chat-folders/order", operation_id="reorderChatFolders")
async def reorder_folders(
    _: ReadSession, body: FolderOrderBody, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Set the folder order. The list names every folder once."""
    try:
        folders = await _call(runtime, chats.reorder_folders, body.folder_ids)
    except KeyError as exc:
        return _unknown(runtime, exc)
    except ValueError as exc:
        return _invalid(runtime, exc)
    return ok({"folders": folders})


@router.delete("/chat-folders/{folder_id}", operation_id="deleteChatFolder")
async def delete_folder(
    _: ManageSession, folder_id: str, runtime: RuntimeDep, chats: ChatsDep
) -> Response:
    """Delete a folder and every chat inside it."""
    try:
        counts = await _call(runtime, chats.delete_folder, folder_id)
    except KeyError as exc:
        return _unknown(runtime, exc)
    return ok(counts)
