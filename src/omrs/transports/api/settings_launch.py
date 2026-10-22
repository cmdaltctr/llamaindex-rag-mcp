"""Settings work that runs once at web launch (ADR-087).

Moves any saved database rows into ``omrs.jsonc`` and records what the
Configuration endpoint needs: the launch snapshot of restart-only values and the
handover notice. It lives apart from ``lifespan.py``, which holds the 500-line
limit.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ... import compose
from ...config.settings_file import read_settings_file
from ...integrations.workspace_sqlite.settings import WorkspaceSettings
from ..settings_view import FILE_ONLY_DEFAULTS
from .restart_snapshot import capture
from .settings_handover import run_handover

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

DEFAULT_WEB_PORT = FILE_ONLY_DEFAULTS["web_port"]


def prepare_settings(app: FastAPI, records: Path, bound_port: int) -> None:
    """Hand over saved rows and publish ``app.state.configuration``.

    Runs before ``McpHttp.prepare`` and ``load_providers`` so both read the file
    after the handover. Blocking: call it with ``asyncio.to_thread``. It never
    raises; a failure leaves the rows where they are and the page without a
    snapshot.

    Args:
        app: The web application. ``app.state.keychain`` is read.
        records: The workspace database file.
        bound_port: The port this launch listens on.
    """
    from .routes.configuration import ConfigurationState  # lazy: the route needs the lifespan

    keychain = getattr(app.state, "keychain", None)
    try:
        handover = run_handover(WorkspaceSettings(records), keychain)
        file = read_settings_file()
        overrides: dict[str, tuple[Any, str]] = {}
        if file.values.get("web_port", DEFAULT_WEB_PORT) != bound_port:
            overrides["web_port"] = (bound_port, "init")
        app.state.configuration = ConfigurationState(
            launch_settings=compose.get_settings(),
            snapshot=capture(file),
            handover=handover,
            overrides=overrides,
        )
    except Exception:
        logger.exception("The settings handover could not run; the rows stay in the database.")
