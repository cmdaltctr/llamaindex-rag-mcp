"""Helpers for the CLI, watcher and installer tests on user-profile collections (task 8.10).

A user profile lives in the workspace database of the default workspace
(``<home>/.omrs/workspace/workspace.db``). The helpers build that database
with the profile service, link it into a temporary home folder, tag a
collection of the test store and count graph runs on the Engine class. This
module holds no tests.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from llama_index.core import Settings as LlamaIndexSettings
from tests.unit.test_engine_profiles_support import PROFILE, make_env

from omrs.core.vectordb.lancedb.store import LanceVectorStore

#: The collection that follows the user profile ``my-notes``.
USER_COLLECTION = "notes"

#: ``PROFILE`` (``my-notes``) is re-exported for the tests.
__all__ = ["PROFILE", "USER_COLLECTION"]


def link_workspace(tmp_path: Path, effective_settings: Any, home: Path) -> Path:
    """Create the workspace with ``my-notes`` and link it as the default workspace of ``home``."""
    env = make_env(tmp_path, effective_settings)
    target = home / ".omrs" / "workspace"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(env.workspace.path.parent, target_is_directory=True)
    return target


def use_home(monkeypatch: pytest.MonkeyPatch, home: Path) -> Path:
    """Point ``Path.home()`` at ``home`` for this test."""
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    return home


def tag_collection(tmp_path: Path, name: str, profile: str | None) -> None:
    """Create ``name`` in the test store with one seed row and tag it with ``profile``.

    A LanceDB collection keeps its tag in memory until the table exists, so the
    seed row makes the tag visible to the store that the command builds.
    """
    from llama_index.core.schema import TextNode

    store = LanceVectorStore(uri=str(tmp_path / "lancedb"))
    store.write_nodes([TextNode(text="seed note")], name)
    if profile is not None:
        store.update_collection_metadata(name, {"profile": profile})


def count_graph_runs(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Spy on ``Engine.run_pipeline`` and return a list with one entry per graph run."""
    from omrs.engine import Engine

    runs: list[str] = []
    original = Engine.run_pipeline

    async def counted(self: Any, *args: Any, **kwargs: Any) -> Any:
        runs.append("run_pipeline")
        return await original(self, *args, **kwargs)

    monkeypatch.setattr(Engine, "run_pipeline", counted)
    return runs


def use_mock_embedder(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the composition root build the shared mock embedder instead of Ollama."""
    from omrs.core.providers.embeddings import registry as embed_registry

    real_get = embed_registry.get

    def _get(name: str) -> Any:
        if name == "ollama":
            return lambda _settings: LlamaIndexSettings.embed_model
        return real_get(name)

    monkeypatch.setattr(embed_registry, "get", _get)


def one_line(text: str) -> str:
    """Collapse the whitespace that Rich line wrapping adds."""
    return re.sub(r"\s+", " ", text).strip()
