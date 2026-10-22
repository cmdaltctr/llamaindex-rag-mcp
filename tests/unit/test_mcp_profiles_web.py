"""MCP profile tools on the web server's endpoint (D11, tasks 8.3 and 8.7).

The endpoint passes the profile service to the tools. ``list_profiles`` shows
the items of ``GET /v1/profiles``. ``change_collection_profile`` binds a ready
user profile, with the same checks as the web route.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_mcp_stdio_profiles_support import (
    COLLECTION,
    PROFILE,
    build_web_server,
    engine_builder,
    make_env,
)

from conftest import direct_ctx
from omrs.core.vectordb.identity import IDENTITY_MODEL_KEY, IDENTITY_PROVIDER_KEY
from omrs.transports.mcp import change_collection_profile, list_profiles


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any) -> tuple[Any, Any, Any]:
    """Return the profile env, the web MCP server and its Engine over a documents collection."""
    env = make_env(tmp_path / "seed", effective_settings)
    env.tags[COLLECTION] = "documents"
    engine = engine_builder(effective_settings(), [], "documents")(env.catalogue)
    return env, build_web_server(engine, env.service), engine


async def test_list_profiles_returns_the_items_of_the_profile_service(web: Any) -> None:
    env, server, _ = web
    env.tags[COLLECTION] = PROFILE
    items = await list_profiles(ctx=direct_ctx(server))
    assert items == env.service.list_profiles()
    assert [i["profile_id"] for i in items] == ["documents", "codebase", PROFILE]
    assert items[2]["used_by"] == [COLLECTION]


async def test_a_ready_user_profile_previews_without_changing_the_tag(web: Any) -> None:
    _, server, engine = web
    result = await change_collection_profile(
        collection=COLLECTION, profile=PROFILE, confirm=False, ctx=direct_ctx(server)
    )
    assert result["status"] == "preview" and result["confirm_required"] is True, result
    assert result["contract"]["new_profile"] == PROFILE
    assert [p["slot"] for p in result["contract"]["pipelines"]] == ["ingest", "search", "answer"]
    assert engine.test_store.profile_tag(COLLECTION) == "documents"


async def test_a_ready_user_profile_binds_on_confirm(web: Any) -> None:
    _, server, engine = web
    result = await change_collection_profile(
        collection=COLLECTION, profile=PROFILE, confirm=True, ctx=direct_ctx(server)
    )
    assert result["status"] == "ok" and result["profile"] == PROFILE, result
    assert engine.test_store.profile_tag(COLLECTION) == PROFILE


@pytest.mark.parametrize("confirm", [False, True], ids=["preview", "confirm"])
async def test_a_profile_that_is_not_ready_is_refused_with_its_reasons(
    confirm: bool, web: Any
) -> None:
    env, server, engine = web
    env.service.create_profile("Empty", source=None)
    result = await change_collection_profile(
        collection=COLLECTION, profile="empty", confirm=confirm, ctx=direct_ctx(server)
    )
    assert result["status"] == "error", result
    assert len(result["not_ready_reasons"]) == 3
    assert "no saved graph" in result["message"]
    assert engine.test_store.profile_tag(COLLECTION) == "documents"


async def test_an_unknown_user_profile_is_refused(web: Any) -> None:
    _, server, engine = web
    result = await change_collection_profile(
        collection=COLLECTION, profile="ghost", confirm=True, ctx=direct_ctx(server)
    )
    assert result["status"] == "error" and "ghost" in result["message"], result
    assert engine.test_store.profile_tag(COLLECTION) == "documents"


async def test_hybrid_is_not_a_profile_on_the_web_endpoint(web: Any) -> None:
    _, server, _ = web
    result = await change_collection_profile(
        collection=COLLECTION, profile="hybrid", confirm=True, ctx=direct_ctx(server)
    )
    assert result == {
        "status": "error",
        "message": "Invalid profile 'hybrid'. Available: documents, codebase.",
    }


async def test_a_built_in_profile_still_binds_on_the_web_endpoint(web: Any) -> None:
    _, server, engine = web
    result = await change_collection_profile(
        collection=COLLECTION, profile="codebase", confirm=True, ctx=direct_ctx(server)
    )
    assert result["status"] == "ok", result
    assert engine.test_store.profile_tag(COLLECTION) == "codebase"


@pytest.mark.parametrize("confirm", [False, True])
async def test_a_built_in_profile_is_refused_for_a_collection_made_with_another_model(
    web: Any, confirm: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    env, server, engine = web
    # On `omrs web` the service and the endpoint share one Engine and store.
    monkeypatch.setattr(env.service.embedding, "_store", lambda **_: engine.test_store)
    engine.test_store.update_collection_metadata(
        COLLECTION, {IDENTITY_PROVIDER_KEY: "other-provider", IDENTITY_MODEL_KEY: "other-model"}
    )
    result = await change_collection_profile(
        collection=COLLECTION, profile="codebase", confirm=confirm, ctx=direct_ctx(server)
    )
    assert result["status"] == "error", result
    assert "other-provider/other-model" in result["message"]
    assert engine.test_store.profile_tag(COLLECTION) == "documents"
