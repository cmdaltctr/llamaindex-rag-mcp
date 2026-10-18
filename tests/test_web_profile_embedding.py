"""Profile embedding model over HTTP (add-profile-embedding-model, tasks 7.5, 8.3, 8.5).

A real Engine, a real LanceDB store and a real SQLite workspace sit behind the
app. The model check is faked, so no provider call happens.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    bearer,
    lance_store,
    login,
    make_engine,
    seed,
)
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402
from tests.unit.test_web_runs_support import build_app  # noqa: E402

from omrg import compose_embedding  # noqa: E402
from omrg.core.profiles.resolver import ProfileResolver  # noqa: E402
from omrg.core.vectordb.identity import (  # noqa: E402
    IDENTITY_MODEL_KEY,
    IDENTITY_PROVIDER_KEY,
    EmbeddingIdentity,
)

HOST = EmbeddingIdentity("llamacpp", "host-model")
COLLECTION = "notes"


class FakeCheck:
    """A model check that records its calls. ``before`` runs before it answers."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.fail: dict[str, str] = {}
        self.before: Callable[[], None] | None = None

    def __call__(self, provider: str, model: str, **_: Any) -> dict[str, Any]:
        self.calls.append((provider, model))
        if provider == "nope":
            raise compose_embedding.UnknownEmbeddingProviderError("Unknown embedding provider")
        if self.before is not None:
            self.before()
        if model in self.fail:
            return {"ok": False, "dimensions": None, "norm": None, "reason": self.fail[model]}
        return {"ok": True, "dimensions": 768, "norm": 1.0, "reason": None}


@pytest.fixture
def check(monkeypatch: pytest.MonkeyPatch) -> FakeCheck:
    fake = FakeCheck()
    monkeypatch.setattr(compose_embedding, "check_embedding_model", fake)
    monkeypatch.setattr(compose_embedding, "server_default_identity", lambda *a, **k: HOST)
    return fake


@pytest.fixture
def setup(tmp_path: Path, effective_settings: Any, check: FakeCheck) -> dict[str, Any]:
    store = lance_store(tmp_path)
    seed(store, COLLECTION, "/data/a.md", 2)
    settings = effective_settings()
    resolver = ProfileResolver(store=store, server_profile="documents", base=settings)
    engine = make_engine(store, settings, profile_resolver=resolver)
    app, policy = build_app(tmp_path, engine)
    return {"store": store, "app": app, "policy": policy}


@pytest.fixture
def client(setup: dict[str, Any]) -> Iterator[TestClient]:
    with TestClient(setup["app"], base_url=BASE) as test_client:
        login(test_client, setup["policy"])
        test_client.policy = setup["policy"]  # type: ignore[attr-defined]
        test_client.store = setup["store"]  # type: ignore[attr-defined]
        yield test_client


def _profile(client: TestClient, title: str = "Mine", **body: Any) -> str:
    response = client.post(
        "/v1/profiles", json={"title": title, "source": "documents", **body}, headers=ORIGIN
    )
    assert response.status_code == 201, response.text
    return response.json()["profile"]["profile_id"]


def _put(client: TestClient, pid: str, provider: str | None, model: str | None) -> Any:
    return client.put(
        f"/v1/profiles/{pid}/embedding",
        json={"provider": provider, "model": model},
        headers=ORIGIN,
    )


def _bind(client: TestClient, collection: str, pid: str) -> None:
    client.store.update_collection_metadata(collection, {"profile": pid})


def _stamp(client: TestClient, collection: str, provider: str, model: str) -> None:
    client.store.update_collection_metadata(
        collection, {IDENTITY_PROVIDER_KEY: provider, IDENTITY_MODEL_KEY: model}
    )


def _item(client: TestClient, pid: str) -> dict[str, Any]:
    return client.get(f"/v1/profiles/{pid}").json()["profile"]


# ── Provider list and check (8.3) ────────────────────────────────────────


def test_the_provider_list_shows_availability_and_the_server_default(client: TestClient) -> None:
    body = client.get("/v1/embedding-providers").json()
    assert body["status"] == "ok"
    assert body["server_default"] == {"provider": "llamacpp", "model": "host-model"}
    names = {p["name"]: p for p in body["providers"]}
    assert {"ollama", "llamacpp", "openrouter"} <= set(names)
    for item in names.values():
        assert set(item) == {"name", "available", "reason"}
    assert names["ollama"]["available"] is True and names["ollama"]["reason"] is None


def test_check_returns_size_and_norm_and_a_failure_is_not_an_error_status(
    client: TestClient, check: FakeCheck
) -> None:
    good = client.post(
        "/v1/embedding-providers/ollama/check", json={"model": "nomic"}, headers=ORIGIN
    )
    assert good.status_code == 200, good.text
    assert good.json() == {
        "status": "ok",
        "ok": True,
        "dimensions": 768,
        "norm": 1.0,
        "reason": None,
    }
    check.fail["bad"] = "ollama could not embed with bad: not found"
    bad = client.post("/v1/embedding-providers/ollama/check", json={"model": "bad"}, headers=ORIGIN)
    assert bad.status_code == 200
    assert bad.json()["ok"] is False and "not found" in bad.json()["reason"]


def test_check_of_an_unregistered_provider_is_404(client: TestClient) -> None:
    response = client.post(
        "/v1/embedding-providers/nope/check", json={"model": "m"}, headers=ORIGIN
    )
    assert response.status_code == 404


def test_check_and_save_need_the_browser_session(client: TestClient) -> None:
    pid = _profile(client)
    reader = bearer(client.policy, "read", "graph")  # type: ignore[attr-defined]
    check = client.post("/v1/embedding-providers/ollama/check", json={"model": "m"}, headers=reader)
    save = client.put(
        f"/v1/profiles/{pid}/embedding", json={"provider": None, "model": None}, headers=reader
    )
    assert check.status_code == 403 and save.status_code == 403
    only_read = bearer(client.policy, "read")  # type: ignore[attr-defined]
    assert client.get("/v1/embedding-providers", headers=only_read).status_code == 200


# ── Save (8.3) ───────────────────────────────────────────────────────────


def test_an_unlocked_profile_saves_a_checked_model(client: TestClient, check: FakeCheck) -> None:
    pid = _profile(client)
    response = _put(client, pid, "ollama", "nomic-embed-text")
    assert response.status_code == 200, response.text
    embedding = response.json()["profile"]["embedding"]
    assert embedding == {
        "provider": "ollama",
        "model": "nomic-embed-text",
        "source": "profile",
        "dimensions": 768,
    }
    assert check.calls == [("ollama", "nomic-embed-text")]
    assert _item(client, pid)["embedding"]["model"] == "nomic-embed-text"


def test_clearing_the_choice_returns_the_server_default(client: TestClient) -> None:
    pid = _profile(client)
    _put(client, pid, "ollama", "nomic-embed-text")
    cleared = _put(client, pid, None, None)
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["profile"]["embedding"] == {
        "provider": "llamacpp",
        "model": "host-model",
        "source": "server_default",
        "dimensions": None,
    }


def test_a_failed_check_is_422_with_the_reason_and_keeps_the_old_model(
    client: TestClient, check: FakeCheck
) -> None:
    pid = _profile(client)
    _put(client, pid, "ollama", "good")
    check.fail["bad"] = "ollama could not embed with bad: model not found"
    response = _put(client, pid, "ollama", "bad")
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["reason"] == "ollama could not embed with bad: model not found"
    assert body["status"] == "error"
    assert _item(client, pid)["embedding"]["model"] == "good"


def test_an_unregistered_provider_on_save_is_404(client: TestClient) -> None:
    assert _put(client, _profile(client), "nope", "m").status_code == 404


def test_a_provider_without_a_model_is_400(client: TestClient) -> None:
    assert _put(client, _profile(client), "ollama", None).status_code == 400


def test_a_built_in_profile_refuses_a_model_change(client: TestClient, check: FakeCheck) -> None:
    response = _put(client, "documents", "ollama", "m")
    assert response.status_code == 400
    assert response.json()["message"] == "Duplicate the profile to choose another model."
    assert check.calls == []


def test_an_unknown_profile_is_404(client: TestClient) -> None:
    assert _put(client, "ghost", None, None).status_code == 404


# ── Lock (8.3) ───────────────────────────────────────────────────────────


def test_a_stamped_collection_locks_the_model_and_names_the_collection(
    client: TestClient,
) -> None:
    pid = _profile(client)
    _put(client, pid, "ollama", "model-a")
    _bind(client, COLLECTION, pid)
    _stamp(client, COLLECTION, "ollama", "model-a")
    response = _put(client, pid, "ollama", "model-b")
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error_type"] == "embedding_locked"
    assert body["collections"] == [
        {"collection": COLLECTION, "provider": "ollama", "model": "model-a", "chunk_count": 2}
    ]
    assert _item(client, pid)["embedding"]["model"] == "model-a"


def test_rows_without_a_stamp_lock_with_a_null_model(client: TestClient) -> None:
    pid = _profile(client)
    _bind(client, COLLECTION, pid)
    body = _put(client, pid, "ollama", "model-b").json()
    assert body["error_type"] == "embedding_locked"
    assert body["collections"][0]["model"] is None
    assert body["collections"][0]["provider"] is None


def test_a_change_back_to_the_stamped_model_is_allowed(client: TestClient) -> None:
    pid = _profile(client)
    _bind(client, COLLECTION, pid)
    _stamp(client, COLLECTION, "ollama", "model-a")
    assert _put(client, pid, "ollama", "model-a").status_code == 200


def test_an_empty_bound_collection_does_not_lock(client: TestClient) -> None:
    pid = _profile(client)
    client.store.update_collection_metadata("drafts", {"profile": pid})
    assert _put(client, pid, "ollama", "model-b").status_code == 200


def test_the_first_blocking_collection_comes_first(client: TestClient) -> None:
    pid = _profile(client)
    seed(client.store, "alpha", "/data/b.md", 1)
    for name in ("alpha", COLLECTION):
        _bind(client, name, pid)
        _stamp(client, name, "ollama", "model-a")
    collections = _put(client, pid, "ollama", "model-b").json()["collections"]
    assert [c["collection"] for c in collections] == ["alpha", COLLECTION]


def test_a_stamp_that_appears_during_the_check_still_blocks_the_save(
    client: TestClient, check: FakeCheck
) -> None:
    pid = _profile(client)
    _bind(client, COLLECTION, pid)

    def stamp_during_the_probe() -> None:
        _stamp(client, COLLECTION, "ollama", "model-a")

    check.before = stamp_during_the_probe
    response = _put(client, pid, "ollama", "model-b")
    assert response.status_code == 409, response.text
    assert response.json()["error_type"] == "embedding_locked"
    assert _item(client, pid)["embedding"]["source"] == "server_default"


def test_the_ingest_write_lock_is_held_while_the_row_is_saved(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.core.ingestion import write_lock

    pid = _profile(client)
    seen: list[bool] = []
    from omrg.compose_profile_embedding import ProfileEmbedding

    original = ProfileEmbedding._states

    def spying(self: Any, collections: list[str]) -> Any:
        seen.append(write_lock.locked())
        return original(self, collections)

    monkeypatch.setattr(ProfileEmbedding, "_states", spying)
    assert _put(client, pid, "ollama", "model-b").status_code == 200
    assert seen[0] is True
    assert not write_lock.locked()


# ── Profile items (8.3) ──────────────────────────────────────────────────


def test_every_profile_item_carries_embedding_and_lock(client: TestClient) -> None:
    pid = _profile(client)
    _bind(client, COLLECTION, pid)
    _stamp(client, COLLECTION, "ollama", "model-a")
    items = {p["profile_id"]: p for p in client.get("/v1/profiles").json()["profiles"]}
    for builtin in ("documents", "codebase"):
        assert items[builtin]["embedding"]["source"] == "server_default"
        assert items[builtin]["embedding"]["model"] == "host-model"
        assert items[builtin]["embedding_lock"] == {"locked": False, "collections": []}
    mine = items[pid]
    assert mine["embedding"]["source"] == "server_default"
    assert mine["embedding_lock"]["locked"] is True
    assert mine["embedding_lock"]["collections"] == [
        {"collection": COLLECTION, "provider": "ollama", "model": "model-a", "chunk_count": 2}
    ]
    detail = _item(client, "documents")
    assert detail["embedding"]["provider"] == "llamacpp" and "embedding_lock" in detail


def test_duplicating_a_profile_copies_its_embedding_choice(client: TestClient) -> None:
    pid = _profile(client)
    _put(client, pid, "ollama", "model-a")
    copy = _profile(client, "Copy", source=pid)
    assert _item(client, copy)["embedding"] == {
        "provider": "ollama",
        "model": "model-a",
        "source": "profile",
        "dimensions": 768,
    }
    fresh = _profile(client, "Fresh", source="documents")
    assert _item(client, fresh)["embedding"]["source"] == "server_default"


# ── Binding (7.5) ────────────────────────────────────────────────────────


def _patch(client: TestClient, pid: str, **body: Any) -> Any:
    return client.patch(
        f"/v1/collections/{COLLECTION}/profile", json={"profile": pid, **body}, headers=ORIGIN
    )


def test_the_preview_refuses_a_profile_with_another_model_and_names_both(
    client: TestClient,
) -> None:
    pid = _profile(client)
    _put(client, pid, "ollama", "model-b")
    _stamp(client, COLLECTION, "ollama", "model-a")
    response = _patch(client, pid)
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["error_type"] == "embedding_mismatch"
    assert "model-a" in body["message"] and "model-b" in body["message"]
    meta = client.store.get_collection_metadata(COLLECTION) or {}
    assert meta.get("profile") in (None, "documents")


def test_the_confirm_step_refuses_too_and_the_tag_stays(client: TestClient) -> None:
    pid = _profile(client)
    _put(client, pid, "ollama", "model-a")
    _stamp(client, COLLECTION, "ollama", "model-a")
    preview = _patch(client, pid)
    assert preview.status_code == 200, preview.text
    token = preview.json()["confirmation"]["token"]
    # A model change that skips the lock check, as a race would: the confirm step must still refuse.
    service = client.app.state.runtime.profiles  # type: ignore[attr-defined]
    service._profiles.set_profile_embedding(
        pid, provider="ollama", model="model-b", dimensions=None
    )
    response = _patch(client, pid, confirm=True, confirmation_token=token)
    assert response.status_code == 409, response.text
    assert response.json()["error_type"] == "embedding_mismatch"
    assert (client.store.get_collection_metadata(COLLECTION) or {}).get("profile") != pid


def test_a_built_in_profile_is_refused_for_a_collection_made_with_another_model(
    client: TestClient,
) -> None:
    _stamp(client, COLLECTION, "ollama", "model-a")
    response = _patch(client, "codebase")
    assert response.status_code == 409
    assert response.json()["error_type"] == "embedding_mismatch"
    assert "model-a" in response.json()["message"] and "host-model" in response.json()["message"]


def test_a_matching_stamp_binds(client: TestClient) -> None:
    pid = _profile(client)
    _put(client, pid, "ollama", "model-a")
    _stamp(client, COLLECTION, "ollama", "model-a")
    preview = _patch(client, pid)
    assert preview.status_code == 200, preview.text
    applied = _patch(
        client, pid, confirm=True, confirmation_token=preview.json()["confirmation"]["token"]
    )
    assert applied.status_code == 200, applied.text
    assert (client.store.get_collection_metadata(COLLECTION) or {}).get("profile") == pid


def test_unstamped_rows_bind_to_the_server_default_only(client: TestClient) -> None:
    other = _profile(client, "Other")
    _put(client, other, "ollama", "model-b")
    assert _patch(client, other).status_code == 409
    default = _profile(client, "Default")
    assert _patch(client, default).status_code == 200


# ── OpenAPI conformance (8.6) ────────────────────────────────────────────


def test_embedding_responses_conform_to_the_contract(client: TestClient, check: FakeCheck) -> None:
    contract = ContractChecker()
    contract.check(client.get("/v1/embedding-providers"), 200)
    contract.check(
        client.post("/v1/embedding-providers/ollama/check", json={"model": "m"}, headers=ORIGIN),
        200,
    )
    check.fail["bad"] = "nope"
    contract.check(
        client.post("/v1/embedding-providers/ollama/check", json={"model": "bad"}, headers=ORIGIN),
        200,
    )
    contract.check(
        client.post("/v1/embedding-providers/nope/check", json={"model": "m"}, headers=ORIGIN),
        404,
    )
    pid = _profile(client)
    contract.check(client.get("/v1/profiles"), 200)
    contract.check(_put(client, pid, "ollama", "model-a"), 200)
    contract.check(_put(client, pid, "ollama", "bad"), 422)
    contract.check(_put(client, "documents", "ollama", "m"), 400)
    contract.check(_put(client, "ghost", None, None), 404)
    seed(client.store, "papers", "/data/p.md", 1)
    _bind(client, "papers", pid)
    _stamp(client, "papers", "ollama", "model-a")
    contract.check(_put(client, pid, "ollama", "model-b"), 409)
    other = _profile(client, "Other")
    _put(client, other, "llamacpp", "model-c")
    contract.check(_patch(client, other), 409)
    assert contract.operations >= FAMILIES["embedding"]
