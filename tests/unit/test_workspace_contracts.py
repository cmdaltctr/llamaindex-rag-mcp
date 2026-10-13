"""Workspace repository contracts stay pure data (task 5.1)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from omrg.core.workspace import canonical_json, content_hash
from omrg.integrations.workspace_sqlite import SqliteWorkspaceRepository


def test_canonical_json_ignores_key_order_and_whitespace() -> None:
    left = {"b": [1, {"y": 2, "x": "é"}], "a": None}
    right = json.loads(json.dumps({"a": None, "b": [1, {"x": "é", "y": 2}]}, indent=4))
    assert canonical_json(left) == canonical_json(right)
    assert canonical_json(left) == '{"a":null,"b":[1,{"x":"é","y":2}]}'
    assert content_hash(left) == content_hash(right)
    assert len(content_hash(left)) == 64


def test_canonical_json_rejects_values_without_a_stable_form() -> None:
    with pytest.raises(ValueError):
        canonical_json({"x": float("nan")})
    with pytest.raises(ValueError):
        canonical_json({"x": {1, 2}})


def test_adapter_hash_matches_core_identity(tmp_path: Path) -> None:
    repo = SqliteWorkspaceRepository(tmp_path / "app.sqlite3")
    pipeline_id = repo.create_pipeline("Demo")["pipeline_id"]
    document = {"version": 1, "nodes": [], "edges": [], "label": "ü"}
    revision = repo.save_revision(pipeline_id, document, schema_version=1)
    assert revision["content_hash"] == content_hash(document)


def test_contract_import_stays_free_of_persistence_and_domain_modules() -> None:
    probe = (
        "import sys; import omrg.core.workspace; "
        "bad = sorted(m for m in sys.modules if m == 'sqlite3' "
        "or m.startswith(('omrg.integrations', 'omrg.transports', 'omrg.core.ingestion', "
        "'omrg.core.retrieval', 'omrg.core.answer', 'omrg.core.pipelines', 'fastapi', "
        "'marimo'))); print(','.join(bad))"
    )
    result = subprocess.run(  # noqa: S603 - fixed interpreter and literal probe
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == ""
