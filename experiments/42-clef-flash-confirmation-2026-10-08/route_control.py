"""Task 4.1: control arm routes from the shipped gate (Experiment 33 route.py pattern).

Each document is read once through ``core.ingestion.backends.local.read_documents``
with packaged settings and ``ocr_client=None``. The script only reads what the
OCR seam stamped (``ocr_required``, ``extraction_fallback_backend``); it never
reimplements the gate. Writes ``output/control_routing.json`` with the pinned commit.

    uv run --no-sync python route_control.py
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from importlib.metadata import version

from exp42_io import EXP_DIR, OUTPUT, atomic_json, plan, read_json, sha256

TARGET = OUTPUT / "control_routing.json"
PACKAGES = ("pdf-inspector", "liteparse", "pypdf", "llama-index-core")


def git(*args: str) -> str:
    """Run git in this worktree."""
    return subprocess.run(  # noqa: S603
        ["/usr/bin/git", *args], capture_output=True, text=True, check=True, cwd=EXP_DIR
    ).stdout.strip()


def main() -> None:
    """Route every document; checkpoint after each."""
    plan()
    if git("status", "--porcelain", "--", "../../src"):
        raise SystemExit("src/ has uncommitted changes; the control commit would not be pinned")
    from omrg.compose import settings_to_effective
    from omrg.config import Settings
    from omrg.core.ingestion.backends.local import read_documents

    effective = settings_to_effective(Settings())
    identity = {
        "commit": git("rev-parse", "HEAD"),
        "src_tree": git("rev-parse", "HEAD:src"),
        "packages": {p: version(p) for p in PACKAGES},
        "pdf_reader": effective.pdf_reader,
        "sources_sha256": sha256(EXP_DIR / "sources.json"),
    }
    payload = read_json(TARGET) if TARGET.exists() else {"identity": identity, "rows": []}
    if payload["identity"]["src_tree"] != identity["src_tree"]:
        raise SystemExit("src/ tree changed since the control run started")
    payload["identity"] = identity
    done = {r["doc_id"] for r in payload["rows"]}
    for doc in read_json(EXP_DIR / "sources.json")["documents"]:
        if doc["doc_id"] in done:
            continue
        start = time.perf_counter()
        documents = asyncio.run(
            read_documents(EXP_DIR / doc["local_path"], settings=effective, ocr_client=None)
        )
        meta = documents[0].metadata if documents else {}
        if meta.get("ocr_used"):
            raise SystemExit("stage separation violated: ocr_used=True")
        if meta.get("ocr_required") is None:
            raise SystemExit("the OCR seam did not stamp ocr_required")
        payload["rows"].append(
            {
                "doc_id": doc["doc_id"],
                "page_count": doc["page_count"],
                "pdf_type": meta.get("pdf_type"),
                "pages_needing_ocr": meta.get("pages_needing_ocr"),
                "pages_needing_ocr_before_fallback": meta.get("pages_needing_ocr_before_fallback"),
                "extraction_fallback_backend": meta.get("extraction_fallback_backend"),
                "ocr_required": bool(meta.get("ocr_required")),
                "read_seconds": round(time.perf_counter() - start, 3),
            }
        )
        atomic_json(TARGET, payload)
        row = payload["rows"][-1]
        print(
            f"[control] {doc['doc_id']}: ocr_required={row['ocr_required']} "
            f"fallback={row['extraction_fallback_backend']}",
            flush=True,
        )


if __name__ == "__main__":
    main()
