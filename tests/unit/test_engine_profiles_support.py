"""Helpers for the Engine tests on user-profile collections (unify-profiles, section 5).

The helpers build an Engine whose collection carries a profile tag and whose
profile resolver reads user profiles from a workspace catalogue. This module
holds no tests.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.unit.test_engine_pipelines_support import FakeStore, build_engine
from tests.unit.test_profile_service import Env

from omrg.core.profiles.resolver import ProfileResolver

COLLECTION = "parity"
PROFILE = "my-notes"


def make_env(tmp_path: Path, effective_settings: Any, reranker: Any = None) -> Env:
    """Return a workspace that holds the user profile ``my-notes`` (a duplicate of documents).

    The duplicate is built on an Engine with ``reranker``, as the web server would build it,
    so its rerank step is enabled exactly when that Engine has a reranker.
    """
    env = Env(tmp_path, effective_settings, reranker=reranker)
    env.service.create_profile("My notes", source="documents")
    return env


def resolver_for(
    env: Env, store: Any, settings: Any, env_overrides: dict[str, str] | None = None
) -> ProfileResolver:
    """Return a resolver over ``store`` that reads user profiles from ``env``."""
    return ProfileResolver(
        store=store,
        server_profile="documents",
        base=settings,
        env_overrides=env_overrides or {},
        catalogue=env.catalogue,
    )


def tagged_engine(
    env: Env,
    settings: Any,
    rows: list[dict[str, Any]],
    tag: str | None,
    *,
    env_overrides: dict[str, str] | None = None,
    **kwargs: Any,
) -> Any:
    """Return an Engine over ``rows`` whose collection ``parity`` carries the profile ``tag``."""
    store = FakeStore(rows, metadata={COLLECTION: {"profile": tag} if tag else {}})
    resolver = resolver_for(env, store, settings, env_overrides)
    return build_engine(settings, store, profile_resolver=resolver, **kwargs)


def slot_graph(env: Env, slot: str, profile_id: str = PROFILE) -> dict[str, Any]:
    """Return the current graph of one slot pipeline of a user profile."""
    return env.graph(env.service.get_profile(profile_id), slot)


def save_slot(env: Env, slot: str, graph: dict[str, Any], profile_id: str = PROFILE) -> None:
    """Save a new revision of one slot pipeline."""
    env.save(env.service.get_profile(profile_id), slot, graph)


def count_graph_runs(engine: Any) -> list[str]:
    """Wrap ``engine.run_pipeline`` and return a list that gets one entry per graph run."""
    runs: list[str] = []
    original = engine.run_pipeline

    async def counted(definition: Any, *args: Any, **kwargs: Any) -> Any:
        runs.append("run_pipeline")
        return await original(definition, *args, **kwargs)

    engine.run_pipeline = counted
    return runs
