"""Notebook guide, plugin absence and no embedded editor (task 8.7).

The workspace starts and serves document and graph routes when no plugin
is registered, and starts no process. Plugin routes then report "not
registered" without an error. No source under ``web/src`` or
``src/omrg/transports`` embeds the editor, and no document claims an
embedded editor. Every path, route, port, variable and command that the
notebook guide cites exists in the code it describes.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402
from tests.unit.test_web_documents_support import (  # noqa: E402
    BASE,
    ORIGIN,
    lance_store,
    login,
    make_engine,
    seed,
)
from tests.unit.test_web_guides_support import (  # noqa: E402
    GUIDES,
    REPO,
    broken_links,
    code_spans,
    links_to,
    missing_repository_paths,
    undeclared_routes,
)

from omrg.integrations import process_launcher  # noqa: E402
from omrg.transports.api.app import create_app  # noqa: E402
from omrg.transports.api.lifespan import DEFAULT_PLUGIN_PORTS, WebConfig  # noqa: E402
from omrg.transports.api.runs_wiring import run_service_factory  # noqa: E402
from omrg.transports.api.security import AccessPolicy  # noqa: E402

GUIDE = GUIDES / "notebooks.md"
PLUGIN = REPO / "plugins" / "marimo"
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
_EMBED = re.compile(r"\bembed(?:s|ded)?\b", re.I)
_EDITOR = re.compile(r"\b(?:editor|notebook|marimo)\b", re.I)
_NEGATION = re.compile(r"\b(?:never|not|no|without)\b", re.I)


def _text() -> str:
    return GUIDE.read_text(encoding="utf-8")


# ── The application works without the plugin ──────────────────────────


def _app(tmp_path: Path, engine: Any) -> tuple[Any, AccessPolicy]:
    config = WebConfig(workspace=tmp_path / "ws", port=8765, static_dir=None)
    policy = AccessPolicy.for_launch(config.host, config.port)
    app = create_app(
        config,
        policy=policy,
        engine_factory=lambda: engine,
        run_service_factory=run_service_factory,
    )
    return app, policy


def test_workspace_serves_documents_and_graphs_without_a_plugin(
    tmp_path: Path, effective_settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No registered plugin: ordinary routes work and no process starts."""

    def no_process(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the workspace started a process without a plugin request")

    monkeypatch.setattr(process_launcher.subprocess, "Popen", no_process)
    store = lance_store(tmp_path)
    seed(store, "notes", str(tmp_path / "a.md"), 2)
    app, policy = _app(tmp_path, make_engine(store, effective_settings()))
    with TestClient(app, base_url=BASE) as client:
        login(client, policy)
        plugins = client.get("/v1/plugins")
        recheck = client.post("/v1/plugins/marimo/recheck", headers=ORIGIN)
        collections = client.get("/v1/collections")
        documents = client.get("/v1/collections/notes/documents")
        operations = client.get("/v1/pipeline-operations")
        pipelines = client.get("/v1/pipelines")
        templates = client.get("/v1/pipeline-templates")
        runs = client.get("/v1/runs")
    body = plugins.json()
    assert plugins.status_code == 200
    assert body["plugins"] == [] and body["editors"] == []
    assert "uv tool install marimo" in body["install_hint"]
    assert body["trust_notice"]
    assert recheck.status_code == 404
    assert recheck.json() == {"status": "error", "message": "Unknown plugin."}
    for response in (collections, documents, operations, pipelines, templates, runs):
        assert response.status_code == 200, response.text
    assert [row["name"] for row in collections.json()] == ["notes"]
    assert operations.json()["operations"]
    assert {t["name"] for t in templates.json()["templates"]} >= {"search", "answer"}


# ── The editor is never embedded ───────────────────────────────────────


def _source_files() -> list[Path]:
    web = [
        path
        for path in (REPO / "web" / "src").rglob("*")
        if path.suffix in {".ts", ".tsx", ".js", ".jsx", ".css", ".html"}
    ]
    transports = [
        path
        for path in (REPO / "src" / "omrg" / "transports").rglob("*")
        if path.suffix in {".py", ".yaml", ".md"} and "static" not in path.parts
    ]
    return [*web, REPO / "web" / "index.html", *transports]


def test_no_source_embeds_the_editor() -> None:
    """No frame or embed element in the frontend or transport sources."""
    files = _source_files()
    assert any(path.suffix == ".tsx" for path in files)
    pattern = re.compile(r"<\s*(?:iframe|frame|embed|object)\b|['\"]iframe['\"]", re.I)
    offenders = [
        str(path.relative_to(REPO))
        for path in files
        if pattern.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == []


def _documents() -> list[Path]:
    return [
        *sorted(GUIDES.glob("*.md")),
        REPO / "README.md",
        PLUGIN / "README.md",
        REPO / "src" / "omrg" / "transports" / "api" / "README.md",
        *[path for path in (REPO / "web" / "src").rglob("*.tsx")],
    ]


def test_no_document_or_view_claims_an_embedded_editor() -> None:
    """A sentence that joins "embed" and "editor" must deny the embedding."""
    claims = []
    for path in _documents():
        for sentence in _SENTENCE.findall(path.read_text(encoding="utf-8")):
            if _EMBED.search(sentence) and _EDITOR.search(sentence):
                if not _NEGATION.search(sentence):
                    claims.append(f"{path.relative_to(REPO)}: {sentence.strip()}")
    assert claims == []


def test_guides_say_the_editor_opens_in_a_separate_tab() -> None:
    for text in (_text(), (PLUGIN / "README.md").read_text(encoding="utf-8")):
        assert "separate browser tab" in text
        assert "never embeds the editor" in text


# ── Every citation of the guide exists ─────────────────────────────────


def test_cited_paths_routes_and_links_exist() -> None:
    text = _text()
    assert missing_repository_paths(text) == []
    assert undeclared_routes(text) == []
    assert broken_links(GUIDE) == []
    assert broken_links(PLUGIN / "README.md") == []


def test_cited_ports_variables_and_range_match_the_code() -> None:
    text = _text()
    ports = [int(port) for port in re.findall(r"\b(27\d\d)\b", text)]
    assert tuple(ports) == DEFAULT_PLUGIN_PORTS
    notebook = (PLUGIN / "starter_notebook.py").read_text(encoding="utf-8")
    variables = {span for span in code_spans(text) if span.startswith("OMRG_")}
    manual = {"OMRG_API_URL", "OMRG_TOKEN_FILE", "OMRG_TOKEN", "OMRG_EXPERIMENT_CONTEXT"}
    assert variables == {*manual, "OMRG_CONNECTION_FILE"}
    assert all(name in notebook for name in variables)
    assert all(name not in process_launcher.ENV_ALLOWLIST for name in variables)
    # OMRG delivers only the connection file path to the editor it starts.
    assert process_launcher.LAUNCH_ENV_ALLOWLIST == ("OMRG_CONNECTION_FILE",)
    assert "omrg_connection.json" in text and "omrg_connection.json" in notebook
    assert "gap" not in text.lower()
    assert "chmod 600" in notebook and 'output" / "runs"' in notebook
    tested = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))["tool"]
    expected = f">={tested['tested_versions']['minimum']},<{tested['tested_versions']['below']}"
    assert f"`{expected}`" in text


def test_cited_commands_match_the_plugin_and_the_cli() -> None:
    text = _text()
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    for command in ("uv tool install marimo", "uv tool upgrade marimo", "command -v marimo"):
        assert command in text and command in readme
    manifest = json.loads((PLUGIN / "manifest.json").read_text(encoding="utf-8"))
    probe = manifest["recipes"]["probe"]
    assert f"marimo {' '.join(probe['version_args'])}" in text
    assert f"marimo {' '.join(probe['help_args'])}" in text
    assert "omrg web --experiment-root" in text


def test_guide_is_linked_from_the_web_guide_and_the_plugin_readme() -> None:
    assert links_to(GUIDES / "web-workspace.md", "notebooks.md")
    assert links_to(PLUGIN / "README.md", "notebooks.md")
    assert links_to(REPO / "README.md", "notebooks.md")
