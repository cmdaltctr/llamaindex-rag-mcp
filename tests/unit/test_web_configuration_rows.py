"""Each Configuration row describes its own control (edit-settings-from-configuration-page 2.1).

The rows of ``GET /v1/settings/configuration`` gain ``editable``,
``read_only_reason``, ``kind``, ``choices``, ``min``, ``max`` and ``nullable``
(design D2). The harness of ``test_web_configuration`` builds the app without
its lifespan, with a temporary config folder.
"""

from __future__ import annotations

from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit import test_web_configuration as base  # noqa: E402
from tests.unit.test_web_configuration import Harness, get, rows  # noqa: E402

from omrs.config.rules import METADATA_EXTRACTION_MODES  # noqa: E402

#: The fixtures of the GET tests.
harness = base.harness
client = base.client
FIELDS = ("editable", "read_only_reason", "kind", "choices", "min", "max", "nullable")


def shape(row: dict[str, Any]) -> dict[str, Any]:
    return {name: row[name] for name in FIELDS}


def test_every_row_has_the_control_fields(harness: Harness, client: TestClient) -> None:
    harness.launch()
    for row in get(client)["settings"]:
        assert set(FIELDS) <= set(row), row["key"]
        assert (row["read_only_reason"] is None) == row["editable"], row["key"]


def test_a_boolean_row(harness: Harness, client: TestClient) -> None:
    harness.launch()
    assert shape(rows(get(client))["answer.enabled"]) == {
        "editable": True,
        "read_only_reason": None,
        "kind": "bool",
        "choices": None,
        "min": None,
        "max": None,
        "nullable": False,
    }


def test_a_bounded_whole_number_row(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["answer.max_rounds"]
    assert (row["editable"], row["kind"], row["min"], row["max"]) == (True, "int", 1, 8)


def test_a_whole_number_greater_than_zero_has_the_minimum_one(
    harness: Harness, client: TestClient
) -> None:
    harness.launch()
    row = rows(get(client))["answer.context_window"]
    assert (row["kind"], row["min"], row["max"]) == ("int", 1, None)


def test_a_choice_row_lists_the_accepted_modes(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("METADATA__EXTRACTION_MODE", raising=False)  # conftest sets it
    harness.launch()
    row = rows(get(client))["metadata.extraction_mode"]
    assert (row["editable"], row["kind"]) == (True, "choice")
    assert row["choices"] == list(METADATA_EXTRACTION_MODES)


def test_the_pdf_reader_row_lists_the_reader_names(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["pdf_reader"]
    assert row["kind"] == "choice" and "auto" in row["choices"]


def test_an_optional_number_row(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["metadata.ollama_classify_timeout_override"]
    assert shape(row) == {
        "editable": True,
        "read_only_reason": None,
        "kind": "float",
        "choices": None,
        "min": None,  # gt 0 has no inclusive bound for a number
        "max": None,
        "nullable": True,
    }


def test_a_file_only_row(harness: Harness, client: TestClient) -> None:
    harness.launch()
    found = rows(get(client))
    assert (found["web_port"]["kind"], found["web_port"]["min"]) == ("int", 1024)
    assert found["mcp_http_enabled"]["kind"] == "bool"


def test_an_identity_row_is_read_only_with_its_reason(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["embed_model"]
    assert row["editable"] is False
    assert row["read_only_reason"] == (
        "The embedding model is part of every collection. Change it in omrs.jsonc and re-ingest."
    )
    assert row["kind"] == "text"


def test_a_storage_row_is_read_only(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["lancedb_uri"]
    assert row["editable"] is False
    assert row["read_only_reason"].startswith("Existing collections stay where they are.")


def test_a_list_row_has_no_kind(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["ingestion.ingest_extensions"]
    assert (row["editable"], row["read_only_reason"], row["kind"]) == (
        False,
        "Edit this in omrs.jsonc.",
        None,
    )


def test_a_secret_row_is_read_only(harness: Harness, client: TestClient) -> None:
    harness.launch()
    row = rows(get(client))["openrouter_api_key"]
    assert row["editable"] is False
    assert row["read_only_reason"] == "Keys are set on the provider cards as references."


def test_an_environment_value_locks_the_row_and_names_the_variable(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RETRIEVAL__TOP_K", "9")
    harness.launch()
    row = rows(get(client))["retrieval.top_k"]
    assert (row["source"], row["editable"]) == ("env", False)
    assert row["read_only_reason"] == (
        "Remove RETRIEVAL__TOP_K from the environment or .env to edit it here."
    )
    assert row["kind"] == "int"  # the control is still described


def test_a_read_only_reason_wins_over_the_environment_lock(
    harness: Harness, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LANCEDB_URI", "./elsewhere")
    harness.launch()
    row = rows(get(client))["lancedb_uri"]
    assert row["read_only_reason"].startswith("Existing collections stay where they are.")


def test_saved_is_the_file_value_and_null_when_absent(harness: Harness, client: TestClient) -> None:
    harness.write('{ "retrieval": { "top_k": 7 }, "openrouter_api_key": "env://MY_KEY" }')
    harness.launch()
    harness.write('{ "retrieval": { "top_k": 20 }, "openrouter_api_key": "env://MY_KEY" }')
    found = rows(get(client))
    top_k = found["retrieval.top_k"]
    assert (top_k["value"], top_k["saved"], top_k["restart_pending"]) == (7, 20, True)
    assert found["answer.max_rounds"]["saved"] is None
    assert found["openrouter_api_key"]["saved"] is None  # never the reference


def test_a_pending_value_names_the_file_as_its_source(harness: Harness, client: TestClient) -> None:
    harness.launch()  # top_k comes from the default at launch
    harness.write('{ "retrieval": { "top_k": 20 } }')
    row = rows(get(client))["retrieval.top_k"]
    assert (row["value"], row["saved"], row["source"], row["restart_pending"]) == (
        10,
        20,
        "config-file",
        True,
    )


def test_a_cleared_pending_value_names_the_default(harness: Harness, client: TestClient) -> None:
    harness.write('{ "retrieval": { "top_k": 7 } }')
    harness.launch()
    harness.write("{}")
    row = rows(get(client))["retrieval.top_k"]
    assert (row["value"], row["saved"], row["source"], row["restart_pending"]) == (
        7,
        None,
        "default",
        True,
    )
