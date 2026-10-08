"""Score candidate B2: Julia 1 on the first 2,000 characters of each page (amendment A3).

Same pinned model, encoder, question and options as B. Only the input length
changes, so B2 reads the same text as hosted Jev (candidate C).
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from experiment_io import (
    OUTPUT,
    approved_plan,
    atomic_json,
    read_json,
    resume_payload,
    sha256,
    text_sha256,
    verify_freeze,
)
from jev_hosted import HEAD_CHARACTERS
from score_signals import eligible_rows, verify_coverage


def run(source: Path, resume: bool) -> None:
    """Score every junk and healthy page/tier pair, checkpointing per document."""
    plan = approved_plan()
    if "B2" not in plan["candidates"]:
        raise RuntimeError("candidate B2 must be registered before scoring")
    verify_freeze(source)
    from julia_onnx import JuliaRuntime

    model = JuliaRuntime(plan, require_parity=True)
    rescue = read_json(OUTPUT / "rescue_text.json")
    rows = eligible_rows(rescue["rows"])
    identity = {
        "candidate": "B2",
        "rescue_sha256": sha256(OUTPUT / "rescue_text.json"),
        "signal_sha256": sha256(Path(__file__).parent / "julia_onnx.py"),
        "runner_sha256": sha256(Path(__file__)),
        "head_characters": HEAD_CHARACTERS,
        "candidate_definition": plan["candidates"]["B2"],
    }
    target = OUTPUT / "candidate_b2.json"
    payload = resume_payload(target, identity, resume)
    for doc_id in rescue["completed_documents"]:
        if doc_id in payload["completed_documents"]:
            continue
        texts = {
            tier: read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
            for tier in ("liteparse", "pypdf")
        }
        for row in (r for r in rows if r["doc_id"] == doc_id):
            text = texts[row["tier"]][row["page"] - 1]
            if text_sha256(text) != row["text_sha256"]:
                raise ValueError("saved page text hash differs from extraction")
            start = time.process_time()
            score = model.probability(text[:HEAD_CHARACTERS])
            payload["rows"].append(
                {**row, "score": score, "cpu_seconds": time.process_time() - start}
            )
        payload["completed_documents"].append(doc_id)
        atomic_json(target, payload)
        print(f"[score B2] {doc_id}", flush=True)
    verify_coverage(rows, payload["rows"])
    print(f"[score B2] complete: {len(payload['rows'])} scores", flush=True)


def main() -> None:
    """Read runtime arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.source_exp.resolve(), args.resume)


if __name__ == "__main__":
    main()
