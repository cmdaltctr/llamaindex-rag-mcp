"""Provider connections: read-only summary and an on-request test (design D13).

``GET /v1/connections`` shows the LLM registry providers from the server's
settings. It sends no request to any provider. ``POST
/v1/connections/{provider}/test`` sends one model-list request and needs
the browser session. Neither route returns a key, a response body or
exception text. Editing is outside this change.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response

from ... import compose
from ...compose_connections import PROVIDERS
from .connection_probe import probe
from .engine_access import ReadScope, RuntimeDep, admitted
from .errors import error_response
from .routes_experiments import ManageScope
from .routes_graphs import ok

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1")


@router.get("/connections", operation_id="getConnections")
async def get_connections(_: ReadScope, runtime: RuntimeDep) -> Response:
    """Return `config_dir` and one entry for each of ollama, llamacpp and openrouter.

    Each entry has the endpoint URLs, configured model names, `key_set` and
    the roles that use the provider. The key value never leaves the server.
    """
    async with admitted(runtime):
        summary = await run_in_threadpool(compose.connection_summary)
    return ok(summary)


@router.post("/connections/{provider}/test", operation_id="testConnection")
async def test_connection(_: ManageScope, provider: str, runtime: RuntimeDep) -> Response:
    """Send one model-list request to *provider* and report `{reachable, reason}`.

    This is the only route that contacts a provider, and only when called.
    """
    if provider not in PROVIDERS:
        return error_response(404, "Unknown provider.")
    async with admitted(runtime):
        target = (await run_in_threadpool(compose.connection_targets))[provider]
        result = await probe(target.urls, target.headers)
    logger.info("Connection test for %s: %s", provider, result["reason"] or "reachable")
    return ok(result)
