"""Post-verdict diagnostic D1: routing when every rescued page is scored.

The pre-registered routing simulation (Experiment 38 ``simulate_routing``) counts
flags only on pages labelled junk or healthy. Production would score every
rescued page. This diagnostic scores every LiteParse page of every rescued
document with both arms at the frozen thresholds and recomputes G1 and G2.
It never changes the verdict, the frozen outputs or the thresholds.

    uv run --no-sync --with wordfreq==3.1.1 --with regex python -u diagnostic_all_pages.py
"""

from __future__ import annotations

import llama_server
from exp42_io import EXP33, EXP38, OUTPUT, atomic_json, load_module, plan, read_json

TARGET = OUTPUT / "diagnostic_all_pages.json"


def route(flags: int, pages: int) -> bool:
    """Unchanged 0.10 routing fraction; no rescued document was routed by the control."""
    return flags / pages >= 0.10


def main() -> None:
    """Score all rescued pages and write the diagnostic."""
    current = plan()
    thresholds = {
        "A": current["thresholds"]["word_check_a"]["value"],
        "clef": current["thresholds"]["clef_flash_q8_0_w1"]["value"],
    }
    labels = read_json(OUTPUT / "labels.json")
    docs = labels["documents"]
    rule = load_module(EXP33 / "build_labels.py", "exp33_rule")
    word = load_module(EXP38 / "candidate_a.py", "exp38_candidate_a")
    hosted = load_module(EXP38 / "jev_hosted.py", "exp38_jev_hosted")
    wordings = load_module(EXP38 / "score_wordings.py", "exp38_score_wordings")
    exp38_plan = read_json(EXP38 / "plan.json")
    clef = wordings.scorer("clefgguf", exp38_plan["wordings"]["W1"], exp38_plan)
    process = llama_server.start(OUTPUT / "llamacpp_server_diagnostic.log")
    pages = []
    try:
        for doc_id in docs:
            texts = read_json(OUTPUT / ".rescue_text" / doc_id / "liteparse.json")
            for number, text in enumerate(texts, start=1):
                row = {"doc_id": doc_id, "page": number, "empty": not text.strip()}
                if not row["empty"]:
                    row["A"] = word.score_a(text, rule)["score"]
                    row["clef"] = clef([text[: hosted.HEAD_CHARACTERS]])[0]["score"]
                pages.append(row)
            print(f"[diag] {doc_id}", flush=True)
    finally:
        llama_server.stop(process)
    result = {"thresholds": thresholds, "arms": {}}
    for arm, threshold in thresholds.items():
        routing = {}
        for doc_id, doc in docs.items():
            rows = [p for p in pages if p["doc_id"] == doc_id]
            flags = sum(not p["empty"] and p[arm] < threshold for p in rows)
            routing[doc_id] = {
                "pages": doc["pages"],
                "flagged_pages": flags,
                "routed": route(flags, doc["pages"]),
                "label": doc["label"],
                "junk_text_layer": doc["junk_text_layer"],
            }
        result["arms"][arm] = {
            "G1_missed_junk_layer_documents": sorted(
                d for d, r in routing.items() if r["junk_text_layer"] and not r["routed"]
            ),
            "G2_usable_documents_routed": sorted(
                d for d, r in routing.items() if r["label"] == "usable" and r["routed"]
            ),
            "routing": routing,
        }
    result["pages_scored"] = sum(not p["empty"] for p in pages)
    result["pages_empty"] = sum(p["empty"] for p in pages)
    atomic_json(TARGET, result)
    for arm, a in result["arms"].items():
        print(
            arm,
            "G1 missed",
            a["G1_missed_junk_layer_documents"],
            "G2 routed",
            a["G2_usable_documents_routed"],
            flush=True,
        )


if __name__ == "__main__":
    main()
