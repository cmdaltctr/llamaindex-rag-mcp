"""The pipeline and library guide examples work (tasks 2.5 and 4.6).

JSON examples validate against the real Engine operation catalogue, the
one ``Engine.validate_pipeline`` uses. Python examples run in order on an
Engine over in-memory fakes, with the web and notebook packages blocked.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from tests.unit.test_engine_pipelines_support import FakeStore, build_engine, chunks
from tests.unit.test_pipeline_support import fixture_host

from omrg.compose_pipelines import build_operation_catalogue
from omrg.core.pipelines import (
    ALLOWED_LEVERS,
    IssueCode,
    PipelineValidationError,
    parse_definition,
    preflight,
)

_DOCS = Path(__file__).resolve().parents[2] / "docs" / "guides"
GUIDE = _DOCS / "pipelines.md"
LIBRARY_GUIDE = _DOCS / "library-usage.md"
_EXAMPLE = re.compile(r"<!-- pipeline-example: (\S+)(?: (\S+))? -->\s*```json\n(.*?)```", re.DOTALL)
_PYTHON = re.compile(r"<!-- pipeline-python: (\S+) -->\s*```python\n(.*?)```", re.DOTALL)

#: Top-level packages of the optional web extra and the notebook plugin.
BLOCKED = ("fastapi", "starlette", "uvicorn", "marimo")

#: Catalogue ids the guide must name (the real Engine catalogue).
_OPERATION_IDS = sorted(d.operation_id for d in build_operation_catalogue().descriptors())


def _examples() -> list[tuple[str, str | None, str]]:
    return [m.groups() for m in _EXAMPLE.finditer(GUIDE.read_text(encoding="utf-8"))]


def _params() -> list[object]:
    return [
        pytest.param(kind, code, body, id=f"{index}-{kind}-{code or 'ok'}")
        for index, (kind, code, body) in enumerate(_examples())
    ]


def _python_examples(path: Path) -> list[tuple[str, str]]:
    return [m.groups() for m in _PYTHON.finditer(path.read_text(encoding="utf-8"))]


def test_guide_has_valid_and_invalid_examples() -> None:
    """The guide shows both passing and failing graphs."""
    kinds = [kind for kind, _, _ in _examples()]
    assert kinds.count("valid") >= 2
    assert kinds.count("invalid") >= 3


@pytest.mark.parametrize(("kind", "code", "body"), _params())
def test_guide_example(kind: str, code: str | None, body: str) -> None:
    """Valid examples pass; invalid examples fail with the documented code."""
    data = json.loads(body)
    try:
        definition = parse_definition(data)
    except PipelineValidationError as exc:
        assert kind == "invalid" and code in exc.codes
        return
    report = preflight(definition, build_operation_catalogue(), host=fixture_host())
    if kind == "valid":
        assert report.issues == ()
    else:
        assert code in {issue.code for issue in report.issues}


def test_guide_lists_every_issue_code() -> None:
    """Every issue code has a row in the validation error table."""
    text = GUIDE.read_text(encoding="utf-8")
    codes = [v for k, v in vars(IssueCode).items() if k.isupper()]
    missing = [code for code in codes if f"`{code}`" not in text]
    assert missing == []


def test_guide_lists_every_allowed_lever() -> None:
    """The lever table matches the allowed lever set."""
    text = GUIDE.read_text(encoding="utf-8")
    assert [lever for lever in ALLOWED_LEVERS if f"`{lever}`" not in text] == []


def test_guide_names_every_catalogue_operation_and_no_provisional_ids() -> None:
    """The operation table lists the real catalogue; no provisional id remains."""
    text = GUIDE.read_text(encoding="utf-8")
    assert [op for op in _OPERATION_IDS if f"`{op}`" not in text] == []
    assert "provisional" not in text.lower()
    named = set(re.findall(r'"operation": "([\w.]+)"', text))
    assert named <= set(_OPERATION_IDS)


# ── Python examples ───────────────────────────────────────────────────


class _BlockWebAndNotebook:
    """Meta-path finder that refuses the web and notebook packages."""

    def find_spec(self, name: str, path: Any = None, target: Any = None) -> None:
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"{name} is blocked: guide examples must not need it")


@pytest.fixture
def no_web_or_notebook(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every import of the web and notebook packages fail."""
    for name in list(sys.modules):
        if name.split(".")[0] in BLOCKED:
            monkeypatch.delitem(sys.modules, name)
    monkeypatch.setattr(sys, "meta_path", [_BlockWebAndNotebook(), *sys.meta_path])


def test_blocker_refuses_web_imports(no_web_or_notebook: None) -> None:
    """The fixture makes a web import fail, so the example test is honest."""
    with pytest.raises(ImportError, match="blocked"):
        __import__("fastapi")


def test_guides_have_execution_and_cancellation_examples() -> None:
    """Both guides show validation, execution, events and cancellation."""
    names = [name for name, _ in _python_examples(GUIDE)]
    assert {"validate", "run", "cancel", "edit"} <= set(names)
    library = "".join(code for _, code in _python_examples(LIBRARY_GUIDE))
    for call in ("validate_pipeline", "run_pipeline", "RunCancellation", "on_event"):
        assert call in library


@pytest.mark.parametrize("guide", [GUIDE, LIBRARY_GUIDE], ids=lambda p: p.name)
def test_python_examples_run_without_web_or_notebook(
    guide: Path, no_web_or_notebook: None, effective_settings: Any, capsys: Any
) -> None:
    """Each guide's Python examples run, in order, on an Engine over fakes."""
    namespace: dict[str, Any] = {
        "engine": build_engine(effective_settings(), FakeStore(chunks())),
        "__name__": "guide_example",
    }
    examples = _python_examples(guide)
    assert examples
    for name, code in examples:
        exec(compile(code, f"{guide.name}:{name}", "exec"), namespace)  # noqa: S102
    printed = capsys.readouterr().out
    assert "cancelled" in printed and "succeeded" in printed
    assert not [m for m in sys.modules if m.split(".")[0] in BLOCKED]


def test_example_modules_import_without_web_or_notebook() -> None:
    """A fresh interpreter imports the example modules and no web package."""
    script = (
        "import sys\n"
        "import omrg.compose_pipelines, omrg.core.pipelines, omrg.engine, omrg.pipeline_templates\n"
        f"print(sorted(m for m in sys.modules if m.split('.')[0] in {BLOCKED!r}))\n"
    )
    root = Path(__file__).resolve().parents[2]
    done = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        check=True,
        cwd=root,
        env={"PYTHONPATH": str(root / "src"), "PDF_READER": "pypdf"},
    )
    assert done.stdout.strip() == "[]"
