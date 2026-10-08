"""Shared paths, hashing, atomic writes and source-experiment imports for Experiment 42."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
OUTPUT = EXP_DIR / "output"
EXPERIMENTS = EXP_DIR.parent
EXP33 = EXPERIMENTS / "33-ocr-routing-natural-positive-2026-09-17"
EXP38 = EXPERIMENTS / "38-rescue-quality-signal-2026-09-30"
#: Gitignored Experiment 38 files (page text, model file) live only in the v3 worktree.
V3_EXP38 = EXPERIMENTS.parent.parent / "llamaindex-rag-mcp-v3" / "experiments" / EXP38.name


def sha256(path: Path) -> str:
    """Hash a file in 1 MiB blocks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    """Hash UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    """Read a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: Any) -> None:
    """Write JSON through a .tmp file and a rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def plan() -> dict:
    """Read plan.json and require every operator decision to be approved."""
    current = read_json(EXP_DIR / "plan.json")
    if any(
        not r["status"].startswith("APPROVED") or not r["date"]
        for r in current["decision_register"]
    ):
        raise RuntimeError("every operator decision must be approved before running")
    return current


def load_module(path: Path, name: str) -> ModuleType:
    """Import a source-experiment module by path, with its folder on sys.path."""
    folder = str(path.parent)
    if folder not in sys.path:
        sys.path.insert(0, folder)
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
