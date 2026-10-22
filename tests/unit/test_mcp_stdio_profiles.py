"""The stdio MCP server and user profiles (D11, unify-profiles-and-pipelines tasks 8.5 to 8.8).

``main()`` hands the read-only catalogue of the default workspace to the Engine,
so ``search_documents`` and ``answer_documents`` follow a user profile. The
server never writes the workspace and cannot bind a user profile.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.pipeline_parity.answer.harness import (
    QUERY as ANSWER_QUERY,
)
from tests.fixtures.pipeline_parity.answer.harness import (
    case_by_name,
    case_rows,
    case_settings,
    make_seam,
)
from tests.fixtures.pipeline_parity.retrieval import harness
from tests.unit.test_answer_graph_adapters_support import FakeLLM
from tests.unit.test_engine_pipelines_support import Factory
from tests.unit.test_engine_profiles_support import count_graph_runs, save_slot, slot_graph
from tests.unit.test_mcp_stdio_profiles_support import (
    COLLECTION,
    PROFILE,
    engine_builder,
    file_digest,
    link_default_workspace,
    make_env,
    start_stdio_server,
)
from tests.unit.test_pipeline_templates_parity import _store_rows

from conftest import connected_client
from omrs.core.retrieval import registry
from omrs.integrations.workspace_sqlite import SqliteProfileCatalogue

BINDING_MESSAGE = (
    "Bind user profiles in Knowledge Base > Profile, or through the MCP endpoint of `omrs web`."
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A temporary HOME, so the default workspace is under the test folder."""
    folder = tmp_path / "home"
    folder.mkdir()
    monkeypatch.setenv("HOME", str(folder))
    return folder


def _data(result: Any) -> Any:
    if getattr(result, "structured_content", None):
        return result.structured_content.get("result", result.structured_content)
    return json.loads(result.content[0].text)


def _search_setup(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch, home: Path
) -> tuple[Any, Any, str, Path]:
    """Return the seeded env, a builder over the parity corpus, the query and the linked db."""
    chunks = harness.load_corpus()["chunks"]
    monkeypatch.setitem(registry._cache, "dense", harness.make_dense(chunks))
    env = make_env(tmp_path / "seed", effective_settings)
    records = link_default_workspace(home, env)
    build = engine_builder(effective_settings(), chunks, PROFILE)
    return env, build, harness.load_corpus()["query"], records


# ── 8.6 main() hands the default workspace to the Engine ──────────────


def test_main_passes_the_default_workspace_catalogue_to_the_engine(
    tmp_path: Path, effective_settings: Any, home: Path
) -> None:
    env = make_env(tmp_path / "seed", effective_settings)
    link_default_workspace(home, env)
    _, seen = start_stdio_server(engine_builder(effective_settings(), [], PROFILE))
    catalogue = seen["catalogue"]
    assert isinstance(catalogue, SqliteProfileCatalogue)
    assert catalogue.get_profile(PROFILE)["base_profile"] == "documents"


def test_main_passes_no_catalogue_when_the_workspace_file_is_missing(
    effective_settings: Any, home: Path
) -> None:
    _, seen = start_stdio_server(engine_builder(effective_settings(), [], PROFILE))
    assert seen["catalogue"] is None
    assert not (home / ".omrs").exists(), "the stdio server must not create the workspace"


# ── 8.5 search and answer follow the user profile ─────────────────────


async def test_search_documents_runs_the_user_profile_search_pipeline(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    _, build, query, records = _search_setup(tmp_path, effective_settings, monkeypatch, home)
    before = file_digest(records)
    server, seen = start_stdio_server(build)
    runs = count_graph_runs(seen["engine"])
    async with connected_client(server) as client:
        rows = _data(
            await client.call_tool("search_documents", {"query": query, "collection": COLLECTION})
        )
    assert runs == ["run_pipeline"], "the my-notes Search graph must run once"
    assert rows and "status" not in rows[0], rows
    assert file_digest(records) == before, "the workspace database must stay unchanged"


async def test_search_documents_lets_the_graph_set_top_k(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch, home: Path
) -> None:
    """Task 8.8: an omitted top_k reaches the graph as None, so the step setting wins."""
    env, build, query, _ = _search_setup(tmp_path, effective_settings, monkeypatch, home)
    graph = slot_graph(env, "search")
    graph["nodes"][0]["params"] = {"top_k": 2, "similarity_threshold": 0.0, "rerank": False}
    save_slot(env, "search", graph)
    server, _ = start_stdio_server(build)
    async with connected_client(server) as client:
        rows = _data(
            await client.call_tool("search_documents", {"query": query, "collection": COLLECTION})
        )
    assert len(rows) == 2, rows


async def test_answer_documents_runs_the_user_profile_answer_pipeline(
    tmp_path: Path, effective_settings: Any, home: Path
) -> None:
    case = case_by_name("ok_single_citation")
    settings = case_settings(effective_settings(), case)
    env = make_env(tmp_path / "seed", effective_settings)
    records = link_default_workspace(home, env)
    complete = make_seam(case.get("complete"))
    build = engine_builder(
        settings,
        _store_rows(case_rows(case)),
        PROFILE,
        env_overrides={"RETRIEVAL__RERANK_ENABLED": "false"},
        answer_llm_factory=Factory(FakeLLM(complete)),
        verify_llm_factory=Factory(None),
    )
    before = file_digest(records)
    server, seen = start_stdio_server(build)
    runs = count_graph_runs(seen["engine"])
    async with connected_client(server) as client:
        result = _data(
            await client.call_tool(
                "answer_documents", {"query": ANSWER_QUERY, "collection": COLLECTION}
            )
        )
    assert result["status"] == "ok", result
    assert result["citations"], result
    assert result["completion_source"] == "server"
    assert runs == ["run_pipeline"], "the my-notes Answer graph must run once"
    assert len(complete.prompts) >= 1, "the server model must write the answer"
    assert file_digest(records) == before, "the workspace database must stay unchanged"


# ── 8.5 no workspace file: the D11 error ──────────────────────────────


async def test_search_documents_without_a_workspace_names_the_profile_and_the_path(
    effective_settings: Any, home: Path
) -> None:
    server, _ = start_stdio_server(engine_builder(effective_settings(), [], PROFILE))
    async with connected_client(server) as client:
        rows = _data(
            await client.call_tool("search_documents", {"query": "q", "collection": COLLECTION})
        )
    assert len(rows) == 1 and rows[0]["status"] == "error", rows
    message = rows[0]["message"]
    assert PROFILE in message
    assert "~/.omrs/workspace/workspace.db" in message
    assert "omrs web" in message


async def test_answer_documents_without_a_workspace_names_the_profile_and_the_path(
    effective_settings: Any, home: Path
) -> None:
    server, _ = start_stdio_server(engine_builder(effective_settings(), [], PROFILE))
    async with connected_client(server) as client:
        result = _data(
            await client.call_tool("answer_documents", {"query": "q", "collection": COLLECTION})
        )
    assert result["status"] == "error", result
    assert PROFILE in result["error"]
    assert "~/.omrs/workspace/workspace.db" in result["error"]
    assert not (home / ".omrs").exists()


# ── 8.7 the stdio server cannot bind a user profile ───────────────────


@pytest.mark.parametrize("confirm", [False, True], ids=["preview", "confirm"])
async def test_change_collection_profile_refuses_a_user_profile_on_stdio(
    confirm: bool, tmp_path: Path, effective_settings: Any, home: Path
) -> None:
    env = make_env(tmp_path / "seed", effective_settings)
    link_default_workspace(home, env)
    server, seen = start_stdio_server(engine_builder(effective_settings(), [], "documents"))
    async with connected_client(server) as client:
        result = _data(
            await client.call_tool(
                "change_collection_profile",
                {"collection": COLLECTION, "profile": PROFILE, "confirm": confirm},
            )
        )
    assert result == {"status": "error", "message": BINDING_MESSAGE}
    assert seen["engine"].test_store.profile_tag(COLLECTION) == "documents"


# ── list_profiles on stdio ────────────────────────────────────────────


async def test_list_profiles_on_stdio_shows_the_default_workspace_profiles(
    tmp_path: Path, effective_settings: Any, home: Path
) -> None:
    env = make_env(tmp_path / "seed", effective_settings)
    link_default_workspace(home, env)
    server, _ = start_stdio_server(engine_builder(effective_settings(), [], PROFILE))
    async with connected_client(server) as client:
        items = _data(await client.call_tool("list_profiles", {}))
    assert [i["profile_id"] for i in items] == ["documents", "codebase", PROFILE]
    mine = items[2]
    assert mine["kind"] == "user" and mine["ready"] is True, mine
    assert mine["used_by"] == [COLLECTION]
    assert {"slots", "base_profile", "title", "description", "not_ready_reasons"} <= set(mine)
