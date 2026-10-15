"""Foundation routes: health, session, bearer credentials, roots and uploads.

Public routes are ``GET /v1/health`` and ``POST /v1/session`` (the
bootstrap exchange). Every other route declares its scope through
:func:`.security.require_scope`. Routes validate, delegate and format only.
"""

from __future__ import annotations

from typing import Annotated, Any
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ... import __version__
from ...core.experiments import ExperimentAdmissionError
from .errors import API_HEADERS, error_response
from .lifespan import AdmissionClosed, WebRuntime, get_runtime
from .security import AccessPolicy, Principal, require_scope
from .uploads import UploadRejected

router = APIRouter(prefix="/v1")

UPLOAD_NAME_HEADER = "X-Upload-Name"


class BootstrapRequest(BaseModel):
    """Body of ``POST /v1/session``."""

    bootstrap: str = Field(min_length=1, max_length=256)


class CredentialRequest(BaseModel):
    """Body of ``POST /v1/credentials``."""

    scopes: list[str] = Field(min_length=1, max_length=3)
    label: str = Field(default="", max_length=80)
    experiment_context: str | None = Field(default=None, min_length=1, max_length=64)


class UploadPreflightRequest(BaseModel):
    """Body of ``POST /v1/uploads/preflight``."""

    name: str = Field(max_length=1024)
    size: int | None = None


RuntimeDep = Annotated[WebRuntime, Depends(get_runtime)]
ReadScope = Annotated[Principal, Depends(require_scope("read"))]
FilesScope = Annotated[Principal, Depends(require_scope("files"))]
CredentialsScope = Annotated[Principal, Depends(require_scope("credentials"))]


def _policy(request: Request) -> AccessPolicy:
    return request.app.state.access_policy


# ── Public ─────────────────────────────────────────────────────────────


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Report liveness and the OMRG version. Public: it returns no workspace data."""
    runtime = getattr(request.app.state, "runtime", None)
    return {
        "status": "ok",
        "ready": runtime is not None and runtime.admission.is_open,
        "version": __version__,
    }


@router.post("/session")
async def create_session(body: BootstrapRequest, request: Request) -> JSONResponse:
    """Exchange the one-time bootstrap secret for a session cookie."""
    policy = _policy(request)
    if not policy.origin_allowed(request.headers.get("origin")):
        raise HTTPException(403, "Cross-origin request rejected.")
    token = policy.exchange_bootstrap(body.bootstrap)
    if token is None:
        raise HTTPException(
            401,
            "The bootstrap link is invalid or was already used. "
            "Restart `omrg web` to get a new link.",
        )
    response = JSONResponse({"status": "ok", "kind": "session"})
    response.set_cookie(
        policy.cookie_name, token, httponly=True, samesite="strict", path="/", secure=False
    )
    return response


# ── Session and credentials ────────────────────────────────────────────


@router.get("/session")
async def read_session(
    request: Request,
    principal: ReadScope,
) -> dict[str, Any]:
    """Describe the caller's credential kind, scopes and the workspace path.

    ``workspace`` is the canonical directory of the running server, or
    ``None`` while the runtime is not started.
    """
    runtime = getattr(request.app.state, "runtime", None)
    workspace = None if runtime is None else str(runtime.config.workspace.resolve())
    return {
        "status": "ok",
        "kind": principal.kind,
        "scopes": sorted(principal.scopes),
        "workspace": workspace,
    }


@router.post("/credentials", status_code=201)
async def issue_credential(
    body: CredentialRequest,
    request: Request,
    _: CredentialsScope,
) -> Any:
    """Issue a bearer credential for a notebook client. The token is shown once.

    With ``experiment_context`` the credential is bound to that active
    experiment context: it runs graphs only there and never reaches the
    live library.
    """
    if body.experiment_context is not None:
        refusal = _check_active_context(request, body.experiment_context)
        if refusal is not None:
            return refusal
    try:
        issued = _policy(request).issue_bearer(
            body.scopes, body.label, experiment_context=body.experiment_context
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None
    return {
        "status": "ok",
        "id": issued.id,
        "token": issued.token,
        "scopes": sorted(issued.scopes),
        "label": issued.label,
        "experiment_context": issued.experiment_context,
    }


def _check_active_context(request: Request, context_id: str) -> JSONResponse | None:
    """Return a 400 refusal unless *context_id* is an active experiment context."""
    runtime = getattr(request.app.state, "runtime", None)
    experiments = getattr(runtime, "experiments", None)
    try:
        if experiments is None:
            raise ExperimentAdmissionError(
                "experiment_context_unknown", "No experiment context has this id.", context_id
            )
        experiments.registry.require_active(context_id)
    except ExperimentAdmissionError as exc:
        return JSONResponse(exc.to_dict(), status_code=400, headers=API_HEADERS)
    return None


@router.get("/credentials")
async def list_credentials(request: Request, _: CredentialsScope) -> dict[str, Any]:
    """List bearer credentials without their secrets."""
    return {"status": "ok", "credentials": _policy(request).list_bearers()}


@router.delete("/credentials/{credential_id}")
async def revoke_credential(
    credential_id: str,
    request: Request,
    _: CredentialsScope,
) -> dict[str, Any]:
    """Revoke a bearer credential."""
    if not _policy(request).revoke_bearer(credential_id):
        raise HTTPException(404, "Unknown credential.")
    return {"status": "ok", "id": credential_id, "revoked": True}


# ── File grants and uploads ────────────────────────────────────────────


@router.get("/roots")
async def list_roots(
    runtime: RuntimeDep,
    _: FilesScope,
) -> dict[str, Any]:
    """List the operator-approved roots and the managed upload root."""
    return {"status": "ok", "roots": runtime.grants.describe()}


@router.post("/uploads/preflight")
async def preflight_upload(
    body: UploadPreflightRequest,
    runtime: RuntimeDep,
    _: FilesScope,
) -> Response:
    """Check a file name, type and size before the browser sends the bytes."""
    try:
        name = runtime.uploads.preflight(body.name, body.size, runtime.config.upload_extensions)
    except UploadRejected as exc:
        return error_response(exc.status_code, exc.message, error_type="validation")
    return JSONResponse({"status": "ok", "name": name, "max_bytes": runtime.uploads.max_bytes})


@router.post("/uploads", status_code=201)
async def upload_file(
    request: Request,
    runtime: RuntimeDep,
    _: FilesScope,
) -> Response:
    """Stream one raw file body into managed storage.

    The file name travels percent-encoded in the ``X-Upload-Name`` header,
    so it stays out of the access log.
    """
    raw_name = request.headers.get(UPLOAD_NAME_HEADER)
    if not raw_name:
        return error_response(400, f"The {UPLOAD_NAME_HEADER} header is required.")
    length = request.headers.get("content-length")
    try:
        size = int(length) if length is not None else None
    except ValueError:
        return error_response(400, "Invalid Content-Length header.")
    try:
        async with runtime.admission.enter():
            record = await runtime.uploads.receive(
                unquote(raw_name), request.stream(), size, runtime.config.upload_extensions
            )
    except UploadRejected as exc:
        return error_response(exc.status_code, exc.message, error_type="validation")
    except AdmissionClosed:
        return error_response(503, "The server is shutting down.")
    return JSONResponse({"status": "ok", "upload": record}, status_code=201)
