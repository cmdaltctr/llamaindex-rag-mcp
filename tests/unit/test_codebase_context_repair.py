"""Regressions for the codebase-map context repair (design D3, D4, D5).

The map and its cache must use the settings and store that the caller
supplies. Default accessors are poisoned so that a hidden lookup fails the
test. Cache reuse must prove its owner context, so two owners that share
one cache directory never return each other's document map.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from omrg.core.codebase import codebase_map as cm
from omrg.core.codebase.codebase_map import CodebaseMap, FileInventory

_SRC = str(Path(__file__).resolve().parents[2] / "src")


# ── Helpers ──────────────────────────────────────────────────────────────


class _FakeStore:
    """Minimal store double: a documents collection with a durable version."""

    def __init__(self, data_version: str | None, rows: int = 0) -> None:
        self.data_version = data_version
        self.rows = rows
        self.calls: list[str] = []

    def count(self, name: str) -> int:
        self.calls.append(f"count:{name}")
        return self.rows

    def fetch_all(self, name: str, include: list[str]) -> dict:
        self.calls.append(f"fetch_all:{name}")
        return {"ids": [], "embeddings": [], "metadatas": [], "documents": []}

    def get_data_version(self, name: str) -> str | None:
        self.calls.append(f"data_version:{name}")
        return self.data_version


@pytest.fixture
def poisoned_defaults(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Make every default settings/store accessor fail loudly and record calls."""
    hits: list[str] = []

    def _poison_settings():
        hits.append("settings")
        raise AssertionError("default effective settings must not be read")

    def _poison_store():
        hits.append("store")
        raise AssertionError("default store must not be read")

    import omrg.core.settings as core_settings
    import omrg.core.vectordb as vectordb

    monkeypatch.setattr(core_settings, "get_default_effective_settings", _poison_settings)
    monkeypatch.setattr(vectordb, "get_default_store", _poison_store)
    # Module-level bindings made with ``from ... import`` before the repair.
    for mod_name in ("omrg.core.codebase.cache", "omrg.core.codebase.codebase_map"):
        mod = sys.modules.get(mod_name)
        if mod is not None and hasattr(mod, "get_default_effective_settings"):
            monkeypatch.setattr(mod, "get_default_effective_settings", _poison_settings)
    return hits


@pytest.fixture(autouse=True)
def _no_magika():
    with patch("omrg.integrations.magika._is_magika_available", return_value=False):
        yield


# ── 4.1 Fresh import orders ──────────────────────────────────────────────


@pytest.mark.parametrize(
    "first, second",
    [
        ("omrg.core.codebase.cache", "omrg.core.codebase.codebase_map"),
        ("omrg.core.codebase.codebase_map", "omrg.core.codebase.cache"),
    ],
    ids=["cache-first", "map-first"],
)
def test_fresh_import_order_is_independent(first: str, second: str) -> None:
    """Both orders import in a fresh interpreter and share one model class."""
    code = (
        f"import {first}, {second}\n"
        "from omrg.core.codebase import cache, codebase_map, models\n"
        "assert cache.CodebaseMap is codebase_map.CodebaseMap is models.CodebaseMap\n"
        "assert cache.FileInventory is codebase_map.FileInventory is models.FileInventory\n"
        "print('OK')\n"
    )
    result = subprocess.run(  # noqa: S603
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        env={"PYTHONPATH": _SRC, "PATH": "/usr/bin:/bin"},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert result.stdout.strip() == "OK"


def test_models_round_trip_through_cache_serialisers() -> None:
    """Facade classes are the shared ones and JSON round trips keep fields."""
    from omrg.core.codebase import cache, models

    assert CodebaseMap is models.CodebaseMap
    assert FileInventory is models.FileInventory
    original = CodebaseMap(
        inventory=FileInventory(
            type_counts={"code/python": 1},
            binary_files=["a.png"],
            mismatches=[("x.txt", "text", "python")],
        ),
        code_communities=[{"label": "Core"}],
        doc_communities=[{"label": "Docs"}],
        cross_links=[{"code": "a", "doc": "b", "relation": "r"}],
        hubs=[{"file": "a.py", "in_degree": 2}],
        commit_hash="abc",
    )
    payload = json.loads(json.dumps(cache._codebase_map_to_dict(original)))
    assert set(payload) == {
        "commit_hash",
        "inventory",
        "code_communities",
        "doc_communities",
        "cross_links",
        "hubs",
    }
    restored = cache._codebase_map_from_dict(payload)
    assert restored == original


# ── 4.2 Explicit settings/store context ─────────────────────────────────


def test_build_uses_supplied_context_without_defaults(
    tmp_path: Path, effective_settings, poisoned_defaults: list[str]
) -> None:
    """Explicit settings/store bypass every default accessor."""
    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "README.md").write_text("# Doc\n")
    store = _FakeStore("lance:e1:3", rows=0)
    result = cm.build_codebase_map(str(tmp_path), settings=effective_settings(), store=store)
    assert "code/python" in result.inventory.type_counts
    assert "count:documents" in store.calls
    assert poisoned_defaults == []


def test_store_less_map_has_no_document_communities(
    tmp_path: Path, effective_settings, poisoned_defaults: list[str]
) -> None:
    """A deliberate store-less map never queries a hidden default store."""
    (tmp_path / "README.md").write_text("# Doc\n")
    with patch("omrg.core.documents.doc_graph.build_document_graph") as build_doc:
        build_doc.side_effect = lambda collection, threshold=None: __import__("networkx").Graph()
        result = cm.build_codebase_map(str(tmp_path), settings=effective_settings(), store=None)
    assert result.doc_communities == []
    for call in build_doc.call_args_list:
        assert call.args[0] is None
    assert poisoned_defaults == []


def test_both_document_graph_calls_receive_supplied_threshold(
    tmp_path: Path, effective_settings, poisoned_defaults: list[str]
) -> None:
    """Community and cross-link graph builds both get the supplied threshold."""
    import networkx as nx

    from omrg.core.codebase.code_graph import Community
    from omrg.core.documents.doc_graph import DocCommunity

    (tmp_path / "app.py").write_text("x = 1\n")
    (tmp_path / "README.md").write_text("# Doc\n")
    settings = effective_settings(doc_similarity_threshold=0.42)
    store = _FakeStore("lance:e1:3", rows=2)
    with (
        patch("omrg.core.documents.doc_graph.build_document_graph") as build_doc,
        patch(
            "omrg.core.codebase.code_graph.detect_communities",
            return_value=[Community(label="Core", files=["app.py"], edge_count=0)],
        ),
        patch(
            "omrg.core.documents.doc_graph.detect_document_communities",
            return_value=[DocCommunity(label="Docs", chunks=["c1"], category="x")],
        ),
        patch("omrg.core.documents.doc_graph.compute_cross_links", return_value=[]),
    ):
        build_doc.return_value = nx.Graph()
        cm.build_codebase_map(str(tmp_path), settings=settings, store=store)

    assert build_doc.call_count == 2
    for call in build_doc.call_args_list:
        assert call.kwargs.get("threshold") == 0.42
    assert poisoned_defaults == []


def test_two_contexts_use_their_own_cache_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    effective_settings,
    poisoned_defaults: list[str],
) -> None:
    """Distinct supplied cache locations are honoured under poisoned defaults."""
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)
    first = effective_settings(codebase_map_cache_dir=".cache-one")
    second = effective_settings(codebase_map_cache_dir=".cache-two")
    with patch("omrg.core.codebase.cache._get_git_commit_hash", return_value="c0ffee"):
        for settings in (first, second):
            text = cm.get_codebase_map_text(".", False, settings=settings, store=None)
            assert "## File Types" in text, text
    assert (tmp_path / ".cache-one" / "codebase-graph.json").exists()
    assert (tmp_path / ".cache-two" / "codebase-graph.json").exists()
    assert not (tmp_path / ".opencode").exists()
    assert poisoned_defaults == []


def test_mcp_handler_forwards_composed_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The MCP boundary supplies composed settings/store to core."""
    from omrg.core.settings import get_default_effective_settings
    from omrg.core.vectordb import get_default_store
    from omrg.transports.mcp import codebase as mcp_codebase

    expected_settings = get_default_effective_settings()
    expected_store = get_default_store()
    seen: dict = {}

    def _record(path=".", refresh=False, *, settings=None, store=None):
        seen.update(path=path, refresh=refresh, settings=settings, store=store)
        return "MAP"

    monkeypatch.setattr(cm, "get_codebase_map_text", _record)
    assert mcp_codebase.get_codebase_map(str(tmp_path), True) == "MAP"
    assert seen["path"] == str(tmp_path)
    assert seen["refresh"] is True
    assert seen["settings"] is expected_settings
    assert seen["store"] is expected_store


def test_mcp_handler_settings_failure_returns_error_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A settings failure at the boundary keeps the JSON error shape."""
    import omrg.core.settings as core_settings
    from omrg.transports.mcp import codebase as mcp_codebase

    def _boom():
        raise RuntimeError("no settings")

    monkeypatch.setattr(core_settings, "get_default_effective_settings", _boom)
    data = json.loads(mcp_codebase.get_codebase_map(".", False))
    assert data["status"] == "error"
    assert "no settings" in data["message"]


# ── 4.3 Owner-context cache validation ──────────────────────────────────


def _count_builds(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Wrap the real builder to count fresh builds and record their stores."""
    builds: list[object] = []
    real = cm.build_codebase_map

    def _wrapped(path, *args, **kwargs):
        builds.append(kwargs.get("store"))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(cm, "build_codebase_map", _wrapped)
    return builds


@pytest.fixture
def git_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "app.py").write_text("x = 1\n")
    monkeypatch.chdir(tmp_path)
    with patch("omrg.core.codebase.cache._get_git_commit_hash", return_value="c0ffee"):
        yield tmp_path


def test_matching_owner_context_reuses_cache(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    builds = _count_builds(monkeypatch)
    settings = effective_settings()
    store = _FakeStore("lance:e1:3")
    cm.get_codebase_map_text(".", False, settings=settings, store=store)
    cm.get_codebase_map_text(".", False, settings=settings, store=store)
    assert len(builds) == 1


def test_same_directory_different_store_is_a_miss(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """Two owners sharing one cache directory never reuse each other's map."""
    builds = _count_builds(monkeypatch)
    settings = effective_settings()
    store_a, store_b = _FakeStore("lance:A:1"), _FakeStore("lance:B:1")
    cm.get_codebase_map_text(".", False, settings=settings, store=store_a)
    cm.get_codebase_map_text(".", False, settings=settings, store=store_b)
    assert builds == [store_a, store_b]


def test_same_directory_different_map_settings_is_a_miss(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    builds = _count_builds(monkeypatch)
    store = _FakeStore("lance:A:1")
    cm.get_codebase_map_text(".", False, settings=effective_settings(), store=store)
    cm.get_codebase_map_text(".", False, settings=effective_settings(community_seed=7), store=store)
    assert len(builds) == 2


def test_unscoped_old_record_is_a_safe_miss(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """A pre-repair record without owner context is ignored, not deleted early."""
    from omrg.core.codebase import cache

    cache_file = git_project / ".opencode" / "codebase-graph.json"
    cache_file.parent.mkdir()
    old = cache._codebase_map_to_dict(CodebaseMap(commit_hash="c0ffee"))
    cache_file.write_text(json.dumps(old))

    loaded = cache._load_cache(
        str(git_project),
        cache_dir=".opencode",
        owner_context=cache.build_owner_context(effective_settings(), None),
    )
    assert loaded is None
    assert cache_file.exists()


def test_unprovable_store_context_never_reuses(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """A store without a durable data version rebuilds on every call."""
    builds = _count_builds(monkeypatch)
    settings = effective_settings()
    store = _FakeStore(None)
    cm.get_codebase_map_text(".", False, settings=settings, store=store)
    cm.get_codebase_map_text(".", False, settings=settings, store=store)
    assert len(builds) == 2


def test_store_data_change_invalidates(
    git_project: Path, monkeypatch: pytest.MonkeyPatch, effective_settings
) -> None:
    """New document data at the same commit is a miss."""
    builds = _count_builds(monkeypatch)
    settings = effective_settings()
    store = _FakeStore("lance:A:1")
    cm.get_codebase_map_text(".", False, settings=settings, store=store)
    store.data_version = "lance:A:2"
    cm.get_codebase_map_text(".", False, settings=settings, store=store)
    assert len(builds) == 2
