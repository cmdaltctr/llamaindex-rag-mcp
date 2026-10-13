"""Tests for preview-bound destructive actions (task 6.5).

Deletion and stored profile changes need a preview first. The preview
returns a single-use confirmation bound to the action, the selector,
the store's observed validity token and an expiry. Altered selectors,
stale validity tokens, expired or reused confirmations are rejected,
and the data stays unchanged until a valid confirmation arrives.
"""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    PENDING_CONTRACT_KEYS,
    assert_conforms,
    bearer,
    build_app,
    lance_store,
    login,
    make_engine,
    process_local_store,
    seed,
    undeclared_keys,
)

from omrg.core.profiles.resolver import ProfileResolver  # noqa: E402
from omrg.transports.api.confirmations import (  # noqa: E402
    CONFIRMATIONS_STATE,
    ConfirmationBook,
)

COLLECTION = "notes"
DOCS = f"/v1/collections/{COLLECTION}/documents"
PROFILE = f"/v1/collections/{COLLECTION}/profile"
A, B = "/data/a.md", "/data/b.md"


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture(params=["durable", "process_local"])
def setup(request: pytest.FixtureRequest, tmp_path: Path, effective_settings) -> dict[str, Any]:
    maker = lance_store if request.param == "durable" else process_local_store
    store = maker(tmp_path)
    seed(store, COLLECTION, A, 3)
    seed(store, COLLECTION, B, 2)
    settings = effective_settings()
    resolver = ProfileResolver(store=store, server_profile="documents", base=settings)
    engine = make_engine(store, settings, profile_resolver=resolver)
    app, policy = build_app(tmp_path, engine)
    clock = Clock()
    setattr(app.state, CONFIRMATIONS_STATE, ConfirmationBook(clock=clock))
    return {
        "kind": request.param,
        "store": store,
        "engine": engine,
        "app": app,
        "policy": policy,
        "clock": clock,
    }


def _delete(client: TestClient, body: dict | None) -> Any:
    return client.request("DELETE", DOCS, json=body, headers=ORIGIN)


def _count(store: Any) -> int:
    return store.count(COLLECTION)


# ── Deletion ─────────────────────────────────────────────────────────────


def test_preview_reports_scope_and_mutates_nothing(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        preview = _delete(client, {"path": A, "dry_run": True})
    body = preview.json()
    assert preview.status_code == 200, preview.text
    assert_conforms("/collections/{collection}/documents", "delete", 200, body)
    assert undeclared_keys("DeleteResult", body) <= PENDING_CONTRACT_KEYS["DeleteResult"]
    assert (body["mode"], body["would_delete"], body["dry_run"]) == ("path", 3, True)
    assert body["confirmation"]["token"]
    assert body["confirmation"]["expires_in"] > 0
    assert _count(setup["store"]) == 5


def test_confirmed_preview_deletes_exactly_the_selection(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        token = _delete(client, {"path": A, "dry_run": True}).json()["confirmation"]["token"]
        done = _delete(client, {"path": A, "confirmation_token": token})
        reused = _delete(client, {"path": A, "confirmation_token": token})
    assert done.status_code == 200, done.text
    assert_conforms("/collections/{collection}/documents", "delete", 200, done.json())
    assert (done.json()["mode"], done.json()["chunks_removed"]) == ("path", 3)
    assert _count(setup["store"]) == 2
    assert reused.status_code == 409  # single use


def test_metadata_and_collection_modes_are_preview_bound(setup: dict) -> None:
    selector = {"metadata_filter": {"file_path": B}}
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        meta = _delete(client, {**selector, "dry_run": True}).json()
        meta_done = _delete(
            client, {**selector, "confirmation_token": meta["confirmation"]["token"]}
        ).json()
        drop = _delete(client, {"dry_run": True}).json()
        drop_done = _delete(client, {"confirmation_token": drop["confirmation"]["token"]})
    assert (meta["mode"], meta["would_delete"]) == ("metadata", 2)
    assert (meta_done["mode"], meta_done["chunks_removed"]) == ("metadata", 2)
    assert (drop["mode"], drop["would_delete"]) == ("collection", 3)
    assert drop_done.status_code == 200
    assert drop_done.json()["mode"] == "collection"
    assert COLLECTION not in setup["store"].list_collections()


def test_delete_without_confirmation_never_mutates(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        no_body = client.request("DELETE", DOCS, headers=ORIGIN)
        no_token = _delete(client, {"path": A})
        unknown = _delete(client, {"path": A, "confirmation_token": "cf_forged"})
    assert no_body.status_code == 428
    assert no_token.status_code == 428
    assert_conforms("/collections/{collection}/documents", "delete", 428, no_token.json())
    assert "preview" in no_token.json()["message"].lower()
    assert unknown.status_code == 409
    assert _count(setup["store"]) == 5


@pytest.mark.parametrize(
    "altered",
    [
        {"path": B},
        {"metadata_filter": {"file_path": A}},
        {},
    ],
)
def test_altered_selector_is_rejected_and_needs_new_preview(setup: dict, altered: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        token = _delete(client, {"path": A, "dry_run": True}).json()["confirmation"]["token"]
        altered_response = _delete(client, {**altered, "confirmation_token": token})
        original_after = _delete(client, {"path": A, "confirmation_token": token})
    assert altered_response.status_code == 409
    assert "preview" in altered_response.json()["message"].lower()
    assert original_after.status_code == 409  # the rejected token is spent
    assert _count(setup["store"]) == 5


def test_altered_collection_is_rejected(setup: dict) -> None:
    seed(setup["store"], "other", A, 3)
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        token = _delete(client, {"path": A, "dry_run": True}).json()["confirmation"]["token"]
        response = client.request(
            "DELETE",
            "/v1/collections/other/documents",
            json={"path": A, "confirmation_token": token},
            headers=ORIGIN,
        )
    assert response.status_code == 409
    assert setup["store"].count("other") == 3


def test_store_change_after_preview_makes_confirmation_stale(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        token = _delete(client, {"path": A, "dry_run": True}).json()["confirmation"]["token"]
        seed(setup["store"], COLLECTION, "/data/c.md", 1)  # a write after the preview
        stale = _delete(client, {"path": A, "confirmation_token": token})
    assert stale.status_code == 409
    assert "changed" in stale.json()["message"].lower()
    assert _count(setup["store"]) == 6


def test_expired_confirmation_is_rejected(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        preview = _delete(client, {"path": A, "dry_run": True}).json()
        setup["clock"].now += preview["confirmation"]["expires_in"] + 1
        expired = _delete(
            client, {"path": A, "confirmation_token": preview["confirmation"]["token"]}
        )
    assert expired.status_code == 409
    assert "expired" in expired.json()["message"].lower()
    assert _count(setup["store"]) == 5


def test_backend_guarantee_is_disclosed(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        confirmation = _delete(client, {"path": A, "dry_run": True}).json()["confirmation"]
    if setup["kind"] == "durable":
        assert confirmation["validity"] == "durable"
        assert confirmation["warning"] is None
    else:
        assert confirmation["validity"] == "process_local"
        assert "another process" in confirmation["warning"]


def test_invalid_selectors_are_validation_errors(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        both = _delete(client, {"path": A, "metadata_filter": {"a": 1}, "dry_run": True})
        empty = _delete(client, {"metadata_filter": {}, "dry_run": True})
        extra = _delete(client, {"path": A, "dry_run": True, "everything": True})
    for response in (both, empty, extra):
        assert response.status_code == 400
        assert_conforms("/collections/{collection}/documents", "delete", 400, response.json())
    assert _count(setup["store"]) == 5


def test_bearer_credentials_cannot_run_destructive_actions(setup: dict) -> None:
    policy = setup["policy"]
    notebook = bearer(policy, "read", "run", "graph")
    with TestClient(setup["app"], base_url=BASE) as client:
        preview = client.request(
            "DELETE", DOCS, json={"path": A, "dry_run": True}, headers=notebook
        )
        profile = client.patch(PROFILE, json={"profile": "codebase"}, headers=notebook)
    assert preview.status_code == 403
    assert profile.status_code == 403
    assert _count(setup["store"]) == 5


def test_destructive_scope_is_session_only() -> None:
    """``manage`` guards deletion and profile changes; no bearer may hold it."""
    from omrg.transports.api import routes_admin
    from omrg.transports.api.security import BEARER_SCOPES, SESSION_SCOPES, AccessPolicy

    assert "manage" in SESSION_SCOPES and "manage" not in BEARER_SCOPES
    policy = AccessPolicy("127.0.0.1", 8765, bootstrap_secret=secrets.token_hex(8))
    with pytest.raises(ValueError):
        policy.issue_bearer({"manage"})
    assert 'require_session("manage")' in Path(routes_admin.__file__).read_text(encoding="utf-8")


# ── Profile change ───────────────────────────────────────────────────────


def _profile_tag(store: Any) -> Any:
    return (store.get_collection_metadata(COLLECTION) or {}).get("profile")


def test_profile_preview_then_confirm_changes_query_defaults_only(setup: dict) -> None:
    store, engine = setup["store"], setup["engine"]
    before = engine.resolve_settings(COLLECTION)
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        preview = client.patch(PROFILE, json={"profile": "codebase"}, headers=ORIGIN)
        body = preview.json()
        assert _profile_tag(store) is None  # preview mutates nothing
        applied = client.patch(
            PROFILE,
            json={
                "profile": "codebase",
                "confirm": True,
                "confirmation_token": body["confirmation"]["token"],
            },
            headers=ORIGIN,
        )
        after = engine.resolve_settings(COLLECTION)
    assert preview.status_code == 200, preview.text
    assert_conforms(
        "/collections/{collection}/profile", "patch", 200, body, variant="ProfilePreview"
    )
    assert undeclared_keys("ProfilePreview", body) <= PENDING_CONTRACT_KEYS["ProfilePreview"]
    assert (body["status"], body["confirm_required"]) == ("preview", True)
    assert body["contract"]["new_profile"] == "codebase"
    assert body["contract"]["chunk_count"] == 5
    assert applied.status_code == 200, applied.text
    assert_conforms(
        "/collections/{collection}/profile",
        "patch",
        200,
        applied.json(),
        variant="ProfileChangeResult",
    )
    assert applied.json() == {
        "status": "ok",
        "collection": COLLECTION,
        "profile": "codebase",
        "chunk_count_unchanged": 5,
    }
    assert _profile_tag(store) == "codebase"
    assert _count(store) == 5
    # Query defaults follow the existing profile contract (documents is
    # dense-only, codebase is hybrid).
    assert (before.hybrid_enabled, after.hybrid_enabled) == (False, True)


def test_profile_confirm_needs_matching_fresh_preview(setup: dict) -> None:
    store = setup["store"]
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        missing = client.patch(
            PROFILE, json={"profile": "codebase", "confirm": True}, headers=ORIGIN
        )
        token = client.patch(PROFILE, json={"profile": "codebase"}, headers=ORIGIN).json()[
            "confirmation"
        ]["token"]
        altered = client.patch(
            PROFILE,
            json={"profile": "documents", "confirm": True, "confirmation_token": token},
            headers=ORIGIN,
        )
        token = client.patch(PROFILE, json={"profile": "codebase"}, headers=ORIGIN).json()[
            "confirmation"
        ]["token"]
        store.update_collection_metadata(COLLECTION, {"profile": "documents"})
        stale = client.patch(
            PROFILE,
            json={"profile": "codebase", "confirm": True, "confirmation_token": token},
            headers=ORIGIN,
        )
        invalid = client.patch(PROFILE, json={"profile": "hybrid"}, headers=ORIGIN)
    assert missing.status_code == 428
    assert altered.status_code == 409
    assert stale.status_code == 409
    assert invalid.status_code == 400
    assert_conforms("/collections/{collection}/profile", "patch", 400, invalid.json())
    assert _profile_tag(store) == "documents"


def test_profile_change_on_missing_collection_is_rejected(setup: dict) -> None:
    with TestClient(setup["app"], base_url=BASE) as client:
        login(client, setup["policy"])
        path = "/v1/collections/absent/profile"
        token = client.patch(path, json={"profile": "codebase"}, headers=ORIGIN).json()[
            "confirmation"
        ]["token"]
        applied = client.patch(
            path,
            json={"profile": "codebase", "confirm": True, "confirmation_token": token},
            headers=ORIGIN,
        )
    assert applied.status_code == 400
    assert "does not exist" in applied.json()["message"]
    assert "absent" not in setup["store"].list_collections()
