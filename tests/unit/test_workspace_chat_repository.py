"""SQLite chat repository (add-chat-history task 1.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.core.workspace.chats import ChatRepository
from omrs.integrations.workspace_sqlite import SqliteWorkspaceRepository
from omrs.integrations.workspace_sqlite.chats import SqliteChatRepository

ANSWER = {"status": "ok", "answer": "Yes [1]", "citations": [{"ordinal": 1}]}


@pytest.fixture
def chats(tmp_path: Path) -> SqliteChatRepository:
    path = tmp_path / "app.sqlite3"
    SqliteWorkspaceRepository(path)
    return SqliteChatRepository(path)


def test_implements_protocol(chats: SqliteChatRepository) -> None:
    assert isinstance(chats, ChatRepository)


def test_create_and_get_chat(chats: SqliteChatRepository) -> None:
    chat = chats.create_chat("First question")
    assert chat["title"] == "First question"
    assert chat["folder_id"] is None
    got = chats.get_chat(chat["chat_id"])
    assert got["turns"] == []


def test_append_turn_assigns_positions_and_round_trips_answer(
    chats: SqliteChatRepository,
) -> None:
    chat_id = chats.create_chat("t")["chat_id"]
    first = chats.append_turn(chat_id, "docs", "q1", ANSWER)
    second = chats.append_turn(chat_id, "docs", "q2", {"status": "ok", "answer": "No"})
    assert (first["position"], second["position"]) == (1, 2)
    turns = chats.get_chat(chat_id)["turns"]
    assert [t["question"] for t in turns] == ["q1", "q2"]
    assert turns[0]["answer"] == ANSWER
    assert turns[0]["collection"] == "docs"


def test_append_to_unknown_chat_raises_key_error(chats: SqliteChatRepository) -> None:
    with pytest.raises(KeyError):
        chats.append_turn("nope", "docs", "q", ANSWER)


def test_list_returns_newest_chat_first_without_turns(chats: SqliteChatRepository) -> None:
    old = chats.create_chat("old")["chat_id"]
    new = chats.create_chat("new")["chat_id"]
    chats.append_turn(old, "docs", "q", ANSWER)
    listing = chats.list_chats()
    assert [c["chat_id"] for c in listing["chats"]] == [old, new]
    assert "turns" not in listing["chats"][0]


def test_folders_create_rename_and_move(chats: SqliteChatRepository) -> None:
    folder = chats.create_folder("Work")
    chat_id = chats.create_chat("t")["chat_id"]
    assert chats.move_chat(chat_id, folder["folder_id"])["folder_id"] == folder["folder_id"]
    assert chats.rename_folder(folder["folder_id"], "Home")["name"] == "Home"
    assert chats.move_chat(chat_id, None)["folder_id"] is None
    listing = chats.list_chats()
    assert [f["name"] for f in listing["folders"]] == ["Home"]


def test_move_to_unknown_folder_raises_key_error(chats: SqliteChatRepository) -> None:
    chat_id = chats.create_chat("t")["chat_id"]
    with pytest.raises(KeyError):
        chats.move_chat(chat_id, "nope")
    with pytest.raises(KeyError):
        chats.move_chat("nope", None)


def test_delete_one_returns_counts(chats: SqliteChatRepository) -> None:
    chat_id = chats.create_chat("t")["chat_id"]
    chats.append_turn(chat_id, "docs", "q", ANSWER)
    assert chats.delete_chat(chat_id) == {"chats": 1, "folders": 0}
    with pytest.raises(KeyError):
        chats.get_chat(chat_id)
    with pytest.raises(KeyError):
        chats.delete_chat(chat_id)


def test_delete_many_is_all_or_nothing(chats: SqliteChatRepository) -> None:
    a = chats.create_chat("a")["chat_id"]
    b = chats.create_chat("b")["chat_id"]
    with pytest.raises(KeyError):
        chats.delete_chats([a, "nope", b])
    assert len(chats.list_chats()["chats"]) == 2
    assert chats.delete_chats([a, b]) == {"chats": 2, "folders": 0}
    assert chats.list_chats()["chats"] == []


def test_delete_many_rolls_back_deletes_made_before_an_unknown_id(
    chats: SqliteChatRepository,
) -> None:
    """The unknown id comes last, so only the transaction restores the first two."""
    a = chats.create_chat("a")["chat_id"]
    b = chats.create_chat("b")["chat_id"]
    with pytest.raises(KeyError):
        chats.delete_chats([a, b, "nope"])
    assert len(chats.list_chats()["chats"]) == 2


def test_delete_folder_removes_its_chats(chats: SqliteChatRepository) -> None:
    folder = chats.create_folder("Work")["folder_id"]
    inside = chats.create_chat("in", folder_id=folder)["chat_id"]
    chats.append_turn(inside, "docs", "q", ANSWER)
    outside = chats.create_chat("out")["chat_id"]
    assert chats.delete_folder(folder) == {"chats": 1, "folders": 1}
    assert [c["chat_id"] for c in chats.list_chats()["chats"]] == [outside]
    with pytest.raises(KeyError):
        chats.delete_folder(folder)


@pytest.mark.parametrize(
    "call",
    [
        lambda r: r.create_chat(""),
        lambda r: r.create_chat("x" * 201),
        lambda r: r.create_folder(""),
        lambda r: r.create_folder("x" * 101),
    ],
)
def test_limits_raise_value_error(chats: SqliteChatRepository, call) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        call(chats)


def test_turn_limits(chats: SqliteChatRepository) -> None:
    chat_id = chats.create_chat("t")["chat_id"]
    with pytest.raises(ValueError):
        chats.append_turn(chat_id, "docs", "", ANSWER)
    with pytest.raises(ValueError):
        chats.append_turn(chat_id, "docs", "q" * 10_001, ANSWER)
    with pytest.raises(ValueError):
        chats.append_turn(chat_id, "docs", "q", {"answer": "x" * (2 * 1024 * 1024)})


def test_new_folders_go_to_the_end(chats: SqliteChatRepository) -> None:
    first = chats.create_folder("First")["folder_id"]
    second = chats.create_folder("Second")["folder_id"]
    assert [f["folder_id"] for f in chats.list_chats()["folders"]] == [first, second]


def test_reorder_folders_sets_the_listing_order(chats: SqliteChatRepository) -> None:
    a, b, c = (chats.create_folder(name)["folder_id"] for name in ("A", "B", "C"))
    returned = chats.reorder_folders([c, a, b])
    assert [f["folder_id"] for f in returned] == [c, a, b]
    assert [f["folder_id"] for f in chats.list_chats()["folders"]] == [c, a, b]
    later = chats.create_folder("D")["folder_id"]
    assert chats.list_chats()["folders"][-1]["folder_id"] == later


@pytest.mark.parametrize("order", [["A"], ["A", "A", "B"], ["A", "B", "B"]])
def test_reorder_needs_every_folder_once(chats: SqliteChatRepository, order: list[str]) -> None:
    ids = {name: chats.create_folder(name)["folder_id"] for name in ("A", "B")}
    with pytest.raises(ValueError):
        chats.reorder_folders([ids[name] for name in order])
    assert [f["name"] for f in chats.list_chats()["folders"]] == ["A", "B"]


def test_reorder_with_an_unknown_folder_raises_key_error(chats: SqliteChatRepository) -> None:
    a = chats.create_folder("A")["folder_id"]
    with pytest.raises(KeyError):
        chats.reorder_folders([a, "nope"])
