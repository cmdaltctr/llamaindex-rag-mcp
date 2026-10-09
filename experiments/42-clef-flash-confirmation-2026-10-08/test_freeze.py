"""Task 3.8 check: the freeze detects one edited label in a temporary copy."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from exp42_io import EXP_DIR, load_module

# Loaded by path: Experiment 33 also has a freeze.py on sys.path.
freeze = load_module(EXP_DIR / "freeze.py", "exp42_freeze")


@pytest.fixture
def frozen_copy(tmp_path: Path) -> Path:
    if not (EXP_DIR / freeze.MANIFEST).exists():
        pytest.skip("freeze not written yet")
    for name in (*freeze.FILES, "plan.json", str(freeze.MANIFEST)):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(EXP_DIR / name, tmp_path / name)
    for folder in freeze.FOLDERS:
        shutil.copytree(EXP_DIR / folder, tmp_path / folder)
    return tmp_path


def test_unchanged_copy_verifies(frozen_copy: Path) -> None:
    assert freeze.check(frozen_copy) == []


def test_one_edited_label_fails(frozen_copy: Path) -> None:
    path = frozen_copy / "output" / "labels.json"
    labels = json.loads(path.read_text(encoding="utf-8"))
    row = labels["rows"][0]
    row["class"] = "junk" if row["class"] != "junk" else "healthy"
    path.write_text(json.dumps(labels), encoding="utf-8")
    assert freeze.check(frozen_copy) == ["output/labels.json"]
