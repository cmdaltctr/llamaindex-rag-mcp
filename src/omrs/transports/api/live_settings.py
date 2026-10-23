"""Live reload of ``omrs.jsonc`` in the running web server (ADR-087, D7).

Before a request, :func:`reload_if_changed` compares the file stamp
``(st_mtime_ns, st_size, st_ino)`` with the one :class:`~.provider_state.ProviderState`
read last. A stat costs microseconds, so there is no watcher thread. On a
change the state re-reads the file under its own lock, and these values swap
in at once:

- provider addresses, keys, the Chat choice, context windows and the llama.cpp
  server values (through ``ProviderState``);
- the per-file upload limit, unless a launch option set it;
- the MCP over HTTP switch.

Engine settings and ``web_port`` need a restart and are not touched here.
A broken file gives no file values, so the defaults apply until it is fixed.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI
from fastapi.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from ...config.settings_file import SettingsFile
from .uploads import MIB

logger = logging.getLogger(__name__)

#: Source words of the per-file upload limit.
LAUNCH, CONFIG_FILE, DEFAULT = "launch", "config-file", "default"


def upload_limit(config: Any, saved_mib: int | None) -> tuple[int, str]:
    """Return the upload limit in bytes and its source: the file value, else the default.

    A launch option is handled by the caller, because it wins and locks the limit.
    """
    if saved_mib is not None:
        return saved_mib * MIB, CONFIG_FILE
    return config.max_upload_bytes, DEFAULT


def initial_upload_limit(config: Any, store: Any | None) -> tuple[int, str]:
    """Return the launch upload limit: launch option, then the file value, then the default."""
    if config.launch_upload_limit_mib is not None:
        return config.launch_upload_limit_mib * MIB, LAUNCH
    saved = None if store is None else store.read().values.get("web_max_upload_mib")
    return upload_limit(config, saved if isinstance(saved, int) else None)


def apply_file_settings(app: FastAPI, runtime: Any, file: SettingsFile) -> None:
    """Swap in the settings of *file* that apply at once and are not provider values."""
    http = getattr(app.state, "mcp_http", None)
    if http is not None:
        http.enabled = file.values.get("mcp_http_enabled") is True
    if runtime.upload_limit_source != LAUNCH:
        saved = file.values.get("web_max_upload_mib")
        runtime.uploads.max_bytes, runtime.upload_limit_source = upload_limit(
            runtime.config, saved if isinstance(saved, int) else None
        )


async def reload_if_changed(app: FastAPI) -> None:
    """Re-read ``omrs.jsonc`` when its stamp changed since the last read."""
    runtime = getattr(app.state, "runtime", None)
    state = getattr(runtime, "providers", None)
    if state is None or not state.file_changed():
        return
    async with state.lock:
        if not state.file_changed():
            return  # another request reloaded while this one waited
        file = await run_in_threadpool(state.reload, runtime.engine)
        apply_file_settings(app, runtime, file)


class LiveSettingsMiddleware:
    """Pure ASGI middleware that calls :func:`reload_if_changed` before each HTTP request."""

    def __init__(self, app: ASGIApp) -> None:
        """Wrap *app*."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Reload when the file changed, then pass the request on. A failed reload is logged."""
        if scope["type"] == "http":
            try:
                await reload_if_changed(scope["app"])
            except Exception:
                logger.exception("omrs.jsonc could not be reloaded; the old values stay.")
        await self.app(scope, receive, send)
