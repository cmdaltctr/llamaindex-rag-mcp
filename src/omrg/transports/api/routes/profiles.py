"""Profile routes: list, create, read, rename and delete (unify-profiles-and-pipelines, D1 to D7).

A profile is a built-in profile (``documents``, ``codebase``) or a user profile
that owns three pipelines: Ingest, Search and Answer. The routes delegate to
:class:`omrg.compose_profiles.ProfileService`. They hold no profile logic.

* ``GET /v1/profiles`` lists built-in and user profiles with readiness and
  ``used_by``.
* ``POST /v1/profiles`` makes a user profile from a built-in, from a user
  profile, or empty.
* ``GET /v1/profiles/{profile_id}`` reads one profile. A built-in carries
  ``standard_graphs``.
* ``PATCH /v1/profiles/{profile_id}`` changes the title and the description.
* ``DELETE /v1/profiles/{profile_id}`` soft-deletes a profile that no
  collection uses.
"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from ....compose_profiles import (
    BuiltinProfileError,
    ProfileInUseError,
    ProfileNotReadyError,
    UnknownProfileError,
)
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import API_HEADERS, error_response
from ..lifespan import WebRuntime
from ..security import Principal, require_scope
from .graphs import ok

router = APIRouter(prefix="/v1")

GraphScope = Annotated[Principal, Depends(require_scope("graph"))]


class CreateProfileBody(BaseModel):
    """Body of ``POST /v1/profiles`` (schema ``ProfileCreateRequest``)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(max_length=4096)
    description: str | None = Field(default=None, max_length=1000)
    source: str | None = Field(default=None, max_length=128)


class UpdateProfileBody(BaseModel):
    """Body of ``PATCH /v1/profiles/{profile_id}`` (schema ``ProfileUpdateRequest``)."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, max_length=4096)
    description: str | None = Field(default=None, max_length=1000)


def get_profiles(runtime: RuntimeDep) -> Any:
    """Route dependency returning the launch's profile service.

    Raises:
        HTTPException: 503 when the server has no profile service.
    """
    if runtime.profiles is None:
        raise HTTPException(503, "Profiles are not available in this server.")
    return runtime.profiles


ProfilesDep = Annotated[Any, Depends(get_profiles)]


def refusal(runtime: WebRuntime, exc: Exception) -> Response:
    """Map a profile service error to its status and envelope.

    Args:
        runtime: The running runtime (its Engine redacts the message).
        exc: A :mod:`omrg.compose_profiles` error or a ``ValueError``.
    """
    redactor = runtime.engine.redact
    if isinstance(exc, UnknownProfileError):
        return error_response(404, str(exc), redactor=redactor)
    if isinstance(exc, BuiltinProfileError):
        return error_response(403, str(exc), redactor=redactor)
    if isinstance(exc, ProfileInUseError):
        body = {"status": "error", "message": str(exc), "used_by": exc.used_by}
        return JSONResponse(body, status_code=409, headers=API_HEADERS)
    if isinstance(exc, ProfileNotReadyError):
        body = {
            "status": "error",
            "message": str(exc),
            "error_type": "validation",
            "not_ready_reasons": exc.reasons,
        }
        return JSONResponse(body, status_code=400, headers=API_HEADERS)
    return error_response(400, str(exc), error_type="validation", redactor=redactor)


@router.get("/profiles", operation_id="listProfiles")
async def list_profiles(_: ReadScope, runtime: RuntimeDep, profiles: ProfilesDep) -> Response:
    """List built-in profiles, then user profiles that are not deleted."""
    async with admitted(runtime):
        items = await run_in_threadpool(profiles.list_profiles)
    return ok({"profiles": items})


@router.post("/profiles", status_code=201, operation_id="createProfile")
async def create_profile(
    _: GraphScope, body: CreateProfileBody, runtime: RuntimeDep, profiles: ProfilesDep
) -> Response:
    """Create a user profile from a built-in, from a user profile, or empty."""
    try:
        async with admitted(runtime):
            item = await run_in_threadpool(
                lambda: profiles.create_profile(
                    body.title, source=body.source, description=body.description
                )
            )
    except (UnknownProfileError, ValueError) as exc:
        return refusal(runtime, exc)
    return ok({"profile": item}, 201)


@router.get("/profiles/{profile_id}", operation_id="getProfile")
async def get_profile(
    _: ReadScope, profile_id: str, runtime: RuntimeDep, profiles: ProfilesDep
) -> Response:
    """Return one profile. A built-in carries ``standard_graphs``."""
    try:
        async with admitted(runtime):
            item = await run_in_threadpool(profiles.get_profile, profile_id)
    except UnknownProfileError as exc:
        return refusal(runtime, exc)
    return ok({"profile": item})


@router.patch("/profiles/{profile_id}", operation_id="updateProfile")
async def update_profile(
    _: GraphScope,
    profile_id: str,
    body: UpdateProfileBody,
    runtime: RuntimeDep,
    profiles: ProfilesDep,
) -> Response:
    """Change the title or the description of a user profile. The id never changes."""
    if body.title is None and body.description is None:
        return error_response(400, "Send a title or a description.", error_type="validation")
    try:
        async with admitted(runtime):
            item = await run_in_threadpool(
                lambda: profiles.rename_profile(
                    profile_id, title=body.title, description=body.description
                )
            )
    except (UnknownProfileError, ValueError) as exc:
        return refusal(runtime, exc)
    return ok({"profile": item})


@router.delete("/profiles/{profile_id}", operation_id="deleteProfile")
async def delete_profile(
    _: GraphScope, profile_id: str, runtime: RuntimeDep, profiles: ProfilesDep
) -> Response:
    """Soft-delete a user profile that no collection uses."""
    try:
        async with admitted(runtime):
            item = await run_in_threadpool(profiles.delete_profile, profile_id)
    except (UnknownProfileError, ValueError) as exc:
        return refusal(runtime, exc)
    return ok({"profile": item})
