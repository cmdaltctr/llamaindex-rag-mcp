"""``GET /v1/settings/configuration`` (move-settings-to-config-file task 7.1).

Each test follows a scenario of the ``settings-file`` and ``workspace-settings``
deltas. The app is built without its lifespan, so no Engine, keychain or
workspace runs. A fake keychain and a temporary config folder replace the real
ones. No test reads the real ``~/.config/omrg``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import BASE, ORIGIN, bearer, login  # noqa: E402
from tests.unit.test_web_openapi_conformance_support import (  # noqa: E402
    FAMILIES,
    ContractChecker,
    iter_api_routes,
)

from omrg.config import Settings, provenance  # noqa: E402
from omrg.config.settings_file import file_revision, read_settings_file, setting_paths  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.restart_snapshot import capture  # noqa: E402
from omrg.transports.api.routes.configuration import ConfigurationState, router  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402
from omrg.transports.api.settings_handover import HandoverResult  # noqa: E402

URL = "/v1/settings/configuration"
KEY = "Zq9XkP3lM7wVb2NrT4yQ1234"  # no run of five characters matches a path or a word
VARIABLES = (
    "RETRIEVAL__TOP_K",
    "ANSWER__MODEL",
    "ANSWER__PROVIDER",
    "OPENROUTER_API_KEY",
    "OLLAMA_BASE_URL",  # conftest sets it
)


class FakeSecret:
    def __init__(self, value: str) -> None:
        self.value = value

    def reveal(self) -> str:
        return self.value


class FakeKeychain:
    available = True

    def __init__(self, entries: dict[str, str] | None = None) -> None:
        self.entries = entries or {}

    def read(self, provider: str) -> FakeSecret | None:
        value = self.entries.get(provider)
        return None if value is None else FakeSecret(value)


class Harness:
    """The app, its policy, the config folder and a settings factory."""

    def __init__(self, app: Any, policy: AccessPolicy, folder: Path, empty_env: Path) -> None:
        self.app = app
        self.policy = policy
        self.folder = folder
        self.empty_env = empty_env

    def write(self, text: str) -> None:
        (self.folder / "omrg.jsonc").write_text(text, encoding="utf-8")

    def settings(self) -> Settings:
        return Settings(_env_file=self.empty_env)

    def launch(self, **extra: Any) -> ConfigurationState:
        """Capture the launch state from the file as it is now."""
        state = ConfigurationState(
            launch_settings=self.settings(),
            snapshot=capture(read_settings_file(self.folder)),
            live_settings=self.settings,
            read_file=lambda: read_settings_file(self.folder),
            **extra,
        )
        self.app.state.configuration = state
        return state


def mount(app: Any) -> None:
    """Add the route when ``create_app`` does not register it yet."""
    if URL not in {path for path, _ in iter_api_routes(app)}:
        app.include_router(router)


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    folder = tmp_path / "omrg-config"
    folder.mkdir(mode=0o700)
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(folder))
    empty_env = tmp_path / "none.env"
    empty_env.write_text("", encoding="utf-8")
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: None, keychain=FakeKeychain())
    mount(app)
    return Harness(app, policy, folder, empty_env)


@pytest.fixture
def client(harness: Harness) -> TestClient:
    """A signed-in client. It is not a context manager, so the lifespan never runs."""
    test_client = TestClient(harness.app, base_url=BASE)
    login(test_client, harness.policy)
    return test_client


def rows(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in body["settings"]}


def get(client: TestClient) -> dict[str, Any]:
    response = client.get(URL)
    assert response.status_code == 200, response.text
    return response.json()


# ── Access ───────────────────────────────────────────────────────────────


def test_needs_a_credential_with_the_read_scope(harness: Harness, client: TestClient) -> None:
    harness.launch()
    client.cookies.clear()
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=bearer(harness.policy, "run")).status_code == 403
    allowed = client.get(URL, headers=bearer(harness.policy, "read"))
    assert allowed.status_code == 200


# ── Shape ────────────────────────────────────────────────────────────────


def test_lists_every_setting_once_with_path_and_revision(
    harness: Harness, client: TestClient
) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    harness.launch()
    body = get(client)
    assert [row["key"] for row in body["settings"]] == list(setting_paths())
    assert body["path"].endswith("omrg.jsonc")
    assert body["revision"] == file_revision(harness.folder)
    assert body["problems"] == []
    assert body["handover"] == {"pending": False, "folder": None}


def test_value_and_source_of_a_file_setting(harness: Harness, client: TestClient) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    harness.launch()
    row = rows(get(client))["retrieval.top_k"]
    assert (row["value"], row["source"]) == (7, "config-file")
    default = rows(get(client))["chunking.chunk_overlap"]
    assert default["source"] == "default" and isinstance(default["value"], int)


def test_a_yaml_default_reads_as_default(harness: Harness, client: TestClient) -> None:
    harness.launch()
    sources = {row["source"] for row in get(client)["settings"]}
    assert "default" in sources and "yaml" not in sources


def test_a_state_never_set_still_answers(harness: Harness, client: TestClient) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    body = get(client)  # app.state.configuration was never set
    assert rows(body)["retrieval.top_k"]["restart_pending"] is False
    assert body["handover"] == {"pending": False, "folder": None}


# ── applies ──────────────────────────────────────────────────────────────


def test_applies_is_live_for_provider_fields_and_restart_for_the_engine(
    harness: Harness, client: TestClient
) -> None:
    harness.launch()
    found = rows(get(client))
    live = (
        "answer.model",
        "answer.provider",
        "answer.verify_provider",
        "answer.verify_model",
        "ollama_base_url",
        "openrouter_api_key",
        "ollama_context_window",
        "llamacpp_server_binary",
        "web_max_upload_mib",
        "mcp_http_enabled",
    )
    restart = (
        "retrieval.top_k",
        "chunking.chunk_overlap",
        "embed_provider",
        "metadata.extraction_mode",
        "web_port",
        "answer.enabled",
        "answer.verify_claims",
    )
    assert {key: found[key]["applies"] for key in live} == dict.fromkeys(live, "live")
    assert {key: found[key]["applies"] for key in restart} == dict.fromkeys(restart, "restart")


# ── restart_pending ──────────────────────────────────────────────────────


def test_hand_edit_of_top_k_shows_the_launch_value_and_restart_pending(
    harness: Harness, client: TestClient
) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    harness.launch()
    harness.write('{ "retrieval": { "top_k": 5 } }')
    row = rows(get(client))["retrieval.top_k"]
    assert row["value"] == 7  # the launch value, not the file value
    assert row["source"] == "config-file"
    assert row["restart_pending"] is True


def test_hand_edit_of_the_chat_model_applies_live(harness: Harness, client: TestClient) -> None:
    harness.write('{ "answer": { "model": "one" } }')
    harness.launch()
    harness.write('{ "answer": { "model": "two" } }')
    row = rows(get(client))["answer.model"]
    assert (row["value"], row["source"], row["restart_pending"]) == ("two", "config-file", False)


def test_hand_edit_of_the_judge_model_applies_live(harness: Harness, client: TestClient) -> None:
    harness.write('{ "answer": { "verify_model": "one" } }')
    harness.launch()
    harness.write('{ "answer": { "verify_model": "two" } }')
    row = rows(get(client))["answer.verify_model"]
    assert (row["value"], row["source"], row["restart_pending"]) == ("two", "config-file", False)


def test_hand_edit_of_verify_claims_still_needs_a_restart(
    harness: Harness, client: TestClient
) -> None:
    harness.write('{ "answer": { "verify_claims": false } }')
    harness.launch()
    harness.write('{ "answer": { "verify_claims": true } }')
    assert rows(get(client))["answer.verify_claims"]["restart_pending"] is True


def test_only_the_edited_restart_key_is_pending(harness: Harness, client: TestClient) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    harness.launch()
    harness.write('{ "retrieval": { "top_k": 5 } }')
    flagged = {key for key, row in rows(get(client)).items() if row["restart_pending"]}
    assert flagged == {"retrieval.top_k"}


def test_an_environment_value_outranks_the_file_so_nothing_is_pending(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RETRIEVAL__TOP_K", "9")
    harness.write('{ "retrieval": { "top_k": 7 } }')
    harness.launch()
    harness.write('{ "retrieval": { "top_k": 5 } }')
    row = rows(get(client))["retrieval.top_k"]
    assert (row["value"], row["source"], row["restart_pending"]) == (9, "env", False)


def test_web_port_is_restart_only_and_shows_the_launch_value(
    harness: Harness, client: TestClient
) -> None:
    harness.write('{ "web_port": 9100 }')
    harness.launch()
    harness.write('{ "web_port": 9200 }')
    row = rows(get(client))["web_port"]
    assert (row["value"], row["source"], row["restart_pending"]) == (9100, "config-file", True)


def test_a_launch_override_fixes_a_file_only_value(harness: Harness, client: TestClient) -> None:
    harness.write('{ "web_port": 9100 }')
    harness.launch(overrides={"web_port": (9300, "init")})
    row = rows(get(client))["web_port"]
    assert (row["value"], row["source"], row["restart_pending"]) == (9300, "init", False)


def test_live_file_only_values_follow_the_file(harness: Harness, client: TestClient) -> None:
    harness.launch()
    assert rows(get(client))["web_max_upload_mib"]["value"] == 50
    harness.write('{ "web_max_upload_mib": 200, "mcp_http_enabled": true }')
    found = rows(get(client))
    assert (found["web_max_upload_mib"]["value"], found["web_max_upload_mib"]["source"]) == (
        200,
        "config-file",
    )
    assert found["mcp_http_enabled"]["value"] is True


def test_file_only_defaults_match_the_launch_defaults() -> None:
    from omrg.transports.api.uploads import DEFAULT_MAX_UPLOAD_BYTES, MIB
    from omrg.transports.cli.web import DEFAULT_PORT
    from omrg.transports.settings_view import FILE_ONLY_DEFAULTS

    assert FILE_ONLY_DEFAULTS["web_port"] == DEFAULT_PORT
    assert FILE_ONLY_DEFAULTS["web_max_upload_mib"] * MIB == DEFAULT_MAX_UPLOAD_BYTES


# ── Masking ──────────────────────────────────────────────────────────────


def no_run_of(text: str, secret: str, size: int = 5) -> bool:
    """Return whether no *size* consecutive characters of *secret* appear in *text*."""
    return not any(secret[i : i + size] in text for i in range(len(secret) - size + 1))


def test_key_from_a_key_file_shows_last_four_and_no_value(
    harness: Harness, client: TestClient
) -> None:
    (harness.folder / "secrets").mkdir()
    (harness.folder / "secrets" / "openrouter.key").write_text(KEY, encoding="utf-8")
    harness.launch()
    response = client.get(URL)
    row = rows(response.json())["openrouter_api_key"]
    assert row["value"] is None
    assert row["last4"] == "1234"
    assert row["source"] == "key-file"
    assert no_run_of(response.text, KEY)


def test_key_from_the_keychain_shows_last_four_and_no_value(
    harness: Harness, client: TestClient
) -> None:
    harness.write('{ "openrouter_api_key": "keychain://openrouter" }')
    harness.app.state.keychain = FakeKeychain({"openrouter": KEY})
    harness.launch()
    response = client.get(URL)
    row = rows(response.json())["openrouter_api_key"]
    assert (row["value"], row["last4"], row["source"]) == (None, "1234", "keychain")
    assert no_run_of(response.text, KEY)


def test_key_from_the_environment_shows_last_four_and_source_env(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", KEY)
    harness.launch()
    response = client.get(URL)
    row = rows(response.json())["openrouter_api_key"]
    assert (row["value"], row["last4"], row["source"]) == (None, "1234", "env")
    assert no_run_of(response.text, KEY)


def test_a_short_key_shows_an_empty_last4(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "abc1234")
    harness.launch()
    response = client.get(URL)
    assert rows(response.json())["openrouter_api_key"]["last4"] == ""
    assert "abc1234" not in response.text


def test_an_unset_key_has_no_last4(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["anthropic_api_key"]
    assert row["value"] is None and "last4" not in row and row["source"] == "default"


def test_every_key_field_is_masked(harness: Harness, client: TestClient) -> None:
    from omrg.config.rules import SECRET_FIELDS

    harness.launch()
    found = rows(get(client))
    for name in SECRET_FIELDS:
        assert found[name]["value"] is None, name


# ── Problems ─────────────────────────────────────────────────────────────


def test_problems_name_the_key_and_never_the_value(harness: Harness, client: TestClient) -> None:
    harness.write(
        '{ "retreival": { "top_k": 5 }, "ollama_base_url": "file:///etc/passwd",'
        ' "retrieval": { "top_k": "many" } }'
    )
    harness.launch()
    response = client.get(URL)
    body = response.json()
    by_key = {problem["key"]: problem for problem in body["problems"]}
    assert by_key["retreival"]["kind"] == "unknown"
    assert by_key["ollama_base_url"]["kind"] == "invalid"
    assert by_key["retrieval.top_k"]["kind"] == "invalid"
    assert all(set(problem) == {"key", "kind", "message"} for problem in body["problems"])
    assert "passwd" not in response.text and "many" not in response.text
    # The ignored values fall back to the default.
    assert rows(body)["ollama_base_url"]["source"] == "default"


def test_a_retired_name_reports_its_replacement(harness: Harness, client: TestClient) -> None:
    harness.write('{ "top_k": 5 }')
    harness.launch()
    problems = get(client)["problems"]
    assert [(p["key"], p["kind"]) for p in problems] == [("top_k", "retired")]
    assert "retrieval.top_k" in problems[0]["message"]


def test_a_broken_file_is_listed_and_the_server_answers(
    harness: Harness, client: TestClient
) -> None:
    harness.write('{ "retrieval": { "top_k": ')
    harness.launch()
    body = get(client)
    assert [(p["key"], p["kind"]) for p in body["problems"]] == [("omrg.jsonc", "broken")]
    assert body["problems"][0]["message"] == "omrg.jsonc could not be read"
    assert not any(row["restart_pending"] for row in body["settings"])


# ── Handover notice ──────────────────────────────────────────────────────


def test_pending_handover_shows_the_folder(harness: Harness, client: TestClient) -> None:
    harness.launch(handover=HandoverResult(pending=True, folder="~/.config/omrg"))
    assert get(client)["handover"] == {"pending": True, "folder": "~/.config/omrg"}


# ── Failure ──────────────────────────────────────────────────────────────


def test_a_failure_returns_the_error_envelope(harness: Harness, client: TestClient) -> None:
    def explode() -> Any:
        raise RuntimeError("secret detail /Users/someone")

    harness.launch()
    harness.app.state.configuration.read_file = explode
    response = client.get(URL)
    assert response.status_code == 500
    assert response.json()["status"] == "error"
    assert "someone" not in response.text


# ── Contract ─────────────────────────────────────────────────────────────


def test_responses_conform_to_the_contract(harness: Harness, client: TestClient) -> None:
    check = ContractChecker()
    harness.write(
        '{ "retrieval": { "top_k": 7 }, "retreival": 1, "web_port": 9100,'
        ' "openrouter_api_key": "keychain://openrouter" }'
    )
    harness.app.state.keychain = FakeKeychain({"openrouter": KEY})
    harness.launch(handover=HandoverResult(pending=True, folder="~/.config/omrg"))
    harness.write('{ "retrieval": { "top_k": 5 }, "retreival": 1, "web_port": 9200 }')
    body = check.check(client.get(URL), 200)
    assert rows(body)["retrieval.top_k"]["restart_pending"] is True
    harness.write("{}")
    check.check(client.get(URL), 200)
    check.check(client.get(URL, headers=ORIGIN), 200)
    assert check.operations >= FAMILIES["configuration"]
