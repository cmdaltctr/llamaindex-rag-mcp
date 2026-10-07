"""Validate frozen recall agreement and classify rescue pages before candidate scoring."""

from __future__ import annotations

import argparse
from decimal import Decimal
from pathlib import Path
from typing import Any

from experiment_io import (
    OUTPUT,
    approved_plan,
    atomic_json,
    load_token_rule,
    read_json,
    sha256,
    verify_freeze,
)
from extract_rescue_text import extraction_identity, validate_checkpoint


def body_reference(source: Path, doc_id: str, page: int, rule: Any) -> list[str]:
    """Read the frozen body split, falling back only when no split exists."""
    stem = f"p{page:03d}.json"
    split = source / "output" / ".transcripts_split" / doc_id / stem
    if split.exists():
        text = read_json(split).get("body_text") or ""
    else:
        text = (
            read_json(source / "output" / ".transcripts" / doc_id / stem).get("transcription") or ""
        )
    return rule.tokens(text)


def classify_page(text: str, reference: list[str], frozen_label: str, rule: Any) -> dict:
    """Apply design D2 using the imported frozen multiset token rule."""
    count = len(rule.tokens(text))
    recall = rule.recall(text, reference)
    reason = None
    if len(reference) < 10:
        reason = "body reference below 10 tokens"
    elif frozen_label in {"unrecoverable", "ambiguous"}:
        reason = f"frozen label {frozen_label}"
    elif not count:
        reason = "empty rescue tokens"
    if reason:
        label = "excluded"
    else:
        label = "junk" if recall < 0.50 else "healthy" if recall >= 0.80 else "grey"
    return {
        "class": label,
        "body_recall": recall,
        "body_reference_tokens": len(reference),
        "text_tokens": count,
        "exclusion_reason": reason,
    }


def verify_pypdf_recall(observed: float, frozen: float, doc_id: str, page: int) -> None:
    """Stop whenever a page's body recall disagrees with frozen r_pypdf."""
    if abs(Decimal(str(observed)) - Decimal(str(frozen))) > Decimal("0.0001"):
        raise ValueError(
            f"pypdf recall mismatch: {doc_id} p{page:03d}, "
            f"body={observed:.8f}, frozen r_pypdf={frozen:.8f}"
        )


def label_rescue(source: Path, resume: bool) -> None:
    """Check each physical page and checkpoint classifications per document."""
    plan = approved_plan()
    verify_freeze(source)
    target = OUTPUT / "rescue_text.json"
    payload = read_json(target)
    if payload["identity"] != extraction_identity(source):
        raise ValueError("extraction identity changed before classification")
    validate_checkpoint(payload)
    if len(payload["completed_documents"]) != plan["source_data"]["documents"]:
        raise ValueError("all documents must be extracted before classification")
    code_hash = sha256(Path(__file__))
    if payload.get("labelled_documents") and not resume:
        raise ValueError("classification checkpoint exists; use --resume")
    if payload.get("classification_sha256", code_hash) != code_hash:
        raise ValueError("classification code changed; resume refused")
    rule = load_token_rule(source)
    evidence = {
        (r["doc_id"], r["page"]): r
        for r in read_json(source / "output" / "page_evidence.json")["pages"]
    }
    checked = (
        read_json(OUTPUT / "recall_check.json")
        if resume and (OUTPUT / "recall_check.json").exists()
        else {"tolerance": 0.0001, "passed": [], "failed": None}
    )
    payload.setdefault("labelled_documents", [])
    payload["classification_sha256"] = code_hash
    for doc_id in payload["completed_documents"]:
        if doc_id in payload["labelled_documents"]:
            continue
        rows = [r for r in payload["rows"] if r["doc_id"] == doc_id]
        texts = {
            tier: read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
            for tier in ("liteparse", "pypdf")
        }
        staged = []
        checks = []
        for row in rows:
            page = row["page"]
            reference = body_reference(source, doc_id, page, rule)
            frozen = evidence[(doc_id, page)]
            result = classify_page(texts[row["tier"]][page - 1], reference, frozen["label"], rule)
            if row["tier"] == "pypdf":
                check = {
                    "doc_id": doc_id,
                    "page": page,
                    "body_recall": result["body_recall"],
                    "frozen_r_pypdf": frozen["r_pypdf"],
                    "body_reference_tokens": len(reference),
                    "frozen_all_reference_tokens": frozen["reference_tokens"],
                }
                try:
                    verify_pypdf_recall(result["body_recall"], frozen["r_pypdf"], doc_id, page)
                except ValueError:
                    checked["failed"] = check
                    atomic_json(OUTPUT / "recall_check.json", checked)
                    raise
                checks.append(check)
            staged.append((row, result))
        for row, result in staged:
            row.update(result)
        checked["passed"].extend(checks)
        checked["failed"] = None
        payload["labelled_documents"].append(doc_id)
        atomic_json(target, payload)
        atomic_json(OUTPUT / "recall_check.json", checked)
        print(f"[labels] {doc_id}: recall agreement verified", flush=True)
    if len(checked["passed"]) != plan["source_data"]["pages"]:
        raise ValueError("recall check did not cover every frozen page")
    print(f"[labels] complete: {len(checked['passed'])} pypdf checks passed", flush=True)


def main() -> None:
    """Run classification with explicit source location and resume support."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    label_rescue(args.source_exp.resolve(), args.resume)


if __name__ == "__main__":
    main()
