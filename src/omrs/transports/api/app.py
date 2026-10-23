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
from ...integrations.keychain import KeychainStore
from .bind_address import validate_bind_host
from .errors import install_error_handlers
from .lifespan import RunServiceFactory, WebConfig, build_lifespan, default_engine_factory
from .live_settings import LiveSettingsMiddleware
from .llamacpp_server import LlamacppServer, owning_lifespan
from .log_buffer import LogBuffer
from .mcp_http import build_mcp_http
from .middleware import GuardMiddleware
from .page_secret import PageSecret
from .routes.admin import router as admin_router
from .routes.answer_stream import router as answer_stream_router
from .routes.chat_reasoning import router as chat_reasoning_router
from .routes.chat_settings import router as chat_settings_router
from .routes.chats import router as chats_router
from .routes.configuration import router as configuration_router
from .routes.connections import router as connections_router
from .routes.document_reading import router as document_reading_router
from .routes.documents import router as documents_router
from .routes.embedding import router as embedding_router
from .routes.experiments import router as experiments_router
from .routes.foundation import router as foundation_router
from .routes.graphs import router as graphs_router
from .routes.inspection import router as inspect_router
from .routes.integrations import router as integrations_router
from .routes.jobs import router as jobs_router
from .routes.judge_settings import router as judge_settings_router
from .routes.llamacpp_server import router as llamacpp_server_router
from .routes.logs import router as logs_router
from .routes.mcp import router as mcp_router
from .routes.plugins import router as plugins_router
from .routes.power import router as power_router
from .routes.profiles import router as profiles_router
from .routes.runs import router as runs_router
from .routes.templates import router as templates_router
from .routes.usage_credit import router as usage_credit_router
from .security import AccessPolicy, SecretSet
from .static import FrontendFallback

#: Route groups registered on every application, in order.
API_ROUTERS: tuple[APIRouter, ...] = (
    foundation_router,
    documents_router,
    answer_stream_router,
    jobs_router,
    inspect_router,
    admin_router,
    graphs_router,
    profiles_router,
    chats_router,
    chat_settings_router,
    chat_reasoning_router,
    judge_settings_router,
    usage_credit_router,
    configuration_router,
    document_reading_router,
    embedding_router,
    runs_router,
    experiments_router,
    templates_router,
    plugins_router,
    mcp_router,
    integrations_router,
    connections_router,
    llamacpp_server_router,
    logs_router,
    power_router,
)


def _default_factory(config: WebConfig) -> Callable[..., Any]:
    """Return the factory that builds the Engine with the catalogue of this workspace.

    The catalogue reads user profiles from the workspace database of the server,
    so a collection tagged with a user profile resolves in this process.
    """

    def factory(provider_source: Any = None) -> Any:
        from ...core.workspace import WorkspaceLayout
        from ...integrations.workspace_sqlite import SqliteProfileCatalogue

        return default_engine_factory(
            SqliteProfileCatalogue(WorkspaceLayout(config.workspace).records),
            provider_source=provider_source,
        )

    return factory


def create_app(
    config: WebConfig,
    *,
    policy: AccessPolicy | None = None,
    engine_factory: Callable[..., Any] | None = None,
    run_service_factory: RunServiceFactory | None = None,
    log_buffer: LogBuffer | None = None,
    secrets: SecretSet | None = None,
    keychain: Any | None = None,
    page_secret: PageSecret | None = None,
) -> FastAPI:
    """Build the web application for one launch.

    Nothing heavy happens here: the Engine is built in the lifespan.

    Args:
        config: Launch options; ``config.host`` must be a loopback address.
        policy: Access policy; a fresh per-launch policy when omitted.
        engine_factory: Builds the owned Engine (default: ``compose.build_engine`` with
            the profile catalogue of ``config.workspace``).
        run_service_factory: Optional run-service hook started and drained
            by the lifespan.
        secrets: Secret values to remove from logs and answer errors. Without
            one the app uses the log buffer's set.
        keychain: Stores provider keys (default: the system keychain). Tests
            pass a fake so no real keychain is read.
        log_buffer: The ring buffer ``omrs web`` attached to the root logger.
            Without one the log routes serve an empty log.
        page_secret: The workspace sign-in secret that the page carries.
            Without one the page signs in only with a launch link.

    Returns:
        The configured FastAPI application.

    Raises:
        ValueError: ``config.host`` is not a loopback address.
    """
    host = validate_bind_host(config.host)
    if policy is None:
        policy = AccessPolicy.for_launch(host, config.port)
    if engine_factory is None:
        engine_factory = _default_factory(config)
    app = FastAPI(
        title="OMRS local workspace",
        version=__version__,
        lifespan=owning_lifespan(
            build_lifespan(
                config,
                engine_factory=engine_factory,
                run_service_factory=run_service_factory,
            )
        ),
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.state.access_policy = policy
    app.state.page_secret = page_secret
    app.state.runtime = None
    app.state.log_buffer = (
        log_buffer if log_buffer is not None else LogBuffer(secrets if secrets is not None else ())
    )
    app.state.secrets = secrets if secrets is not None else app.state.log_buffer.secrets
    app.state.keychain = keychain if keychain is not None else KeychainStore()
    app.state.llamacpp_server = LlamacppServer(config.workspace / "llamacpp-server.log")
    install_error_handlers(app)
    for router in API_ROUTERS:
        app.include_router(router)
    app.state.mcp_http = build_mcp_http(app, config, policy)
    app.router.default = FrontendFallback(config.static_dir, policy=policy, page_secret=page_secret)
    app.add_middleware(LiveSettingsMiddleware)  # inside the guard: only allowed requests reload
    app.add_middleware(GuardMiddleware, policy=policy)
    return app
