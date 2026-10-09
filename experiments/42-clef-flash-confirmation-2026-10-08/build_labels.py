"""Tasks 3.3 to 3.5: page and document labels and rescue-page classes (A7, A8, A9).

Population: rescued documents only (control-run ``extraction_fallback_backend``
is not None). Imported unchanged:
- Experiment 33 ``build_labels._evidence`` (Gemini transcription, pdftotext and
  pypdf layers, body/figure split) and ``document_label``;
- Experiment 38 ``score_candidates.body_reference`` and ``classify_page``.

Writes ``output/labels.json`` (hashes, recall and classes; no page text).

    uv run --no-sync python build_labels.py
"""

from __future__ import annotations

from collections import Counter

from exp42_io import (
    EXP33,
    EXP38,
    EXP_DIR,
    OUTPUT,
    atomic_json,
    load_module,
    plan,
    read_json,
    sha256,
)

TARGET = OUTPUT / "labels.json"


def junk_text_layer(liteparse_junk: int, pages: int) -> bool:
    """Design D5: LiteParse junk pages reach 10% of the document's pages."""
    return liteparse_junk / pages >= 0.10


def rescued_ids() -> list[str]:
    """Documents the shipped chain rescued in the control run (amendment A8)."""
    rows = read_json(OUTPUT / "control_routing.json")["rows"]
    return [r["doc_id"] for r in rows if r["extraction_fallback_backend"]]


def load_rules():
    """Experiment 33 rules pointed at this experiment's evidence folders."""
    rule = load_module(EXP33 / "build_labels.py", "exp33_build_labels")
    rule.PAGES_DIR = OUTPUT / ".pages"
    rule.TRANSCRIPTS_DIR = OUTPUT / ".transcripts"
    rule.SPLIT_DIR = OUTPUT / ".transcripts_split"
    return rule


def label_document(doc: dict, rule, scoring) -> tuple[dict, list[dict]]:
    """Label every page and tier of one rescued document."""
    doc_id, pages = doc["doc_id"], doc["page_count"]
    texts = {
        tier: read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
        for tier in ("liteparse", "pypdf")
    }
    hashes = {
        (r["page"], r["tier"]): r["text_sha256"]
        for r in read_json(OUTPUT / "rescue_text.json")["rows"]
        if r["doc_id"] == doc_id
    }
    page_labels, rows, cost = Counter(), [], 0.0
    for page in range(1, pages + 1):
        evidence = rule._evidence(doc, page)  # noqa: SLF001 - frozen Experiment 33 rule
        page_labels[evidence["label"]] += 1
        cost += float(evidence.get("cost_usd") or 0.0)
        reference = scoring.body_reference(EXP_DIR, doc_id, page, rule)
        for tier, tier_texts in texts.items():
            rows.append(
                {
                    "doc_id": doc_id,
                    "page": page,
                    "tier": tier,
                    "text_sha256": hashes[(page, tier)],
                    "page_label": evidence["label"],
                    "page_label_all_text": evidence["label_all_text"],
                    **scoring.classify_page(
                        tier_texts[page - 1], reference, evidence["label"], rule
                    ),
                }
            )
    lite_junk = sum(r["tier"] == "liteparse" and r["class"] == "junk" for r in rows)
    return {
        "doc_id": doc_id,
        "stratum": doc["stratum"],
        "source": doc["source"],
        "pages": pages,
        "page_label_counts": dict(page_labels),
        "label": rule.document_label(page_labels, pages),
        "liteparse_junk_pages": lite_junk,
        "liteparse_healthy_pages": sum(
            r["tier"] == "liteparse" and r["class"] == "healthy" for r in rows
        ),
        "junk_text_layer": junk_text_layer(lite_junk, pages),
        "reference_cost_usd": round(cost, 6),
    }, rows


def main() -> None:
    """Label every rescued document."""
    plan()
    rule = load_rules()
    scoring = load_module(EXP38 / "score_candidates.py", "exp38_score_candidates")
    sources = {d["doc_id"]: d for d in read_json(EXP_DIR / "sources.json")["documents"]}
    documents, rows = {}, []
    for doc_id in rescued_ids():
        summary, doc_rows = label_document(sources[doc_id], rule, scoring)
        documents[doc_id] = summary
        rows += doc_rows
    atomic_json(
        TARGET,
        {
            "population": "rescued documents (amendment A8)",
            "rules": {
                "page_evidence": "experiments/33-ocr-routing-natural-positive-2026-09-17/"
                "build_labels.py _evidence and document_label",
                "page_evidence_sha256": sha256(EXP33 / "build_labels.py"),
                "classify_page": "experiments/38-rescue-quality-signal-2026-09-30/"
                "score_candidates.py body_reference and classify_page",
                "classify_page_sha256": sha256(EXP38 / "score_candidates.py"),
                "reference_engine": "google/gemini-3.8-flash (amendment A7)",
            },
            "documents": documents,
            "rows": rows,
        },
    )
    lite = Counter(r["class"] for r in rows if r["tier"] == "liteparse")
    print(f"[labels] {len(documents)} rescued documents labelled ({sum(lite.values())} pages)")


if __name__ == "__main__":
    main()
