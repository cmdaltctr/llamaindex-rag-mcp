"""Read-only source guards and atomic experiment checkpoints."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

EXP_DIR = Path(__file__).resolve().parent
OUTPUT = EXP_DIR / "output"


def sha256(path: Path) -> str:
    """Hash a file without loading model weights into memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_sha256(text: str) -> str:
    """Hash a page's normalised UTF-8 text."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    """Read a local JSON artefact."""
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, payload: Any) -> None:
    """Replace a checkpoint only after its complete JSON has been written."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def verify_freeze(source: Path) -> None:
    """Require the source experiment's read-only freeze check to pass."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(source / "freeze.py"), "--check"],
        cwd=source,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode or "freeze verified" not in result.stdout.splitlines():
        raise RuntimeError("source freeze check failed; no extraction or scoring allowed")
    print("freeze verified", flush=True)


def approved_plan() -> dict:
    """Require both recorded operator approvals before gated work."""
    plan = read_json(EXP_DIR / "plan.json")
    if len(plan["decision_register"]) != 2 or any(
        not item["status"].startswith("APPROVED") or not item["date"]
        for item in plan["decision_register"]
    ):
        raise RuntimeError("both operator approvals must be recorded before running")
    return plan


def load_token_rule(source: Path) -> Any:
    """Import the frozen Experiment 33 token functions without running its CLI."""
    spec = importlib.util.spec_from_file_location("exp33_frozen_labels", source / "build_labels.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("frozen token rule cannot be imported")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def resume_payload(path: Path, identity: Any, resume: bool) -> dict:
    """Refuse accidental overwrite or resume against changed inputs."""
    if not path.exists():
        return {"identity": identity, "completed_documents": [], "rows": []}
    if not resume:
        raise ValueError("checkpoint exists; use --resume")
    payload = read_json(path)
    if payload["identity"] != identity:
        raise ValueError("checkpoint identity changed; resume refused")
    return payload
