"""Tests for the shared OCR worker core (change modular-ocr-workers-dots-mocr).

Covers tasks 1.2, 1.3 and 1.6: the engine contract, entry-point loading
(zero, one and two registered engines), the capability command with
``backend_id``, the framing seam, page checks, and the model cache
location. The OMRG main environment has neither Paddle nor PyTorch, so
every test here is also the "Paddle-free, PyTorch-free" proof for the
core.

Engines are registered by writing a ``.dist-info`` folder with an
``entry_points.txt`` onto ``sys.path`` (or ``PYTHONPATH`` for a
subprocess). Nothing is installed.
"""

from __future__ import annotations

import importlib
import importlib.util
import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.isolation import isolated_worker_modules

from omrg.integrations.ocr_worker import protocol as omrg_protocol
from omrg.integrations.ocr_worker.fingerprint import fingerprint_from_output

REPO_ROOT = Path(__file__).resolve().parent.parent
CORE_SRC = REPO_ROOT / "ocr-workers" / "core" / "src"
PADDLE_SRC = REPO_ROOT / "ocr-workers" / "engines" / "paddleocr-vl" / "src"
STUB_SRC = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_engine"
STUB_TARGET = "omrg_ocr_stub_engine:ENGINE"
SECOND_TARGET = "omrg_ocr_stub_engine:SECOND_ENGINE"


def register_engines(root: Path, engines: dict[str, str]) -> Path:
    """Write one fake distribution per engine entry point under *root*."""
    root.mkdir(parents=True, exist_ok=True)
    for index, (name, target) in enumerate(engines.items()):
        dist = root / f"omrg_test_engine_{index}-0.0.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: omrg-test-engine-{index}\nVersion: 0.0\n",
            encoding="utf-8",
        )
        (dist / "entry_points.txt").write_text(
            f"[omrg.ocr_engine]\n{name} = {target}\n", encoding="utf-8"
        )
    return root


@pytest.fixture
def core(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Import the worker core and the stub engine from source."""
    monkeypatch.syspath_prepend(str(STUB_SRC))
    monkeypatch.syspath_prepend(str(CORE_SRC))
    with isolated_worker_modules():
        yield importlib.import_module("omrg_ocr_worker_core")


@pytest.fixture
def one_page_pdf(tmp_path: Path) -> Path:
    """A real one-page PDF."""
    from pypdf import PdfWriter

    pdf = tmp_path / "one.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.write(pdf)
    return pdf


@pytest.fixture
def three_page_pdf(tmp_path: Path) -> Path:
    """A real three-page PDF."""
    from pypdf import PdfWriter

    pdf = tmp_path / "three.pdf"
    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=200, height=200)
    writer.write(pdf)
    return pdf


# ── Entry-point loading (task 1.3) ─────────────────────────────────────────


def test_zero_engines_is_unavailable(core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """An environment with no registered engine cannot load one."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    monkeypatch.syspath_prepend(str(register_engines(tmp_path / "none", {})))
    with pytest.raises(engine_mod.EngineLoadError, match="found 0"):
        engine_mod.load_engine()


def test_one_engine_loads(core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Exactly one registered engine loads and passes the contract check."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    monkeypatch.syspath_prepend(str(register_engines(tmp_path / "one", {"stub": STUB_TARGET})))
    engine = engine_mod.load_engine()
    assert engine.name == "stub"
    assert isinstance(engine, engine_mod.OcrEngine)


def test_two_engines_is_unavailable(
    core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two registered engines make the environment unavailable, naming both."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    root = register_engines(tmp_path / "two", {"stub": STUB_TARGET, "stub-two": SECOND_TARGET})
    monkeypatch.syspath_prepend(str(root))
    with pytest.raises(engine_mod.EngineLoadError, match="found 2 \\(stub, stub-two\\)"):
        engine_mod.load_engine()


def test_object_breaking_the_contract_is_unavailable(
    core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An entry point naming a non-engine object is rejected."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    root = register_engines(tmp_path / "bad", {"bad": "omrg_ocr_stub_engine:NOT_AN_ENGINE"})
    monkeypatch.syspath_prepend(str(root))
    with pytest.raises(engine_mod.EngineLoadError, match="'name'"):
        engine_mod.load_engine()


def test_unimportable_engine_is_unavailable(
    core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An entry point whose module cannot import is rejected, not raised raw."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    root = register_engines(tmp_path / "missing", {"ghost": "omrg_no_such_module:ENGINE"})
    monkeypatch.syspath_prepend(str(root))
    with pytest.raises(engine_mod.EngineLoadError, match="cannot load engine 'ghost'"):
        engine_mod.load_engine()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("declared_packages", ["not", "a", "tuple"]),
        ("pipeline", ("only-one",)),
        ("model", ("", "1")),
        ("parse", None),
    ],
)
def test_contract_fields_are_checked(core: Any, field: str, value: Any) -> None:
    """Each static field and ``parse`` is validated."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    stub = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    setattr(stub, field, value)
    with pytest.raises(engine_mod.EngineLoadError):
        engine_mod.validate_engine(stub)


def _core_env(extra: Path) -> dict[str, str]:
    """Environment for a core subprocess with *extra* on the path."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(extra), str(STUB_SRC), str(CORE_SRC), str(PADDLE_SRC)])
    return env


@pytest.mark.parametrize(
    ("engines", "available"),
    [
        ({}, False),
        ({"stub": STUB_TARGET}, True),
        ({"stub": STUB_TARGET, "stub-two": SECOND_TARGET}, False),
    ],
)
def test_capability_probe_matches_the_two_engines_scenario(
    tmp_path: Path, engines: dict[str, str], available: bool
) -> None:
    """Spec: "An environment with two engines is unavailable".

    The real ``python -m omrg_ocr_worker_core --capabilities`` prints a
    fingerprint only for exactly one engine. With zero or two it prints
    nothing on stdout and exits non-zero, which the host maps to the
    stable unavailable fingerprint.
    """
    root = register_engines(tmp_path / "dists", engines)
    completed = subprocess.run(
        [sys.executable, "-m", "omrg_ocr_worker_core", "--capabilities"],
        env=_core_env(root),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if available:
        assert completed.returncode == 0
        fingerprint = fingerprint_from_output(completed.stdout)
        assert fingerprint is not None and fingerprint.available
        assert fingerprint.backend_id == "stub_engine"
        assert fingerprint.pipeline_identity == "stub-pipeline"
    else:
        assert completed.returncode != 0
        assert completed.stdout == ""
        assert "unavailable" in completed.stderr


def test_parse_loop_refuses_requests_without_one_engine(tmp_path: Path) -> None:
    """With two engines the loop reads no request and writes nothing."""
    root = register_engines(tmp_path / "dists", {"stub": STUB_TARGET, "stub-two": SECOND_TARGET})
    completed = subprocess.run(
        [sys.executable, "-m", "omrg_ocr_worker_core"],
        env=_core_env(root),
        input='{"id":"r","protocol_version":"1.0","type":"parse","pdf_path":"x"}\n',
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert completed.returncode == 3
    assert completed.stdout == ""
    assert "refusing parse requests" in completed.stderr


def test_capability_payload_carries_backend_id_and_versions(core: Any) -> None:
    """The payload names the engine's backend id and package versions."""
    capabilities = importlib.import_module("omrg_ocr_worker_core.capabilities")
    stub = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    stub.declared_packages = ("pypdf", "omrg-no-such-distribution")
    payload = capabilities.fingerprint_payload(stub)
    assert payload["backend_id"] == "stub_engine"
    assert payload["protocol_version"] == "1.1"
    assert payload["packages"]["omrg-no-such-distribution"] == "not-installed"
    assert payload["packages"]["pypdf"] != "not-installed"
    assert payload["pipeline"] == {"identity": "stub-pipeline", "revision": "1"}


# ── The framing seam (task 1.2) ────────────────────────────────────────────


def _run_loop(framing: Any, engine: Any, request: Any, monkeypatch: pytest.MonkeyPatch) -> Any:
    """Serve one request in process and decode the single response line."""
    monkeypatch.setattr(sys, "stdin", io.StringIO(omrg_protocol.encode_line(request) + "\n"))
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stdout)
    assert framing.serve(engine) == 0
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    return omrg_protocol.decode_response_line(lines[0], expected_id=request.id)


def test_whole_document_request_joins_pages(
    core: Any, monkeypatch: pytest.MonkeyPatch, one_page_pdf: Path
) -> None:
    """A whole-document request returns the joined pages, no page list."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    decoded = _run_loop(
        framing, engine, omrg_protocol.make_request("w1", str(one_page_pdf)), monkeypatch
    )
    assert isinstance(decoded, omrg_protocol.ParseSuccess)
    assert decoded.markdown == "# Stub page 1"
    assert decoded.pages_markdown is None
    assert decoded.metadata["ocr_backend"] == "stub"
    assert decoded.metadata["pipeline"] == "stub-pipeline"


def test_page_listed_request_answers_per_page_and_keeps_empty_pages(
    core: Any, monkeypatch: pytest.MonkeyPatch, three_page_pdf: Path
) -> None:
    """An engine's ``""`` for an unreadable page passes through untouched."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    monkeypatch.setattr(engine, "parse", lambda pdf, pages: ["# three", ""])
    request = omrg_protocol.make_request("p1", str(three_page_pdf), pages=[1, 3])
    decoded = _run_loop(framing, engine, request, monkeypatch)
    assert isinstance(decoded, omrg_protocol.ParseSuccess)
    assert decoded.pages_markdown == ("# three", "")
    assert decoded.markdown == "# three"
    assert decoded.metadata["page_count"] == 2


def test_out_of_range_page_is_rejected_before_the_engine(
    core: Any, monkeypatch: pytest.MonkeyPatch, one_page_pdf: Path
) -> None:
    """The core checks pages; the engine never sees an invalid page."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()

    def must_not_run(pdf: Path, pages: Any) -> list[str]:
        raise AssertionError("engine called for an invalid page")

    monkeypatch.setattr(engine, "parse", must_not_run)
    request = omrg_protocol.make_request("bad-page", str(one_page_pdf), pages=[2])
    decoded = _run_loop(framing, engine, request, monkeypatch)
    assert isinstance(decoded, omrg_protocol.ParseFailure)
    assert decoded.error.code == "invalid_page"


@pytest.mark.parametrize(
    ("returned", "code"),
    [(["# only one"], "page_selection_mismatch"), ("not a list", "engine_contract")],
)
def test_engine_answer_shape_is_checked(
    core: Any,
    monkeypatch: pytest.MonkeyPatch,
    three_page_pdf: Path,
    returned: Any,
    code: str,
) -> None:
    """A wrong page count or a non-list answer is a structured failure."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    monkeypatch.setattr(engine, "parse", lambda pdf, pages: returned)
    request = omrg_protocol.make_request("shape", str(three_page_pdf), pages=[1, 2])
    decoded = _run_loop(framing, engine, request, monkeypatch)
    assert isinstance(decoded, omrg_protocol.ParseFailure)
    assert decoded.error.code == code


def test_empty_whole_document_is_a_failure(
    core: Any, monkeypatch: pytest.MonkeyPatch, one_page_pdf: Path
) -> None:
    """A whole-document request with no text on any page is ``empty_markdown``."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    monkeypatch.setattr(engine, "parse", lambda pdf, pages: ["  "])
    decoded = _run_loop(
        framing, engine, omrg_protocol.make_request("empty", str(one_page_pdf)), monkeypatch
    )
    assert isinstance(decoded, omrg_protocol.ParseFailure)
    assert decoded.error.code == "empty_markdown"


def test_parse_document_hook_takes_precedence(
    core: Any, monkeypatch: pytest.MonkeyPatch, three_page_pdf: Path
) -> None:
    """An engine that assembles the request itself keeps its own Markdown."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    engine.parse_document = lambda pdf, pages: engine_mod.DocumentMarkdown(  # type: ignore[attr-defined]
        markdown="# merged table", pages_markdown=("# a", "# b"), page_count=2
    )
    request = omrg_protocol.make_request("hook", str(three_page_pdf), pages=[1, 2])
    decoded = _run_loop(framing, engine, request, monkeypatch)
    assert decoded.markdown == "# merged table"
    assert decoded.pages_markdown == ("# a", "# b")


def test_parse_document_hook_answer_is_checked(
    core: Any, monkeypatch: pytest.MonkeyPatch, three_page_pdf: Path
) -> None:
    """A hook returning the wrong type or a non-parallel page list fails."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    engine.parse_document = lambda pdf, pages: "wrong"  # type: ignore[attr-defined]
    request = omrg_protocol.make_request("hook-bad", str(three_page_pdf), pages=[1, 2])
    assert _run_loop(framing, engine, request, monkeypatch).error.code == "engine_contract"
    engine.parse_document = lambda pdf, pages: engine_mod.DocumentMarkdown(  # type: ignore[attr-defined]
        markdown="# x", pages_markdown=("# a",), page_count=1
    )
    request = omrg_protocol.make_request("hook-short", str(three_page_pdf), pages=[1, 2])
    assert _run_loop(framing, engine, request, monkeypatch).error.code == "page_selection_mismatch"


def test_unreadable_pdf_is_structured(
    core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A page-listed request on a file that is not a PDF fails cleanly."""
    framing = importlib.import_module("omrg_ocr_worker_core.framing")
    engine = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"not a pdf")
    request = omrg_protocol.make_request("broken", str(broken), pages=[1])
    decoded = _run_loop(framing, engine, request, monkeypatch)
    assert decoded.error.code == "invalid_pdf"


def test_page_subset_holds_exactly_the_pages_and_is_removed(
    core: Any, three_page_pdf: Path, tmp_path: Path
) -> None:
    """The shared subset writer yields the listed pages and cleans up."""
    from pypdf import PdfReader

    pages = importlib.import_module("omrg_ocr_worker_core.pages")
    with pages.page_subset(three_page_pdf, [1, 3], directory=tmp_path) as subset:
        assert subset != three_page_pdf
        assert len(PdfReader(str(subset)).pages) == 2
        assert subset.name.startswith(pages.SUBSET_PREFIX)
    assert not subset.exists()
    with pages.page_subset(three_page_pdf, None) as same:
        assert same == three_page_pdf
    with pytest.raises(pages.WorkerParseError, match="outside 1..3"):
        pages.write_page_subset(three_page_pdf, [4], directory=tmp_path)


# ── Model cache location (task 1.6) ────────────────────────────────────────


def test_model_cache_uses_the_variable_per_engine(
    core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With OMRG_OCR_MODEL_CACHE set, engine x uses $OMRG_OCR_MODEL_CACHE/x/."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    monkeypatch.setenv("OMRG_OCR_MODEL_CACHE", str(tmp_path / "weights"))
    assert engine_mod.model_cache_dir("x", tmp_path / "engines" / "x") == tmp_path / "weights" / "x"


@pytest.mark.parametrize("value", [None, "", "   "])
def test_model_cache_defaults_to_the_engine_folder(
    core: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str | None
) -> None:
    """Unset or blank, the engine folder's .model-cache/ is used."""
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    if value is None:
        monkeypatch.delenv("OMRG_OCR_MODEL_CACHE", raising=False)
    else:
        monkeypatch.setenv("OMRG_OCR_MODEL_CACHE", value)
    folder = tmp_path / "engines" / "x"
    assert engine_mod.model_cache_dir("x", folder) == folder / ".model-cache"


# ── Isolation of the core package ──────────────────────────────────────────


def test_core_manifest_declares_no_model_runtime() -> None:
    """The core depends on pypdf only: no Paddle, no PyTorch."""
    import tomllib

    manifest = tomllib.loads(
        (REPO_ROOT / "ocr-workers" / "core" / "pyproject.toml").read_text(encoding="utf-8")
    )
    assert manifest["project"]["dependencies"] == ["pypdf"]
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (CORE_SRC / "omrg_ocr_worker_core").glob("*.py")
    )
    for forbidden in ("import torch", "import paddle", "from paddle", "transformers"):
        assert forbidden not in source


def test_core_capabilities_stdout_is_one_json_line(tmp_path: Path) -> None:
    """The capability command writes exactly one JSON object on stdout."""
    root = register_engines(tmp_path / "dists", {"stub": STUB_TARGET})
    completed = subprocess.run(
        [sys.executable, "-m", "omrg_ocr_worker_core", "--capabilities"],
        env=_core_env(root),
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(lines) == 1
    assert json.loads(lines[0])["backend_id"] == "stub_engine"
    assert importlib.util.find_spec("torch") is None


def test_readme_checklist_matches_the_stub_engine(core: Any) -> None:
    """Task 1.7: the add-an-engine checklist names every contract piece the stub has."""
    readme = (REPO_ROOT / "ocr-workers" / "README.md").read_text(encoding="utf-8")
    checklist = readme.split("## Add an engine", 1)[1]
    stub = importlib.import_module("omrg_ocr_stub_engine").StubEngine()
    engine_mod = importlib.import_module("omrg_ocr_worker_core.engine")
    engine_mod.validate_engine(stub)
    for field in ("name", "backend_id", "declared_packages", "pipeline", "model", "parse"):
        assert f"`{field}" in checklist, field
        assert hasattr(stub, field), field
    for piece in (
        "pyproject.toml",
        "uv.lock",
        ".gitignore",
        "omrg.ocr_engine",
        "omrg-ocr-worker-core",
        "requires-acceptance",
        "omrg-ocr-fetch",
        "ENGINE",
    ):
        assert piece in checklist, piece
    assert "Wave status" not in readme
