"""``GET`` and ``PUT /v1/settings/document-reading`` (document-reading-settings, task 1.7).

Each test follows a scenario of the ``workspace-settings`` and ``settings-file``
deltas, or a row of the design D10 error table. The app is built without its
lifespan, so no Engine runs. A temporary config folder replaces the real one;
no test reads ``~/.config/omrg``. The PDF reader probes are faked.
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
)

from omrg import capabilities  # noqa: E402
from omrg.config import Settings, provenance  # noqa: E402
from omrg.config.rules import DOCUMENT_READING_KEYS  # noqa: E402
from omrg.config.settings_file import file_revision, read_settings_file  # noqa: E402
from omrg.config.user_config import parse_jsonc  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.document_reading import reset_reader_in_use  # noqa: E402
from omrg.transports.api.lifespan import WebConfig  # noqa: E402
from omrg.transports.api.restart_snapshot import capture  # noqa: E402
from omrg.transports.api.routes.configuration import ConfigurationState  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402

URL = "/v1/settings/document-reading"
OPTIONS = {"pypdf": None, "pypdfium2": "The package 'pypdfium2' is not installed."}
VARIABLES = tuple(key.upper() for key in DOCUMENT_READING_KEYS) + (
    "OCR_WORKERS_DIR",
    "OCR_WORKER_COMMAND",
)
SUBMITTED = "zz-submitted-zz"


class Harness:
    """The app, its policy and the config folder."""

    def __init__(self, app: Any, policy: AccessPolicy, folder: Path, empty_env: Path) -> None:
        self.app = app
        self.policy = policy
        self.folder = folder
        self.empty_env = empty_env

    @property
    def path(self) -> Path:
        return self.folder / "omrg.jsonc"

    def write(self, text: str) -> None:
        self.path.write_text(text, encoding="utf-8")

    def text(self) -> str:
        return self.path.read_text(encoding="utf-8") if self.path.exists() else ""

    def launch(self) -> None:
        self.app.state.configuration = ConfigurationState(
            launch_settings=Settings(_env_file=self.empty_env),
            snapshot=capture(read_settings_file(self.folder)),
            read_file=lambda: read_settings_file(self.folder),
        )


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset())
    monkeypatch.setattr(capabilities, "pdf_reader_options", lambda: dict(OPTIONS))
    monkeypatch.setattr(capabilities, "resolve_pdf_reader", lambda settings: "pypdf")
    reset_reader_in_use()
    folder = tmp_path / "omrg-config"
    folder.mkdir(mode=0o700)
    monkeypatch.setenv("OMRG_CONFIG_DIR", str(folder))
    empty_env = tmp_path / "none.env"
    empty_env.write_text("", encoding="utf-8")
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(config, policy=policy, engine_factory=lambda: None)
    yield Harness(app, policy, folder, empty_env)
    reset_reader_in_use()


@pytest.fixture
def client(harness: Harness) -> TestClient:
    """A signed-in client. It is not a context manager, so the lifespan never runs."""
    test_client = TestClient(harness.app, base_url=BASE)
    login(test_client, harness.policy)
    return test_client


def rows(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {row["key"]: row for row in body["settings"]}


def put(client: TestClient, values: dict[str, Any], revision: str = "absent") -> Any:
    return client.put(URL, json={"values": values, "revision": revision}, headers=ORIGIN)


def refused(response: Any, status: int, message: str | None = None) -> str:
    assert response.status_code == status, response.text
    body = response.json()
    assert body["status"] == "error"
    if message is not None:
        assert body["message"] == message
    return body["message"]


# ── Access ───────────────────────────────────────────────────────────────


def test_get_needs_the_read_scope(harness: Harness, client: TestClient) -> None:
    harness.launch()
    client.cookies.clear()
    assert client.get(URL).status_code == 401
    assert client.get(URL, headers=bearer(harness.policy, "run")).status_code == 403
    assert client.get(URL, headers=bearer(harness.policy, "read")).status_code == 200


def test_put_refuses_a_bearer_credential(harness: Harness, client: TestClient) -> None:
    harness.launch()
    client.cookies.clear()
    headers = {**ORIGIN, **bearer(harness.policy, "read", "run", "graph")}
    body = {"values": {"pdf_reader": "pypdf"}, "revision": "absent"}
    assert client.put(URL, json=body, headers=headers).status_code == 403
    assert harness.text() == ""


# ── Read ─────────────────────────────────────────────────────────────────


def test_read_the_section(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = client.get(URL)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert [row["key"] for row in body["settings"]] == list(DOCUMENT_READING_KEYS)
    assert body["pdf_readers"][0] == {"name": "auto", "available": True, "reason": None}
    assert isinstance(body["ocr"]["engines"], list)


def test_value_saved_but_not_yet_in_force(harness: Harness, client: TestClient) -> None:
    harness.write('{ "pdf_reader": "auto" }')
    harness.launch()
    harness.write('{ "pdf_reader": "liteparse" }')
    row = rows(client.get(URL).json())["pdf_reader"]
    assert (row["value"], row["saved"], row["restart_pending"]) == ("auto", "liteparse", True)


def test_blank_saved_fallback_shows_as_not_set(harness: Harness, client: TestClient) -> None:
    # The file reader treats a blank value as not set, so the engine keeps its default.
    harness.write('{ "ocr_engine_fallback": "" }')
    harness.launch()
    row = rows(client.get(URL).json())["ocr_engine_fallback"]
    assert row["saved"] is None


def test_key_locked_by_dotenv(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    monkeypatch.setattr(provenance, "DOTENV_KEYS", frozenset({"OCR_ROUTING_UNIT"}))
    harness.launch()
    row = rows(client.get(URL).json())["ocr_routing_unit"]
    assert (row["locked"], row["source"]) == (True, "dotenv")
    assert row["lock_reason"] == (
        "Remove OCR_ROUTING_UNIT from the environment or .env to edit it here."
    )


def test_a_read_failure_gives_the_envelope(harness: Harness, client: TestClient) -> None:
    def explode() -> Any:
        raise RuntimeError("detail /Users/someone")

    harness.launch()
    harness.app.state.configuration.read_file = explode
    response = client.get(URL)
    refused(response, 500)
    assert "someone" not in response.text


# ── Write ────────────────────────────────────────────────────────────────


def test_save_a_fraction(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"ocr_fallback_page_fraction": 0.2})
    assert response.status_code == 200, response.text
    body = response.json()
    assert parse_jsonc(harness.text())["ocr_fallback_page_fraction"] == 0.2
    row = rows(body)["ocr_fallback_page_fraction"]
    assert (row["value"], row["saved"], row["restart_pending"]) == (0.1, 0.2, True)
    assert body["revision"] == file_revision(harness.folder)


def test_use_default_removes_the_key(harness: Harness, client: TestClient) -> None:
    harness.write('// mine\n{ "ocr_engine_fallback": "my-engine" }\n')
    harness.launch()
    response = put(client, {"ocr_engine_fallback": None}, file_revision(harness.folder))
    assert response.status_code == 200, response.text
    assert "ocr_engine_fallback" not in parse_jsonc(harness.text())
    assert harness.text().startswith("// mine\n")


def test_unprovisioned_engine_is_allowed(harness: Harness, client: TestClient) -> None:
    harness.launch()
    response = put(client, {"ocr_engine_primary": "my-engine"})
    assert response.status_code == 200, response.text
    assert parse_jsonc(harness.text())["ocr_engine_primary"] == "my-engine"
    engines = {engine["name"]: engine for engine in response.json()["ocr"]["engines"]}
    assert engines["my-engine"]["available"] is False
    assert engines["my-engine"]["reason"]


def test_all_nine_keys_in_one_save(harness: Harness, client: TestClient) -> None:
    harness.launch()
    values = {
        "pdf_reader": "pypdf",
        "ocr_fallback_enabled": False,
        "ocr_fallback_min_confidence": 1,
        "ocr_fallback_page_fraction": 0,
        "ocr_routing_unit": "page",
        "ocr_engine_primary": "a",
        "ocr_engine_fallback": "b",
        "ocr_maths_routing_enabled": False,
        "ocr_maths_page_fraction": 0.5,
    }
    response = put(client, values)
    assert response.status_code == 200, response.text
    saved = {key: row["saved"] for key, row in rows(response.json()).items()}
    assert saved == values


# ── Refusals, in the D10 order ───────────────────────────────────────────


@pytest.mark.parametrize(
    "body",
    [
        {"values": {"pdf_reader": "pypdf"}},
        {"values": {"pdf_reader": "pypdf"}, "revision": "absent", "extra": 1},
        {"values": ["pdf_reader"], "revision": "absent"},
        {"values": {}, "revision": "absent"},
        {"values": {f"k{i}": 1 for i in range(10)}, "revision": "absent"},
        {"values": {"pdf_reader": "pypdf"}, "revision": "r" * 129},
    ],
)
def test_1_body_shape(harness: Harness, client: TestClient, body: dict[str, Any]) -> None:
    harness.launch()
    message = refused(client.put(URL, json=body, headers=ORIGIN), 400)
    assert message.startswith("Invalid request.")
    assert harness.text() == ""


def test_2_key_outside_the_nine(harness: Harness, client: TestClient) -> None:
    harness.launch()
    refused(
        put(client, {"embed_provider": "local"}),
        400,
        "embed_provider is not a document reading setting.",
    )
    assert harness.text() == ""


def test_3_locked_key(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PDF_READER", "pypdf")
    harness.launch()
    message = "Remove PDF_READER from the environment or .env to edit it here."
    refused(put(client, {"pdf_reader": "liteparse"}), 409, message)
    refused(put(client, {"pdf_reader": None}), 409, message)
    assert harness.text() == ""


def test_4_value_out_of_range(harness: Harness, client: TestClient) -> None:
    harness.launch()
    message = refused(put(client, {"ocr_maths_page_fraction": 1.5}), 400)
    assert message == "ocr_maths_page_fraction: The value must be a number from 0.0 to 1.0."
    assert "1.5" not in message
    assert harness.text() == ""


def test_4_one_bad_value_stops_the_whole_save(harness: Harness, client: TestClient) -> None:
    harness.write('{ "web_port": 9100 }')
    harness.launch()
    before = harness.text()
    response = put(client, {"ocr_routing_unit": "page", "ocr_engine_primary": "../x"})
    refused(response, 400)
    assert harness.text() == before


def test_4_blank_text(harness: Harness, client: TestClient) -> None:
    harness.launch()
    refused(
        put(client, {"ocr_engine_fallback": ""}),
        400,
        "ocr_engine_fallback: The value must not be blank. Send null to use the default.",
    )


def test_5_uninstalled_reader(harness: Harness, client: TestClient) -> None:
    harness.launch()
    refused(
        put(client, {"pdf_reader": "pypdfium2"}),
        400,
        "pdf_reader: This PDF reader is not installed. Install its package, then save again.",
    )
    assert harness.text() == ""


def test_6_stale_revision(harness: Harness, client: TestClient) -> None:
    harness.write("{}")
    harness.launch()
    revision = file_revision(harness.folder)
    harness.write('{ "web_port": 9100 }')
    refused(
        put(client, {"pdf_reader": "pypdf"}, revision),
        409,
        "omrg.jsonc changed on disk. Reload to see the new values.",
    )


def test_7_broken_file(harness: Harness, client: TestClient) -> None:
    harness.write('{ "pdf_reader": ')
    harness.launch()
    refused(
        put(client, {"pdf_reader": "pypdf"}, file_revision(harness.folder)),
        409,
        "omrg.jsonc could not be read. Fix it, then save again.",
    )


def test_8_disk_refuses_the_write(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from omrg.config import settings_file_write

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise settings_file_write.SettingsFileWriteError(settings_file_write.WRITE_FAILED)

    monkeypatch.setattr(settings_file_write, "_write_atomically", refuse)
    harness.launch()
    refused(put(client, {"pdf_reader": "pypdf"}), 500, "omrg.jsonc could not be written.")


@pytest.mark.parametrize(
    "values",
    [
        {"pdf_reader": SUBMITTED},
        {"ocr_engine_primary": f"../{SUBMITTED}"},
        {"ocr_fallback_enabled": SUBMITTED},
        {"ocr_maths_page_fraction": SUBMITTED},
        {"ocr_routing_unit": SUBMITTED},
    ],
)
def test_no_message_holds_the_submitted_value(
    harness: Harness, client: TestClient, values: dict[str, Any]
) -> None:
    harness.launch()
    response = put(client, values)
    assert response.status_code == 400
    assert SUBMITTED not in response.text


def test_no_shape_message_holds_the_submitted_value(harness: Harness, client: TestClient) -> None:
    harness.launch()
    body = {"values": {"pdf_reader": "x"}, "revision": SUBMITTED * 10}
    response = client.put(URL, json=body, headers=ORIGIN)
    assert response.status_code == 400 and SUBMITTED not in response.text


# ── Contract ─────────────────────────────────────────────────────────────


def test_responses_conform_to_the_contract(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("OCR_WORKERS_DIR", str(tmp_path / "workers"))
    monkeypatch.setenv("OCR_ROUTING_UNIT", "page")
    check = ContractChecker()
    harness.write('{ "ocr_engine_fallback": "" }')
    harness.launch()
    body = check.check(client.get(URL), 200)
    check.check(put(client, {"pdf_reader": "pypdf"}, body["revision"]), 200)
    check.check(put(client, {"pdf_reader": "pypdf"}, "stale"), 409)
    check.check(put(client, {"ocr_routing_unit": "page"}), 409)
    check.check(put(client, {"embed_provider": "x"}), 400)
    check.check(client.put(URL, json={"values": {}}, headers=ORIGIN), 400)
    assert check.operations >= FAMILIES["document_reading"]
