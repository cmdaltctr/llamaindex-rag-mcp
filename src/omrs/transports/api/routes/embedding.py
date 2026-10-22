"""Embedding provider and profile model routes (add-profile-embedding-model, ADR-081, D10).

* ``GET /v1/embedding-providers`` lists the registered embedding providers,
  whether each can be built, and the server default model.
* ``POST /v1/embedding-providers/{provider}/check`` embeds one probe text with
  a throwaway embedder. A failed check is 200 with ``ok: false`` and a reason.
* ``PUT /v1/profiles/{profile_id}/embedding`` checks and saves the embedding
  model of a user profile. A bound collection that holds vectors locks the model
  (409 ``embedding_locked``). A failed check is 422 with the reason.

The routes hold no embedding logic: the composition root (``compose_embedding``
and the profile service) decides, and errors pass through ``Engine.redact``.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from .... import compose_embedding
from ....compose_profile_embedding import EmbeddingCheckFailedError, EmbeddingLockedError
from ....compose_profiles import BuiltinProfileError, UnknownProfileError
from ..engine_access import ReadScope, RuntimeDep, admitted
from ..errors import API_HEADERS, error_response
from .experiments import ManageScope
from .graphs import ok
from .profiles import ProfilesDep

router = APIRouter(prefix="/v1")


class CheckModelBody(BaseModel):
    """Body of ``POST /v1/embedding-providers/{provider}/check`` (``EmbeddingCheckRequest``)."""

    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=512)


class ProfileEmbeddingBody(BaseModel):
    """Body of ``PUT /v1/profiles/{profile_id}/embedding`` (``ProfileEmbeddingRequest``).

    Both values set choose a model. Both ``null`` return to the server default.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str | None = Field(max_length=64)
    model: str | None = Field(max_length=512)


@router.get("/embedding-providers", operation_id="listEmbeddingProviders")
async def list_embedding_providers(_: ReadScope, runtime: RuntimeDep) -> Response:
    """List the embedding providers and the server default model."""

    def read() -> dict:
        default = compose_embedding.server_default_identity()
        return {
            "providers": compose_embedding.provider_listing(),
            "server_default": {"provider": default.provider, "model": default.model},
        }

    async with admitted(runtime):
        return ok(await run_in_threadpool(read))


@router.post("/embedding-providers/{provider}/check", operation_id="checkEmbeddingModel")
async def check_embedding_model(
    _: ManageScope, provider: str, body: CheckModelBody, runtime: RuntimeDep
) -> Response:
    """Embed one probe text with *provider* and the model, and report the vector."""
    redactor = runtime.engine.redact
    try:
        async with admitted(runtime):
            result = await run_in_threadpool(
                lambda: compose_embedding.check_embedding_model(
                    provider, body.model, redact=redactor
                )
            )
    except compose_embedding.UnknownEmbeddingProviderError as exc:
        return error_response(404, str(exc), redactor=redactor)
    return ok(result)


@router.put("/profiles/{profile_id}/embedding", operation_id="setProfileEmbedding")
async def set_profile_embedding(
    _: ManageScope,
    profile_id: str,
    body: ProfileEmbeddingBody,
    runtime: RuntimeDep,
    profiles: ProfilesDep,
) -> Response:
    """Check and save the embedding model of a user profile."""
    redactor = runtime.engine.redact
    try:
        async with admitted(runtime):
            item = await run_in_threadpool(
                profiles.set_embedding, profile_id, body.provider, body.model
            )
    except UnknownProfileError as exc:
        return error_response(404, str(exc), redactor=redactor)
    except compose_embedding.UnknownEmbeddingProviderError as exc:
        return error_response(404, str(exc), redactor=redactor)
    except BuiltinProfileError as exc:
        return error_response(400, str(exc), error_type="validation", redactor=redactor)
    except EmbeddingLockedError as exc:
        locked = {
            "status": "error",
            "message": redactor(str(exc)),
            "error_type": "embedding_locked",
            "collections": exc.collections,
        }
        return JSONResponse(locked, status_code=409, headers=API_HEADERS)
    except EmbeddingCheckFailedError as exc:
        reason = redactor(exc.reason)
        failed = {"status": "error", "message": reason, "reason": reason}
        return JSONResponse(failed, status_code=422, headers=API_HEADERS)
    except ValueError as exc:
        return error_response(400, str(exc), error_type="validation", redactor=redactor)
    return ok({"profile": item})
