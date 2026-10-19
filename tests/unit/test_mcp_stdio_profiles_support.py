"""Helpers for the MCP tests on user-profile collections (unify-profiles, section 8).

The helpers start the stdio server through ``main()`` over a fake Engine, build
Engines whose collection carries a profile tag, and link a seeded workspace as
the default workspace of a temporary ``HOME``. This module holds no tests.
"""

from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from tests.unit.test_engine_pipelines_support import FakeStore, build_engine
from tests.unit.test_engine_profiles_support import COLLECTION, PROFILE, make_env
from tests.unit.test_profile_service import Env

from omrg.core.profiles.resolver import ProfileResolver

__all__ = [
    "COLLECTION",
    "PROFILE",
    "ListingStore",
    "build_web_server",
    "engine_builder",
    "file_digest",
    "link_default_workspace",
    "make_env",
    "start_stdio_server",
]


class ListingStore(FakeStore):
    """A fake store that lists its collections and applies metadata updates."""

    def list_collections(self) -> list[str]:
        """Return the names of the collections that hold metadata."""
        return sorted(self._metadata)

    def update_collection_metadata(self, name: str, updates: dict[str, Any]) -> None:
        """Merge ``updates`` into the collection metadata."""
        self._metadata.setdefault(name, {}).update(updates)

    def profile_tag(self, name: str) -> str | None:
        """Return the stored profile tag of a collection."""
        return self._metadata.get(name, {}).get("profile")


def engine_builder(
    settings: Any,
    rows: list[dict[str, Any]],
    tag: str | None,
    *,
    env_overrides: dict[str, str] | None = None,
    **engine_kwargs: Any,
) -> Callable[[Any], Any]:
    """Return ``build(catalogue)``: an Engine over ``rows`` that reads user profiles from it.

    The collection ``parity`` carries the profile ``tag``. The Engine keeps its
    store on ``engine.test_store`` so a test can read the stored tag.
    """

    def build(catalogue: Any) -> Any:
        store = ListingStore(rows, metadata={COLLECTION: {"profile": tag} if tag else {}})
        resolver = ProfileResolver(
            store=store,
            server_profile="documents",
            base=settings,
            env_overrides=env_overrides or {},
            catalogue=catalogue,
        )
        engine = build_engine(settings, store, profile_resolver=resolver, **engine_kwargs)
        engine.test_store = store
        return engine

    return build


def build_web_server(engine: Any, profiles: Any) -> Any:
    """Build the MCP server as the web endpoint does: the context carries the profile service."""
    from omrg.transports.mcp import create_mcp_server
    from omrg.transports.mcp.context import McpContext, PathPolicy, no_admission

    context = McpContext(engine, PathPolicy.allow_all(), no_admission, profiles=profiles)

    @asynccontextmanager
    async def lifespan(_server: Any) -> AsyncIterator[McpContext]:
        yield context

    server = create_mcp_server(lifespan)
    server.test_context = context
    return server


def link_default_workspace(home: Path, env: Env) -> Path:
    """Make the workspace folder of ``env`` the default workspace of ``home``.

    The folder is linked, so the database file is the one ``env`` seeded.

    Returns:
        The database file as the default workspace shows it.
    """
    folder = home / ".omrg"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "workspace").symlink_to(env.catalogue.path.parent, target_is_directory=True)
    return folder / "workspace" / "workspace.db"


def file_digest(path: Path) -> str:
    """Return the SHA-256 digest of the bytes of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def start_stdio_server(build: Callable[[Any], Any]) -> tuple[Any, dict[str, Any]]:
    """Run the stdio ``main()`` over the Engine that ``build(catalogue)`` returns.

    ``main()`` calls ``compose.build_engine``; the fake passes the catalogue
    that ``main()`` chose to ``build`` and keeps the keyword arguments it saw.
    The stdio transport itself does not start.

    Returns:
        The real MCP server that ``main()`` built, and a dict with the keys
        ``catalogue`` (what ``main()`` passed), ``engine`` and ``kwargs``.
    """
    from omrg.transports import mcp as mcp_package

    seen: dict[str, Any] = {}
    real_factory = mcp_package.create_mcp_server

    def fake_build_engine(*args: Any, **kwargs: Any) -> Any:
        seen["kwargs"] = kwargs
        seen["catalogue"] = kwargs.get("catalogue")
        seen["engine"] = build(seen["catalogue"])
        return seen["engine"]

    def fake_create_server(lifespan: Any) -> Any:
        seen["server"] = real_factory(lifespan)
        return SimpleNamespace(run=lambda **_: None)

    with (
        patch("omrg.transports.mcp.compose.build_engine", side_effect=fake_build_engine),
        patch("omrg.transports.mcp.create_mcp_server", side_effect=fake_create_server),
        patch("logging.basicConfig"),
    ):
        mcp_package.main()
    return seen["server"], seen
