"""Experiment 29 classifier: preregistered repeat of the routing study.

Repairs over experiment 28's runner (change ``repeat-pdf-routing-study``,
tasks 1.1-1.2):

- The collection is an *approved list*, not a directory scan. Discovery
  reads ``output/.collection.private.json`` (built by
  ``prepare_collection.py`` from operator-approved paths) and nothing
  else. Every document's sha256 is verified before it is classified, so
  an added, removed or replaced document is detected, not silently
  absorbed.
- The checkpoint carries a ``run_identity`` block binding the frozen
  plan, the frozen labels, the public collection manifest, the policy
  spec and the routing source code. A resume under a changed plan,
  collection, label set or policy is refused with the differing fields
  named — never silently continued.
- Public error rows carry the exception *class* only. The exception
  message — which can embed a private path — goes to the gitignored
  ``output/.errors.private.json``. Before every checkpoint write,
  ``_assert_no_private_leak`` walks every string leaf of the payload and
  raises rather than persist a registered private string.

The study replays three policies per document, all through the
production gate function ``ocr_required_by_gate`` — never a
reimplementation:

- ``baseline``: the historical policy, pinned at revision
  ``plan["baseline_policy"]["pinned_revision"]``. The unconditional
  ``pdf_type`` set is parsed out of that revision's source via
  ``git show`` and verified against the frozen plan at preflight, so the
  working tree can never silently become the baseline.
- ``candidate``: the committed policy at the freeze commit.
- ``enable_only``: the candidate's unconditional set with both
  thresholds at their ``0.0`` never-trigger sentinels — what happens to
  a ``mixed`` PDF when only the enable switch is set.

Nothing is ingested, embedded or sent anywhere. No OCR worker is started
and no model is loaded.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
PLAN_PATH = EXP_DIR / "plan.json"
LABELS_PATH = EXP_DIR / "labels.json"
OUT_DIR = EXP_DIR / "output"
OUT_PATH = OUT_DIR / "classifications.json"
PUBLIC_COLLECTION = OUT_DIR / "collection.public.json"
PRIVATE_COLLECTION = OUT_DIR / ".collection.private.json"
PRIVATE_ERRORS = OUT_DIR / ".errors.private.json"

#: Routing source bound into the run identity and guarded by the
#: routing-code-clean preflight (relative to PROJECT_ROOT).
ROUTING_SOURCES = (
    "src/omrg/integrations/pdf/ocr_routing.py",
    "src/omrg/integrations/pdf/ocr_policy.py",
)

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXP_DIR.parent))

_UNCONDITIONAL_RE = re.compile(r"OCR_UNCONDITIONAL_TYPES[^=\n]*=\s*frozenset\(\s*(\{[^}]*\})")


@dataclass(frozen=True)
class _Gate:
    """Minimal settings shim carrying only the two threshold fields."""

    ocr_fallback_min_confidence: float
    ocr_fallback_page_fraction: float


def _git(*args: str) -> str:
    """Run a read-only git command in the project root, returning stdout."""
    result = subprocess.run(  # noqa: S603 — git is the intended binary
        ["git", *args],  # noqa: S607 — PATH resolution is intended
        capture_output=True,
        text=True,
        cwd=PROJECT_ROOT,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr.strip()[:200]}")
    return result.stdout


def _routing_code_clean() -> bool:
    """True when the routing sources have no uncommitted changes.

    The candidate policy is the committed code at the freeze commit; an
    uncommitted local patch must never silently become either arm of the
    comparison.
    """
    return not _git("status", "--porcelain", "--", *ROUTING_SOURCES).strip()


def _unconditional_types_at(revision: str, source_path: str) -> frozenset[str]:
    """Parse the unconditional-type set out of a pinned revision's source."""
    source = _git("show", f"{revision}:{source_path}")
    match = _UNCONDITIONAL_RE.search(source)
    if match is None:
        raise RuntimeError(f"cannot locate OCR_UNCONDITIONAL_TYPES in {revision}:{source_path}")
    return frozenset(ast.literal_eval(match.group(1)))


def _live_unconditional_types() -> frozenset[str]:
    from omrg.integrations.pdf.ocr_policy import OCR_UNCONDITIONAL_TYPES

    return frozenset(OCR_UNCONDITIONAL_TYPES)


def _load_private_collection() -> list[dict]:
    """Read the approved collection; fail loudly when it is absent."""
    if not PRIVATE_COLLECTION.exists():
        raise SystemExit(
            f"approved collection missing: {PRIVATE_COLLECTION.name}. "
            "Run prepare_collection.py with the operator-approved paths first."
        )
    entries = json.loads(PRIVATE_COLLECTION.read_text(encoding="utf-8"))
    documents = entries.get("documents")
    if not isinstance(documents, list) or not documents:
        raise SystemExit("approved collection is empty or malformed")
    return documents


def _write_public_collection(documents: list[dict]) -> None:
    """Write the committed, path-free collection manifest once.

    Existing content must match exactly: the public manifest is frozen
    with the protocol, and a drifted file means the collection changed
    outside the approved process.
    """
    public = [
        {"doc_id": d["doc_id"], "sha256": d["sha256"], "split": d["split"]}
        for d in sorted(documents, key=lambda d: d["doc_id"])
    ]
    payload = {"documents": public}
    if PUBLIC_COLLECTION.exists():
        existing = json.loads(PUBLIC_COLLECTION.read_text(encoding="utf-8"))
        if existing != payload:
            raise SystemExit(
                f"{PUBLIC_COLLECTION.name} differs from the approved collection; "
                "refusing to overwrite frozen membership"
            )
        return
    PUBLIC_COLLECTION.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _verify_digests(documents: list[dict]) -> list[tuple[str, Path]]:
    """Verify every approved document's sha256 before any classification."""
    verified: list[tuple[str, Path]] = []
    for entry in documents:
        path = Path(entry["path"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"]:
            raise SystemExit(
                f"{entry['doc_id']} digest mismatch: the approved document "
                "was replaced or moved; refusing to classify it"
            )
        verified.append((entry["doc_id"], path))
    return verified


def _private_strings(documents: list[dict]) -> list[str]:
    """Strings that must never reach a committed artefact."""
    strings = {str(Path.home())}
    for entry in documents:
        path = Path(entry["path"])
        strings.add(str(path))
        strings.add(path.name)
        strings.add(path.parent.name)
    return sorted(strings)


def _assert_no_private_leak(payload: object, private: list[str]) -> None:
    """Raise when any string leaf of *payload* contains a private string."""
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, str):
            for needle in private:
                if needle and needle in value:
                    raise SystemExit(
                        "privacy check failed: a registered private string "
                        "appears in the public checkpoint; refusing to write it"
                    )
        elif isinstance(value, dict):
            stack.extend(value.keys())
            stack.extend(value.values())
        elif isinstance(value, (list, tuple)):
            stack.extend(value)


def _record_error(doc_id: str, exc: Exception, documents: list[dict]) -> dict:
    """Split one failure into a public row and a private diagnostic."""
    public_row = {"doc_id": doc_id, "error_class": type(exc).__name__}
    private = {}
    if PRIVATE_ERRORS.exists():
        private = json.loads(PRIVATE_ERRORS.read_text(encoding="utf-8"))
    PRIVATE_ERRORS.parent.mkdir(parents=True, exist_ok=True)
    private[doc_id] = {
        "path": next(d["path"] for d in documents if d["doc_id"] == doc_id),
        "error": f"{type(exc).__name__}: {exc}",
    }
    PRIVATE_ERRORS.write_text(json.dumps(private, indent=2), encoding="utf-8")
    return public_row


def _gate_decision(evidence: dict, gate: _Gate, unconditional: frozenset[str]) -> bool:
    """Route one document through the production gate under a policy."""
    from omrg.integrations.pdf import ocr_routing

    original = ocr_routing.OCR_UNCONDITIONAL_TYPES
    try:
        ocr_routing.OCR_UNCONDITIONAL_TYPES = unconditional
        return ocr_routing.ocr_required_by_gate(settings=gate, **evidence)
    finally:
        ocr_routing.OCR_UNCONDITIONAL_TYPES = original


def _runtime_manifest(plan: dict, documents: list[dict]) -> dict:
    """Manifest checked against the frozen plan's preflight assertions."""
    return {
        "classifier": {"reader": "pdf_inspector"},
        "collection": {
            "source": "operator_approved_list",
            "size": len(documents),
            "splits": sorted({d["split"] for d in documents}),
        },
        "policies": plan["policies"],
        "routing_code_clean": _routing_code_clean(),
        "labels_frozen": json.loads(LABELS_PATH.read_text(encoding="utf-8")).get("frozen", False),
        "privacy": {"filenames_recorded": False, "content_recorded": False},
        "ocr": {"worker_started": False, "model_loaded": False, "network_calls": 0},
    }


def _preflight(plan: dict, documents: list[dict]) -> dict:
    """Abort before reading any file when the frozen terms do not hold."""
    from _lib.preflight import PreflightError, evaluate_assertions

    manifest = _runtime_manifest(plan, documents)
    failures = evaluate_assertions(manifest, plan.get("preflight_assertions", []))

    for name, policy in plan["policies"].items():
        declared = frozenset(policy["unconditional_types"])
        if "pinned_revision" in policy:
            actual = _unconditional_types_at(policy["pinned_revision"], policy["source_path"])
            origin = f"pinned revision {policy['pinned_revision']}"
        else:
            actual = _live_unconditional_types()
            origin = "the committed code"
        if actual != declared:
            failures.append(
                f"policy {name}: unconditional_types {sorted(declared)} do not "
                f"match {origin} ({sorted(actual)})"
            )

    if failures:
        raise PreflightError("; ".join(failures))
    print("[preflight] assertions passed; pinned policies verified against git", flush=True)
    return manifest


def _run_identity(manifest: dict) -> dict:
    """Bind plan, labels, collection, policy spec and routing code."""
    from _lib.checkpoint_validity import run_identity

    return run_identity(
        plan_path=PLAN_PATH,
        gt_path=LABELS_PATH,
        corpus_manifest_path=PUBLIC_COLLECTION,
        runtime_manifest=manifest,
        code_paths=[PROJECT_ROOT / rel for rel in ROUTING_SOURCES] + [EXP_DIR / "classify.py"],
    )


def _load_checkpoint() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {"done": [], "rows": [], "errors": []}


def _save_checkpoint(payload: dict, private: list[str]) -> None:
    _assert_no_private_leak(payload, private)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(OUT_PATH)


def _classify_one(reader, path: Path, policies: dict) -> dict:
    """Classify one PDF and replay the routing decision under each policy."""
    started = time.perf_counter()
    documents = reader.load_data(path)
    elapsed = time.perf_counter() - started

    evidence = documents[0].metadata if documents else {}
    characters = sum(len(doc.text) for doc in documents)
    evidence_kwargs = {
        "pdf_type": str(evidence.get("pdf_type", "")),
        "pdf_confidence": float(evidence.get("pdf_confidence", 1.0)),
        "pages_needing_ocr": int(evidence.get("pages_needing_ocr", 0)),
        "page_count": int(evidence.get("page_count", 0)),
    }

    row = {
        **evidence_kwargs,
        "extracted_characters": characters,
        "characters_per_page": round(characters / evidence_kwargs["page_count"], 2)
        if evidence_kwargs["page_count"]
        else 0.0,
        "classification_seconds": round(elapsed, 3),
    }
    for name, policy in policies.items():
        row[f"routed_{name}"] = _gate_decision(
            evidence_kwargs,
            _Gate(policy["min_confidence"], policy["page_fraction"]),
            frozenset(policy["unconditional_types"]),
        )
    return row


def main() -> None:
    """Classify the approved collection, checkpointing after every document."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="smoke: first N documents")
    args = parser.parse_args()

    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    documents = _load_private_collection()
    _write_public_collection(documents)
    manifest = _preflight(plan, documents)
    identity = _run_identity(manifest)

    verified = _verify_digests(documents)
    if args.limit:
        verified = verified[: args.limit]

    import omrg.integrations.pdf  # noqa: F401 - populates the reader registry
    from omrg.integrations.pdf.registry import get as get_pdf_reader

    reader_cls = get_pdf_reader("pdf_inspector")
    reader = reader_cls() if isinstance(reader_cls, type) else reader_cls

    state = _load_checkpoint()
    from _lib.checkpoint_validity import evaluate_resume

    decision = evaluate_resume({"classifications": state if state["done"] else None}, identity)
    if decision["action"] == "refuse":
        raise SystemExit("unsafe resume refused: " + "; ".join(decision["reasons"]))
    state["run_identity"] = identity
    state["policies"] = manifest["policies"]

    private = _private_strings(documents)
    done = set(state["done"])
    splits = {d["doc_id"]: d["split"] for d in documents}
    print(
        f"[classify] {len(verified)} approved documents, resume skips {len(done)}",
        flush=True,
    )

    for doc_id, path in verified:
        if doc_id in done:
            continue
        try:
            row = {
                "doc_id": doc_id,
                "split": splits[doc_id],
                **_classify_one(reader, path, plan["policies"]),
            }
            state["rows"].append(row)
            routed = " ".join(f"{name}={row[f'routed_{name}']}" for name in plan["policies"])
            print(
                f"[classify] {doc_id} ({splits[doc_id]}) type={row['pdf_type']} "
                f"conf={row['pdf_confidence']:.2f} pages={row['page_count']} "
                f"chars/page={row['characters_per_page']:.0f} routed: {routed}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            state["errors"].append(_record_error(doc_id, exc, documents))
            print(f"[classify] {doc_id} PARSE FAILURE: {type(exc).__name__}", flush=True)
        state["done"].append(doc_id)
        _save_checkpoint(state, private)

    print(
        f"[classify] complete: {len(state['rows'])} classified, "
        f"{len(state['errors'])} parse failures",
        flush=True,
    )


if __name__ == "__main__":
    main()
