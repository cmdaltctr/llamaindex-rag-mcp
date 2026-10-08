"""Task 3.8: freeze the corpus, references, rescue texts and labels.

    uv run --no-sync python freeze.py --write   # once, after labels pass task 3.7
    uv run --no-sync python freeze.py --check   # before every later step

``--check`` prints ``freeze verified`` or lists every drifted file and exits 1.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
MANIFEST = Path("output") / "frozen.manifest.json"
FILES = ("sources.json", "output/rescue_text.json", "output/labels.json")
FOLDERS = ("corpus", "output/.references", "output/.rescue_text")
PLAN_KEYS = ("thresholds", "decision_register", "gates", "classes", "document_labels")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def snapshot(root: Path) -> dict:
    """Hash every frozen file under *root* and the frozen plan sections."""
    files = {name: _sha256(root / name) for name in FILES}
    for folder in FOLDERS:
        for path in sorted((root / folder).rglob("*")):
            if path.is_file() and not path.name.endswith(".tmp"):
                files[str(path.relative_to(root))] = _sha256(path)
    plan = json.loads((root / "plan.json").read_text(encoding="utf-8"))
    sections = json.dumps({k: plan[k] for k in PLAN_KEYS}, sort_keys=True).encode()
    return {"files": files, "plan_sections_sha256": hashlib.sha256(sections).hexdigest()}


def check(root: Path = EXP_DIR) -> list[str]:
    """Return every difference between *root* and its manifest."""
    frozen = json.loads((root / MANIFEST).read_text(encoding="utf-8"))
    now = snapshot(root)
    drift = [
        name
        for name in sorted(set(frozen["files"]) | set(now["files"]))
        if frozen["files"].get(name) != now["files"].get(name)
    ]
    if frozen["plan_sections_sha256"] != now["plan_sections_sha256"]:
        drift.append("plan.json frozen sections")
    return drift


def main() -> int:
    """Write or check the manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=EXP_DIR)
    args = parser.parse_args()
    if args.write:
        if (args.root / MANIFEST).exists():
            print("manifest exists; the freeze is final", file=sys.stderr)
            return 1
        payload = snapshot(args.root)
        (args.root / MANIFEST).write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
        print(f"frozen {len(payload['files'])} files", flush=True)
        return 0
    drift = check(args.root)
    if drift:
        print("freeze check FAILED:\n" + "\n".join(drift[:50]), flush=True)
        return 1
    print("freeze verified", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
