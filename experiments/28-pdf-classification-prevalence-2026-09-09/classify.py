"""Experiment 28 classifier: pdf-inspector over a real PDF library (task 5.5).

Classifies every de-duplicated PDF in the population declared in the
frozen `plan.json`, records the routing decision the production gate
function would make, and writes anonymised per-document rows.

Nothing is ingested, embedded, or sent anywhere. No OCR worker is
started and no model is loaded: the composition root is deliberately NOT
invoked, so this runs without an embedding provider configured. The
classifier is `pdf-inspector` and the routing decision comes from
`ocr_required_by_gate`, the production function — never a
reimplementation, so a drift between this experiment and shipped
behaviour is impossible.

Privacy (protocol section 8, enforced by preflight): committed rows carry
sequential ids, page counts, character counts, classification labels and
routing decisions. No filename, path, or extracted text is ever written
to a committed file. The id-to-path map goes to
`output/.local_manifest.json`, which is gitignored.

Checkpoint/resume is automatic: rows are appended to
`output/classifications.json` with tmp-then-rename atomic writes, so an
interrupted run resumes at the first unclassified document.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
PLAN_PATH = EXP_DIR / "plan.json"
OUT_PATH = EXP_DIR / "output/classifications.json"
LOCAL_MANIFEST = EXP_DIR / "output/.local_manifest.json"

#: Population declared in the frozen plan. Expanded here, never widened.
LIBRARY_ROOT = Path.home() / "Zotero/storage"

#: The candidate gate under test (frozen plan, controlled_variables).
GATE_MIN_CONFIDENCE = 0.5
GATE_PAGE_FRACTION = 0.5

sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(EXP_DIR.parent))


@dataclass(frozen=True)
class _Gate:
    """Minimal settings shim carrying only the two threshold fields.

    ``ocr_required_by_gate`` reads exactly these two attributes. Passing
    a purpose-built object keeps the experiment from depending on a
    resolved ``EffectiveSettings`` and therefore on an embedding
    provider being installed.
    """

    ocr_fallback_min_confidence: float
    ocr_fallback_page_fraction: float


def _runtime_manifest() -> dict:
    """Manifest checked against the frozen plan's preflight assertions."""
    return {
        "classifier": {"reader": "pdf_inspector", "library_root": str(LIBRARY_ROOT)},
        "gate": {
            "ocr_fallback_enabled": True,
            "ocr_fallback_min_confidence": GATE_MIN_CONFIDENCE,
            "ocr_fallback_page_fraction": GATE_PAGE_FRACTION,
        },
        "privacy": {"filenames_recorded": False, "content_recorded": False},
        "ocr": {"worker_started": False, "model_loaded": False, "network_calls": 0},
    }


def _preflight() -> dict:
    """Abort before reading any file if the plan's assertions do not hold."""
    from _lib.preflight import PreflightError, evaluate_assertions

    manifest = _runtime_manifest()
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    failures = evaluate_assertions(manifest, plan.get("preflight_assertions", []))
    if failures:
        raise PreflightError("; ".join(failures))
    print(f"[preflight] {len(plan['preflight_assertions'])} assertions passed", flush=True)
    return manifest


def _discover() -> list[tuple[str, Path]]:
    """De-duplicate the population by content sha256, in a stable order.

    Returns:
        ``(doc_id, path)`` pairs. Ids are sequential over the sha-ordered
        list, so the same library yields the same ids on a re-run.
    """
    by_digest: dict[str, Path] = {}
    for path in sorted(LIBRARY_ROOT.rglob("*.pdf")):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        by_digest.setdefault(digest, path)
    ordered = sorted(by_digest.items())
    return [(f"doc_{index:03d}", path) for index, (_, path) in enumerate(ordered, start=1)]


def _load_checkpoint() -> dict:
    if OUT_PATH.exists():
        return json.loads(OUT_PATH.read_text(encoding="utf-8"))
    return {"done": [], "rows": [], "errors": []}


def _save_checkpoint(payload: dict) -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(OUT_PATH)


def _classify_one(reader, path: Path, gate) -> dict:
    """Classify one PDF and compute the routing decision it would receive."""
    from omrg.integrations.pdf.ocr_routing import ocr_required_by_gate

    documents = reader.load_data(path)
    evidence = documents[0].metadata if documents else {}
    characters = sum(len(doc.text) for doc in documents)
    pdf_type = str(evidence.get("pdf_type", ""))
    confidence = float(evidence.get("pdf_confidence", 1.0))
    flagged = int(evidence.get("pages_needing_ocr", 0))
    pages = int(evidence.get("page_count", 0))
    kwargs = {
        "pdf_type": pdf_type,
        "pdf_confidence": confidence,
        "pages_needing_ocr": flagged,
        "page_count": pages,
    }
    return {
        "pdf_type": pdf_type,
        "pdf_confidence": confidence,
        "pages_needing_ocr": flagged,
        "page_count": pages,
        "extracted_characters": characters,
        "characters_per_page": round(characters / pages, 2) if pages else 0.0,
        "routed_candidate_gate": ocr_required_by_gate(settings=gate, **kwargs),
        # Thresholds at their never-trigger sentinels: isolates the
        # unconditional pdf_type rule from the calibrated thresholds.
        "routed_classification_only": ocr_required_by_gate(settings=_Gate(0.0, 0.0), **kwargs),
    }


def main() -> None:
    """Classify the population, checkpointing after every document."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="smoke: first N documents")
    args = parser.parse_args()

    _preflight()
    if not LIBRARY_ROOT.exists():
        raise SystemExit(f"population root not found: {LIBRARY_ROOT}")

    import omrg.integrations.pdf  # noqa: F401 - populates the reader registry
    from omrg.integrations.pdf.registry import get as get_pdf_reader

    reader_cls = get_pdf_reader("pdf_inspector")
    reader = reader_cls() if isinstance(reader_cls, type) else reader_cls
    gate = _Gate(GATE_MIN_CONFIDENCE, GATE_PAGE_FRACTION)

    population = _discover()
    if args.limit:
        population = population[: args.limit]
    LOCAL_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_MANIFEST.write_text(
        json.dumps({doc_id: str(path) for doc_id, path in population}, indent=2),
        encoding="utf-8",
    )

    state = _load_checkpoint()
    done = set(state["done"])
    print(
        f"[classify] {len(population)} de-duplicated PDFs, resume skips {len(done)}",
        flush=True,
    )

    for doc_id, path in population:
        if doc_id in done:
            continue
        try:
            row = {"doc_id": doc_id, **_classify_one(reader, path, gate)}
            state["rows"].append(row)
            print(
                f"[classify] {doc_id} type={row['pdf_type']} conf={row['pdf_confidence']:.2f} "
                f"pages={row['page_count']} chars/page={row['characters_per_page']:.0f} "
                f"routed={row['routed_candidate_gate']}",
                flush=True,
            )
        except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
            state["errors"].append(
                {"doc_id": doc_id, "error_class": type(exc).__name__, "message": str(exc)[:300]}
            )
            print(f"[classify] {doc_id} PARSE FAILURE: {type(exc).__name__}", flush=True)
        state["done"].append(doc_id)
        _save_checkpoint(state)

    print(
        f"[classify] complete: {len(state['rows'])} classified, "
        f"{len(state['errors'])} parse failures",
        flush=True,
    )


if __name__ == "__main__":
    main()
