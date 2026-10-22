"""``GET`` and ``PUT /v1/settings/document-reading`` (document-reading-settings, D10).

The pair reads and writes the nine document-reading keys in ``omrs.jsonc``.
Each key applies at the next launch only. ``PUT`` needs a browser session with
the manage scope: a bearer credential never passes. The checks run in the
contract order and stop at the first failure, so nothing is written on any
failure: body shape (400), a key outside the nine (400), a locked key (409), a
value that breaks its rule (400), a PDF reader that is not installed (400),
then the file write (409 for a stale revision or a broken file, 500 for a disk
error). No message holds a submitted value.

The body builder and checks 2 to 5 live in ``api/document_reading.py``, which
imports no web framework.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from ....config.rules import DOCUMENT_READING_KEYS
from ....config.settings_file_write import SettingsFileError
from ..document_reading import build_document_reading, launch_settings, update_refusal
from ..engine_access import ReadScope, require_session
from ..errors import error_response
from ..security import Principal
from ..settings_store import refusal_response
from .graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]
READ_FAILED = "The document reading settings could not be read."


class DocumentReadingUpdate(BaseModel):
    """Body of ``PUT /v1/settings/document-reading``.

    Attributes:
        values: One to nine of the nine keys. ``null`` removes a key from the file.
        revision: The ``revision`` the page last read.
    """

    model_config = ConfigDict(extra="forbid")

    values: Annotated[dict[str, Any], Field(min_length=1, max_length=len(DOCUMENT_READING_KEYS))]
    revision: Annotated[str, Field(max_length=128)]


async def _state(request: Request) -> Response:
    state = getattr(request.app.state, "configuration", None)
    try:
        body = await run_in_threadpool(build_document_reading, state)
    except Exception:
        logger.exception("The document reading settings could not be built.")
        return error_response(500, READ_FAILED)
    return ok(body)


@router.get("/settings/document-reading", operation_id="getDocumentReadingSettings")
async def get_document_reading(_: ReadScope, request: Request) -> Response:
    """Return the nine document-reading keys, the PDF readers and the OCR engines."""
    return await _state(request)


@router.put("/settings/document-reading", operation_id="setDocumentReadingSettings")
async def set_document_reading(
    _: ManageScope, body: DocumentReadingUpdate, request: Request
) -> Response:
    """Write document-reading keys to ``omrs.jsonc`` for the next launch, all or none."""
    state = getattr(request.app.state, "configuration", None)
    launch = await run_in_threadpool(launch_settings, state)
    refusal = await run_in_threadpool(update_refusal, body.values, launch)
    if refusal is not None:
        return error_response(*refusal)
    store = request.app.state.mcp_http.store
    try:
        await run_in_threadpool(store.write, body.values, body.revision)
    except SettingsFileError as exc:
        return refusal_response(exc)
    return await _state(request)
