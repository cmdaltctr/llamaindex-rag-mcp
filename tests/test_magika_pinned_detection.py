"""Base-install Magika detection and the detection-only smoke guard.

pin-magika-detection: the base dependency set pins ``magika`` so
a standard ``uv sync`` + ``uv run`` environment classifies files by
content, not by filename. These tests assert the installed-detector
path with no skip-if-absent guards — after this change the package is a
base dependency and is always present. Degradation coverage (binary
genuinely unavailable) stays with the fallback tests that patch
``omrg.integrations.magika._is_magika_available`` to ``False``.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

from omrg.core.codebase.codebase_map import detect_file_types
from omrg.integrations.magika import _is_magika_available

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SMOKE_TOOL = _REPO_ROOT / "scripts" / "magika_label_smoke.py"

# Python source behind a ``.txt`` extension: the suffix map can only
# produce ``document/text`` for it, so a ``code/python`` label proves
# the Magika model made the classification.
_PYTHON_SOURCE = (
    '"""Probe module for content-based detection."""\n'
    "\n"
    "\n"
    "def add(left: int, right: int) -> int:\n"
    '    """Return the sum."""\n'
    "    return left + right\n"
    "\n"
    "\n"
    "class Probe:\n"
    '    label = "python-source"\n'
    "\n"
    "    def render(self) -> str:\n"
    '        return f"{self.label}: {add(2, 3)}"\n'
)


def test_base_install_detects_by_content(tmp_path: Path) -> None:
    """The venv MUST carry the Magika CLI and classify by content.

    Availability is asserted first — the pin's whole point is that no
    operator action is needed — then a Python source file named
    ``.txt`` must classify as ``code/python``, a label the suffix map
    cannot produce for that extension.
    """
    assert _is_magika_available(), (
        "Magika CLI not on PATH: magika is a base dependency, so `uv sync` must provide it"
    )
    probe = tmp_path / "probe.txt"
    probe.write_text(_PYTHON_SOURCE, encoding="utf-8")

    inventory = detect_file_types(str(probe))

    assert len(inventory.entries) == 1
    entry = inventory.entries[0]
    assert f"{entry.group}/{entry.label}" == "code/python", (
        f"probe classified as {entry.group}/{entry.label}; expected the "
        "Magika model's code/python, not a suffix-map label"
    )


def test_smoke_tool_imports_no_ingestion_store_or_embedding() -> None:
    """Static guard: the smoke tool is detection-only by construction.

    The no-re-ingest constraint is mechanical, not aspirational. Parse
    the tool's AST and reject any import rooted at the ingestion
    pipeline, the vector stores, the composition root, llama_index, or
    any module whose dotted name mentions ingest/embed — so
    ``ingest_path_async`` can never be reached.
    """
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    tree = ast.parse(_SMOKE_TOOL.read_text(encoding="utf-8"))

    banned_roots = ("omrg.core.ingestion", "omrg.core.vectordb", "omrg.compose", "llama_index")
    banned_symbols = {"build_codebase_map", "Engine"}
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)

    assert imported, "expected at least the detection imports in the smoke tool"
    for module in imported:
        assert not module.startswith(banned_roots), f"smoke tool imports banned module {module!r}"
        assert "ingest" not in module and "embed" not in module, (
            f"smoke tool imports banned module {module!r}"
        )
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            assert node.id not in banned_symbols, f"smoke tool references banned symbol {node.id!r}"
        elif isinstance(node, ast.Attribute):
            assert node.attr not in banned_symbols, (
                f"smoke tool references banned symbol {node.attr!r}"
            )
        elif isinstance(node, ast.Call):
            is_dynamic_import = (
                isinstance(node.func, ast.Name)
                and node.func.id == "__import__"
                or isinstance(node.func, ast.Attribute)
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "importlib"
                and node.func.attr == "import_module"
            )
            if is_dynamic_import and node.args and isinstance(node.args[0], ast.Constant):
                module = node.args[0].value
                if isinstance(module, str):
                    assert not module.startswith(banned_roots), (
                        f"smoke tool dynamically imports banned module {module!r}"
                    )


def test_smoke_tool_reports_changed_label_for_mixed_fixture_paths(tmp_path: Path) -> None:
    """A mixed fixture reports its changed label and fails the smoke gate.

    ``note.md`` is a common type: suffix map and Magika model must agree
    (a disagreement here is the taxonomy stop-gate firing).
    ``probe.txt`` carries Python source behind a ``.txt`` name: a
    designed mismatch whose would-change flag must be reported so
    index-identity shifts are visible before any re-ingest.
    """
    assert _SMOKE_TOOL.exists(), f"smoke tool missing: {_SMOKE_TOOL}"
    (tmp_path / "note.md").write_text(
        "# Note\n\nplain markdown probe with enough words to classify\n",
        encoding="utf-8",
    )
    (tmp_path / "probe.txt").write_text(_PYTHON_SOURCE, encoding="utf-8")

    proc = subprocess.run(
        [sys.executable, str(_SMOKE_TOOL), "--json", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=_REPO_ROOT,
    )
    assert proc.returncode != 0, "a changed label must fail the smoke gate"

    payload = json.loads(proc.stdout)
    files = {f["path"]: f for g in payload["groups"] for f in g["files"]}

    note = files["note.md"]
    assert note["suffix_label"] == "document/markdown"
    assert note["magika_label"] == "document/markdown", (
        "common-type disagreement: Magika labels markdown differently "
        "from the suffix map — taxonomy stop-gate"
    )
    assert note["would_change"] is False

    probe = files["probe.txt"]
    assert probe["suffix_label"] == "document/text"
    assert probe["magika_label"] == "code/python"
    assert probe["would_change"] is True

    assert payload["total_files"] == 2
    assert payload["would_change_count"] == 1
