"""Tasks 3.6 and 3.7: label-check sample (operator check waived, A1) and D3 targets.

    uv run --no-sync python set_check.py

Writes ``output/label_check.json`` (60 stratified pages, seed 42, with review
renders under gitignored ``output/.renders/``) and ``output/set_check.json``.
Exits 1 when any D3 target is missed. Uses labels and control routes only.
"""

from __future__ import annotations

import random
import sys
from collections import Counter

from exp42_io import EXP_DIR, OUTPUT, atomic_json, plan, read_json

RENDERS = OUTPUT / ".renders"


def targets(labels: dict, control: dict, overlap: int, minimums: dict) -> dict:
    """Return each D3 target with its observed value and pass flag."""
    lite = [r for r in labels["rows"] if r["tier"] == "liteparse"]
    junk_by_doc = Counter(r["doc_id"] for r in lite if r["class"] == "junk")
    junk_total = sum(junk_by_doc.values())
    layer_docs = [d for d, v in labels["documents"].items() if v["junk_text_layer"]]
    missed = [d for d in layer_docs if not control[d]["ocr_required"]]
    observed = {
        "healthy_pages_min": sum(r["class"] == "healthy" for r in lite),
        "junk_pages_min": junk_total,
        "junk_text_layer_documents_min": len(layer_docs),
        "junk_text_layer_documents_not_routed_by_control_min": len(missed),
        "largest_document_share_of_junk_pages_max": (
            max(junk_by_doc.values()) / junk_total if junk_total else 1.0
        ),
        "usable_documents_min": sum(v["label"] == "usable" for v in labels["documents"].values()),
        "overlap_with_experiment_33": overlap,
    }
    out = {}
    for key, value in observed.items():
        limit = 0 if key == "overlap_with_experiment_33" else minimums[key]
        ok = value <= limit if key.endswith("_max") or key.startswith("overlap") else value >= limit
        out[key] = {"observed": value, "target": limit, "pass": ok}
    out["junk_text_layer_documents"] = layer_docs
    out["junk_text_layer_documents_not_routed_by_control"] = missed
    return out


def review_sample(rows: list[dict]) -> list[dict]:
    """20 junk, 20 healthy, 20 grey or boundary LiteParse pages, seed 42."""
    lite = [r for r in rows if r["tier"] == "liteparse"]
    rng = random.Random(42)  # noqa: S311 - seeded sample, not security
    pools = {
        "junk": [r for r in lite if r["class"] == "junk"],
        "healthy": [r for r in lite if r["class"] == "healthy"],
        "grey_or_boundary": [
            r
            for r in lite
            if r["class"] == "grey"
            or (r["class"] in {"junk", "healthy"} and abs(r["body_recall"] - 0.5) < 0.05)
            or (r["class"] in {"junk", "healthy"} and abs(r["body_recall"] - 0.8) < 0.05)
        ],
    }
    sample = []
    for stratum, pool in pools.items():
        for r in rng.sample(pool, min(20, len(pool))):
            sample.append(
                {
                    "stratum": stratum,
                    **{k: r[k] for k in ("doc_id", "page", "class", "body_recall")},
                }
            )
    return sample


def render(sample: list[dict]) -> None:
    """Render review images at 150 dpi, long side at least 1,600 px (amendment A3)."""
    import pypdfium2 as pdfium

    sources = {d["doc_id"]: d for d in read_json(EXP_DIR / "sources.json")["documents"]}
    for item in sample:
        out = RENDERS / item["doc_id"] / f"p{item['page']:03d}.png"
        if out.exists():
            continue
        out.parent.mkdir(parents=True, exist_ok=True)
        document = pdfium.PdfDocument(str(EXP_DIR / sources[item["doc_id"]]["local_path"]))
        page = document[item["page"] - 1]
        scale = max(150 / 72, 1600 / max(page.get_size()))
        page.render(scale=scale).to_pil().save(out)
        document.close()


def main() -> int:
    """Write the label-check sample and the D3 target check."""
    current = plan()
    labels = read_json(OUTPUT / "labels.json")
    control = {r["doc_id"]: r for r in read_json(OUTPUT / "control_routing.json")["rows"]}
    sources = read_json(EXP_DIR / "sources.json")["documents"]
    from prepare_corpus import exp33_exclusions, is_excluded

    exclusions = exp33_exclusions()
    overlap = sum(is_excluded(d["sha256"], d["source_identifier"], exclusions) for d in sources)
    sample = review_sample(labels["rows"])
    try:
        render(sample)
        rendered = True
    except ImportError:
        rendered = False
    atomic_json(
        OUTPUT / "label_check.json",
        {
            "status": "operator check WAIVED by amendment A1 (2026-10-09); sample kept for review",
            "renders": "output/.renders/<doc_id>/pNNN.png (gitignored)"
            if rendered
            else "not rendered",
            "max_class_disagreements": 3,
            "disagreements": None,
            "sample": sample,
        },
    )
    result = targets(labels, control, overlap, current["sample_size"])
    passed = all(v["pass"] for v in result.values() if isinstance(v, dict))
    atomic_json(OUTPUT / "set_check.json", {"passed": passed, "targets": result})
    for key, value in result.items():
        if isinstance(value, dict):
            print(
                f"{key}: {value['observed']} (target {value['target']}) "
                f"{'pass' if value['pass'] else 'MISS'}"
            )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
