"""Document routes: collection and source listing, search and answering.

These implement the reviewed ``/v1`` operations ``listCollections``,
``listDocuments``, ``searchCollection`` and ``answerCollection``. Each
handler validates the request, delegates to the Engine that the
lifespan owns or to the existing core listing functions with that
Engine's store, and formats the result. Omitted controls stay ``None``
so the Engine resolves them from the collection profile.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .engine_access import ReadScope, RuntimeDep, admitted, engine_store, failure_text
from .errors import error_response
from .security import redact

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


class SearchBody(BaseModel):
    """Body of ``searchCollection`` (schema ``SearchRequest``)."""

    model_config = ConfigDict(extra="forbid")

    query: str
    top_k: int | None = Field(default=None, ge=1)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank: bool | None = None
    hybrid: bool | None = None
    expand_window: int = Field(default=0, ge=0)
    diagnostics: bool = False
    metadata_filter: dict[str, Any] | None = None


class AnswerBody(BaseModel):
    """Body of ``answerCollection`` (schema ``AnswerRequest``)."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(max_length=4096)
    top_k: int | None = Field(default=None, ge=1, le=100)
    similarity_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    rerank: bool | None = None
    hybrid: bool | None = None
    expand_window: int = Field(default=0, ge=0, le=10)
    metadata_filter: dict[str, Any] | None = None


def _json(payload: Any, status_code: int = 200) -> JSONResponse:
    return JSONResponse(jsonable_encoder(payload), status_code=status_code)


# ── Listing ──────────────────────────────────────────────────────────────


def _stored_profile(store: Any, collection: str) -> str | None:
    """Return the collection's stored profile tag, or ``None``.

    This is the same metadata read the profile-change preview uses. A
    failed read gives ``None``; it never hides the collection.
    """
    try:
        profile = (store.get_collection_metadata(collection) or {}).get("profile")
    except Exception:
        return None
    return profile if isinstance(profile, str) else None


def _store_info() -> dict[str, str]:
    """Return the configured backend name and its registry label.

    Only these two registry values are returned, so paths, URIs and cloud
    credentials never reach the response.
    """
    from ... import compose
    from ...core.vectordb import registry

    name = compose.configured_vector_store()
    return {"name": name, "label": registry.describe(name)["label"]}


def _collections_with_profiles(store: Any) -> list[dict[str, Any]]:
    from ...core.retrieval import list_collections as core_list_collections

    rows = core_list_collections(store)
    info = _store_info()
    return [{**row, "profile": _stored_profile(store, row["name"]), "store": info} for row in rows]


@router.get("/collections", operation_id="listCollections")
async def list_collections(runtime: RuntimeDep, _: ReadScope) -> Response:
    """List collections with document and chunk counts and stored profile."""
    store = engine_store(runtime.engine)
    async with admitted(runtime):
        rows = await run_in_threadpool(_collections_with_profiles, store)
    return _json(rows)


@router.get("/collections/{collection}/documents", operation_id="listDocuments")
async def list_documents(collection: str, runtime: RuntimeDep, _: ReadScope) -> Response:
    """List the sources of one collection with machine-local orphan status."""
    from ...core.ingestion import list_documents as core_list_documents

    store = engine_store(runtime.engine)
    async with admitted(runtime):
        rows = await run_in_threadpool(core_list_documents, collection, store)
    return _json(rows)


# ── Search ───────────────────────────────────────────────────────────────


@router.post("/collections/{collection}/search", operation_id="searchCollection")
async def search_collection(
    collection: str,
    body: SearchBody,
    runtime: RuntimeDep,
    _: ReadScope,
) -> Response:
    """Search one collection through the owning Engine.

    The Engine search is synchronous, so it runs in the thread pool.
    """
    async with admitted(runtime):
        try:
            rows = await run_in_threadpool(
                runtime.engine.search,
                body.query,
                top_k=body.top_k,
                similarity_threshold=body.similarity_threshold,
                rerank=body.rerank,
                hybrid=body.hybrid,
                expand_window=body.expand_window,
                collection_name=collection,
                metadata_filter=body.metadata_filter,
                include_diagnostics=body.diagnostics,
            )
        except ValueError as exc:
            return error_response(400, str(exc), error_type="validation")
        except Exception as exc:
            logger.warning("Web search failed: %s", redact(repr(exc)))
            error_type = "retrieval" if body.metadata_filter is not None else "internal"
            return error_response(500, f"Search failed: {failure_text(exc)}", error_type=error_type)
    return _json(rows)


# ── Answer ───────────────────────────────────────────────────────────────


def _answer_failure(query: str, exc: BaseException) -> dict[str, Any]:
    """Return the answer error shape the MCP tool uses for an Engine failure."""
    return {
        "status": "error",
        "query": query,
        "answer": None,
        "citations": [],
        "evidence": [],
        "failure_stage": None,
        "error": f"{type(exc).__name__}: answering failed before a result was produced.",
        "completion_source": "none",
    }


@router.post("/collections/{collection}/answer", operation_id="answerCollection")
async def answer_collection(
    collection: str,
    body: AnswerBody,
    runtime: RuntimeDep,
    _: ReadScope,
) -> Response:
    """Answer a question with deterministic citations through the owning Engine.

    Retrieval and generation failures come back inside the answer result
    (``failure_stage``), not as HTTP errors, as in the MCP tool.
    """
    async with admitted(runtime):
        try:
            result = await runtime.engine.answer(
                body.query,
                top_k=body.top_k,
                similarity_threshold=body.similarity_threshold,
                rerank=body.rerank,
                hybrid=body.hybrid,
                expand_window=body.expand_window,
                collection_name=collection,
                metadata_filter=body.metadata_filter,
            )
        except ValueError as exc:
            return error_response(400, str(exc), error_type="validation")
        except Exception as exc:
            logger.warning("Web answer failed: %s", redact(repr(exc)))
            result = _answer_failure(body.query, exc)
    return _json(result)
