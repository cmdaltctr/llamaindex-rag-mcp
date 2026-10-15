"""Integration catalogue route (design D7).

``GET /v1/integrations`` shows which optional integrations the running
server can use. It reads the runtime probes only. It never installs,
downloads or changes a package.
"""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from .engine_access import ReadScope, RuntimeDep, admitted
from .integrations_catalogue import describe_integrations
from .routes_graphs import ok

router = APIRouter(prefix="/v1")


@router.get("/integrations", operation_id="listIntegrations")
async def list_integrations(_: ReadScope, runtime: RuntimeDep) -> Response:
    """List every installable integration with its availability in this launch.

    The probes may import optional packages, so they run off the event
    loop. A probe that fails gives the ``unknown`` state for that entry.
    """
    async with admitted(runtime):
        try:
            settings = runtime.engine.resolve_settings()
        except Exception:
            settings = None
        entries = await run_in_threadpool(describe_integrations, settings)
    return ok({"integrations": entries})
