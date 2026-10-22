"""Experiment 33 Stage A: routing only on the shipped reader path (tasks 3.2-3.4).

Each natural document is read ONCE through the production local backend,
``core.ingestion.backends.local.read_documents``, with the packaged settings
and ``ocr_client=None``. That path builds the reader through
``build_pdf_reader``, so the ``OcrRoutedPdfInspector`` seam wraps
pdf-inspector and the reader fallback chain runs before the gate reads its
evidence (ADR-066, TDR-024). The harness only reads what the seam stamped;
it never replays or reimplements the gate.

Stage separation (task 3.4): this script never imports the OCR worker
package, never passes an OCR client, and aborts if any row reports
``ocr_used``. Stage B (real OCR) needs its own script after a separate
decision-register entry.

Outputs:
- ``output/runtime_manifest.json``: policy identity, versions, detection
  path. Secret-free (checked against ``compose.redaction_values()``).
- ``output/routing.json``: per-document rows plus the run identity,
  checkpointed atomically after every document (``--resume`` is implicit:
  completed documents are skipped when the run identity matches).
- ``output/.extractions/<doc_id>.txt``: fast-path text for the
  reader-quality measurement (gitignored).

    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/route.py \
        --arm sampled_baseline --code-root ../llamaindex-rag-mcp-exp33-arm-baseline
    uv run python .../route.py --smoke tests/fixtures/smoke_text.pdf --smoke-out /tmp/x
    uv run python .../route.py --probe    # exploratory boundary probe, output/probe/
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import subprocess
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
PLAN_PATH = EXP_DIR / "plan.json"
LABELS_PATH = EXP_DIR / "labels.json"
SOURCES_PATH = EXP_DIR / "sources.json"
NATURAL_DIR = EXP_DIR / "corpus" / "natural"

#: Repository whose ``src/`` is measured. ``--code-root`` points it at a
#: detached worktree for a pinned arm (plan.json ``arms``); ``omrg`` must
#: not be imported before ``main`` sets it.
CODE_ROOT = PROJECT_ROOT
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXP_DIR.parent))
sys.path.insert(0, str(EXP_DIR))

#: Sources whose content defines the measured policy (repo-relative).
POLICY_SOURCES = (
    "src/omrg/integrations/pdf/ocr_routing.py",
    "src/omrg/integrations/pdf/ocr_policy.py",
    "src/omrg/integrations/pdf/pdf_inspector.py",
    "src/omrg/integrations/pdf/factory.py",
    "src/omrg/core/ingestion/backends/local.py",
)

#: Preflight assertions that only a real (frozen) run can satisfy.
FREEZE_ONLY_FIELDS = {"freeze.verified", "labels.frozen"}

PACKAGES = ("pdf-inspector", "liteparse", "pypdf", "magika", "llama-index-core")


def _git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 - git is the intended binary
        ["git", *args],  # noqa: S607 - PATH resolution is intended
        capture_output=True,
        text=True,
        cwd=CODE_ROOT,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def _detection(directory: Path, effective) -> dict:
    """Record the content-type detection path the ingestion pipeline would take."""
    from omrg.core.codebase.codebase_map import detect_file_types
    from omrg.integrations.magika import _is_magika_available, _magika_binary, scan_with_magika

    path = "suffix"
    magika_version = None
    if _is_magika_available(effective):
        try:
            scan_with_magika(str(directory), effective)
            path = "magika"
        except Exception:  # noqa: BLE001 - mirrors the pipeline's degrade-to-suffix rule
            path = "suffix_fallback_after_magika_failure"
        probe = subprocess.run(  # noqa: S603 - pinned detector binary from settings
            [_magika_binary(effective), "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        magika_version = (probe.stdout or probe.stderr).strip() or None
    inventory = detect_file_types(str(directory), settings=effective)
    labels = {Path(e.path).name: f"{e.group}/{e.label}" for e in inventory.entries}
    return {"path": path, "magika_version": magika_version, "labels": labels}


def _runtime_manifest(
    effective, reader, detection: dict, freeze_ok: bool, arm: str | None = None
) -> dict:
    import omrg
    from omrg.integrations.pdf.ocr_policy import OCR_UNCONDITIONAL_TYPES

    labels = json.loads(LABELS_PATH.read_text(encoding="utf-8")) if LABELS_PATH.exists() else {}
    return {
        "experiment": EXP_DIR.name,
        "stage": "A",
        "settings": {
            "pdf_reader": effective.pdf_reader,
            "ocr_fallback_enabled": effective.ocr_fallback_enabled,
            "ocr_fallback_min_confidence": effective.ocr_fallback_min_confidence,
            "ocr_fallback_page_fraction": effective.ocr_fallback_page_fraction,
            "ocr_worker_command_set": bool(effective.ocr_worker_command),
        },
        "policy": {
            "unconditional_types": sorted(OCR_UNCONDITIONAL_TYPES),
            "seam_class": type(reader).__name__,
            "git_commit": _git("rev-parse", "HEAD"),
            "routing_code_clean": not _git("status", "--porcelain", "--", *POLICY_SOURCES),
            "source_sha256": {rel: _sha256(CODE_ROOT / rel) for rel in POLICY_SOURCES},
            "arm": arm,
            "omrg_loaded_from_code_root": Path(omrg.__file__)
            .resolve()
            .is_relative_to(CODE_ROOT.resolve() / "src"),
        },
        "packages": _versions(),
        "detection": {"path": detection["path"], "magika_version": detection["magika_version"]},
        "ocr": {"client_injected": False, "worker_started": False},
        "freeze": {"verified": freeze_ok},
        "labels": {"frozen": bool(labels.get("frozen"))},
        "secrets": {"recorded": False},
    }


def _assert_secret_free(payload: object) -> None:
    """Abort when any configured secret value appears in *payload*."""
    from omrg.compose import redaction_values

    serialised = json.dumps(payload)
    for value in redaction_values().values():
        if value and len(value) >= 8 and value in serialised:
            raise SystemExit("secret check failed: a configured secret appears in an artefact")


def _preflight(plan: dict, manifest: dict, *, smoke: bool) -> None:
    from _lib.preflight import PreflightError, evaluate_assertions

    assertions = plan["preflight_assertions"]
    if smoke:
        assertions = [a for a in assertions if a["manifest_field"] not in FREEZE_ONLY_FIELDS]
    failures = evaluate_assertions(manifest, assertions)
    arm = manifest["policy"]["arm"]
    if arm is not None:
        expected = plan["arms"][arm]["source_sha256"]
        for rel, digest in expected.items():
            if manifest["policy"]["source_sha256"].get(rel) != digest:
                failures.append(f"arm {arm}: {rel} differs from the pinned arm source")
    if failures:
        raise PreflightError("; ".join(failures))
    print(f"[preflight] {len(assertions)} assertions passed", flush=True)


def _read_one(path: Path, effective) -> tuple[dict, str]:
    from omrg.core.ingestion.backends.local import read_documents

    started = time.perf_counter()
    documents = asyncio.run(read_documents(path, settings=effective, ocr_client=None))
    elapsed = time.perf_counter() - started
    if not documents:
        raise RuntimeError("reader returned no documents")
    meta = documents[0].metadata
    if meta.get("ocr_used"):
        raise SystemExit("stage separation violated: a document reports ocr_used=True")
    text = "\n\n".join(doc.text for doc in documents if doc.text)
    row = {
        "pdf_type": meta.get("pdf_type"),
        "pdf_confidence": meta.get("pdf_confidence"),
        "page_count": meta.get("page_count"),
        "pages_needing_ocr": meta.get("pages_needing_ocr"),
        "pages_needing_ocr_before_fallback": meta.get("pages_needing_ocr_before_fallback"),
        "extraction_fallback_backend": meta.get("extraction_fallback_backend"),
        "ocr_required": meta.get("ocr_required"),
        "ocr_used": meta.get("ocr_used"),
        "ocr_backend": meta.get("ocr_backend"),
        "extracted_characters": len(text),
        "read_seconds": round(elapsed, 3),
    }
    if row["ocr_required"] is None:
        raise SystemExit("the OCR seam did not stamp ocr_required; the gate is not active")
    return row, text


def _save_atomic(path: Path, payload: object) -> None:
    _assert_secret_free(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _documents(smoke: list[str] | None, *, probe: bool = False) -> list[dict]:
    if probe:
        return json.loads((EXP_DIR / "probe.json").read_text(encoding="utf-8"))["documents"]
    if smoke:
        return [
            {"doc_id": f"smoke_{i:02d}", "stratum": "smoke", "local_path": str(Path(p).resolve())}
            for i, p in enumerate(smoke, start=1)
        ]
    sources = json.loads(SOURCES_PATH.read_text(encoding="utf-8"))
    return [d for d in sources["documents"] if d["stratum"] != "synthetic"]


def main() -> int:
    """Run Stage A routing and checkpoint after every document."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", nargs="+", help="harness check on these PDFs; no freeze")
    parser.add_argument("--smoke-out", type=Path, help="output directory for --smoke")
    parser.add_argument(
        "--probe", action="store_true", help="exploratory boundary probe (probe.json); no freeze"
    )
    parser.add_argument("--arm", help="measured arm from plan.json arms (natural runs)")
    parser.add_argument("--code-root", type=Path, help="checkout whose src/ is measured")
    args = parser.parse_args()
    smoke = bool(args.smoke) or args.probe
    if not smoke and (args.arm is None or args.code_root is None):
        parser.error("natural runs need --arm (plan.json arms) and --code-root")
    global CODE_ROOT
    if args.code_root is not None:
        if "omrg" in sys.modules:
            raise SystemExit("omrg was imported before --code-root took effect")
        CODE_ROOT = args.code_root.resolve()
        sys.path.insert(0, str(CODE_ROOT / "src"))
    if args.smoke and not args.smoke_out:
        parser.error("--smoke needs --smoke-out (smoke runs never write to output/)")
    out_dir = EXP_DIR / "output" / f"arm_{args.arm}"
    if args.smoke:
        out_dir = args.smoke_out
    elif args.probe:
        out_dir = EXP_DIR / "output" / "probe"

    from omrg.compose import settings_to_effective
    from omrg.config import Settings
    from omrg.integrations.pdf import build_pdf_reader

    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    effective = settings_to_effective(Settings())
    reader = build_pdf_reader(effective.pdf_reader, effective, ocr_client=None)

    freeze_ok = False
    if not smoke:
        import freeze

        drift = freeze.check()
        if drift:
            raise SystemExit("freeze check failed: " + "; ".join(drift))
        freeze_ok = True

    documents = _documents(args.smoke, probe=args.probe)
    detection_dir = NATURAL_DIR
    if args.smoke:
        detection_dir = Path(documents[0]["local_path"]).parent
    elif args.probe:
        detection_dir = EXP_DIR / "corpus" / "probe"
    detection = _detection(detection_dir, effective)
    manifest = _runtime_manifest(effective, reader, detection, freeze_ok, args.arm)
    _preflight(plan, manifest, smoke=smoke)
    _save_atomic(out_dir / "runtime_manifest.json", manifest)

    from _lib.checkpoint_validity import evaluate_resume, run_identity

    identity = None
    if not smoke:
        identity = run_identity(
            plan_path=PLAN_PATH,
            gt_path=LABELS_PATH,
            corpus_manifest_path=SOURCES_PATH,
            runtime_manifest=manifest,
            code_paths=[Path(__file__).resolve()],
        )
        identity["code"] = {Path(k).name: v for k, v in identity["code"].items()}

    routing_path = out_dir / "routing.json"
    state: dict = {"rows": [], "done": []}
    if routing_path.exists() and not smoke:
        saved = json.loads(routing_path.read_text(encoding="utf-8"))
        decision = evaluate_resume({"routing": saved}, identity)
        if decision["action"] == "refuse":
            raise SystemExit("unsafe resume refused: " + "; ".join(decision["reasons"]))
        state = saved
    state["run_identity"] = identity
    done = set(state["done"])

    for doc in documents:
        if doc["doc_id"] in done:
            continue
        path = Path(doc["local_path"])
        if not path.is_absolute():
            path = EXP_DIR / path
        row = {"doc_id": doc["doc_id"], "stratum": doc["stratum"]}
        row["content_type"] = detection["labels"].get(path.name)
        try:
            measured, text = _read_one(path, effective)
            row.update(measured)
            extraction = out_dir / ".extractions" / f"{doc['doc_id']}.txt"
            extraction.parent.mkdir(parents=True, exist_ok=True)
            extraction.write_text(text, encoding="utf-8")
            print(
                f"[route] {doc['doc_id']} ({doc['stratum']}) type={row['pdf_type']} "
                f"conf={row['pdf_confidence']} pages={row['page_count']} "
                f"flagged={row['pages_needing_ocr']} "
                f"fallback={row['extraction_fallback_backend']} "
                f"ocr_required={row['ocr_required']}",
                flush=True,
            )
        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001 - recorded as an outcome, never dropped
            row["error_class"] = type(exc).__name__
            print(f"[route] {doc['doc_id']} READ FAILURE: {type(exc).__name__}", flush=True)
        state["rows"].append(row)
        state["done"].append(doc["doc_id"])
        _save_atomic(routing_path, state)

    print(f"[route] complete: {len(state['rows'])} rows -> {routing_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
