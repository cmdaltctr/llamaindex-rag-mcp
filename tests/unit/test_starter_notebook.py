"""The marimo starter notebook's helpers against a real app (task 8.6).

marimo is not in OMRG's environment, so the tests import the notebook with a
stand-in ``marimo`` module whose ``App`` keeps every cell. The helpers talk
to a ``TestClient``-backed application through an injected transport, with
a bearer credential bound
to an experiment context. The tests prove shared graph execution with the
canvas, parameter changes without reruns, atomic checkpoints, revocation,
and that the token is never printed or stored.
"""

from __future__ import annotations

import ast
import contextlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_experiments_support import (  # noqa: E402
    BASE,
    ORIGIN,
    build_experiment_app,
    login,
    register,
)
from tests.unit.test_web_runs_support import make_engine  # noqa: E402

NOTEBOOK = Path(__file__).resolve().parents[2] / "plugins" / "marimo" / "starter_notebook.py"


class _StubApp:
    """Stand-in for ``marimo.App``: decorators keep functions unchanged."""

    def __init__(self, **_options: object) -> None:
        self.cells: list[object] = []

    def cell(self, func: Any = None, **_options: object) -> Any:
        if func is None:
            return self.cell
        self.cells.append(func)
        return func

    def function(self, func: Any = None, **_options: object) -> Any:
        return func if func is not None else self.function

    def class_definition(self, cls: Any = None, **_options: object) -> Any:
        return cls if cls is not None else self.class_definition

    @property
    def setup(self) -> contextlib.AbstractContextManager[None]:
        return contextlib.nullcontext()


def load_notebook(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """Import the notebook file with a stand-in ``marimo`` module.

    marimo is not in OMRG's environment. The notebook keeps marimo's file
    layout (a top-level ``import marimo``), so the test supplies the module.
    """
    stub = ModuleType("marimo")
    stub.App = _StubApp  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "marimo", stub)
    spec = importlib.util.spec_from_file_location("omrg_starter_notebook", NOTEBOOK)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Recording:
    """A transport over the test client that records each (method, path)."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        self.calls: list[tuple[str, str]] = []

    def __call__(self, method: str, url: str, body: Any, headers: dict) -> tuple[int, Any]:
        path = url.removeprefix(BASE).split("?")[0]
        self.calls.append((method, path))
        response = self.client.request(method, url, json=body, headers=headers)
        return response.status_code, response.json() if response.content else None

    def since(self, mark: int) -> list[tuple[str, str]]:
        return [(m, re.sub(r"/[0-9a-f]{32}", "/ID", p)) for m, p in self.calls[mark:]]


@pytest.fixture
def notebook(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    return load_notebook(monkeypatch)


@pytest.fixture
def lab(tmp_path: Path, effective_settings: Any, notebook: ModuleType) -> Any:
    parts = build_experiment_app(tmp_path, make_engine(effective_settings), effective_settings)
    with TestClient(parts.app, base_url=BASE) as client:
        login(client, parts.policy)
        context_id = register(client, parts.root, actions=["read"])["experiment"]["context_id"]
        issued = client.post(
            "/v1/credentials",
            json={"scopes": ["graph", "read", "run"], "experiment_context": context_id},
            headers=ORIGIN,
        ).json()
        token_file = tmp_path / "token"
        token_file.write_text(issued["token"] + "\n")
        token_file.chmod(0o600)
        env = {
            "OMRG_API_URL": BASE,
            "OMRG_TOKEN_FILE": str(token_file),
            "OMRG_EXPERIMENT_CONTEXT": context_id,
        }
        transport = Recording(client)
        api = notebook.ApiClient.from_environment(env, transport=transport)
        output = parts.root / "exp-a" / "output" / "runs"
        session = notebook.ExperimentSession(
            api, notebook.experiment_context_from_environment(env), output, poll_interval=0.01
        )
        yield {
            "client": client,
            "parts": parts,
            "context_id": context_id,
            "token": issued["token"],
            "credential_id": issued["id"],
            "transport": transport,
            "session": session,
            "output": output,
            "env": env,
        }


def _search(notebook: ModuleType, session: Any, top_k: int) -> dict[str, Any]:
    templates = {t["name"]: t for t in notebook.list_templates(session.client)}
    return notebook.set_node_params(templates["search"]["document"], {"prepare": {"top_k": top_k}})


# ── Structure ────────────────────────────────────────────────────────────


def test_notebook_imports_without_marimo_and_keeps_explicit_run_controls(
    notebook: ModuleType,
) -> None:
    assert type(notebook.app).__name__ == "_StubApp"
    assert len(notebook.app.cells) >= 7
    text = NOTEBOOK.read_text(encoding="utf-8")
    # marimo's parser (0.25.1) needs: docstring, `import marimo`,
    # `__generated_with`, `app = marimo.App(...)`. Any other statement first
    # makes `marimo check` reject the file (evidence/marimo-qualification.md).
    head = [type(node).__name__ for node in ast.parse(text).body[:4]]
    assert head == ["Expr", "Import", "Assign", "Assign"]
    assert ast.parse(text).body[1].names[0].name == "marimo"  # type: ignore[attr-defined]
    assert "app = marimo.App(" in text
    assert "mo.ui.run_button(" in text and "mo.stop(\n        not run_button.value" in text
    assert "run_requested=True" in text
    assert not re.search(r"omrg_bt_[A-Za-z0-9]", text)  # no hard-coded credential
    assert "print(" not in text


def test_connection_settings_are_checked(notebook: ModuleType, tmp_path: Path) -> None:
    token_file = tmp_path / "t"
    token_file.write_text("omrg_bt_x.y")
    token_file.chmod(0o644)
    with pytest.raises(notebook.ApiConfigError, match="private"):
        notebook.read_token({"OMRG_TOKEN_FILE": str(token_file)})
    with pytest.raises(notebook.ApiConfigError):
        notebook.read_token({})
    with pytest.raises(notebook.ApiConfigError, match="loopback"):
        notebook.ApiClient("http://example.com:8765", "secret")
    with pytest.raises(notebook.ApiConfigError):
        notebook.experiment_context_from_environment({})
    assert notebook.read_token({"OMRG_TOKEN": " abc "}) == "abc"


def _connection_file(tmp_path: Path, token: str, context: str, url: str = BASE) -> Path:
    """Write a connection file and its token file as OMRG does (mode 600)."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    token_file = tmp_path / "omrg-api-token"
    token_file.write_text(token)
    token_file.chmod(0o600)
    path = tmp_path / "omrg_connection.json"
    details = {"api_url": url, "experiment_context": context, "token_file": str(token_file)}
    path.write_text(json.dumps(details))
    path.chmod(0o600)
    return path


def test_connection_file_is_preferred_over_the_variables(
    notebook: ModuleType, tmp_path: Path
) -> None:
    path = _connection_file(tmp_path, "omrg_bt_file.token", "exp_file")
    env = {
        "OMRG_CONNECTION_FILE": str(path),
        "OMRG_API_URL": "http://127.0.0.1:1",
        "OMRG_TOKEN": "omrg_bt_env.token",
        "OMRG_EXPERIMENT_CONTEXT": "exp_env",
    }
    client = notebook.ApiClient.from_environment(env)
    assert client.base_url == BASE and client._token == "omrg_bt_file.token"  # noqa: S105
    assert notebook.experiment_context_from_environment(env) == "exp_file"
    fallback = {key: value for key, value in env.items() if key != "OMRG_CONNECTION_FILE"}
    client = notebook.ApiClient.from_environment(fallback)
    assert client.base_url == "http://127.0.0.1:1" and client._token == "omrg_bt_env.token"  # noqa: S105
    assert notebook.experiment_context_from_environment(fallback) == "exp_env"


@pytest.mark.parametrize("target", ["connection", "token"])
@pytest.mark.parametrize("mode", [0o644, 0o640, 0o700, 0o604])
def test_connection_or_token_file_wider_than_600_is_refused(
    notebook: ModuleType, tmp_path: Path, target: str, mode: int
) -> None:
    path = _connection_file(tmp_path, "omrg_bt_file.token", "exp_file")
    (path if target == "connection" else tmp_path / "omrg-api-token").chmod(mode)
    env = {"OMRG_CONNECTION_FILE": str(path)}
    with pytest.raises(notebook.ApiConfigError, match="chmod 600"):
        notebook.ApiClient.from_environment(env)
    with pytest.raises(notebook.ApiConfigError, match="chmod 600"):
        notebook.experiment_context_from_environment(env)


@pytest.mark.parametrize(
    "content", ["not json", "[]", '{"api_url": "http://127.0.0.1:1"}', '{"api_url": 1}']
)
def test_malformed_connection_file_is_refused(
    notebook: ModuleType, tmp_path: Path, content: str
) -> None:
    path = _connection_file(tmp_path, "omrg_bt_file.token", "exp_file")
    path.write_text(content)
    with pytest.raises(notebook.ApiConfigError, match="OMRG_CONNECTION_FILE"):
        notebook.ApiClient.from_environment({"OMRG_CONNECTION_FILE": str(path)})


def test_missing_connection_file_is_refused(notebook: ModuleType, tmp_path: Path) -> None:
    env = {"OMRG_CONNECTION_FILE": str(tmp_path / "gone.json"), "OMRG_TOKEN": "x"}
    with pytest.raises(notebook.ApiConfigError, match="cannot be read"):
        notebook.ApiClient.from_environment({**env, "OMRG_API_URL": BASE})


def test_connection_file_runs_a_graph(notebook: ModuleType, lab: dict, tmp_path: Path) -> None:
    path = _connection_file(tmp_path / "launch", lab["token"], lab["context_id"])
    env = {"OMRG_CONNECTION_FILE": str(path)}
    api = notebook.ApiClient.from_environment(env, transport=lab["transport"])
    session = notebook.ExperimentSession(
        api, notebook.experiment_context_from_environment(env), lab["output"], poll_interval=0.01
    )
    record = session.run(_search(notebook, session, 2), {"query": "x"}, run_requested=True)
    assert record["status"] == "succeeded" and record["experiment_context"] == lab["context_id"]


# ── Shared graph execution ───────────────────────────────────────────────


def test_notebook_and_canvas_share_the_graph_and_record_identities(
    notebook: ModuleType, lab: dict
) -> None:
    session, client = lab["session"], lab["client"]
    record = session.run(
        _search(notebook, session, 2), {"query": "text"}, run_requested=True, name="search"
    )
    assert record["status"] == "succeeded", record["failure"]
    identity = lab["parts"].experiments.identity(lab["context_id"]).provenance()
    assert record["backend"] == identity and record["index_identity"] == identity["index_identity"]
    assert record["experiment_context"] == lab["context_id"]
    assert record["effective_settings"] and record["inputs"] == {"query": "text"}
    assert record["outputs"]["results"][0]["text"].startswith("exp text")
    assert record["event_count"] > 0
    # The canvas (browser session) submits the same revision in the same context.
    revision = record["graph_revision"]
    canvas = client.post(
        "/v1/runs",
        json={
            "revision_id": revision["revision_id"],
            "inputs": {"query": "text"},
            "experiment_context": lab["context_id"],
        },
        headers=ORIGIN,
    ).json()["run"]
    assert canvas["graph_hash"] == revision["graph_hash"]
    assert canvas["resources"]["graph_identity"] == revision["graph_identity"]
    assert canvas["run_id"] != record["run_id"]  # each run keeps its own snapshot
    assert canvas["resources"]["experiment"]["backend"] == identity


def test_parameter_change_without_a_request_admits_nothing(notebook: ModuleType, lab: dict) -> None:
    session, transport = lab["session"], lab["transport"]
    document = _search(notebook, session, 2)
    mark = len(transport.calls)
    assert session.run(document, {"query": "changed"}, run_requested=False) is None
    assert transport.calls[mark:] == [] and session.runs_submitted == 0
    assert lab["client"].get("/v1/runs").json()["runs"] == []


def test_parameter_change_runs_again_without_repeating_unrelated_steps(
    notebook: ModuleType, lab: dict
) -> None:
    session, transport = lab["session"], lab["transport"]
    templates = notebook.list_templates(session.client)
    search = next(t for t in templates if t["name"] == "search")["document"]
    first = session.run(
        notebook.set_node_params(search, {"prepare": {"top_k": 2}}),
        {"query": "a"},
        run_requested=True,
    )
    # A changed input reuses the saved revision: no template, pipeline or revision call.
    mark = len(transport.calls)
    second = session.run(
        notebook.set_node_params(search, {"prepare": {"top_k": 2}}),
        {"query": "b"},
        run_requested=True,
    )
    steps = {call for call in transport.since(mark)}
    assert ("POST", "/v1/runs") in steps
    assert not any(path.startswith("/v1/pipeline") for _, path in steps)
    assert second["graph_revision"]["revision_id"] == first["graph_revision"]["revision_id"]
    # A changed node parameter saves one new revision in the same pipeline.
    mark = len(transport.calls)
    third = session.run(
        notebook.set_node_params(search, {"prepare": {"top_k": 3}}),
        {"query": "b"},
        run_requested=True,
    )
    calls = transport.since(mark)
    assert [c for c in calls if c[0] == "POST"] == [
        ("POST", "/v1/pipelines/ID/revisions"),
        ("POST", "/v1/runs"),
    ]
    assert ("GET", "/v1/pipeline-templates") not in calls
    assert third["graph_revision"]["revision_id"] != first["graph_revision"]["revision_id"]
    assert third["graph_revision"]["pipeline_id"] == first["graph_revision"]["pipeline_id"]
    assert session.runs_submitted == 3


# ── Checkpoints ──────────────────────────────────────────────────────────


def test_checkpoint_is_written_atomically(notebook: ModuleType, lab: dict) -> None:
    session = lab["session"]
    record = session.run(_search(notebook, session, 2), {"query": "x"}, run_requested=True)
    path = Path(record["checkpoint"])
    assert path.parent == lab["output"] and path.suffix == ".json"
    stored = json.loads(path.read_text())
    assert stored == {k: v for k, v in record.items() if k != "checkpoint"}
    assert list(lab["output"].glob("*.tmp")) == []
    assert lab["token"] not in path.read_text()


def test_failed_checkpoint_keeps_the_previous_file(
    notebook: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = notebook.checkpoint({"n": 1}, tmp_path, "same")
    original = first.read_text()

    def broken_replace(src: Any, dst: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(notebook.os, "replace", broken_replace)
    with pytest.raises(OSError):
        notebook.checkpoint({"n": 2}, tmp_path, "same")
    assert first.read_text() == original
    assert sorted(p.name for p in tmp_path.iterdir()) == ["same.json"]


# ── Revocation and secrecy ───────────────────────────────────────────────


def test_revoked_context_fails_the_next_run_cleanly(notebook: ModuleType, lab: dict) -> None:
    session, client = lab["session"], lab["client"]
    document = _search(notebook, session, 2)
    session.run(document, {"query": "x"}, run_requested=True)
    before = sorted(lab["output"].iterdir())
    client.delete(f"/v1/experiments/{lab['context_id']}", headers=ORIGIN)
    with pytest.raises(notebook.ApiError) as caught:
        session.run(document, {"query": "y"}, run_requested=True)
    assert caught.value.status == 403 and caught.value.code == "experiment_context_revoked"
    assert sorted(lab["output"].iterdir()) == before  # no partial checkpoint
    assert len(client.get("/v1/runs").json()["runs"]) == 1


def test_revoked_credential_fails_the_next_run_cleanly(notebook: ModuleType, lab: dict) -> None:
    session, client = lab["session"], lab["client"]
    client.delete(f"/v1/credentials/{lab['credential_id']}", headers=ORIGIN)
    with pytest.raises(notebook.ApiError) as caught:
        session.run(_search(notebook, session, 2), {"query": "y"}, run_requested=True)
    assert caught.value.status == 401
    assert lab["token"] not in str(caught.value)


def test_token_is_never_shown(
    notebook: ModuleType, lab: dict, capsys: pytest.CaptureFixture[str]
) -> None:
    session = lab["session"]
    record = session.run(_search(notebook, session, 2), {"query": "x"}, run_requested=True)
    shown = repr(session.client) + json.dumps(record) + str(vars(session.client).get("base_url"))
    assert lab["token"] not in shown
    assert "<hidden>" in repr(session.client)
    captured = capsys.readouterr()
    assert lab["token"] not in captured.out + captured.err
