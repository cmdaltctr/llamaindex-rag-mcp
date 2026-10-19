"""The profile service: readiness, create, rename, delete, standard graphs.

unify-profiles-and-pipelines, design D4, D6, D7, D9, D12, D18, D23, tasks 4.3-4.6.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_engine_pipelines_support import build_engine

from omrg.compose_profiles import (
    BuiltinProfileError,
    ProfileInUseError,
    ProfileService,
    UnknownProfileError,
)
from omrg.core.pipelines import PipelineIssue, PipelineValidationError
from omrg.core.profiles.resolver import ProfileResolver
from omrg.integrations.workspace_sqlite import (
    SqliteProfileCatalogue,
    SqliteProfileRepository,
    SqliteWorkspaceRepository,
)

SLOTS = ("ingest", "search", "answer")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("RETRIEVAL__HYBRID_ENABLED", "RETRIEVAL__RERANK_ENABLED", "RETRIEVAL__TOP_K"):
        monkeypatch.delenv(name, raising=False)


class Env:
    """A service over a temporary workspace, with settable collection tags."""

    def __init__(self, tmp_path: Path, effective_settings: Any, reranker: Any = None) -> None:
        path = tmp_path / "ws" / "workspace.db"
        self.workspace = SqliteWorkspaceRepository(path)
        self.profiles = SqliteProfileRepository(path)
        base = effective_settings()
        resolver = ProfileResolver(
            store=None, server_profile="documents", base=base, env_overrides={}
        )
        self.engine = build_engine(base, profile_resolver=resolver, reranker=reranker)
        self.tags: dict[str, str | None] = {}
        self.catalogue = SqliteProfileCatalogue(path)
        self.service = ProfileService(
            self.engine,
            self.workspace,
            self.profiles,
            self.catalogue,
            collection_tags=lambda: dict(self.tags),
        )

    def graph(self, profile: dict, slot: str) -> dict[str, Any]:
        pipeline = self.workspace.get_pipeline(profile["slots"][slot])
        return copy.deepcopy(
            self.workspace.get_revision(pipeline["current_revision_id"])["document"]
        )

    def save(self, profile: dict, slot: str, graph: dict[str, Any]) -> None:
        self.workspace.save_revision(profile["slots"][slot], graph, schema_version=1)

    def reasons(self, profile_id: str) -> list[str]:
        return self.service.get_profile(profile_id)["not_ready_reasons"]


@pytest.fixture
def env(tmp_path: Path, effective_settings) -> Env:
    return Env(tmp_path, effective_settings)


def _suffixed(graph: dict[str, Any], suffix: str) -> dict[str, Any]:
    """Return a copy of ``graph`` with every node id, input and output renamed."""
    text = copy.deepcopy(graph)
    for node in text["nodes"]:
        node["id"] += suffix
    for edge in text["edges"]:
        for end in ("source", "target"):
            edge[end]["node"] += suffix
    for spec in text["inputs"]:
        spec["name"] += suffix
        for target in spec["targets"]:
            target["node"] += suffix
    for out in text["outputs"]:
        out["name"] += suffix
        out["source"]["node"] += suffix
    return text


def _merged(first: dict[str, Any], second: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(first)
    for key in ("nodes", "edges", "inputs", "outputs"):
        merged[key] += copy.deepcopy(second[key])
    return merged


# ── Readiness (task 4.3) ──────────────────────────────────────────────


def test_a_duplicate_of_a_built_in_is_ready(env: Env) -> None:
    for source in ("documents", "codebase"):
        item = env.service.create_profile("Copy of " + source, source=source)
        assert item["ready"] is True, item["not_ready_reasons"]
        assert item["not_ready_reasons"] == []


def test_an_empty_profile_names_each_pipeline_without_a_graph(env: Env) -> None:
    item = env.service.create_profile("Empty", source=None)
    assert item["ready"] is False
    reasons = item["not_ready_reasons"]
    assert len(reasons) == 3
    for title in ("Ingest", "Search", "Answer"):
        assert any(title in r and "no saved graph" in r for r in reasons), (title, reasons)


def test_a_search_graph_without_a_results_output(env: Env) -> None:
    item = env.service.create_profile("Mine", source="documents")
    graph = env.graph(item, "search")
    graph["outputs"][0]["name"] = "out"
    env.save(item, "search", graph)
    reasons = env.reasons("mine")
    assert len(reasons) == 1
    assert "Search pipeline needs an output named `results`" in reasons[0]


def test_a_graph_input_of_the_wrong_kind(env: Env) -> None:
    item = env.service.create_profile("Mine", source="documents")
    graph = env.graph(item, "answer")
    graph["inputs"][0]["name"] = "question"
    env.save(item, "answer", graph)
    reasons = env.reasons("mine")
    assert any("Answer pipeline needs an input named `query`" in r for r in reasons), reasons


@pytest.mark.parametrize("slot", ["search", "answer"])
def test_a_write_step_in_a_read_only_pipeline_names_the_step(env: Env, slot: str) -> None:
    item = env.service.create_profile("Mine", source="documents")
    write = _suffixed(env.graph(item, "ingest"), "_w")
    env.save(item, slot, _merged(env.graph(item, slot), write))
    reasons = env.reasons("mine")
    title = slot.capitalize()
    assert any(f"{title} pipeline must not write" in r and "commit_w" in r for r in reasons), (
        reasons
    )


def test_an_ingest_pipeline_with_no_write_step(env: Env) -> None:
    item = env.service.create_profile("Mine", source="documents")
    env.save(item, "ingest", env.graph(item, "search"))
    reasons = env.reasons("mine")
    assert any("Ingest pipeline needs exactly one write step" in r for r in reasons), reasons


def test_an_ingest_pipeline_with_two_write_steps(env: Env) -> None:
    item = env.service.create_profile("Mine", source="documents")
    ingest = env.graph(item, "ingest")
    env.save(item, "ingest", _merged(ingest, _suffixed(ingest, "_2")))
    reasons = env.reasons("mine")
    assert any("Ingest pipeline needs exactly one write step" in r and "2" in r for r in reasons), (
        reasons
    )


def test_a_draft_issue_gives_a_plain_line_that_names_the_pipeline_and_step(env: Env) -> None:
    item = env.service.create_profile("Mine", source="documents")
    graph = env.graph(item, "search")
    graph["nodes"][1]["operation"] = "retrieve.nothing"
    env.save(item, "search", graph)
    reasons = env.reasons("mine")
    assert any("Search pipeline" in r and "step 'dense'" in r for r in reasons), reasons


def test_no_reason_is_a_bare_issue_code(env: Env) -> None:
    item = env.service.create_profile("Mine", source="documents")
    graph = env.graph(item, "search")
    graph["nodes"][1]["operation"] = "retrieve.nothing"
    env.save(item, "search", graph)
    env.service.create_profile("Empty", source=None)
    for profile_id in ("mine", "empty"):
        for reason in env.reasons(profile_id):
            assert not re.fullmatch(r"[a-z_]+", reason), reason
            assert reason.endswith("."), reason


def test_an_embedding_identity_issue_alone_does_not_make_a_profile_not_ready(
    env: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    env.service.create_profile("Mine", source="documents")
    issue = PipelineIssue(code="embedding_identity_mismatch", message="Collection 'x' differs.")

    def mismatch(*args: Any, **kwargs: Any) -> Any:
        raise PipelineValidationError([issue])

    monkeypatch.setattr(env.engine, "validate_pipeline", mismatch)
    item = env.service.get_profile("mine")
    assert item["ready"] is True and item["not_ready_reasons"] == []


# ── Create, rename, delete, used_by (task 4.4) ───────────────────────


def test_the_list_holds_built_ins_then_user_profiles_without_graphs(env: Env) -> None:
    env.service.create_profile("Notes", source="documents")
    items = env.service.list_profiles()
    assert [i["profile_id"] for i in items] == ["documents", "codebase", "notes"]
    assert [i["kind"] for i in items] == ["builtin", "builtin", "user"]
    for item in items[:2]:
        assert item["ready"] is True
        assert item["slots"] == {"ingest": None, "search": None, "answer": None}
        assert item["base_profile"] == item["profile_id"]
    assert set(items[2]["slots"]) == set(SLOTS)
    assert all(slot is not None for slot in items[2]["slots"].values())
    assert all("standard_graphs" not in item for item in items)
    assert {
        "profile_id",
        "kind",
        "title",
        "description",
        "base_profile",
        "slots",
        "ready",
        "not_ready_reasons",
        "used_by",
        "embedding",
        "embedding_lock",
    } == set(items[2])


def test_create_from_a_built_in_saves_the_standard_graphs_as_revision_one(env: Env) -> None:
    item = env.service.create_profile("Code notes", source="codebase", description="For code")
    assert (item["profile_id"], item["kind"], item["base_profile"]) == (
        "code-notes",
        "user",
        "codebase",
    )
    assert item["description"] == "For code"
    standard = env.service.get_profile("codebase")["standard_graphs"]
    for slot in SLOTS:
        pipeline = env.workspace.get_pipeline(item["slots"][slot])
        revision = env.workspace.get_revision(pipeline["current_revision_id"])
        assert revision["revision_number"] == 1
        assert revision["document"] == standard[slot]


def test_create_from_a_user_profile_copies_current_revisions_and_layouts(env: Env) -> None:
    source = env.service.create_profile("Source", source="documents")
    changed = env.graph(source, "search")
    changed["overrides"] = {"retrieval.top_k": 3}
    env.save(source, "search", changed)
    env.workspace.save_layout(source["slots"]["search"], {"title": "My search"})
    copy_item = env.service.create_profile("Copy", source="source")
    assert copy_item["base_profile"] == "documents"
    assert env.graph(copy_item, "search") == changed
    copied_layout = env.workspace.get_pipeline(copy_item["slots"]["search"])["layout"]
    assert copied_layout == {"title": "My search"}
    assert set(copy_item["slots"].values()).isdisjoint(source["slots"].values())
    # Later edits to the copy never change the source.
    further = env.graph(copy_item, "search")
    further["overrides"] = {"retrieval.top_k": 9}
    env.save(copy_item, "search", further)
    assert env.graph(env.service.get_profile("source"), "search") == changed


def test_create_from_a_user_profile_keeps_a_slot_without_a_revision_empty(env: Env) -> None:
    env.service.create_profile("Empty", source=None)
    copy_item = env.service.create_profile("Copy", source="empty")
    assert copy_item["base_profile"] == "documents"
    assert copy_item["ready"] is False and len(copy_item["not_ready_reasons"]) == 3


def test_create_from_an_unknown_or_deleted_source(env: Env) -> None:
    with pytest.raises(UnknownProfileError):
        env.service.create_profile("X", source="nope")
    env.service.create_profile("Gone", source="documents")
    env.service.delete_profile("gone")
    with pytest.raises(UnknownProfileError):
        env.service.create_profile("X", source="gone")


def test_empty_profile_has_base_documents_and_no_revisions(env: Env) -> None:
    item = env.service.create_profile("Blank", source=None)
    assert item["base_profile"] == "documents"
    for slot in SLOTS:
        assert env.workspace.get_pipeline(item["slots"][slot])["current_revision_id"] is None


@pytest.mark.parametrize("title", ["", "   ", "x" * 81, "bad\x07title", "two\nlines"])
def test_invalid_titles_are_refused(env: Env, title: str) -> None:
    with pytest.raises(ValueError, match="title"):
        env.service.create_profile(title, source="documents")


def test_a_title_of_eighty_characters_is_accepted(env: Env) -> None:
    item = env.service.create_profile("  " + "x" * 80 + "  ", source="documents")
    assert item["title"] == "x" * 80


def test_rename_changes_title_and_description_but_not_the_id(env: Env) -> None:
    env.service.create_profile("Notes", source="documents")
    renamed = env.service.rename_profile("notes", title="Meeting notes", description="Weekly")
    assert (renamed["profile_id"], renamed["title"], renamed["description"]) == (
        "notes",
        "Meeting notes",
        "Weekly",
    )
    only_description = env.service.rename_profile("notes", description="Daily")
    assert only_description["title"] == "Meeting notes"


def test_a_built_in_cannot_be_renamed_or_deleted(env: Env) -> None:
    with pytest.raises(BuiltinProfileError):
        env.service.rename_profile("documents", title="Mine")
    with pytest.raises(BuiltinProfileError):
        env.service.delete_profile("codebase")


def test_rename_and_delete_of_an_unknown_profile(env: Env) -> None:
    for call in (
        lambda: env.service.rename_profile("nope", title="X"),
        lambda: env.service.delete_profile("nope"),
        lambda: env.service.get_profile("nope"),
    ):
        with pytest.raises(UnknownProfileError):
            call()


def test_delete_hides_the_profile_but_keeps_its_rows(env: Env) -> None:
    item = env.service.create_profile("Notes", source="documents")
    deleted = env.service.delete_profile("notes")
    assert deleted["profile_id"] == "notes"
    assert "notes" not in [i["profile_id"] for i in env.service.list_profiles()]
    with pytest.raises(UnknownProfileError):
        env.service.get_profile("notes")
    pipeline = env.workspace.get_pipeline(item["slots"]["search"])
    assert env.workspace.get_revision(pipeline["current_revision_id"])["revision_number"] == 1
    assert env.profiles.get_profile("notes")["archived_at"] is not None
    assert env.service.create_profile("Notes", source="documents")["profile_id"] == "notes-2"


def test_delete_is_refused_while_a_collection_uses_the_profile(env: Env) -> None:
    env.service.create_profile("Notes", source="documents")
    env.tags.update({"b-notes": "notes", "a-notes": "notes", "other": "documents", "plain": None})
    with pytest.raises(ProfileInUseError) as caught:
        env.service.delete_profile("notes")
    assert caught.value.used_by == ["a-notes", "b-notes"]
    assert env.service.get_profile("notes")["title"] == "Notes"


def test_used_by_comes_from_collection_tags(env: Env) -> None:
    env.service.create_profile("Notes", source="documents")
    env.tags.update({"notes": "notes", "docs": "documents", "plain": None})
    assert env.service.get_profile("notes")["used_by"] == ["notes"]
    assert env.service.get_profile("documents")["used_by"] == ["docs"]
    assert env.service.get_profile("codebase")["used_by"] == []
    by_id = {i["profile_id"]: i["used_by"] for i in env.service.list_profiles()}
    assert by_id == {"documents": ["docs"], "codebase": [], "notes": ["notes"]}


# ── Standard graphs (task 4.5) ────────────────────────────────────────


@pytest.mark.parametrize("base", ["documents", "codebase"])
def test_a_built_in_returns_graphs_equal_to_revision_one_of_a_duplicate(
    env: Env, base: str
) -> None:
    standard = env.service.get_profile(base)["standard_graphs"]
    assert tuple(standard) == SLOTS
    duplicate = env.service.create_profile("Copy", source=base)
    for slot in SLOTS:
        assert env.graph(duplicate, slot) == standard[slot]
        assert standard[slot]["profile"] == base and standard[slot]["collection"] is None


def test_codebase_graphs_follow_codebase_settings_on_a_documents_host(env: Env) -> None:
    standard = env.service.get_profile("codebase")["standard_graphs"]
    nodes = {n["id"] for n in standard["search"]["nodes"]}
    assert {"sparse", "fuse"} <= nodes
    documents = env.service.get_profile("documents")["standard_graphs"]
    assert not {"sparse", "fuse"} & {n["id"] for n in documents["search"]["nodes"]}


def test_a_user_profile_has_no_standard_graphs(env: Env) -> None:
    env.service.create_profile("Notes", source="documents")
    assert env.service.get_profile("notes")["standard_graphs"] is None
