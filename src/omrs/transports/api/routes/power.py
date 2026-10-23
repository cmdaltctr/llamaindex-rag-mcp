"""Power control routes: ``GET`` and ``POST /v1/server/power`` (design D2 to D4, D8).

Both routes need the browser session with the ``manage`` scope. A bearer
credential never passes. ``POST`` takes a closed choice of two
actions and answers 422 to any other value, so no free text reaches a
launchctl argv.

``GET`` reports ``managed``: true only when the app runs as the login item,
which ``cli/web.py`` states by setting ``application.state.power_control``.
``POST`` answers 409 and changes nothing when the app is not managed or
when work is running. Otherwise it answers 202 and acts after the response
has been sent, so the answer and the browser's next poll leave before the
process ends.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from starlette.background import BackgroundTask

from ..engine_access import RuntimeDep, require_session
from ..errors import error_response
from ..lifespan import WebRuntime
from ..power_control import ACTIONS, PowerControl
from ..security import Principal
from .graphs import ok

router = APIRouter(prefix="/v1")

ManageScope = Annotated[Principal, Depends(require_session("manage"))]

NOT_MANAGED = "This server does not run as the login item, so it cannot restart or turn itself off."
BUSY = "Work is running. Wait until it finishes, then try again."
BAD_ACTION = 'The action must be "restart" or "off".'


class PowerBody(BaseModel):
    """Body of ``requestServerPower`` (schema ``PowerRequest``).

    ``action`` is a plain string here so that a well-formed body with an
    unknown action reaches the route and gets 422 (see :data:`ACTIONS`).
    A body of the wrong shape fails framework validation with 400, as on
    every other route.
    """

    model_config = ConfigDict(extra="forbid")

    action: str = Field(max_length=32)


def _control(request: Request) -> PowerControl | None:
    """Return the power control that ``omrs web --login-item`` set, if any."""
    return getattr(request.app.state, "power_control", None)


def _is_busy(runtime: WebRuntime) -> bool:
    """Return whether admitted work, a running graph or a waiting run exists.

    Ingestion and map jobs run through the run service. Other engine calls
    hold admission. The run service may be absent or a test double, so its
    counters are read with ``getattr``.
    """
    if runtime.admission.active:
        return True
    service = getattr(runtime.run_service, "service", None)
    if service is None:
        return False
    return getattr(service, "active_run_id", None) is not None or bool(
        getattr(service, "waiting_count", 0)
    )


@router.get("/server/power", operation_id="getServerPower")
async def get_power(_: ManageScope, request: Request) -> Response:
    """Report whether the app can restart or turn itself off."""
    return ok({"managed": _control(request) is not None})


@router.post("/server/power", operation_id="requestServerPower")
async def request_power(
    _: ManageScope, body: PowerBody, request: Request, runtime: RuntimeDep
) -> Response:
    """Restart the app or turn it off, after the response has been sent."""
    action = body.action
    if action not in ACTIONS:
        return error_response(422, BAD_ACTION, error_type="validation")
    control = _control(request)
    if control is None:
        return error_response(409, NOT_MANAGED)
    if _is_busy(runtime):
        return error_response(409, BUSY)
    response = ok({"action": action}, 202)
    response.background = BackgroundTask(control.act, action)
    return response
