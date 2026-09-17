"""Experiment 33 labels from page evidence (task 1.1 rule, applied).

Reads the local page evidence written by ``label_pages.py`` and applies the
frozen page and document rules from ``plan.json``:

- ``output/page_evidence.json`` (committed): per page, the match scores,
  reference token count, legibility, finish reason, model id and label. It
  carries no document text.
- ``labels.json`` (committed): per document, page-label counts and the
  document label. ``frozen`` stays ``false``; the operator spot check sets it.
- ``spot_check.json`` (committed): the review list, created once. Existing
  verdicts are never overwritten.

pdf-inspector and routing output are never read.

    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/build_labels.py
"""

from __future__ import annotations

import json
import random
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
SOURCES = EXP_DIR / "sources.json"
PAGES_DIR = EXP_DIR / "output" / ".pages"
TRANSCRIPTS_DIR = EXP_DIR / "output" / ".transcripts"
SPLIT_DIR = EXP_DIR / "output" / ".transcripts_split"
EVIDENCE = EXP_DIR / "output" / "page_evidence.json"
LABELS = EXP_DIR / "labels.json"
SPOT_CHECK = EXP_DIR / "spot_check.json"

USABLE_AT = 0.80
NEEDS_OCR_BELOW = 0.50
MIN_REFERENCE_TOKENS = 10
DOC_TOLERANCE = 0.10
UNRECOVERABLE_DOC_SHARE = 0.50
SPOT_SAMPLE_SHARE = 0.10

_LATEX_COMMAND = re.compile(r"\\[A-Za-z]+")
_SPLIT = re.compile(r"[\W_]+")


def tokens(text: str) -> list[str]:
    """Apply the frozen token rule (plan.json labels.token_rule)."""
    normalised = _LATEX_COMMAND.sub(" ", unicodedata.normalize("NFKC", text).lower())
    return [token for token in _SPLIT.split(normalised) if len(token) >= 2]


def recall(layer: str, reference: list[str]) -> float:
    """Multiset token recall of *layer* against the reference tokens."""
    have = Counter(tokens(layer))
    want = Counter(reference)
    total = sum(want.values())
    return sum(min(have[t], n) for t, n in want.items()) / total if total else 1.0


def page_label(record: dict, reference: list[str], r_best: float) -> str:
    """Apply the frozen page rule; the first matching condition wins."""
    if record.get("legibility") == "illegible":
        return "unrecoverable"
    if record.get("label_error") or record.get("finish_reason") == "length":
        return "ambiguous"
    if len(reference) < MIN_REFERENCE_TOKENS:
        return "usable"
    if r_best >= USABLE_AT:
        return "usable"
    if r_best < NEEDS_OCR_BELOW:
        return "needs_ocr"
    return "ambiguous"


def document_label(counts: Counter, pages: int) -> str:
    """Apply the frozen document rule; the first matching condition wins."""
    if counts["unrecoverable"] / pages >= UNRECOVERABLE_DOC_SHARE:
        return "unrecoverable"
    if counts["needs_ocr"] / pages >= DOC_TOLERANCE:
        return "needs_ocr"
    if (counts["needs_ocr"] + counts["ambiguous"]) / pages < DOC_TOLERANCE:
        return "usable"
    return "ambiguous"


def _evidence(doc: dict, page: int) -> dict:
    stem = f"p{page:03d}"
    record = json.loads((TRANSCRIPTS_DIR / doc["doc_id"] / f"{stem}.json").read_text("utf-8"))
    page_dir = PAGES_DIR / doc["doc_id"]
    reference = tokens(record.get("transcription") or "")
    r_poppler = recall((page_dir / f"{stem}.pdftotext.txt").read_text("utf-8"), reference)
    r_pypdf = recall((page_dir / f"{stem}.pypdf.txt").read_text("utf-8"), reference)
    r_best = max(r_poppler, r_pypdf)
    label_all_text = page_label(record, reference, r_best)
    body = {"label": label_all_text, "r_best": round(r_best, 4), "reference_tokens": len(reference)}
    figure_tokens = figure_missing = None
    split_path = SPLIT_DIR / doc["doc_id"] / f"{stem}.json"
    if split_path.exists():
        # Amendment 2026-09-17: body text decides the label; figure text is
        # measured apart as text at risk inside figures.
        split = json.loads(split_path.read_text("utf-8"))
        body_ref = tokens(split.get("body_text") or "")
        layers = [
            (page_dir / f"{stem}.{name}.txt").read_text("utf-8") for name in ("pdftotext", "pypdf")
        ]
        body_r = max(recall(layer, body_ref) for layer in layers)
        body = {
            "label": page_label(split, body_ref, body_r),
            "r_best": round(body_r, 4),
            "reference_tokens": len(body_ref),
        }
        figure_ref = tokens(split.get("figure_text") or "")
        figure_tokens = len(figure_ref)
        figure_missing = round(
            (1 - max(recall(layer, figure_ref) for layer in layers)) * len(figure_ref)
        )
    elif label_all_text in {"needs_ocr", "ambiguous"}:
        raise SystemExit(
            f"{doc['doc_id']} p{page}: split transcript missing; run label_pages.py --split"
        )
    return {
        "doc_id": doc["doc_id"],
        "page": page,
        "legibility": record.get("legibility"),
        "finish_reason": record.get("finish_reason"),
        "label_error": record.get("label_error"),
        "model": record.get("model"),
        "reference_tokens": len(reference),
        "r_pdftotext": round(r_poppler, 4),
        "r_pypdf": round(r_pypdf, 4),
        "r_best": round(r_best, 4),
        "pypdf_error": (page_dir / f"{stem}.pypdf.error").exists(),
        "cost_usd": (record.get("usage") or {}).get("cost"),
        "label_all_text": label_all_text,
        "body_r_best": body["r_best"],
        "body_reference_tokens": body["reference_tokens"],
        "figure_tokens": figure_tokens,
        "figure_tokens_missing": figure_missing,
        "label": body["label"],
    }


def _write(path: Path, payload: object) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _spot_check(rows: list[dict], doc_labels: dict[str, str]) -> dict:
    required = [
        r for r in rows if r["label"] == "unrecoverable" or doc_labels[r["doc_id"]] == "ambiguous"
    ]
    required_keys = {(r["doc_id"], r["page"]) for r in required}
    rest = [r for r in rows if (r["doc_id"], r["page"]) not in required_keys]
    rng = random.Random(33)  # noqa: S311 - reproducible sampling, not security
    sample = rng.sample(rest, round(len(rest) * SPOT_SAMPLE_SHARE))

    def entry(row: dict, reason: str) -> dict:
        return {
            "doc_id": row["doc_id"],
            "page": row["page"],
            "reason": reason,
            "rule_label": row["label"],
            "all_text_label": row["label_all_text"],
            "operator_label": None,
            "note": None,
        }

    return {
        "instructions": (
            "For each page, open output/.pages/<doc_id>/p<NNN>.png and the two .txt text "
            "layers beside it. Set operator_label to usable, needs_ocr, unrecoverable or "
            "ambiguous by the protocol definitions, judging BODY text only (text inside "
            "figures, charts, drawings, photographs, stamps and signatures does not count). "
            "Disagreement on the random_sample "
            "entries must be 10% or less before labels.json is frozen."
        ),
        "required": [
            entry(r, "unrecoverable page or page of an ambiguous document") for r in required
        ],
        "random_sample": [
            entry(r, "seeded 10% sample")
            for r in sorted(sample, key=lambda r: (r["doc_id"], r["page"]))
        ],
    }


def main() -> int:
    """Build page evidence, document labels and the spot-check list."""
    documents = json.loads(SOURCES.read_text(encoding="utf-8"))["documents"]
    missing = [
        f"{d['doc_id']} p{p}"
        for d in documents
        for p in range(1, d["page_count"] + 1)
        if not (TRANSCRIPTS_DIR / d["doc_id"] / f"p{p:03d}.json").exists()
    ]
    if missing:
        print(f"{len(missing)} pages lack a transcript, first: {missing[:5]}", file=sys.stderr)
        return 1

    rows = [_evidence(d, p) for d in documents for p in range(1, d["page_count"] + 1)]
    labels: dict[str, dict] = {}
    for doc in documents:
        doc_rows = [r for r in rows if r["doc_id"] == doc["doc_id"]]
        counts = Counter(r["label"] for r in doc_rows)
        counts_all = Counter(r["label_all_text"] for r in doc_rows)
        labels[doc["doc_id"]] = {
            "stratum": doc["stratum"],
            "pages": doc["page_count"],
            "page_labels": {
                k: counts[k] for k in ("usable", "needs_ocr", "unrecoverable", "ambiguous")
            },
            "needs_ocr_share": round(counts["needs_ocr"] / doc["page_count"], 4),
            "label": document_label(counts, doc["page_count"]),
            "label_all_text": document_label(counts_all, doc["page_count"]),
            "figure_tokens_missing": sum(r["figure_tokens_missing"] or 0 for r in doc_rows),
        }

    _write(EVIDENCE, {"rule": "plan.json labels", "pages": rows})
    existing = json.loads(LABELS.read_text(encoding="utf-8")) if LABELS.exists() else {}
    if existing.get("frozen"):
        print("labels.json is frozen; refusing to overwrite", file=sys.stderr)
        return 1
    _write(
        LABELS,
        {
            "frozen": False,
            "rule": (
                "plan.json labels; label: body text (amendment 2026-09-17); "
                "label_all_text: all visible text"
            ),
            "total_cost_usd": round(sum(r["cost_usd"] or 0.0 for r in rows), 4),
            "documents": labels,
        },
    )
    if not SPOT_CHECK.exists():
        doc_labels = {k: v["label"] for k, v in labels.items()}
        _write(SPOT_CHECK, _spot_check(rows, doc_labels))

    summary = Counter(v["label"] for v in labels.values())
    by_stratum = Counter((v["stratum"], v["label"]) for v in labels.values())
    print(f"[labels] {len(rows)} pages, documents: {dict(summary)}")
    for (stratum, label), n in sorted(by_stratum.items()):
        print(f"[labels]   {stratum:22s} {label:14s} {n}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
