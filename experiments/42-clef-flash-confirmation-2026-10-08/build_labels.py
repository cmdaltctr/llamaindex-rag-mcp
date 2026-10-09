"""Tasks 3.3 to 3.5: body-text split, page classes and document labels.

Imported, not copied:
- Experiment 33 ``build_labels.tokens``, ``recall``, ``page_label``, ``document_label``;
- Experiment 38 ``score_candidates.classify_page`` (junk < 0.50, healthy >= 0.80).

Body text follows plan.json ``labelling.body_text_rule``. Page labels use
r_best = max(LiteParse recall, pypdf recall) (amendment A4).

Writes ``output/labels.json`` (hashes, recall and classes; no page text).

    uv run --no-sync python build_labels.py
"""

from __future__ import annotations

import re
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
_HTML_TAG = re.compile(r"<[^>]+>")
MIN_TOKENS = 10


def body_text(markdown: str) -> str:
    """Apply the written body-text rule to one dots.mocr page."""
    return _HTML_TAG.sub(" ", markdown)


def legibility(reference: list[str], rescue_token_counts: list[int]) -> str | None:
    """Mark an empty reference as illegible when a rescue text still holds text."""
    if reference:
        return None
    return "illegible" if max(rescue_token_counts) >= MIN_TOKENS else "no_text"


def junk_text_layer(liteparse_junk: int, pages: int) -> bool:
    """Design D5: LiteParse junk pages reach 10% of the document's pages."""
    return liteparse_junk / pages >= 0.10


def label_document(doc: dict, rule, classify, state: dict) -> tuple[dict, list[dict]]:
    """Label every page and tier of one document."""
    doc_id, pages = doc["doc_id"], doc["page_count"]
    texts = {
        tier: read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
        for tier in ("liteparse", "pypdf")
    }
    rescue_rows = {
        (r["page"], r["tier"]): r
        for r in read_json(OUTPUT / "rescue_text.json")["rows"]
        if r["doc_id"] == doc_id
    }
    page_labels, rows = Counter(), []
    for page in range(1, pages + 1):
        key = f"{doc_id}:{page}"
        entry = state["pages"].get(key, {})
        path = OUTPUT / ".references" / doc_id / f"p{page:03d}.md"
        if entry.get("status") != "ok" or not path.is_file():
            raise SystemExit(f"reference missing for {key}")
        reference = rule.tokens(body_text(path.read_text(encoding="utf-8")))
        recalls = {t: rule.recall(texts[t][page - 1], reference) for t in texts}
        counts = [len(rule.tokens(texts[t][page - 1])) for t in texts]
        record = {"legibility": legibility(reference, counts)}
        page_label = rule.page_label(record, reference, max(recalls.values()))
        page_labels[page_label] += 1
        for tier, text in texts.items():
            frozen = "unrecoverable" if record["legibility"] == "illegible" else page_label
            classified = classify(text, reference, frozen, rule)
            if record["legibility"] == "illegible":
                classified["exclusion_reason"] = "page illegible (empty reference)"
            rows.append(
                {
                    **{k: rescue_rows[(page, tier)][k] for k in ("doc_id", "page", "tier")},
                    "text_sha256": rescue_rows[(page, tier)]["text_sha256"],
                    "reference_sha256": sha256(path),
                    "page_label": page_label,
                    **classified,
                }
            )
    lite_junk = sum(r["tier"] == "liteparse" and r["class"] == "junk" for r in rows)
    return {
        "doc_id": doc_id,
        "stratum": doc["stratum"],
        "group": doc.get("group"),
        "pages": pages,
        "page_label_counts": dict(page_labels),
        "label": rule.document_label(page_labels, pages),
        "liteparse_junk_pages": lite_junk,
        "liteparse_healthy_pages": sum(
            r["tier"] == "liteparse" and r["class"] == "healthy" for r in rows
        ),
        "junk_text_layer": junk_text_layer(lite_junk, pages),
    }, rows


def main() -> None:
    """Label every document whose references are complete."""
    plan()
    rule = load_module(EXP33 / "build_labels.py", "exp33_build_labels")
    scoring = load_module(EXP38 / "score_candidates.py", "exp38_score_candidates")
    state = read_json(OUTPUT / "reference_state.json")
    lane_b = OUTPUT / "reference_state_b.json"
    if lane_b.is_file():
        state["pages"] = {**read_json(lane_b)["pages"], **state["pages"]}
    documents, rows = {}, []
    for doc in read_json(EXP_DIR / "sources.json")["documents"]:
        summary, doc_rows = label_document(doc, rule, scoring.classify_page, state)
        documents[doc["doc_id"]] = summary
        rows += doc_rows
    atomic_json(
        TARGET,
        {
            "rules": {
                "token_rule": str(EXP33.relative_to(EXP33.parent.parent) / "build_labels.py"),
                "token_rule_sha256": sha256(EXP33 / "build_labels.py"),
                "classify_page": str(
                    EXP38.relative_to(EXP38.parent.parent) / "score_candidates.py"
                ),
                "classify_page_sha256": sha256(EXP38 / "score_candidates.py"),
                "body_text_rule": "plan.json labelling.body_text_rule",
                "reference_engine": state["engine"],
            },
            "documents": documents,
            "rows": rows,
        },
    )
    count = Counter(r["class"] for r in rows if r["tier"] == "liteparse")
    print(f"[labels] {len(documents)} documents; LiteParse classes {dict(count)}", flush=True)


if __name__ == "__main__":
    main()
