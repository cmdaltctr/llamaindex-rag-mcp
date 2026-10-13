"""Preview-bound destructive routes: document deletion and profile change.

These implement the reviewed ``/v1`` operations ``deleteDocuments`` and
``changeCollectionProfile`` with a required preview step (design D8):

1. A preview request (``dry_run: true`` for deletion, ``confirm: false``
   for a profile change) mutates nothing. It returns the existing core
   preview plus a ``confirmation`` object with a single-use token.
2. The confirming request repeats the same selector with
   ``confirmation_token``. The token must match the action, collection,
   selector and the store state the preview observed, and must not be
   expired. Otherwise the request fails with 409 (428 without a token)
   and the data stays unchanged.

The handlers reuse the existing writer and profile functions with the
Engine's store; they do not reimplement deletion. Both routes need a
browser session: bearer credentials for notebooks never pass.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .confirmations import ConfirmationRejected, confirmation_book, observe
from .engine_access import RuntimeDep, admitted, engine_resolver, engine_store, require_session
from .errors import error_response
from .security import Principal

router = APIRouter(prefix="/v1")

DestructiveScope = Annotated[Principal, Depends(require_session("manage"))]

DELETE_ACTION = "delete_documents"
PROFILE_ACTION = "change_collection_profile"


class DeleteBody(BaseModel):
    """Body of ``deleteDocuments`` (schema ``DeleteRequest`` plus the token)."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(default=None, max_length=4096)
    metadata_filter: dict[str, Any] | None = None
    dry_run: bool = False
    confirmation_token: str | None = Field(default=None, max_length=128)


class ProfileBody(BaseModel):
    """Body of ``changeCollectionProfile`` (``ProfileChangeRequest`` plus the token)."""

    model_config = ConfigDict(extra="forbid")

    profile: Literal["documents", "codebase"]
    confirm: bool = False
    confirmation_token: str | None = Field(default=None, max_length=128)


def _rejected(exc: ConfirmationRejected) -> Response:
    return error_response(exc.status_code, exc.message, error_type="validation")


# ── Deletion ─────────────────────────────────────────────────────────────


def _delete_selector(body: DeleteBody) -> dict[str, Any] | str:
    """Return the selector, or an error message for an invalid one."""
    if body.path is not None and body.metadata_filter is not None:
        return "path and metadata_filter are mutually exclusive."
    if body.metadata_filter is not None and not body.metadata_filter:
        return "metadata_filter must be a non-empty object."
    if body.path is not None:
        return {"mode": "path", "path": body.path}
    if body.metadata_filter is not None:
        return {"mode": "metadata", "metadata_filter": body.metadata_filter}
    return {"mode": "collection"}


def _preview_delete(store: Any, collection: str, selector: dict[str, Any]) -> tuple[Any, dict]:
    from ...core.ingestion import preview_delete

    # Observe first: a write between the two reads then makes the token stale.
    state = observe(store, collection)
    result = preview_delete(
        path=selector.get("path"),
        metadata_filter=selector.get("metadata_filter"),
        collection_name=collection,
        store=store,
    )
    return state, result


def _remove_path(store: Any, collection: str, selector: dict[str, Any]) -> dict[str, Any]:
    from ...core.ingestion import remove_document

    return remove_document(selector["path"], collection, store)


def _remove_metadata(store: Any, collection: str, selector: dict[str, Any]) -> dict[str, Any]:
    from ...core.ingestion import remove_by_metadata

    return remove_by_metadata(selector["metadata_filter"], collection, store)


def _remove_collection(store: Any, collection: str, selector: dict[str, Any]) -> dict[str, Any]:
    from ...core.ingestion import remove_collection

    return remove_collection(collection, store)


#: The existing writer function for each deletion mode.
_REMOVERS = {
    "path": _remove_path,
    "metadata": _remove_metadata,
    "collection": _remove_collection,
}


def _apply_delete(store: Any, collection: str, selector: dict[str, Any]) -> dict[str, Any]:
    mode = selector["mode"]
    return {**_REMOVERS[mode](store, collection, selector), "mode": mode}


@router.delete("/collections/{collection}/documents", operation_id="deleteDocuments")
async def delete_documents(
    collection: str,
    request: Request,
    runtime: RuntimeDep,
    _: DestructiveScope,
    body: DeleteBody | None = None,
) -> Response:
    """Preview, or confirm a previewed, document or collection deletion."""
    body = body or DeleteBody()
    selector = _delete_selector(body)
    if isinstance(selector, str):
        return error_response(400, selector, error_type="validation")
    store = engine_store(runtime.engine)
    book = confirmation_book(request.app.state)
    async with admitted(runtime):
        if body.dry_run:
            state, result = await run_in_threadpool(_preview_delete, store, collection, selector)
            if result.get("status") != "ok":
                return error_response(400, result.get("message", "Invalid deletion preview."))
            result["confirmation"] = book.issue(DELETE_ACTION, collection, selector, state)
            return JSONResponse(result)
        state = await run_in_threadpool(observe, store, collection)
        try:
            book.redeem(body.confirmation_token, DELETE_ACTION, collection, selector, state)
        except ConfirmationRejected as exc:
            return _rejected(exc)
        result = await run_in_threadpool(_apply_delete, store, collection, selector)
    if result.get("status") != "ok":
        return error_response(400, result.get("message", "Deletion failed."))
    return JSONResponse(result)


# ── Profile change ───────────────────────────────────────────────────────


def _profile_state(store: Any, collection: str) -> Any:
    """Observe the store and the collection's current profile tag."""
    try:
        meta = store.get_collection_metadata(collection) or {}
    except Exception:
        meta = {}
    return observe(store, collection, extra=f"profile={meta.get('profile')}")


def _preview_profile(engine: Any, store: Any, collection: str, profile: str) -> tuple[Any, dict]:
    from ...core.profiles import generate_safety_contract

    state = _profile_state(store, collection)
    contract = generate_safety_contract(
        collection, profile, store=store, resolver=engine_resolver(engine)
    )
    return state, contract


@router.patch("/collections/{collection}/profile", operation_id="changeCollectionProfile")
async def change_collection_profile(
    collection: str,
    body: ProfileBody,
    request: Request,
    runtime: RuntimeDep,
    _: DestructiveScope,
) -> Response:
    """Preview, or confirm a previewed, change of the stored collection profile.

    Existing chunks stay unchanged; query-time levers follow the new
    profile at once and ingest-time levers apply to later ingests.
    """
    from ...core.profiles import apply_profile_change

    store = engine_store(runtime.engine)
    book = confirmation_book(request.app.state)
    selector = {"profile": body.profile}
    async with admitted(runtime):
        if not body.confirm:
            state, contract = await run_in_threadpool(
                _preview_profile, runtime.engine, store, collection, body.profile
            )
            return JSONResponse(
                {
                    "status": "preview",
                    "contract": contract,
                    "confirm_required": True,
                    "confirmation": book.issue(PROFILE_ACTION, collection, selector, state),
                }
            )
        state = await run_in_threadpool(_profile_state, store, collection)
        try:
            book.redeem(body.confirmation_token, PROFILE_ACTION, collection, selector, state)
        except ConfirmationRejected as exc:
            return _rejected(exc)
        try:
            result = await run_in_threadpool(apply_profile_change, collection, body.profile, store)
        except ValueError as exc:
            return error_response(400, str(exc), error_type="validation")
    return JSONResponse(result)
