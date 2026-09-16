"""Fail-first smoke-tool contracts for ``pin-magika-detection``.

The production tool does not exist yet. These tests define its narrow API:
``run_comparison(paths, settings)`` returns a payload dict and ``main(argv)``
returns the CLI exit status. Scanner functions remain module-level seams so
tests can compare fixtures without invoking Magika or ingestion.
"""

from __future__ import annotations

import ast
import importlib.util
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from omrg.integrations.magika import FileEntry

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SMOKE_TOOL = _REPO_ROOT / "scripts" / "magika_label_smoke.py"
_BANNED_ROOTS = ("omrg.core.ingestion", "omrg.core.vectordb", "omrg.compose", "llama_index")
_BANNED_SYMBOLS = {"build_codebase_map", "Engine"}


def _load_smoke_tool():
    """Import the smoke script by file path for in-process seam patches."""
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    spec = importlib.util.spec_from_file_location("magika_label_smoke", _SMOKE_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _assert_static_tool_safe(path: Path) -> None:
    """Reject forbidden imports, dynamic imports, and orchestration symbols."""
    tree = ast.parse(path.read_text(encoding="utf-8"))

    def assert_module_allowed(module: str) -> None:
        assert not module.startswith(_BANNED_ROOTS), f"banned module reference: {module!r}"
        assert "ingest" not in module and "embed" not in module, (
            f"banned module reference: {module!r}"
        )

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert_module_allowed(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                assert_module_allowed(node.module)
            for alias in node.names:
                assert alias.name not in _BANNED_SYMBOLS, f"banned symbol import: {alias.name}"
        elif isinstance(node, ast.Name):
            assert node.id not in _BANNED_SYMBOLS, f"banned symbol reference: {node.id}"
        elif isinstance(node, ast.Attribute):
            assert node.attr not in _BANNED_SYMBOLS, f"banned symbol reference: {node.attr}"
        elif isinstance(node, ast.Call):
            dynamic_import = (
                isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "importlib"
                and node.func.attr == "import_module"
            )
            if dynamic_import:
                # Fail closed: a computed (non-literal) import target cannot
                # be statically vetted, so reject it outright.
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    assert_module_allowed(node.args[0].value)
                else:
                    raise AssertionError(
                        "smoke tool uses a dynamic import whose target is not a static string"
                    )


def _payload_entries(paths: list[str]) -> list[FileEntry]:
    """Build deterministic scanner entries from ``path:label`` strings."""
    entries: list[FileEntry] = []
    for item in paths:
        path, label = item.split(":", 1)
        group, _, name = label.partition("/")
        entries.append(FileEntry(path, group, name, group != "binary", Path(path).suffix))
    return entries


def _patch_scanners(
    monkeypatch: pytest.MonkeyPatch, tool, suffix: list[str], magika: list[str]
) -> None:
    """Patch the declared detection-only scanner seams."""
    monkeypatch.setattr(tool, "scan_with_suffix", lambda path, settings: _payload_entries(suffix))
    monkeypatch.setattr(tool, "scan_with_magika", lambda path, settings: _payload_entries(magika))


def test_static_guard_rejects_forbidden_symbols_and_is_mutation_sensitive(tmp_path: Path) -> None:
    """Task 1.7: static inspection blocks forbidden imports and names."""
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    _assert_static_tool_safe(_SMOKE_TOOL)

    mutated = tmp_path / "mutated_smoke.py"
    mutated.write_text(
        _SMOKE_TOOL.read_text(encoding="utf-8")
        + "\nfrom omrg.core.codebase.codebase_map import build_codebase_map\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="banned symbol"):
        _assert_static_tool_safe(mutated)


def test_static_guard_rejects_dynamic_forbidden_import(tmp_path: Path) -> None:
    """Task 1.7: importlib cannot bypass the static no-ingestion boundary."""
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    mutated = tmp_path / "dynamic_smoke.py"
    mutated.write_text(
        _SMOKE_TOOL.read_text(encoding="utf-8")
        + "\nimport importlib\nimportlib.import_module('omrg.core.ingestion')\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="banned module"):
        _assert_static_tool_safe(mutated)


def test_static_guard_rejects_computed_dynamic_import(tmp_path: Path) -> None:
    """A dynamic import with a non-literal target fails closed.

    Guards that only inspect literal module arguments let a computed
    forbidden import pass static inspection, so any dynamic import whose
    target cannot be resolved statically must fail.
    """
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    mutated = tmp_path / "computed_import_smoke.py"
    mutated.write_text(
        _SMOKE_TOOL.read_text(encoding="utf-8")
        + "\nimport importlib\nname = 'omrg.core.ingestion'\n"
        "importlib.import_module(name)\n",
        encoding="utf-8",
    )
    with pytest.raises(AssertionError, match="not a static string"):
        _assert_static_tool_safe(mutated)


def test_duplicate_path_spellings_fail_before_scanning(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two spellings of one file must fail validation, not double-count.

    ``file.py`` and ``./file.py`` re-key to distinct direct-file keys, so
    the downstream path-set comparison cannot catch them; validation on
    resolved paths must reject the input before any scanner runs.
    """
    tool = _load_smoke_tool()
    monkeypatch.setattr(
        tool,
        "scan_with_suffix",
        lambda path, settings: pytest.fail("scanner must not run for invalid input"),
    )
    monkeypatch.setattr(
        tool,
        "scan_with_magika",
        lambda path, settings: pytest.fail("scanner must not run for invalid input"),
    )
    with pytest.raises(ValueError, match="overlap"):
        tool.run_comparison(["file.py", "./file.py"])


def test_file_inside_supplied_directory_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A file nested in a supplied directory must fail validation upfront."""
    tool = _load_smoke_tool()
    monkeypatch.setattr(
        tool,
        "scan_with_suffix",
        lambda path, settings: pytest.fail("scanner must not run for invalid input"),
    )
    monkeypatch.setattr(
        tool,
        "scan_with_magika",
        lambda path, settings: pytest.fail("scanner must not run for invalid input"),
    )
    inner = tmp_path / "inner.py"
    inner.write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="inside another supplied directory"):
        tool.run_comparison([str(tmp_path), str(inner)])


def _run_with_import_blocker(path: Path) -> subprocess.CompletedProcess[str]:
    """Import and call a smoke tool behind a meta-path import blocker."""
    program = textwrap.dedent(
        """
        import importlib.util
        import sys

        BANNED = ('omrg.core.ingestion', 'omrg.core.vectordb', 'omrg.compose', 'llama_index')

        class Blocker:
            def find_spec(self, fullname, path=None, target=None):
                if fullname.startswith(BANNED):
                    raise ImportError(f'blocked forbidden import: {fullname}')
                return None

        sys.meta_path.insert(0, Blocker())
        spec = importlib.util.spec_from_file_location('magika_label_smoke', sys.argv[1])
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            module.run_comparison([], object())
        except (SystemExit, ValueError):
            pass
        """
    )
    env = {**os.environ, "PYTHONPATH": str(_REPO_ROOT / "src")}
    return subprocess.run(
        [sys.executable, "-c", program, str(path)],
        cwd=_REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_isolated_import_blocker_allows_detection_only_tool_and_catches_mutation(
    tmp_path: Path,
) -> None:
    """Task 1.7: the process guard catches dynamic forbidden imports."""
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    clean = _run_with_import_blocker(_SMOKE_TOOL)
    assert clean.returncode == 0, clean.stderr

    mutated = tmp_path / "dynamic_forbidden_smoke.py"
    mutated.write_text(
        _SMOKE_TOOL.read_text(encoding="utf-8")
        + "\nimport importlib\nimportlib.import_module('omrg.core.ingestion')\n",
        encoding="utf-8",
    )
    blocked = _run_with_import_blocker(mutated)
    assert blocked.returncode != 0
    assert "blocked forbidden import" in blocked.stderr


def test_isolated_import_blocker_catches_transitive_forbidden_import(tmp_path: Path) -> None:
    """Task 1.7: imports cannot hide a prohibited dependency in a helper."""
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    helper = tmp_path / "transitive_helper.py"
    helper.write_text("import omrg.core.vectordb\n", encoding="utf-8")
    mutated = tmp_path / "transitive_smoke.py"
    mutated.write_text(
        _SMOKE_TOOL.read_text(encoding="utf-8")
        + f"\nimport sys\nsys.path.insert(0, {str(tmp_path)!r})\nimport transitive_helper\n",
        encoding="utf-8",
    )

    blocked = _run_with_import_blocker(mutated)
    assert blocked.returncode != 0
    assert "blocked forbidden import" in blocked.stderr


def test_smoke_comparison_reports_mixed_fixture_as_non_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 1.6: a changed Python label remains a visible stop-gate."""
    tool = _load_smoke_tool()
    _patch_scanners(
        monkeypatch,
        tool,
        ["note.md:document/markdown", "probe.txt:document/text"],
        ["note.md:document/markdown", "probe.txt:code/python"],
    )

    payload = tool.run_comparison([str(tmp_path)], object())

    files = {item["path"]: item for group in payload["groups"] for item in group["files"]}
    assert files["probe.txt"] == {
        "path": "probe.txt",
        "suffix_label": "document/text",
        "magika_label": "code/python",
        "would_change": True,
    }
    assert payload["total_files"] == 2
    assert payload["would_change_count"] == 1
    assert tool.main(["--json", str(tmp_path)]) != 0


def test_smoke_comparison_accepts_complete_non_empty_all_match_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 1.6: matching Markdown and TXT labels pass the smoke gate."""
    tool = _load_smoke_tool()
    entries = ["note.md:document/markdown", "plain.txt:document/text"]
    _patch_scanners(monkeypatch, tool, entries, entries)

    payload = tool.run_comparison([str(tmp_path)], object())

    assert payload["total_files"] == 2
    assert payload["would_change_count"] == 0
    assert tool.main(["--json", str(tmp_path)]) == 0


@pytest.mark.parametrize(
    ("suffix", "magika"),
    [
        (["note.md:document/markdown"], []),
        ([], ["note.md:document/markdown"]),
        (["note.md:document/markdown"], ["note.md:document/markdown"] * 2),
    ],
    ids=("missing", "extra", "duplicate"),
)
def test_smoke_comparison_rejects_incomplete_path_sets(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    suffix: list[str],
    magika: list[str],
) -> None:
    """Task 1.6: missing, extra, and duplicate paths fail closed."""
    tool = _load_smoke_tool()
    _patch_scanners(monkeypatch, tool, suffix, magika)

    with pytest.raises(ValueError, match="path"):
        tool.run_comparison([str(tmp_path)], object())


def test_smoke_comparison_matches_entries_by_path_not_scanner_order(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 1.6: reordered equal path sets remain a zero-change success."""
    tool = _load_smoke_tool()
    _patch_scanners(
        monkeypatch,
        tool,
        ["note.md:document/markdown", "plain.txt:document/text"],
        ["plain.txt:document/text", "note.md:document/markdown"],
    )

    payload = tool.run_comparison([str(tmp_path)], object())

    assert payload["would_change_count"] == 0
    assert tool.main(["--json", str(tmp_path)]) == 0


def test_smoke_comparison_supports_multiple_explicit_file_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 3.2: two explicit files must not collide on the "." key.

    Direct-file scans key their single entry "." (the ingestion
    direct-file key). The tool re-keys it to the operator-supplied path
    so one invocation over many explicit files stays distinct. The
    scanner doubles are path-aware: a real direct-file scan returns
    exactly one entry for the one file it was asked about.
    """
    tool = _load_smoke_tool()
    file_a = tmp_path / "note.md"
    file_b = tmp_path / "plain.txt"
    file_a.write_text("# note\n", encoding="utf-8")
    file_b.write_text("plain\n", encoding="utf-8")

    def fake_scan(path: str, settings: object) -> list[FileEntry]:
        if "note" in path:
            return [FileEntry(".", "document", "markdown", True, ".md")]
        return [FileEntry(".", "document", "text", True, ".txt")]

    monkeypatch.setattr(tool, "scan_with_suffix", fake_scan)
    monkeypatch.setattr(tool, "scan_with_magika", fake_scan)

    payload = tool.run_comparison([str(file_a), str(file_b)], object())

    paths = sorted(record["path"] for group in payload["groups"] for record in group["files"])
    assert paths == sorted([str(file_a), str(file_b)])
    assert payload["total_files"] == 2
    assert payload["would_change_count"] == 0


def test_smoke_comparison_rejects_empty_input_and_detector_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Task 1.6: no paths and unavailable detection never pass acceptance."""
    tool = _load_smoke_tool()
    _patch_scanners(monkeypatch, tool, [], [])
    with pytest.raises(ValueError, match="empty"):
        tool.run_comparison([], object())

    monkeypatch.setattr(
        tool, "scan_with_magika", lambda path, settings: (_ for _ in ()).throw(FileNotFoundError())
    )
    with pytest.raises(FileNotFoundError):
        tool.run_comparison([str(tmp_path)], object())
