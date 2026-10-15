"""FastAPI application factory for the local web workspace.

:func:`create_app` wires the request guard, error envelope, foundation
routes, the lifespan that owns the Engine, and the frontend fallback.
Later route groups add their ``APIRouter`` to :data:`API_ROUTERS`; the
fallback runs only when no route matched, so it cannot shadow them.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, FastAPI

from ... import __version__
from .errors import install_error_handlers
from .lifespan import RunServiceFactory, WebConfig, build_lifespan, default_engine_factory
from .log_buffer import LogBuffer
from .mcp_http import build_mcp_http
from .middleware import GuardMiddleware
from .routes import router as foundation_router
from .routes_admin import router as admin_router
from .routes_connections import router as connections_router
from .routes_documents import router as documents_router
from .routes_experiments import router as experiments_router
from .routes_graphs import router as graphs_router
from .routes_inspect import router as inspect_router
from .routes_integrations import router as integrations_router
from .routes_jobs import router as jobs_router
from .routes_logs import router as logs_router
from .routes_mcp import router as mcp_router
from .routes_plugins import router as plugins_router
from .routes_runs import router as runs_router
from .routes_templates import router as templates_router
from .security import AccessPolicy, validate_bind_host
from .static import FrontendFallback

#: Route groups registered on every application, in order.
API_ROUTERS: tuple[APIRouter, ...] = (
    foundation_router,
    documents_router,
    jobs_router,
    inspect_router,
    admin_router,
    graphs_router,
    runs_router,
    experiments_router,
    templates_router,
    plugins_router,
    mcp_router,
    integrations_router,
    connections_router,
    logs_router,
)


def create_app(
    config: WebConfig,
    *,
    policy: AccessPolicy | None = None,
    engine_factory: Callable[[], Any] | None = None,
    run_service_factory: RunServiceFactory | None = None,
    log_buffer: LogBuffer | None = None,
) -> FastAPI:
    """Build the web application for one launch.

    Nothing heavy happens here: the Engine is built in the lifespan.

    Args:
        config: Launch options; ``config.host`` must be a loopback address.
        policy: Access policy; a fresh per-launch policy when omitted.
        engine_factory: Builds the owned Engine (default: ``compose.build_engine``).
        run_service_factory: Optional run-service hook started and drained
            by the lifespan.
        log_buffer: The ring buffer ``omrg web`` attached to the root logger.
            Without one the log routes serve an empty log.

    Returns:
        The configured FastAPI application.

    Raises:
        ValueError: ``config.host`` is not a loopback address.
    """
    host = validate_bind_host(config.host)
    if policy is None:
        policy = AccessPolicy.for_launch(host, config.port)
    app = FastAPI(
        title="OMRG local workspace",
        version=__version__,
        lifespan=build_lifespan(
            config,
            engine_factory=engine_factory or default_engine_factory,
            run_service_factory=run_service_factory,
        ),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.access_policy = policy
    app.state.runtime = None
    app.state.log_buffer = log_buffer if log_buffer is not None else LogBuffer()
    install_error_handlers(app)
    for router in API_ROUTERS:
        app.include_router(router)
    app.state.mcp_http = build_mcp_http(app, config, policy)
    app.router.default = FrontendFallback(config.static_dir)
    app.add_middleware(GuardMiddleware, policy=policy)
    return app
