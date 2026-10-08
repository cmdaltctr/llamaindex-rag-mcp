"""Synthetic tests for frozen-data guards and per-page rescue extraction."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))


@pytest.fixture
def extraction():
    return importlib.import_module("extract_rescue_text")


@pytest.fixture
def io():
    return importlib.import_module("experiment_io")


def test_freeze_requires_verified_message(io, tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: SimpleNamespace(returncode=0, stdout="", stderr="")
    )
    with pytest.raises(RuntimeError, match="freeze"):
        io.verify_freeze(tmp_path)


def test_freeze_rejects_nonzero_exit(io, tmp_path, monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=1, stdout="freeze verified", stderr="drift"),
    )
    with pytest.raises(RuntimeError, match="freeze"):
        io.verify_freeze(tmp_path)


def test_freeze_calls_check_read_only(io, tmp_path, monkeypatch):
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout="freeze verified\n", stderr="")

    monkeypatch.setattr(subprocess, "run", run)
    io.verify_freeze(tmp_path)
    assert calls[0][0][-2:] == [str(tmp_path / "freeze.py"), "--check"]
    assert calls[0][1]["cwd"] == tmp_path


def test_atomic_json_preserves_previous_checkpoint_on_failure(io, tmp_path, monkeypatch):
    target = tmp_path / "checkpoint.json"
    target.write_text('{"old": true}')
    monkeypatch.setattr(Path, "replace", lambda *a: (_ for _ in ()).throw(OSError("failed")))
    with pytest.raises(OSError):
        io.atomic_json(target, {"new": True})
    assert json.loads(target.read_text()) == {"old": True}


def test_atomic_json_writes_complete_payload(io, tmp_path):
    target = tmp_path / "nested" / "checkpoint.json"
    io.atomic_json(target, {"documents": ["test"]})
    assert json.loads(target.read_text()) == {"documents": ["test"]}
    assert not target.with_suffix(".json.tmp").exists()


def test_liteparse_maps_observed_pages_and_preserves_blanks(extraction):
    docs = [SimpleNamespace(text="<div>hola &amp; mundo</div>", metadata={"page": 2})]
    assert extraction.page_texts(docs, "liteparse", 3) == ["", "hola & mundo", ""]


def test_pypdf_uses_physical_order_not_custom_labels(extraction):
    docs = [
        SimpleNamespace(text="uno", metadata={"page_label": "i"}),
        SimpleNamespace(text="dos", metadata={"page_label": "9"}),
    ]
    assert extraction.page_texts(docs, "pypdf", 2) == ["uno", "dos"]


def test_pypdf_rejects_missing_pages(extraction):
    with pytest.raises(ValueError, match="page count"):
        extraction.page_texts([], "pypdf", 2)


@pytest.mark.parametrize("pages", [[0], [4], [1, 1]])
def test_liteparse_rejects_invalid_or_duplicate_pages(extraction, pages):
    docs = [SimpleNamespace(text="text", metadata={"page": p}) for p in pages]
    with pytest.raises(ValueError, match="page"):
        extraction.page_texts(docs, "liteparse", 3)


def test_resume_rejects_changed_identity(io, tmp_path):
    target = tmp_path / "checkpoint.json"
    io.atomic_json(target, {"identity": "old", "completed_documents": []})
    with pytest.raises(ValueError, match="identity"):
        io.resume_payload(target, "new", True)


def test_resume_requires_explicit_flag(io, tmp_path):
    target = tmp_path / "checkpoint.json"
    io.atomic_json(target, {"identity": "same", "completed_documents": []})
    with pytest.raises(ValueError, match="resume"):
        io.resume_payload(target, "same", False)
