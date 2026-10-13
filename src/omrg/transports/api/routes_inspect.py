"""Protected stored-chunk inspection (design D7, D8).

``GET /v1/collections/{collection}/chunks/{chunk_id}`` returns one
stored chunk by its stable ``chunk_id`` with the neighbouring chunks of
the same source version. It reads the store through the existing
lineage navigation; it never opens the original source file, so a
citation stays inspectable when its source is outside the approved
roots or missing on this machine.

Chunk text is returned as a JSON string with ``text_format: "plain"``.
Clients must render it as text and never as markup. API responses also
carry ``nosniff`` and a restrictive content security policy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Any

from fastapi import APIRouter, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response

from .engine_access import ReadScope, RuntimeDep, admitted, engine_store
from .errors import error_response

router = APIRouter(prefix="/v1")

#: Largest neighbour window per side.
MAX_WINDOW = 5
_LINEAGE_KEYS = (
    "chunk_id",
    "source_id",
    "source_version",
    "source_chunk_index",
    "source_chunk_count",
)


def _chunk_view(text: str, metadata: Mapping[str, Any]) -> dict[str, Any]:
    """Format one stored row; the internal row id stays private."""
    meta = dict(metadata)
    view: dict[str, Any] = {key: meta.get(key) for key in _LINEAGE_KEYS}
    view["source"] = meta.get("file_path") or meta.get("file_name")
    view["page_label"] = meta.get("page_label")
    view["text"] = text
    view["metadata"] = meta
    return view


class _ChunkUnavailable(Exception):
    """The store cannot serve filtered chunk reads."""


def _inspect(store: Any, collection: str, chunk_id: str, window: int) -> dict[str, Any] | None:
    """Read one chunk and its neighbours; ``None`` when the chunk is unknown."""
    from ...core.retrieval.lineage import neighbours

    try:
        rows = list(store.iter_filtered_documents(collection, {"chunk_id": chunk_id}))
    except NotImplementedError:
        raise _ChunkUnavailable from None
    if not rows:
        return None
    # A replacement attempt can briefly hold two rows for one chunk id;
    # the lowest row id wins, as in lineage navigation.
    _row_id, text, metadata = min(rows, key=lambda row: row[0])
    anchor = _chunk_view(text, metadata)
    around = neighbours([anchor], store, collection, window)
    index = anchor["source_chunk_index"]
    previous, following = [], []
    for row in around:
        view = _chunk_view(row["text"], row["metadata"])
        (previous if view["source_chunk_index"] < index else following).append(view)
    return {
        "status": "ok",
        "collection": collection,
        "text_format": "plain",
        "chunk": anchor,
        "previous": previous,
        "next": following,
    }


@router.get("/collections/{collection}/chunks/{chunk_id}", operation_id="getChunk")
async def get_chunk(
    collection: str,
    chunk_id: str,
    runtime: RuntimeDep,
    _: ReadScope,
    window: Annotated[int, Query(ge=0, le=MAX_WINDOW)] = 1,
) -> Response:
    """Return one stored chunk and up to *window* neighbours per side."""
    store = engine_store(runtime.engine)
    async with admitted(runtime):
        try:
            result = await run_in_threadpool(_inspect, store, collection, chunk_id, window)
        except _ChunkUnavailable:
            return error_response(501, "This vector store cannot serve chunk inspection.")
    if result is None:
        return error_response(404, "Unknown chunk.")
    return JSONResponse(jsonable_encoder(result))
