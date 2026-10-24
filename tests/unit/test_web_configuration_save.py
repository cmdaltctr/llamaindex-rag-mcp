"""``PUT /v1/settings/configuration`` (edit-settings-from-configuration-page 2.2).

Each test follows a scenario of the ``settings-file`` delta or a check of the
shared contract. The app is built without its lifespan (the harness of
``test_web_configuration``), so the route writes through the app's settings
store. Two tests add a stand-in runtime to cover the live apply path. No test
reads the real ``~/.config/omrs``.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit import test_web_configuration as base  # noqa: E402
from tests.unit.test_web_configuration import URL, FakeKeychain, Harness, rows  # noqa: E402
from tests.unit.test_web_documents_support import ORIGIN, bearer  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import FAMILIES, ContractChecker  # noqa: E402

from omrs import capabilities  # noqa: E402
from omrs.config.settings_file import file_revision  # noqa: E402
from omrs.config.user_config import parse_jsonc  # noqa: E402
from omrs.transports.api.provider_state import ProviderState  # noqa: E402
from omrs.transports.api.secret_set import SecretSet  # noqa: E402

#: The fixtures of the GET tests.
harness = base.harness
client = base.client
SUBMITTED = "zz-submitted-zz"
CHANGED = "omrs.jsonc changed on disk. Reload to see the new values."


def put(client: TestClient, changes: dict[str, Any], revision: str = "absent", **extra: Any) -> Any:
    body = {"revision": revision, "changes": changes}
    return client.put(URL, json=body, headers={**ORIGIN, **extra.pop("headers", {})}, **extra)


def refused(response: Any, status: int, message: str | None = None) -> str:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["status"] == "error"
    if message is not None:
        assert body["message"] == message
    return body["message"]


def text(harness: Harness) -> str:
    path = harness.folder / "omrs.jsonc"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def data(harness: Harness) -> dict[str, Any]:
    return parse_jsonc(text(harness) or "{}")


# ── Saves ────────────────────────────────────────────────────────────────


def test_two_keys_are_saved_together(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"retrieval.top_k": 20, "retrieval.rerank_enabled": True})
    assert response.status_code == 200, response.text
    assert data(harness) == {"retrieval": {"top_k": 20, "rerank_enabled": True}}
    body = response.json()
    assert body["status"] == "ok"
    assert body["revision"] == file_revision(harness.folder)
    found = rows(body)
    for key in ("retrieval.top_k", "retrieval.rerank_enabled"):
        assert (found[key]["source"], found[key]["restart_pending"]) == ("config-file", True)
    assert found["retrieval.top_k"]["value"] == 10  # the launch value stays in force


def test_a_save_merges_into_the_existing_block_and_keeps_comments(
    harness: Harness, client: TestClient
) -> None:
    harness.write('// mine\n{\n  "retrieval": { "hybrid_enabled": true } // keep\n}\n')
    harness.launch()
    response = put(client, {"retrieval.top_k": 20}, file_revision(harness.folder))
    assert response.status_code == 200, response.text
    assert "// keep" in text(harness) and text(harness).startswith("// mine\n")
    assert data(harness)["retrieval"] == {"hybrid_enabled": True, "top_k": 20}


def test_null_clears_an_optional_key(harness: Harness, client: TestClient) -> None:
    harness.write('{ "metadata": { "ollama_classify_timeout_override": 30 } }')
    harness.launch()
    response = put(
        client,
        {"metadata.ollama_classify_timeout_override": None},
        file_revision(harness.folder),
    )
    assert response.status_code == 200, response.text
    assert "ollama_classify_timeout_override" not in data(harness).get("metadata", {})


def test_a_live_file_only_key_is_shown_at_once(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"web_max_upload_mib": 200})
    assert response.status_code == 200, response.text
    row = rows(response.json())["web_max_upload_mib"]
    assert (row["value"], row["source"], row["restart_pending"]) == (200, "config-file", False)


# ── Refusals ─────────────────────────────────────────────────────────────


def test_one_bad_value_stops_the_whole_save(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"retrieval.top_k": 20, "answer.max_rounds": 12})
    refused(response, 400, "answer.max_rounds: The value must be a whole number from 1 to 8.")
    assert text(harness) == ""


def test_a_choice_outside_the_list_is_refused(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("METADATA__EXTRACTION_MODE", raising=False)  # conftest sets it
    harness.launch()
    message = refused(put(client, {"metadata.extraction_mode": "magic"}), 400)
    assert message.startswith("metadata.extraction_mode: The value must be one of: disabled,")
    assert text(harness) == ""


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("embed_model", "other-model"),
        ("lancedb_uri", "./elsewhere"),
        ("openrouter_api_key", "keychain://openrouter"),
        ("ingestion.ingest_extensions", ".pdf"),
        ("not_a_setting", 1),
        ("config_file_fields", 1),
    ],
)
def test_a_key_the_page_may_not_write_is_refused(
    harness: Harness, client: TestClient, key: str, value: Any
) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    before = text(harness)
    harness.launch()
    response = put(client, {"retrieval.top_k": 20, key: value}, file_revision(harness.folder))
    refused(response, 400, f"{key} is not a setting that can be changed here.")
    assert text(harness) == before


def test_a_read_only_key_is_refused_before_a_lock(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RETRIEVAL__TOP_K", "9")
    harness.launch()
    response = put(client, {"retrieval.top_k": 20, "embed_model": "x"})
    refused(response, 400, "embed_model is not a setting that can be changed here.")


@pytest.fixture
def readers(monkeypatch: pytest.MonkeyPatch) -> None:
    """``pypdf`` is installed and ``pypdfium2`` is not. ``PDF_READER`` is unset."""
    monkeypatch.delenv("PDF_READER", raising=False)  # conftest sets it
    options = {"pypdf": None, "pypdfium2": "The package 'pypdfium2' is not installed."}
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(options))


@pytest.mark.usefixtures("readers")
def test_a_pdf_reader_that_is_not_installed_is_refused(
    harness: Harness, client: TestClient
) -> None:
    harness.launch()
    response = put(client, {"retrieval.top_k": 20, "pdf_reader": "pypdfium2"})
    refused(
        response,
        400,
        "pdf_reader: This PDF reader is not installed. Install its package, then save again.",
    )
    assert text(harness) == ""


@pytest.mark.usefixtures("readers")
def test_an_installed_pdf_reader_is_saved(harness: Harness, client: TestClient) -> None:
    harness.launch()
    assert put(client, {"pdf_reader": "pypdf"}).status_code == 200
    assert data(harness) == {"pdf_reader": "pypdf"}


@pytest.mark.usefixtures("readers")
def test_a_value_rule_is_checked_before_the_reader(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"pdf_reader": "pypdfium2", "answer.max_rounds": 12})
    refused(response, 400, "answer.max_rounds: The value must be a whole number from 1 to 8.")


def test_a_key_set_in_the_environment_is_locked(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RETRIEVAL__TOP_K", "9")
    harness.launch()
    response = put(client, {"retrieval.top_k": 20})
    refused(response, 409, "Remove RETRIEVAL__TOP_K from the environment or .env to edit it here.")
    assert text(harness) == ""


def test_a_lock_is_checked_before_the_value(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RETRIEVAL__TOP_K", "9")
    harness.launch()
    response = put(client, {"answer.max_rounds": 12, "retrieval.top_k": 20})
    assert response.status_code == 409


def test_a_launch_value_from_the_environment_locks_a_file_only_key(
    harness: Harness, client: TestClient
) -> None:
    harness.launch(overrides={"web_max_upload_mib": (64, "env")})
    response = put(client, {"web_max_upload_mib": 200})
    refused(
        response, 409, "Remove WEB_MAX_UPLOAD_MIB from the environment or .env to edit it here."
    )


def test_a_stale_revision_is_refused(harness: Harness, client: TestClient) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    harness.launch()
    revision = file_revision(harness.folder)
    harness.write('{ "retrieval": { "top_k": 5 } }')
    before = text(harness)
    refused(put(client, {"retrieval.top_k": 20}, revision), 409, CHANGED)
    assert text(harness) == before


def test_a_broken_file_is_refused(harness: Harness, client: TestClient) -> None:
    harness.write("{ broken")
    harness.launch()
    response = put(client, {"retrieval.top_k": 20}, file_revision(harness.folder))
    refused(response, 409, "omrs.jsonc could not be read. Fix it, then save again.")
    assert text(harness) == "{ broken"


def test_a_message_never_holds_the_submitted_value(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("METADATA__EXTRACTION_MODE", raising=False)  # conftest sets it
    harness.launch()
    for changes in (
        {"answer.timeout": SUBMITTED},
        {"embed_model": SUBMITTED},
        {"ollama_base_url": f"http://{SUBMITTED}@host:1"},
        {"metadata.extraction_mode": SUBMITTED},
    ):
        response = put(client, changes)
        assert response.status_code == 400, response.text
        assert SUBMITTED not in response.text


@pytest.mark.parametrize(
    "body",
    [
        {"revision": "absent", "changes": {}},
        {"revision": "absent"},
        {"changes": {"retrieval.top_k": 20}},
        {"revision": "absent", "changes": {"retrieval.top_k": 20}, "extra": 1},
    ],
)
def test_a_bad_body_is_refused(harness: Harness, client: TestClient, body: dict) -> None:
    harness.launch()
    response = client.put(URL, json=body, headers=ORIGIN)
    assert response.status_code == 400, response.text
    assert text(harness) == ""


# ── Access ───────────────────────────────────────────────────────────────


def test_a_bearer_credential_is_refused(harness: Harness, client: TestClient) -> None:
    harness.launch()
    client.cookies.clear()
    headers = bearer(harness.policy, "read", "run", "graph")
    response = put(client, {"retrieval.top_k": 20}, headers=headers)
    assert response.status_code == 403
    assert text(harness) == ""


def test_no_credential_is_refused(harness: Harness, client: TestClient) -> None:
    harness.launch()
    client.cookies.clear()
    assert put(client, {"retrieval.top_k": 20}).status_code == 401


# ── With a runtime ───────────────────────────────────────────────────────


class FakeAdmission:
    @contextlib.asynccontextmanager
    async def enter(self) -> AsyncIterator[None]:
        yield


class FakeEngine:
    def __init__(self) -> None:
        self.calls = 0

    def use_provider_settings(self, _: Any) -> None:
        self.calls += 1


def runtime(harness: Harness) -> SimpleNamespace:
    """A stand-in runtime with the real provider state over the harness folder."""
    store = harness.app.state.mcp_http.store
    providers = ProviderState(store, FakeKeychain(), SecretSet())
    providers.load()
    found = SimpleNamespace(
        providers=providers,
        engine=FakeEngine(),
        admission=FakeAdmission(),
        upload_limit_source="default",
        uploads=SimpleNamespace(max_bytes=50 * 1024 * 1024),
        config=SimpleNamespace(max_upload_bytes=50 * 1024 * 1024),
    )
    harness.app.state.runtime = found
    return found


def test_with_a_runtime_a_live_key_applies_at_once(harness: Harness, client: TestClient) -> None:
    harness.launch()
    found = runtime(harness)
    response = put(client, {"web_max_upload_mib": 200, "mcp_http_enabled": True})
    assert response.status_code == 200, response.text
    assert found.uploads.max_bytes == 200 * 1024 * 1024
    assert found.upload_limit_source == "config-file"
    assert harness.app.state.mcp_http.enabled is True
    assert found.providers.revision == file_revision(harness.folder)


def test_with_a_runtime_a_provider_field_reaches_the_engine(
    harness: Harness, client: TestClient
) -> None:
    harness.launch()
    found = runtime(harness)
    response = put(client, {"ollama_context_window": 32768})
    assert response.status_code == 200, response.text
    assert found.engine.calls == 1
    assert rows(response.json())["ollama_context_window"]["value"] == 32768


# ── Contract ─────────────────────────────────────────────────────────────


def test_responses_conform_to_the_contract(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    check = ContractChecker()
    harness.launch()
    check.check(put(client, {"retrieval.top_k": 20}), 200)
    revision = file_revision(harness.folder)
    check.check(put(client, {"answer.max_rounds": 12}, revision), 400)
    check.check(put(client, {"retrieval.top_k": 21}, "stale"), 409)
    monkeypatch.setenv("ANSWER__TIMEOUT", "30")
    harness.launch()
    check.check(put(client, {"answer.timeout": 60}, revision), 409)
    client.cookies.clear()
    check.check(put(client, {"retrieval.top_k": 20}, headers=bearer(harness.policy, "read")), 403)
    assert check.operations >= FAMILIES["configuration_save"]
