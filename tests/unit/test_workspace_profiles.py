"""User profiles in the workspace database (unify-profiles-and-pipelines, tasks 1.7-1.10)."""

from __future__ import annotations

import hashlib
import re
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from omrg.core.workspace import PROFILE_ID_PATTERN, ProfileRepository
from omrg.integrations.workspace_sqlite import (
    SCHEMA_MIGRATIONS,
    SqliteProfileCatalogue,
    SqliteProfileRepository,
    SqliteWorkspaceRepository,
    WorkspaceSchemaError,
)

GRAPH: dict[str, Any] = {"version": 1, "nodes": [], "edges": []}


def _graph(label: str) -> dict[str, Any]:
    return {**GRAPH, "label": label}


class _Clock:
    """A clock that moves one second on every read."""

    def __init__(self) -> None:
        self.now = datetime(2026, 10, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        self.now += timedelta(seconds=1)
        return self.now


@pytest.fixture
def stores(tmp_path: Path) -> tuple[SqliteWorkspaceRepository, SqliteProfileRepository]:
    path = tmp_path / "ws" / "workspace.db"
    clock = _Clock()
    return (
        SqliteWorkspaceRepository(path, clock=clock),
        SqliteProfileRepository(path, clock=clock),
    )


def _slots(label: str = "x") -> dict[str, Any]:
    return {
        "ingest": _graph(f"{label}-ingest"),
        "search": _graph(f"{label}-search"),
        "answer": _graph(f"{label}-answer"),
    }


def _counts(path: Path) -> tuple[int, int, int]:
    conn = sqlite3.connect(path)
    try:
        return tuple(  # type: ignore[return-value]
            conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            for table in ("profiles", "pipelines", "pipeline_revisions")
        )
    finally:
        conn.close()


def test_store_satisfies_the_repository_protocol(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    assert isinstance(stores[1], ProfileRepository)


def test_create_writes_profile_pipelines_and_first_revisions(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    record = profiles.create_profile(
        "My notes",
        base_profile="codebase",
        slots=_slots(),
        schema_version=1,
        description="For notes",
    )
    assert record["profile_id"] == "my-notes"
    assert re.fullmatch(PROFILE_ID_PATTERN, record["profile_id"])
    assert (record["title"], record["description"], record["base_profile"]) == (
        "My notes",
        "For notes",
        "codebase",
    )
    assert record["archived_at"] is None
    titles = {}
    for slot in ("ingest", "search", "answer"):
        pipeline = workspace.get_pipeline(record[f"{slot}_pipeline_id"])
        titles[slot] = pipeline["title"]
        revision = workspace.get_revision(pipeline["current_revision_id"])
        assert revision["revision_number"] == 1
        assert revision["document"]["label"] == f"x-{slot}"
    assert titles == {"ingest": "Ingest", "search": "Search", "answer": "Answer"}


def test_create_with_no_graphs_leaves_the_pipelines_without_revisions(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    record = profiles.create_profile(
        "Empty",
        base_profile="documents",
        slots={"ingest": None, "search": None, "answer": None},
        schema_version=1,
    )
    for slot in ("ingest", "search", "answer"):
        pipeline = workspace.get_pipeline(record[f"{slot}_pipeline_id"])
        assert pipeline["current_revision_id"] is None
        assert workspace.list_revisions(pipeline["pipeline_id"]) == []


def test_a_failed_create_rolls_back_every_row(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    before = _counts(workspace.path)
    slots = _slots()
    slots["answer"] = "no-such-pipeline"
    with pytest.raises(KeyError):
        profiles.create_profile("Broken", base_profile="documents", slots=slots, schema_version=1)
    assert _counts(workspace.path) == before

    slots = _slots()
    slots["answer"] = {"version": 1, "bad": {1, 2}}  # not JSON-compatible
    with pytest.raises(ValueError):
        profiles.create_profile("Broken", base_profile="documents", slots=slots, schema_version=1)
    assert _counts(workspace.path) == before


def test_an_existing_pipeline_becomes_a_slot_and_keeps_its_revisions(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    old = workspace.create_pipeline("Canvas")["pipeline_id"]
    first = workspace.save_revision(old, _graph("one"), schema_version=1)
    second = workspace.save_revision(old, _graph("two"), schema_version=1)
    slots = _slots()
    slots["search"] = old
    record = profiles.create_profile(
        "Migrated", base_profile="documents", slots=slots, schema_version=1
    )
    assert record["search_pipeline_id"] == old
    assert workspace.get_pipeline(old)["current_revision_id"] == second["revision_id"]
    assert [r["revision_id"] for r in workspace.list_revisions(old)] == [
        first["revision_id"],
        second["revision_id"],
    ]
    assert profiles.find_profile_by_pipeline(old) == (record, "search")


def test_a_pipeline_that_fills_a_slot_cannot_fill_another(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    first = profiles.create_profile(
        "First", base_profile="documents", slots=_slots(), schema_version=1
    )
    before = _counts(workspace.path)
    slots = _slots()
    slots["search"] = first["search_pipeline_id"]
    with pytest.raises(ValueError, match="slot"):
        profiles.create_profile("Second", base_profile="documents", slots=slots, schema_version=1)
    assert _counts(workspace.path) == before


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"base_profile": "hybrid"}, "base"),
        ({"base_profile": "nope"}, "base"),
        ({"slots": {"ingest": None, "search": None}}, "slot"),
        ({"slots": {"ingest": None, "search": None, "answer": None, "extra": None}}, "slot"),
        ({"title": "   "}, "title"),
    ],
)
def test_invalid_input_is_refused_before_any_write(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
    kwargs: dict[str, Any],
    match: str,
) -> None:
    workspace, profiles = stores
    before = _counts(workspace.path)
    args: dict[str, Any] = {
        "title": "Ok",
        "base_profile": "documents",
        "slots": _slots(),
        "schema_version": 1,
    }
    args.update(kwargs)
    title = args.pop("title")
    with pytest.raises(ValueError, match=match):
        profiles.create_profile(title, **args)
    assert _counts(workspace.path) == before


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("My Notes", "my-notes"),
        ("  Notes & Co.  ", "notes-co"),
        ("--A--", "a"),
        ("Café 2026", "caf-2026"),
        ("日本語", "profile"),
        ("x" * 100, "x" * 64),
        ("Documents", "documents-2"),
        ("CODEBASE", "codebase-2"),
        ("Hybrid", "hybrid-2"),
    ],
)
def test_ids_come_from_the_title(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
    title: str,
    expected: str,
) -> None:
    record = stores[1].create_profile(
        title, base_profile="documents", slots=_slots(), schema_version=1
    )
    assert record["profile_id"] == expected
    assert re.fullmatch(PROFILE_ID_PATTERN, record["profile_id"])


def test_a_taken_id_gets_a_numeric_suffix(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    ids = [
        profiles.create_profile(
            "Notes", base_profile="documents", slots=_slots(), schema_version=1
        )["profile_id"]
        for _ in range(3)
    ]
    assert ids == ["notes", "notes-2", "notes-3"]


def test_a_full_length_id_keeps_the_suffix_inside_the_limit(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    title = "y" * 80
    ids = [
        profiles.create_profile(title, base_profile="documents", slots=_slots(), schema_version=1)[
            "profile_id"
        ]
        for _ in range(2)
    ]
    assert ids == ["y" * 64, "y" * 62 + "-2"]
    assert all(re.fullmatch(PROFILE_ID_PATTERN, i) for i in ids)


def test_an_archived_id_is_never_reused(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    first = profiles.create_profile(
        "Notes", base_profile="documents", slots=_slots(), schema_version=1
    )
    archived = profiles.archive_profile(first["profile_id"])
    assert archived["archived_at"] is not None
    again = profiles.create_profile(
        "Notes", base_profile="documents", slots=_slots(), schema_version=1
    )
    assert again["profile_id"] == "notes-2"
    assert profiles.get_profile("notes")["archived_at"] == archived["archived_at"]


def test_archiving_twice_keeps_the_first_time(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    record = profiles.create_profile(
        "Notes", base_profile="documents", slots=_slots(), schema_version=1
    )
    first = profiles.archive_profile(record["profile_id"])
    second = profiles.archive_profile(record["profile_id"])
    assert second["archived_at"] == first["archived_at"]


def test_list_leaves_out_archived_profiles_unless_asked(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    for title in ("One", "Two", "Three"):
        profiles.create_profile(title, base_profile="documents", slots=_slots(), schema_version=1)
    profiles.archive_profile("two")
    assert [p["profile_id"] for p in profiles.list_profiles()] == ["one", "three"]
    assert [p["profile_id"] for p in profiles.list_profiles(include_archived=True)] == [
        "one",
        "two",
        "three",
    ]


def test_rename_changes_title_and_description_but_not_the_id(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    record = profiles.create_profile(
        "Notes", base_profile="documents", slots=_slots(), schema_version=1
    )
    renamed = profiles.update_profile("notes", title="Research notes")
    assert renamed["profile_id"] == "notes"
    assert renamed["title"] == "Research notes"
    assert renamed["description"] == ""
    assert renamed["updated_at"] > record["updated_at"]
    described = profiles.update_profile("notes", description="Papers")
    assert (described["title"], described["description"]) == ("Research notes", "Papers")
    # The slot pipeline titles stay "Ingest", "Search" and "Answer".
    assert workspace.get_pipeline(record["search_pipeline_id"])["title"] == "Search"


def test_a_blank_title_is_refused_on_rename(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    profiles.create_profile("Notes", base_profile="documents", slots=_slots(), schema_version=1)
    with pytest.raises(ValueError, match="title"):
        profiles.update_profile("notes", title="  ")


def test_an_unknown_profile_raises_key_error(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    for call in (
        lambda: profiles.get_profile("nope"),
        lambda: profiles.update_profile("nope", title="x"),
        lambda: profiles.archive_profile("nope"),
    ):
        with pytest.raises(KeyError):
            call()
    assert profiles.find_profile_by_pipeline("nope") is None


# --- The read-only catalogue (tasks 1.9, 1.10) ---


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _user_version(path: Path) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])
    finally:
        conn.close()


def test_catalogue_reads_profiles_and_slot_documents(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    record = profiles.create_profile(
        "Notes", base_profile="codebase", slots=_slots("n"), schema_version=1
    )
    profiles.create_profile("Gone", base_profile="documents", slots=_slots(), schema_version=1)
    profiles.archive_profile("gone")
    catalogue = SqliteProfileCatalogue(workspace.path)
    assert catalogue.get_profile("notes") == record
    assert catalogue.get_profile("nope") is None
    assert catalogue.get_profile("gone")["archived_at"] is not None
    assert [p["profile_id"] for p in catalogue.list_profiles()] == ["notes"]
    assert catalogue.slot_document("notes", "search")["label"] == "n-search"
    revision = catalogue.slot_revision("notes", "answer")
    assert revision["revision_number"] == 1
    assert catalogue.slot_document("notes", "bogus") is None
    assert catalogue.slot_document("nope", "search") is None


def test_catalogue_slot_without_a_revision_reads_as_none(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    profiles.create_profile(
        "Empty",
        base_profile="documents",
        slots={"ingest": None, "search": None, "answer": None},
        schema_version=1,
    )
    assert SqliteProfileCatalogue(workspace.path).slot_document("empty", "ingest") is None


def test_catalogue_connection_cannot_write(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    profiles.create_profile("Notes", base_profile="documents", slots=_slots(), schema_version=1)
    before = _digest(workspace.path)
    catalogue = SqliteProfileCatalogue(workspace.path)
    with catalogue.connection() as conn:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("UPDATE profiles SET title = 'x'")
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            conn.execute("DELETE FROM pipelines")
    assert _digest(workspace.path) == before


def test_reading_leaves_the_file_and_its_directory_unchanged(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    workspace, profiles = stores
    profiles.create_profile("Notes", base_profile="documents", slots=_slots(), schema_version=1)
    before_bytes, before_files = _digest(workspace.path), sorted(workspace.path.parent.iterdir())
    catalogue = SqliteProfileCatalogue(workspace.path)
    catalogue.get_profile("notes")
    catalogue.list_profiles()
    catalogue.slot_document("notes", "ingest")
    assert _digest(workspace.path) == before_bytes
    assert sorted(workspace.path.parent.iterdir()) == before_files
    assert _user_version(workspace.path) == SCHEMA_MIGRATIONS[-1][0]


def test_a_version_two_file_reads_as_no_profiles_and_stays_version_two(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    SqliteWorkspaceRepository(path, migrations=SCHEMA_MIGRATIONS[:2]).create_pipeline("Old")
    before = _digest(path)
    catalogue = SqliteProfileCatalogue(path)
    assert catalogue.get_profile("notes") is None
    assert catalogue.list_profiles() == []
    assert catalogue.slot_document("notes", "search") is None
    assert _digest(path) == before
    assert _user_version(path) == 2
    assert list(tmp_path.glob("*.bak")) == []


def test_an_empty_file_reads_as_no_profiles(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    path.touch()
    catalogue = SqliteProfileCatalogue(path)
    assert catalogue.get_profile("notes") is None
    assert catalogue.list_profiles() == []
    assert path.stat().st_size == 0


def test_a_newer_schema_is_refused_with_the_path(tmp_path: Path) -> None:
    path = tmp_path / "workspace.db"
    SqliteWorkspaceRepository(path)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA user_version = 99")
    conn.close()
    with pytest.raises(WorkspaceSchemaError, match="newer") as excinfo:
        SqliteProfileCatalogue(path).get_profile("notes")
    assert str(path) in str(excinfo.value)
    assert _user_version(path) == 99


def test_a_file_that_is_not_a_workspace_is_refused_with_the_path(tmp_path: Path) -> None:
    path = tmp_path / "other.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE vectors (id INTEGER)")
    conn.close()
    before = _digest(path)
    with pytest.raises(WorkspaceSchemaError, match="not an OMRG workspace") as excinfo:
        SqliteProfileCatalogue(path).list_profiles()
    assert str(path) in str(excinfo.value)
    assert _digest(path) == before


def test_a_missing_file_is_an_error_that_names_the_path_and_is_not_created(
    tmp_path: Path,
) -> None:
    path = tmp_path / "gone" / "workspace.db"
    with pytest.raises(WorkspaceSchemaError) as excinfo:
        SqliteProfileCatalogue(path).get_profile("notes")
    assert str(path) in str(excinfo.value)
    assert not path.exists()
    assert not path.parent.exists()


# ── Embedding choice (add-profile-embedding-model, task 7.4) ─────────────


def test_a_new_profile_has_no_embedding_choice(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    record = stores[1].create_profile(
        "Plain", base_profile="documents", slots=_slots(), schema_version=1
    )
    assert (record["embed_provider"], record["embed_model"], record["embed_dimensions"]) == (
        None,
        None,
        None,
    )


def test_the_embedding_choice_is_saved_read_and_cleared(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    record = profiles.create_profile(
        "Mine", base_profile="documents", slots=_slots(), schema_version=1
    )
    saved = profiles.set_profile_embedding(
        record["profile_id"], provider="ollama", model="nomic-embed-text", dimensions=768
    )
    assert (saved["embed_provider"], saved["embed_model"], saved["embed_dimensions"]) == (
        "ollama",
        "nomic-embed-text",
        768,
    )
    assert profiles.get_profile(record["profile_id"])["embed_model"] == "nomic-embed-text"
    cleared = profiles.set_profile_embedding(
        record["profile_id"], provider=None, model=None, dimensions=None
    )
    assert (cleared["embed_provider"], cleared["embed_model"]) == (None, None)


def test_a_provider_without_a_model_is_refused_by_the_repository(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    profiles = stores[1]
    record = profiles.create_profile(
        "Mine", base_profile="documents", slots=_slots(), schema_version=1
    )
    with pytest.raises(ValueError):
        profiles.set_profile_embedding(
            record["profile_id"], provider="ollama", model=None, dimensions=None
        )
    with pytest.raises(KeyError):
        profiles.set_profile_embedding("nope", provider=None, model=None, dimensions=None)


def test_create_can_carry_an_embedding_choice(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    record = stores[1].create_profile(
        "Copy",
        base_profile="documents",
        slots=_slots(),
        schema_version=1,
        embedding=("llamacpp", "model-b", 1024),
    )
    assert (record["embed_provider"], record["embed_model"], record["embed_dimensions"]) == (
        "llamacpp",
        "model-b",
        1024,
    )


def test_the_catalogue_exposes_the_embedding_keys(
    stores: tuple[SqliteWorkspaceRepository, SqliteProfileRepository],
) -> None:
    from omrg.integrations.workspace_sqlite import SqliteProfileCatalogue

    profiles = stores[1]
    record = profiles.create_profile(
        "Mine", base_profile="documents", slots=_slots(), schema_version=1
    )
    profiles.set_profile_embedding(
        record["profile_id"], provider="ollama", model="m", dimensions=None
    )
    seen = SqliteProfileCatalogue(profiles.path).get_profile(record["profile_id"])
    assert seen is not None
    assert (seen["embed_provider"], seen["embed_model"]) == ("ollama", "m")
