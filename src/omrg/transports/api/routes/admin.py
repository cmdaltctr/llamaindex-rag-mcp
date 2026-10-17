"""Collection admin routes: document deletion, profile change and display name.

Deletion and profile change implement the reviewed ``/v1`` operations
``deleteDocuments`` and ``changeCollectionProfile`` with a required
preview step (design D8):

1. A preview request (``dry_run: true`` for deletion, ``confirm: false``
   for a profile change) mutates nothing. It returns the existing core
   preview plus a ``confirmation`` object with a single-use token.
2. The confirming request repeats the same selector with
   ``confirmation_token``. The token must match the action, collection,
   selector and the store state the preview observed, and must not be
   expired. Otherwise the request fails with 409 (428 without a token)
   and the data stays unchanged.

``setCollectionDisplayName`` has no preview step: it changes only a
label in the collection metadata, loses no data and is reversible.

The handlers reuse the existing writer and profile functions with the
Engine's store; they do not reimplement deletion. All routes need a
browser session: bearer credentials for notebooks never pass.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ....compose_profiles import UnknownProfileError
from ....core.workspace import PROFILE_ID_PATTERN
from ..confirmations import ConfirmationRejected, confirmation_book, observe
from ..engine_access import RuntimeDep, admitted, engine_resolver, engine_store, require_session
from ..errors import API_HEADERS, error_response
from ..lifespan import WebRuntime
from ..security import Principal

router = APIRouter(prefix="/v1")

DestructiveScope = Annotated[Principal, Depends(require_session("manage"))]

DELETE_ACTION = "delete_documents"
PROFILE_ACTION = "change_collection_profile"
DISPLAY_NAME_MAX = 80


class DeleteBody(BaseModel):
    """Body of ``deleteDocuments`` (schema ``DeleteRequest`` plus the token)."""

    model_config = ConfigDict(extra="forbid")

    path: str | None = Field(default=None, max_length=4096)
    metadata_filter: dict[str, Any] | None = None
    dry_run: bool = False
    confirmation_token: str | None = Field(default=None, max_length=128)


class ProfileBody(BaseModel):
    """Body of ``changeCollectionProfile`` (``ProfileChangeRequest`` plus the token).

    ``profile`` is ``documents``, ``codebase`` or the id of a ready user profile.
    """

    model_config = ConfigDict(extra="forbid")

    profile: str = Field(pattern=PROFILE_ID_PATTERN)
    confirm: bool = False
    confirmation_token: str | None = Field(default=None, max_length=128)

    @field_validator("profile")
    @classmethod
    def _not_a_mode(cls, value: str) -> str:
        if value == "hybrid":
            raise ValueError("hybrid selects a mode and is not a profile")
        return value


class DisplayNameBody(BaseModel):
    """Body of ``setCollectionDisplayName`` (schema ``DisplayNameRequest``).

    The raw length bound only caps the payload. The 80 code point limit
    applies after trimming, in :func:`_clean_display_name`.
    """

    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(max_length=4096)


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
    from ....core.ingestion import preview_delete

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
    from ....core.ingestion import remove_document

    return remove_document(selector["path"], collection, store)


def _remove_metadata(store: Any, collection: str, selector: dict[str, Any]) -> dict[str, Any]:
    from ....core.ingestion import remove_by_metadata

    return remove_by_metadata(selector["metadata_filter"], collection, store)


def _remove_collection(store: Any, collection: str, selector: dict[str, Any]) -> dict[str, Any]:
    from ....core.ingestion import remove_collection

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


def _profile_state(store: Any, collection: str, target: str = "") -> Any:
    """Observe the store, the collection's profile tag and the target profile.

    ``target`` is the fingerprint of the profile being bound. A save of one of
    its pipelines, or its delete, between preview and confirm changes it.
    """
    try:
        meta = store.get_collection_metadata(collection) or {}
    except Exception:
        meta = {}
    return observe(store, collection, extra=f"profile={meta.get('profile')};target={target}")


def _profile_service(runtime: WebRuntime) -> Any:
    """Return the profile service of the running server."""
    if runtime.profiles is None:
        raise ValueError("Profiles are not available in this server.")
    return runtime.profiles


def _preview_profile(
    runtime: WebRuntime, store: Any, collection: str, profile: str
) -> tuple[Any, dict]:
    from ....core.profiles import generate_safety_contract

    profiles = _profile_service(runtime)
    with profiles.lock:
        profiles.check_binding(profile, collection)
        state = _profile_state(store, collection, profiles.fingerprint(profile))
        contract = generate_safety_contract(
            collection,
            profile,
            store=store,
            resolver=engine_resolver(runtime.engine),
            catalogue=profiles.catalogue,
        )
    return state, contract


def _apply_profile(runtime: WebRuntime, store: Any, collection: str, profile: str) -> dict:
    """Check the profile again, then write the tag, under the lock that a delete takes."""
    from ....core.profiles import apply_profile_change

    profiles = _profile_service(runtime)
    with profiles.lock:
        profiles.check_binding(profile, collection)
        return apply_profile_change(collection, profile, store, catalogue=profiles.catalogue)


def _refusal(runtime: WebRuntime, exc: Exception) -> Response:
    """Map a profile check failure to 400 with the reasons."""
    from ....compose_profiles import ProfileNotReadyError

    redactor = runtime.engine.redact
    if isinstance(exc, ProfileNotReadyError):
        body = {
            "status": "error",
            "message": redactor(str(exc)),
            "error_type": "validation",
            "not_ready_reasons": exc.reasons,
        }
        return JSONResponse(body, status_code=400, headers=API_HEADERS)
    return error_response(400, str(exc), error_type="validation", redactor=redactor)


@router.patch("/collections/{collection}/profile", operation_id="changeCollectionProfile")
async def change_collection_profile(
    collection: str,
    body: ProfileBody,
    request: Request,
    runtime: RuntimeDep,
    _: DestructiveScope,
) -> Response:
    """Preview, or confirm a previewed, change of the stored collection profile.

    The profile is ``documents``, ``codebase`` or the id of a ready user
    profile. Existing chunks stay unchanged; query-time levers follow the new
    profile at once and ingest-time levers apply to later ingests.
    """
    if runtime.profiles is None:
        return error_response(503, "Profiles are not available in this server.")
    store = engine_store(runtime.engine)
    book = confirmation_book(request.app.state)
    selector = {"profile": body.profile}
    async with admitted(runtime):
        if not body.confirm:
            try:
                state, contract = await run_in_threadpool(
                    _preview_profile, runtime, store, collection, body.profile
                )
            except (ValueError, UnknownProfileError) as exc:
                return _refusal(runtime, exc)
            return JSONResponse(
                {
                    "status": "preview",
                    "contract": contract,
                    "confirm_required": True,
                    "confirmation": book.issue(PROFILE_ACTION, collection, selector, state),
                }
            )
        fingerprint = await run_in_threadpool(runtime.profiles.fingerprint, body.profile)
        state = await run_in_threadpool(_profile_state, store, collection, fingerprint)
        try:
            book.redeem(body.confirmation_token, PROFILE_ACTION, collection, selector, state)
        except ConfirmationRejected as exc:
            return _rejected(exc)
        try:
            result = await run_in_threadpool(
                _apply_profile, runtime, store, collection, body.profile
            )
        except (ValueError, UnknownProfileError) as exc:
            return _refusal(runtime, exc)
    return JSONResponse(result)


# ── Display name ─────────────────────────────────────────────────────────


def _clean_display_name(raw: str) -> tuple[str, str | None]:
    """Return ``(value, error)``: the trimmed name, or why it is invalid.

    An empty trimmed value is valid and clears the display name. The limit
    counts Unicode code points, the same unit the web editor counts.
    """
    value = raw.strip()
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
        return value, "The display name must not contain control characters."
    if len(value) > DISPLAY_NAME_MAX:
        return value, f"The display name must be at most {DISPLAY_NAME_MAX} characters."
    return value, None


def _write_display_name(store: Any, collection: str, value: str) -> bool:
    """Store *value* (``""`` clears it); return ``False`` for an unknown collection.

    The existence check comes first: without it Chroma would create an empty
    collection and LanceDB would park the value for a name that has no data.
    """
    if not store.collection_exists(collection):
        return False
    store.update_collection_metadata(collection, {"display_name": value})
    return True


@router.patch("/collections/{collection}/display-name", operation_id="setCollectionDisplayName")
async def set_collection_display_name(
    collection: str,
    body: DisplayNameBody,
    runtime: RuntimeDep,
    _: DestructiveScope,
) -> Response:
    """Set or clear the display name of a collection.

    Only a label in the collection metadata changes. The collection name,
    the stored vectors and every retrieval call stay as they were, so there
    is no preview step. An empty value clears the name.
    """
    value, problem = _clean_display_name(body.display_name)
    if problem is not None:
        return error_response(400, problem, error_type="validation")
    store = engine_store(runtime.engine)
    async with admitted(runtime):
        found = await run_in_threadpool(_write_display_name, store, collection, value)
    if not found:
        return error_response(404, "Unknown collection.")
    return JSONResponse({"collection": collection, "display_name": value or None})
