"""Experiment 33 local OCR tier measurement (task 6.7, evidence for page-level-ocr-routing).

Runs pdf-inspector selective OCR (PP-OCRv6 Small on ONNX Runtime, CPU) in
``force`` mode on exactly the natural pages the frozen labels mark as needing
OCR, so pdf-inspector's own routing is never consulted. Each page's OCR text
is scored against the reference transcription (body text, and all visible
text) with the frozen token rule.

Authorisation: plan.json decision_register entry "local OCR tier
measurement" (subset, timeout and budget named there). Local only; no cloud.
Refuses to run unless the labels are frozen and the freeze verifies.

Environment (paths, not secrets):
    PDFIUM_LIB_PATH       PDFium shared library (the LiteParse-bundled one)
    ORT_DYLIB_PATH        ONNX Runtime shared library
    PDF_INSPECTOR_MODEL_CACHE  model cache (default output/.pdfi_models)

    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/local_ocr.py
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import sys
import time
from collections import defaultdict
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR))

import freeze  # noqa: E402
from build_labels import SPLIT_DIR, TRANSCRIPTS_DIR, recall, tokens  # noqa: E402

OUT_DIR = EXP_DIR / "output" / "local_ocr"
CHECKPOINT = OUT_DIR / "pages.json"
TEXT_DIR = EXP_DIR / "output" / ".local_ocr_text"
BUDGET_SECONDS = 3600
DOC_SOFT_TIMEOUT_SECONDS = 900
CONFIDENCE_CUTS = (0.5, 0.6, 0.7, 0.8, 0.9)


def _reference(doc_id: str, page: int) -> tuple[list[str], list[str]]:
    stem = f"p{page:03d}.json"
    first = json.loads((TRANSCRIPTS_DIR / doc_id / stem).read_text("utf-8"))
    split_path = SPLIT_DIR / doc_id / stem
    body = first.get("transcription") or ""
    if split_path.exists():
        body = json.loads(split_path.read_text("utf-8")).get("body_text") or ""
    return tokens(body), tokens(first.get("transcription") or "")


def _identity() -> dict:
    lib = os.environ.get("PDFIUM_LIB_PATH", "")
    return {
        "pdf_inspector": importlib.metadata.version("pdf-inspector"),
        "onnxruntime": importlib.metadata.version("onnxruntime"),
        "pdfium_lib_sha256": hashlib.sha256(Path(lib).read_bytes()).hexdigest() if lib else None,
        "mode": "force",
        "subset": "natural pages whose frozen body label or all-text label is needs_ocr",
    }


def _pages_to_run(evidence: list[dict]) -> dict[str, list[int]]:
    wanted: dict[str, list[int]] = defaultdict(list)
    for row in evidence:
        if "needs_ocr" in (row["label"], row["label_all_text"]):
            wanted[row["doc_id"]].append(row["page"])
    return dict(wanted)


def summarise(rows: list[dict]) -> dict:
    """Quality, calibration and escalation summary over measured pages."""
    body = [r for r in rows if r["body_label"] == "needs_ocr" and r["body_recall"] is not None]

    def share(items, predicate):
        return round(sum(1 for r in items if predicate(r)) / len(items), 4) if items else None

    calibration = {}
    for cut in CONFIDENCE_CUTS:
        kept = [r for r in body if (r["confidence"] or 0) >= cut and not r["hosted_recommended"]]
        calibration[str(cut)] = {
            "escalation_share": round(1 - len(kept) / len(body), 4) if body else None,
            "kept_pages_recall_ge_0_8": share(kept, lambda r: r["body_recall"] >= 0.8),
        }
    seconds = sum(r["doc_seconds_share"] for r in rows)
    return {
        "label": "Stage B local OCR tier; natural pages; not a routing measurement",
        "pages_measured": len(rows),
        "body_needs_ocr_pages": len(body),
        "body_recall_ge_0_8_share": share(body, lambda r: r["body_recall"] >= 0.8),
        "body_recall_lt_0_5_share": share(body, lambda r: r["body_recall"] < 0.5),
        "no_text_share": share(body, lambda r: r["chars"] == 0),
        "hosted_recommended_share": share(body, lambda r: r["hosted_recommended"]),
        "escalation_by_confidence_cut": calibration,
        "seconds_per_page": round(seconds / len(rows), 3) if rows else None,
        "figure_only_pages": sum(
            1 for r in rows if r["body_label"] != "needs_ocr" and r["all_text_label"] == "needs_ocr"
        ),
    }


def main() -> int:
    """Measure the local OCR tier, checkpointing after every document."""
    labels = json.loads((EXP_DIR / "labels.json").read_text(encoding="utf-8"))
    if not labels.get("frozen"):
        print("labels.json is not frozen; refusing to run real OCR", file=sys.stderr)
        return 1
    drift = freeze.check()
    if drift:
        print("freeze check failed: " + "; ".join(drift), file=sys.stderr)
        return 1
    for var in ("PDFIUM_LIB_PATH", "ORT_DYLIB_PATH"):
        if not os.environ.get(var):
            print(f"{var} is not set", file=sys.stderr)
            return 1
    os.environ.setdefault("PDF_INSPECTOR_MODEL_CACHE", str(EXP_DIR / "output" / ".pdfi_models"))

    import pdf_inspector

    sources = {
        d["doc_id"]: d for d in json.loads((EXP_DIR / "sources.json").read_text())["documents"]
    }
    evidence = json.loads((EXP_DIR / "output" / "page_evidence.json").read_text())["pages"]
    by_key = {(r["doc_id"], r["page"]): r for r in evidence}
    state = json.loads(CHECKPOINT.read_text()) if CHECKPOINT.exists() else {"rows": [], "done": []}
    state["identity"] = _identity()
    started = time.perf_counter()

    for doc_id, pages in sorted(_pages_to_run(evidence).items()):
        if doc_id in state["done"]:
            continue
        if time.perf_counter() - started > BUDGET_SECONDS:
            print("[local_ocr] runtime budget reached; stopping (resume later)", flush=True)
            break
        t0 = time.perf_counter()
        try:
            result = pdf_inspector.process_pdf_with_ocr(
                str(EXP_DIR / sources[doc_id]["local_path"]), mode="force", page_numbers=pages
            )
            error = None
        except Exception as exc:  # noqa: BLE001 - a failed document is an outcome
            result, error = None, type(exc).__name__
        elapsed = time.perf_counter() - t0
        outputs = {pg.page_number: pg for pg in (result.pages if result else [])}
        hosted = set(result.pages_recommending_hosted) if result else set()
        for page in pages:
            body_ref, all_ref = _reference(doc_id, page)
            out = outputs.get(page)
            text = out.markdown if out else ""
            TEXT_DIR.joinpath(doc_id).mkdir(parents=True, exist_ok=True)
            TEXT_DIR.joinpath(doc_id, f"p{page:03d}.md").write_text(text, encoding="utf-8")
            provenance = out.provenance if out else None
            row = by_key[(doc_id, page)]
            state["rows"].append(
                {
                    "doc_id": doc_id,
                    "page": page,
                    "stratum": sources[doc_id]["stratum"],
                    "body_label": row["label"],
                    "all_text_label": row["label_all_text"],
                    "source": provenance.source if provenance else None,
                    "confidence": provenance.ocr_confidence if provenance else None,
                    "model": (
                        f"{provenance.ocr_model.name}@{provenance.ocr_model.revision}"
                        if provenance and provenance.ocr_model
                        else None
                    ),
                    "hosted_recommended": page in hosted,
                    "warnings": list(provenance.warnings) if provenance else [],
                    "chars": len(text),
                    "body_recall": round(recall(text, body_ref), 4) if body_ref else None,
                    "all_text_recall": round(recall(text, all_ref), 4) if all_ref else None,
                    "doc_seconds_share": round(elapsed / len(pages), 3),
                    "error_class": error,
                    "doc_over_soft_timeout": elapsed > DOC_SOFT_TIMEOUT_SECONDS,
                }
            )
        state["done"].append(doc_id)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        tmp = CHECKPOINT.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, indent=1), encoding="utf-8")
        tmp.replace(CHECKPOINT)
        print(
            f"[local_ocr] {doc_id}: {len(pages)} pages in {elapsed:.1f}s error={error}", flush=True
        )

    summary = summarise(state["rows"])
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
