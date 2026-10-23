"""Chat routes: browser session only, deletes need ``manage`` (add-chat-history task 1.3)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

ANSWER = {"status": "ok", "answer": "Yes [1]", "citations": [{"ordinal": 1}]}


@pytest.fixture
def web(tmp_path: Path, effective_settings: Any):  # type: ignore[no-untyped-def]
    engine = make_engine(lance_store(tmp_path), effective_settings())
    app, policy = build_app(tmp_path, engine)
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        yield client, policy, app


def _chat(client: TestClient, title: str = "Q", **extra: Any) -> str:
    response = client.post("/v1/chats", json={"title": title, **extra}, headers=ORIGIN)
    assert response.status_code == 201, response.text
    return response.json()["chat"]["chat_id"]


def _turn(client: TestClient, chat_id: str, answer: Any = ANSWER) -> Any:
    body = {"collection": "docs", "question": "q", "answer": answer}
    return client.post(f"/v1/chats/{chat_id}/turns", json=body, headers=ORIGIN)


def test_create_list_and_get(web: Any) -> None:
    client = web[0]
    chat_id = _chat(client, "First")
    assert _turn(client, chat_id).status_code == 201
    listing = client.get("/v1/chats").json()
    assert listing["chats"][0]["chat_id"] == chat_id
    assert "turns" not in listing["chats"][0]
    got = client.get(f"/v1/chats/{chat_id}").json()["chat"]
    assert got["turns"][0]["answer"] == ANSWER


def test_unknown_chat_is_404(web: Any) -> None:
    client = web[0]
    assert client.get("/v1/chats/nope").status_code == 404
    assert _turn(client, "nope").status_code == 404


def test_empty_title_is_a_validation_error(web: Any) -> None:
    client = web[0]
    assert client.post("/v1/chats", json={"title": " "}, headers=ORIGIN).status_code == 400


def test_answer_over_two_mib_is_413(web: Any) -> None:
    client = web[0]
    chat_id = _chat(client)
    assert _turn(client, chat_id, {"answer": "x" * (2 * 1024 * 1024)}).status_code == 413


def test_folder_move_rename_and_delete_counts(web: Any) -> None:
    client = web[0]
    folder = client.post("/v1/chat-folders", json={"name": "Work"}, headers=ORIGIN).json()
    folder_id = folder["folder"]["folder_id"]
    chat_id = _chat(client, folder_id=folder_id)
    assert (
        client.patch(f"/v1/chat-folders/{folder_id}", json={"name": "Home"}, headers=ORIGIN).json()[
            "folder"
        ]["name"]
        == "Home"
    )
    moved = client.patch(f"/v1/chats/{chat_id}", json={"folder_id": None}, headers=ORIGIN)
    assert moved.json()["chat"]["folder_id"] is None
    client.patch(f"/v1/chats/{chat_id}", json={"folder_id": folder_id}, headers=ORIGIN)
    deleted = client.delete(f"/v1/chat-folders/{folder_id}", headers=ORIGIN)
    assert deleted.status_code == 200
    assert (deleted.json()["chats"], deleted.json()["folders"]) == (1, 1)


def test_delete_one_and_many_report_counts(web: Any) -> None:
    client = web[0]
    a, b, c = _chat(client, "a"), _chat(client, "b"), _chat(client, "c")
    one = client.delete(f"/v1/chats/{a}", headers=ORIGIN).json()
    assert (one["chats"], one["folders"]) == (1, 0)
    many = client.post("/v1/chats/delete", json={"chat_ids": [b, c]}, headers=ORIGIN).json()
    assert many["chats"] == 2


def test_bulk_delete_with_unknown_id_is_404_and_deletes_nothing(web: Any) -> None:
    client = web[0]
    a = _chat(client, "a")
    response = client.post("/v1/chats/delete", json={"chat_ids": [a, "nope"]}, headers=ORIGIN)
    assert response.status_code == 404
    assert len(client.get("/v1/chats").json()["chats"]) == 1


def test_bulk_delete_limits(web: Any) -> None:
    client = web[0]
    assert client.post("/v1/chats/delete", json={"chat_ids": []}, headers=ORIGIN).status_code == 400
    too_many = {"chat_ids": [str(i) for i in range(501)]}
    assert client.post("/v1/chats/delete", json=too_many, headers=ORIGIN).status_code == 400


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/v1/chats"),
        ("get", "/v1/chats/x"),
        ("post", "/v1/chats"),
        ("delete", "/v1/chats/x"),
        ("post", "/v1/chats/delete"),
    ],
)
def test_bearer_token_is_refused_even_with_every_scope(web: Any, method: str, path: str) -> None:
    client, policy, _ = web
    client.cookies.clear()  # leave only the bearer credential
    headers = {**bearer(policy, "graph", "read", "run"), **ORIGIN}
    response = client.request(method, path, headers=headers, json={"title": "x"})
    assert response.status_code == 403, response.text


def test_chat_responses_conform_to_the_contract(web: Any) -> None:
    client = web[0]
    check = ContractChecker()
    folder = check.check(
        client.post("/v1/chat-folders", json={"name": "Work"}, headers=ORIGIN), 201
    )["folder"]["folder_id"]
    check.check(
        client.patch(f"/v1/chat-folders/{folder}", json={"name": "Home"}, headers=ORIGIN), 200
    )
    chat = check.check(
        client.post("/v1/chats", json={"title": "Q", "folder_id": folder}, headers=ORIGIN), 201
    )["chat"]["chat_id"]
    check.check(_turn(client, chat), 201)
    check.check(client.get("/v1/chats"), 200)
    check.check(client.get(f"/v1/chats/{chat}"), 200)
    check.check(client.patch(f"/v1/chats/{chat}", json={"folder_id": None}, headers=ORIGIN), 200)
    order = {"folder_ids": [folder]}
    check.check(client.put("/v1/chat-folders/order", json=order, headers=ORIGIN), 200)
    check.check(client.put("/v1/chat-folders/order", json={"folder_ids": []}, headers=ORIGIN), 400)
    check.check(client.get("/v1/chats/nope"), 404)
    check.check(_turn(client, chat, {"answer": "x" * (2 * 1024 * 1024)}), 413)
    check.check(client.post("/v1/chats", json={"title": " "}, headers=ORIGIN), 400)
    other = _chat(client, "other")
    check.check(client.post("/v1/chats/delete", json={"chat_ids": [other]}, headers=ORIGIN), 200)
    check.check(client.delete(f"/v1/chats/{chat}", headers=ORIGIN), 200)
    check.check(client.delete(f"/v1/chat-folders/{folder}", headers=ORIGIN), 200)
    assert check.operations >= FAMILIES["chats"]


def test_unknown_ids_are_404_on_every_route_that_takes_one(web: Any) -> None:
    client = web[0]
    missing = [
        client.patch("/v1/chats/nope", json={"folder_id": None}, headers=ORIGIN),
        client.delete("/v1/chats/nope", headers=ORIGIN),
        client.patch("/v1/chat-folders/nope", json={"name": "x"}, headers=ORIGIN),
        client.delete("/v1/chat-folders/nope", headers=ORIGIN),
    ]
    assert [r.status_code for r in missing] == [404, 404, 404, 404]
    assert all(r.json()["status"] == "error" for r in missing)


def test_creating_a_chat_in_an_unknown_folder_is_404(web: Any) -> None:
    client = web[0]
    response = client.post("/v1/chats", json={"title": "Q", "folder_id": "nope"}, headers=ORIGIN)
    assert response.status_code == 404


def test_moving_a_chat_into_an_unknown_folder_is_404(web: Any) -> None:
    client = web[0]
    chat_id = _chat(client)
    response = client.patch(f"/v1/chats/{chat_id}", json={"folder_id": "nope"}, headers=ORIGIN)
    assert response.status_code == 404


def test_blank_folder_and_question_values_are_400(web: Any) -> None:
    client = web[0]
    chat_id = _chat(client)
    folder_id = client.post("/v1/chat-folders", json={"name": "Work"}, headers=ORIGIN).json()[
        "folder"
    ]["folder_id"]
    blank = [
        client.post("/v1/chat-folders", json={"name": "   "}, headers=ORIGIN),
        client.patch(f"/v1/chat-folders/{folder_id}", json={"name": "   "}, headers=ORIGIN),
        client.post(
            f"/v1/chats/{chat_id}/turns",
            json={"collection": "docs", "question": "   ", "answer": ANSWER},
            headers=ORIGIN,
        ),
    ]
    assert [r.status_code for r in blank] == [400, 400, 400]


def test_chat_routes_answer_503_when_the_server_has_no_chat_store(web: Any) -> None:
    client, _, app = web
    runtime = app.state.runtime
    saved, runtime.chats = runtime.chats, None
    try:
        assert client.get("/v1/chats").status_code == 503
    finally:
        runtime.chats = saved


def test_reorder_folders_changes_the_listing_order(web: Any) -> None:
    client = web[0]
    ids = [
        client.post("/v1/chat-folders", json={"name": name}, headers=ORIGIN).json()["folder"][
            "folder_id"
        ]
        for name in ("A", "B", "C")
    ]
    order = [ids[2], ids[0], ids[1]]
    response = client.put("/v1/chat-folders/order", json={"folder_ids": order}, headers=ORIGIN)
    assert response.status_code == 200, response.text
    assert [f["folder_id"] for f in response.json()["folders"]] == order
    assert [f["folder_id"] for f in client.get("/v1/chats").json()["folders"]] == order


def test_reorder_folders_rejects_a_partial_or_unknown_list(web: Any) -> None:
    client = web[0]
    a = client.post("/v1/chat-folders", json={"name": "A"}, headers=ORIGIN).json()["folder"][
        "folder_id"
    ]
    client.post("/v1/chat-folders", json={"name": "B"}, headers=ORIGIN)
    partial = client.put("/v1/chat-folders/order", json={"folder_ids": [a]}, headers=ORIGIN)
    unknown = client.put("/v1/chat-folders/order", json={"folder_ids": [a, "nope"]}, headers=ORIGIN)
    assert (partial.status_code, unknown.status_code) == (400, 404)
