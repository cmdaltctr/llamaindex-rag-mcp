"""Saved Studio pipelines become user profiles on upgrade (design D10, tasks 4.7-4.8)."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_profile_service import Env

from omrg.compose_templates import profile_templates
from omrg.core.workspace import TASK_LAYOUT_KEY

SLOTS = ("ingest", "search", "answer")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def env(tmp_path: Path, effective_settings) -> Env:
    return Env(tmp_path, effective_settings)


def _graph(env: Env, slot: str, profile: str | None = "documents") -> dict[str, Any]:
    graph = copy.deepcopy(profile_templates(env.engine, "documents")[slot])
    graph["profile"] = profile
    return graph


def _saved(
    env: Env,
    title: str,
    graph: dict[str, Any] | None,
    layout: dict[str, Any] | None = None,
) -> str:
    pipeline_id = env.workspace.create_pipeline(title, layout=layout or {})["pipeline_id"]
    if graph is not None:
        env.workspace.save_revision(pipeline_id, graph, schema_version=1)
    return pipeline_id


def _profile_of(env: Env, pipeline_id: str) -> tuple[dict[str, Any], str]:
    found = env.profiles.find_profile_by_pipeline(pipeline_id)
    assert found is not None, "the pipeline belongs to no profile"
    return dict(found[0]), found[1]


def _item(env: Env, pipeline_id: str) -> dict[str, Any]:
    return env.service.get_profile(_profile_of(env, pipeline_id)[0]["profile_id"])


def test_a_search_pipeline_fills_the_search_slot_and_keeps_its_runs(env: Env) -> None:
    pipeline_id = _saved(env, "Docs search", _graph(env, "search"))
    revision_id = env.workspace.get_pipeline(pipeline_id)["current_revision_id"]
    run = env.workspace.create_run(revision_id, settings={}, resources={}, inputs={})
    created = env.service.upgrade_saved_pipelines()
    record, slot = _profile_of(env, pipeline_id)
    assert created == [record["profile_id"]]
    assert (slot, record["title"], record["profile_id"]) == ("search", "Docs search", "docs-search")
    assert env.workspace.get_run(run["run_id"])["pipeline_id"] == pipeline_id
    item = env.service.get_profile("docs-search")
    assert item["slots"]["search"] == pipeline_id
    assert item["ready"] is True, item["not_ready_reasons"]


@pytest.mark.parametrize("slot", SLOTS)
def test_each_graph_goes_to_the_slot_whose_contract_it_matches(env: Env, slot: str) -> None:
    pipeline_id = _saved(env, f"My {slot}", _graph(env, slot))
    env.service.upgrade_saved_pipelines()
    assert _profile_of(env, pipeline_id)[1] == slot
    assert _item(env, pipeline_id)["ready"] is True


def test_the_other_slots_get_the_standard_graphs_of_the_base_profile(env: Env) -> None:
    pipeline_id = _saved(env, "Docs search", _graph(env, "search"))
    env.service.upgrade_saved_pipelines()
    record, _ = _profile_of(env, pipeline_id)
    standard = profile_templates(env.engine, "documents")
    for slot in ("ingest", "answer"):
        assert env.graph(_item(env, pipeline_id), slot) == standard[slot]


def test_a_non_empty_canvas_title_wins(env: Env) -> None:
    pipeline_id = _saved(
        env, "New pipeline", _graph(env, "search"), layout={"title": "  Papers search "}
    )
    env.service.upgrade_saved_pipelines()
    assert _profile_of(env, pipeline_id)[0]["title"] == "Papers search"


@pytest.mark.parametrize("layout", [{}, {"title": ""}, {"title": "   "}, {"title": 5}])
def test_an_empty_or_blank_canvas_title_gives_the_pipeline_title(
    env: Env, layout: dict[str, Any]
) -> None:
    pipeline_id = _saved(env, "Saved title", _graph(env, "search"), layout=layout)
    env.service.upgrade_saved_pipelines()
    assert _profile_of(env, pipeline_id)[0]["title"] == "Saved title"


def test_a_long_or_odd_title_is_made_valid(env: Env) -> None:
    long_id = _saved(env, "x" * 200, _graph(env, "search"))
    odd_id = _saved(env, "bad\x07\ntitle", _graph(env, "search"))
    blank_id = _saved(env, "  ", _graph(env, "search"))
    env.service.upgrade_saved_pipelines()
    assert _profile_of(env, long_id)[0]["title"] == "x" * 80
    assert _profile_of(env, odd_id)[0]["title"] == "badtitle"
    assert _profile_of(env, blank_id)[0]["title"] == "Untitled"


def test_a_codebase_graph_keeps_its_base_and_gets_codebase_standard_graphs(env: Env) -> None:
    graph = profile_templates(env.engine, "codebase")["search"]
    pipeline_id = _saved(env, "Code search", graph)
    env.service.upgrade_saved_pipelines()
    record, slot = _profile_of(env, pipeline_id)
    assert (record["base_profile"], slot) == ("codebase", "search")
    standard = profile_templates(env.engine, "codebase")
    item = _item(env, pipeline_id)
    assert env.graph(item, "ingest") == standard["ingest"]
    assert env.graph(item, "answer") == standard["answer"]
    assert len(env.workspace.list_revisions(pipeline_id)) == 1


def test_a_graph_without_a_profile_gets_base_documents_and_one_new_revision(env: Env) -> None:
    pipeline_id = _saved(env, "No profile", _graph(env, "search", profile=None))
    before = env.workspace.list_revisions(pipeline_id)
    env.service.upgrade_saved_pipelines()
    record, _ = _profile_of(env, pipeline_id)
    assert record["base_profile"] == "documents"
    after = env.workspace.list_revisions(pipeline_id)
    assert [r["revision_id"] for r in after[:1]] == [before[0]["revision_id"]]
    assert len(after) == 2 and after[1]["document"]["profile"] == "documents"
    assert env.workspace.get_pipeline(pipeline_id)["current_revision_id"] == after[1]["revision_id"]
    rest = {k: v for k, v in after[1]["document"].items() if k != "profile"}
    assert rest == {k: v for k, v in before[0]["document"].items() if k != "profile"}


def test_a_workspace_job_pipeline_is_skipped_and_keeps_its_runs(env: Env) -> None:
    job_id = env.workspace.create_pipeline(
        "Workspace job: ingest", layout={TASK_LAYOUT_KEY: "ingest"}
    )["pipeline_id"]
    revision = env.workspace.save_revision(job_id, {"task": "ingest"}, schema_version=1)
    run = env.workspace.create_run(revision["revision_id"], settings={}, resources={}, inputs={})
    assert env.service.upgrade_saved_pipelines() == []
    assert env.profiles.find_profile_by_pipeline(job_id) is None
    assert env.workspace.get_run(run["run_id"])["pipeline_id"] == job_id


def test_a_pipeline_titled_like_a_job_without_the_layout_key_is_migrated(env: Env) -> None:
    pipeline_id = _saved(env, "Workspace job: ingest", _graph(env, "ingest"))
    env.service.upgrade_saved_pipelines()
    assert _profile_of(env, pipeline_id)[1] == "ingest"


def test_a_pipeline_without_a_revision_gives_a_profile_that_is_not_ready(env: Env) -> None:
    pipeline_id = _saved(env, "Empty canvas", None)
    env.service.upgrade_saved_pipelines()
    record, slot = _profile_of(env, pipeline_id)
    assert (slot, record["base_profile"]) == ("search", "documents")
    item = _item(env, pipeline_id)
    assert item["ready"] is False
    assert any("Search pipeline has no saved graph" in r for r in item["not_ready_reasons"])
    assert env.workspace.get_pipeline(pipeline_id)["current_revision_id"] is None


def test_a_graph_that_matches_no_contract_goes_to_search_and_is_not_ready(env: Env) -> None:
    graph = _graph(env, "search")
    graph["inputs"] = []
    pipeline_id = _saved(env, "Odd", graph)
    env.service.upgrade_saved_pipelines()
    record, slot = _profile_of(env, pipeline_id)
    assert slot == "search"
    item = _item(env, pipeline_id)
    assert item["ready"] is False
    assert any("Search pipeline" in r for r in item["not_ready_reasons"])


def test_a_document_that_is_not_a_graph_is_kept_in_the_search_slot(env: Env) -> None:
    pipeline_id = _saved(env, "Broken", {"nodes": "nope"})
    env.service.upgrade_saved_pipelines()
    assert _profile_of(env, pipeline_id)[1] == "search"
    assert _item(env, pipeline_id)["ready"] is False
    assert len(env.workspace.list_revisions(pipeline_id)) == 1


def test_the_upgrade_runs_once(env: Env) -> None:
    pipeline_id = _saved(env, "Docs search", _graph(env, "search", profile=None))
    first = env.service.upgrade_saved_pipelines()
    revisions = len(env.workspace.list_revisions(pipeline_id))
    count = len(env.profiles.list_profiles(include_archived=True))
    assert len(first) == 1
    assert env.service.upgrade_saved_pipelines() == []
    assert len(env.profiles.list_profiles(include_archived=True)) == count
    assert len(env.workspace.list_revisions(pipeline_id)) == revisions


def test_a_deleted_profile_is_not_made_again(env: Env) -> None:
    pipeline_id = _saved(env, "Docs search", _graph(env, "search"))
    env.service.upgrade_saved_pipelines()
    env.service.delete_profile(_profile_of(env, pipeline_id)[0]["profile_id"])
    assert env.service.upgrade_saved_pipelines() == []
    assert len(env.profiles.list_profiles(include_archived=True)) == 1


def test_profile_slot_pipelines_are_not_upgraded_again(env: Env) -> None:
    env.service.create_profile("Mine", source="documents")
    assert env.service.upgrade_saved_pipelines() == []
    assert len(env.profiles.list_profiles()) == 1
