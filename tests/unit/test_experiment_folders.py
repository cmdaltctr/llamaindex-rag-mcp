"""Experiment folders: path validation, directory creation and the tree (tasks 5.1).

A folder is a directory below an approved experiment root. The checks run
on the path text first, then on the real file system (links). A refused
request creates nothing.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omrs.core.experiments import ExperimentPathError, ExperimentRegistry
from omrs.core.experiments.folders import (
    MAX_FOLDER_DEPTH,
    MAX_TREE_NODES,
    create_folder,
    folder_tree,
    split_folder_path,
)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    path = tmp_path / "experiments"
    path.mkdir()
    return path.resolve()


def _entries(root: Path) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.rglob("*"))


def _code(exc: pytest.ExceptionInfo[ExperimentPathError]) -> str:
    return exc.value.code


# ── Path text rules ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "parts"),
    [
        ("hybrid-search", ("hybrid-search",)),
        ("a/b", ("a", "b")),
        ("run_1.v2/x y", ("run_1.v2", "x y")),
        ("/".join("d" * 3 for _ in range(MAX_FOLDER_DEPTH)), ("ddd",) * MAX_FOLDER_DEPTH),
    ],
)
def test_valid_paths_split_into_segments(text: str, parts: tuple[str, ...]) -> None:
    assert split_folder_path(text) == parts


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("..", "traversal"),
        ("../x", "traversal"),
        ("a/../b", "traversal"),
        ("a/..", "traversal"),
        ("/etc/passwd", "not_relative"),
        ("a//b", "invalid_name"),
        ("a/", "invalid_name"),
        ("", "invalid_name"),
        (".", "invalid_name"),
        ("a/./b", "invalid_name"),
        (".hidden", "invalid_name"),
        ("a\\b", "invalid_name"),
        ("a\x00b", "invalid_name"),
        ("name with ~", "invalid_name"),
        ("trailing.", "invalid_name"),
        ("trailing ", "invalid_name"),
        ("x" * 81, "invalid_name"),
        ("output", "invalid_name"),
        ("a/output", "invalid_name"),
        ("/".join(["d"] * (MAX_FOLDER_DEPTH + 1)), "too_deep"),
    ],
)
def test_bad_paths_are_refused(text: str, code: str) -> None:
    with pytest.raises(ExperimentPathError) as exc:
        split_folder_path(text)
    assert _code(exc) == code


# ── Creation ─────────────────────────────────────────────────────────────


def test_create_makes_the_directory_below_the_root(root: Path) -> None:
    created = create_folder((root,), "hybrid-search")
    assert created == root / "hybrid-search"
    assert created.is_dir()


def test_create_makes_nested_directories(root: Path) -> None:
    created = create_folder((root,), "hybrid-search/run-1")
    assert created == root / "hybrid-search" / "run-1"
    assert created.is_dir()


@pytest.mark.parametrize("text", ["../escape", "a/../../escape", "/tmp/escape", "a/../b"])
def test_traversal_creates_nothing(root: Path, text: str) -> None:
    sibling = root.parent / "escape"
    with pytest.raises(ExperimentPathError):
        create_folder((root,), text)
    assert _entries(root) == []
    assert not sibling.exists()


def test_depth_limit_creates_nothing(root: Path) -> None:
    with pytest.raises(ExperimentPathError) as exc:
        create_folder((root,), "/".join(["d"] * (MAX_FOLDER_DEPTH + 1)))
    assert _code(exc) == "too_deep"
    assert _entries(root) == []


def test_a_symbolic_link_in_the_path_is_refused(root: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ExperimentPathError) as exc:
        create_folder((root,), "link/inside")
    assert _code(exc) == "symlink_escape"
    assert list(outside.iterdir()) == []


def test_an_existing_folder_is_refused(root: Path) -> None:
    (root / "taken").mkdir()
    with pytest.raises(ExperimentPathError) as exc:
        create_folder((root,), "taken")
    assert _code(exc) == "exists"


def test_a_file_in_the_way_is_refused(root: Path) -> None:
    (root / "file").write_text("x", encoding="utf-8")
    with pytest.raises(ExperimentPathError) as exc:
        create_folder((root,), "file/child")
    assert _code(exc) == "not_a_directory"
    assert _entries(root) == ["file"]


def test_root_selection(root: Path, tmp_path: Path) -> None:
    other = tmp_path / "other"
    other.mkdir()
    other = other.resolve()
    with pytest.raises(ExperimentPathError) as exc:
        create_folder((root, other), "x")
    assert _code(exc) == "root_required"
    assert create_folder((root, other), "x", root=str(other)) == other / "x"
    with pytest.raises(ExperimentPathError) as exc:
        create_folder((root, other), "x", root=str(tmp_path))
    assert _code(exc) == "root_unknown"
    with pytest.raises(ExperimentPathError) as exc:
        create_folder((), "x")
    assert _code(exc) == "root_unknown"


# ── Tree ─────────────────────────────────────────────────────────────────


def _names(nodes: list[dict]) -> list[str]:
    return [node["name"] for node in nodes]


def test_tree_shows_empty_folders_and_groups_contexts(root: Path) -> None:
    registry = ExperimentRegistry([root])
    for rel in ("reranker-calibration/run-1", "reranker-calibration/run-2", "input-quality/a"):
        create_folder((root,), rel)
    create_folder((root,), "empty-folder")
    one = registry.register(root / "reranker-calibration" / "run-1")
    registry.register(root / "reranker-calibration" / "run-2")
    registry.register(root / "input-quality" / "a")
    tree = folder_tree(root, registry.contexts())
    assert _names(tree) == ["empty-folder", "input-quality", "reranker-calibration"]
    empty, quality, rerank = tree
    assert empty["children"] == [] and empty["context_id"] is None
    assert _names(rerank["children"]) == ["run-1", "run-2"]
    assert rerank["path"] == "reranker-calibration"
    assert rerank["workspace"] == str(root / "reranker-calibration")
    run_one = rerank["children"][0]
    assert run_one["context_id"] == one.context_id
    assert run_one["path"] == "reranker-calibration/run-1"
    assert quality["children"][0]["context_id"] is not None


def test_a_context_workspace_is_a_leaf(root: Path) -> None:
    registry = ExperimentRegistry([root])
    create_folder((root,), "main/sub")
    (root / "main" / "sub" / "output" / "deeper").mkdir(parents=True)
    registry.register(root / "main" / "sub")
    sub = folder_tree(root, registry.contexts())[0]["children"][0]
    assert sub["children"] == []


def test_a_revoked_context_leaves_the_folder_without_a_context(root: Path) -> None:
    registry = ExperimentRegistry([root])
    create_folder((root,), "main/sub")
    context = registry.register(root / "main" / "sub")
    registry.revoke(context.context_id)
    sub = folder_tree(root, registry.contexts())[0]["children"][0]
    assert sub["context_id"] is None


def test_tree_skips_hidden_directories_links_and_deep_levels(root: Path, tmp_path: Path) -> None:
    (root / ".git").mkdir()
    (root / "ok").mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "link").symlink_to(outside, target_is_directory=True)
    deep = root / "ok"
    for index in range(MAX_FOLDER_DEPTH + 2):
        deep = deep / f"l{index}"
    deep.mkdir(parents=True)
    tree = folder_tree(root, [])
    assert _names(tree) == ["ok"]
    node, depth = tree[0], 1
    while node["children"]:
        node, depth = node["children"][0], depth + 1
    assert depth == MAX_FOLDER_DEPTH


def test_tree_keeps_a_context_deeper_than_the_depth_limit(root: Path) -> None:
    registry = ExperimentRegistry([root])
    deep = root
    for index in range(MAX_FOLDER_DEPTH + 1):
        deep = deep / f"l{index}"
    deep.mkdir(parents=True)
    context = registry.register(deep)
    node = folder_tree(root, registry.contexts())[0]
    while node["children"]:
        node = node["children"][0]
    assert node["context_id"] == context.context_id


def test_tree_node_count_is_capped(root: Path) -> None:
    for index in range(MAX_TREE_NODES + 20):
        (root / f"f{index:04d}").mkdir()
    assert len(folder_tree(root, [])) == MAX_TREE_NODES
