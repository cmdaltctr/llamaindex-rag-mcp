"""Leave-one-document-out equal-cost thresholds (amendment A3).

Each document is flagged with a threshold chosen only on the healthy LiteParse
pages of the other documents, so no threshold is tested on its own pages.
"""

from __future__ import annotations

import math

from signal_stats import auc_badness, equal_cost_threshold


def lodo_thresholds(rows: list[dict]) -> dict[str, float]:
    """Return one equal-cost threshold per document, excluding that document."""
    primary = [row for row in rows if row["tier"] == "liteparse"]
    documents = sorted({row["doc_id"] for row in rows})
    return {
        doc_id: equal_cost_threshold([row for row in primary if row["doc_id"] != doc_id])
        for doc_id in documents
    }


def held_out(rows: list[dict], thresholds: dict[str, float]) -> list[dict]:
    """Shift each score by its document's threshold so the shared cut-off is 0.

    For floats, ``score < t`` holds exactly when ``score - t < 0``, so the
    existing strict-threshold helpers give the held-out flags unchanged.
    """
    return [{**row, "score": row["score"] - thresholds[row["doc_id"]]} for row in rows]


def _auc(rows: list[dict]) -> float:
    """Junk-versus-healthy ranking on LiteParse pages; lower score means junkier."""
    pairs = [
        {"score": r["score"], "body_recall": 0.0 if r["class"] == "junk" else 1.0}
        for r in rows
        if r["tier"] == "liteparse"
    ]
    return auc_badness(pairs) or 0.0


def nested_select(variants: dict[str, list[dict]]) -> tuple[list[dict], dict[str, str]]:
    """Pick a variant and a threshold per held-out document using only other documents.

    Returns shifted rows (cut-off 0) built from each document's chosen variant,
    and the variant chosen for each document.
    """
    documents = sorted({row["doc_id"] for rows in variants.values() for row in rows})
    shifted, chosen = [], {}
    for doc_id in documents:
        others = {
            name: [r for r in rows if r["doc_id"] != doc_id] for name, rows in variants.items()
        }
        best = max(sorted(others), key=lambda name: _auc(others[name]))
        threshold = equal_cost_threshold([r for r in others[best] if r["tier"] == "liteparse"])
        chosen[doc_id] = best
        shifted += [
            {**r, "score": r["score"] - threshold} for r in variants[best] if r["doc_id"] == doc_id
        ]
    return shifted, chosen


def cascade_select(
    screen: list[dict], confirm: list[dict], screen_rate: float = 0.20
) -> tuple[list[dict], float]:
    """Held-out cascade: the cheap signal screens, the model confirms suspect pages only.

    Returns shifted rows (cut-off 0) and the share of pages sent to the model.
    Unscreened pages get a confirm score of 2.0, above any probability, so the
    equal-cost rule counts every healthy page in its allowance.
    """

    def key(row: dict) -> tuple:
        return row["doc_id"], row["page"], row["tier"]

    model = {key(r): r["score"] for r in confirm}
    documents = sorted({r["doc_id"] for r in screen})
    shifted, sent = [], 0
    for doc_id in documents:
        healthy = sorted(
            r["score"]
            for r in screen
            if r["doc_id"] != doc_id and r["tier"] == "liteparse" and r["class"] == "healthy"
        )
        cut = healthy[math.floor(screen_rate * len(healthy))]
        combined = [{**r, "score": model[key(r)] if r["score"] < cut else 2.0} for r in screen]
        threshold = equal_cost_threshold(
            [r for r in combined if r["doc_id"] != doc_id and r["tier"] == "liteparse"]
        )
        own = [r for r in combined if r["doc_id"] == doc_id]
        sent += sum(r["score"] < 2.0 for r in own)
        shifted += [{**r, "score": r["score"] - threshold} for r in own]
    return shifted, sent / len(screen)
