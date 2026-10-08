"""Score the registered candidates locally, checkpointing after each document."""

from __future__ import annotations

import argparse
import time
from importlib.metadata import version
from pathlib import Path
from typing import Any

from experiment_io import (
    EXP_DIR,
    OUTPUT,
    approved_plan,
    atomic_json,
    load_token_rule,
    read_json,
    resume_payload,
    sha256,
    text_sha256,
    verify_freeze,
)


def eligible_rows(rows: list[dict]) -> list[dict]:
    """Return the junk and healthy population; grey pages are reported only."""
    return [row for row in rows if row["class"] in {"junk", "healthy"}]


def verify_coverage(expected: list[dict], scored: list[dict]) -> None:
    """Require exactly one score for every eligible page and rescue tier."""

    def key(row: dict) -> tuple[str, int, str]:
        return row["doc_id"], row["page"], row["tier"]

    if len(scored) != len(expected) or {key(r) for r in scored} != {key(r) for r in expected}:
        raise ValueError("candidate score coverage differs from eligible pages")


def score_document(
    rows: list[dict], texts: dict[str, list[str]], rule: Any, candidate: str, model: Any = None
) -> list[dict]:
    """Score one document without copying private page text into the result."""
    scored = []
    for row in rows:
        text = texts[row["tier"]][row["page"] - 1]
        if text_sha256(text) != row["text_sha256"]:
            raise ValueError("saved page text hash differs from extraction")
        cpu_start = time.process_time()
        wall_start = time.perf_counter()
        if candidate == "A":
            from candidate_a import score_a

            result = score_a(text, rule)
        elif candidate == "B" and model is not None:
            result = {"score": model.probability(text)}
        else:
            raise ValueError("unknown or unavailable candidate")
        scored.append(
            {
                **row,
                **result,
                "cpu_seconds": time.process_time() - cpu_start,
                "wall_seconds": time.perf_counter() - wall_start,
            }
        )
    return scored


def run(source: Path, candidate: str, resume: bool) -> None:
    """Score all eligible rescue pages using unchanged labels and settings."""
    plan = approved_plan()
    verify_freeze(source)
    rescue = read_json(OUTPUT / "rescue_text.json")
    check = read_json(OUTPUT / "recall_check.json")
    if len(rescue.get("labelled_documents", [])) != plan["source_data"]["documents"] or (
        check["failed"] is not None or len(check["passed"]) != plan["source_data"]["pages"]
    ):
        raise ValueError("all-page recall agreement is required before candidate scoring")
    rows = eligible_rows(rescue["rows"])
    model = None
    if candidate == "A":
        from candidate_a import LANGUAGES

        if (
            version("wordfreq") != plan["candidates"]["A"]["A1"]["version"]
            or list(LANGUAGES) != plan["candidates"]["A"]["A1"]["languages"]
        ):
            raise ValueError("candidate A differs from the approved wordfreq pin or languages")
        packages = {name: version(name) for name in ("wordfreq", "regex")}
        signal_path = EXP_DIR / "candidate_a.py"
    else:
        from julia_onnx import JuliaRuntime

        model = JuliaRuntime(plan, require_parity=True)
        packages = {name: version(name) for name in ("onnxruntime", "tokenizers", "numpy")}
        signal_path = EXP_DIR / "julia_onnx.py"
    identity = {
        "candidate": candidate,
        "population": "rescue",
        "rescue_sha256": sha256(OUTPUT / "rescue_text.json"),
        "token_rule_sha256": sha256(source / "build_labels.py"),
        "signal_sha256": sha256(signal_path),
        "runner_sha256": sha256(Path(__file__)),
        "package_versions": packages,
        "candidate_definition": plan["candidates"][candidate],
    }
    target = OUTPUT / f"candidate_{candidate.lower()}.json"
    payload = resume_payload(target, identity, resume)
    rule = load_token_rule(source)
    for doc_id in rescue["completed_documents"]:
        if doc_id in payload["completed_documents"]:
            print(f"[resume {candidate}] {doc_id}", flush=True)
            continue
        doc_rows = [row for row in rows if row["doc_id"] == doc_id]
        texts = {
            tier: read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
            for tier in ("liteparse", "pypdf")
        }
        payload["rows"].extend(score_document(doc_rows, texts, rule, candidate, model))
        payload["completed_documents"].append(doc_id)
        atomic_json(target, payload)
        print(f"[score {candidate}] {doc_id}: {len(doc_rows)} page/tier scores", flush=True)
    verify_coverage(rows, payload["rows"])
    print(f"[score {candidate}] complete: {len(payload['rows'])} scores", flush=True)


def main() -> None:
    """Read runtime source and candidate arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument("--candidate", required=True, choices=("A", "B"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.source_exp.resolve(), args.candidate, args.resume)


if __name__ == "__main__":
    main()
