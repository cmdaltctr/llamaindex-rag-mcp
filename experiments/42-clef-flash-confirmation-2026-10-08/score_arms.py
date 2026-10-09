"""Tasks 5.1 to 5.3: score candidate A and Clef-flash Q8_0 W1 on every eligible page.

No interim look: this script prints progress counts only, never a metric.

    uv run --no-sync --with wordfreq==3.1.1 python score_arms.py --arm a --resume
    uv run --no-sync python -u score_arms.py --arm clef --resume

Candidate A runs the Experiment 38 ``candidate_a.score_a`` on the full page text.
Clef-flash runs the Experiment 38 ``score_wordings.scorer("clefgguf", W1)`` path
(one request at a time) on the first 2,000 characters.
"""

from __future__ import annotations

import argparse
import statistics
import subprocess
import sys
import time
from importlib.metadata import version
from pathlib import Path

import llama_server
from exp42_io import (
    EXP38,
    EXP_DIR,
    OUTPUT,
    atomic_json,
    load_module,
    plan,
    read_json,
    sha256,
    text_sha256,
)

TARGETS = {"a": OUTPUT / "candidate_a.json", "clef": OUTPUT / "clef_flash.json"}
FAIL_SHARE = 0.01


def verify_freeze() -> None:
    """Require this experiment's freeze check to pass."""
    result = subprocess.run(  # noqa: S603
        [sys.executable, str(EXP_DIR / "freeze.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
        cwd=EXP_DIR,
    )
    if "freeze verified" not in result.stdout.splitlines():
        raise SystemExit("freeze check failed; no scoring")


def eligible() -> list[dict]:
    """Junk and healthy rows of both tiers, in document order."""
    return [
        r for r in read_json(OUTPUT / "labels.json")["rows"] if r["class"] in {"junk", "healthy"}
    ]


def page_text(doc_id: str, page: int, tier: str, expected: str, cache: dict) -> str:
    """Read one saved rescue page and check its hash."""
    if (doc_id, tier) not in cache:
        cache[(doc_id, tier)] = read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
    text = cache[(doc_id, tier)][page - 1]
    if text_sha256(text) != expected:
        raise SystemExit(f"saved text hash differs: {doc_id} p{page} {tier}")
    return text


def checkpoint(path: Path, identity: dict, resume: bool) -> dict:
    """Load or start a checkpoint bound to *identity*."""
    if not path.exists():
        return {"identity": identity, "completed_documents": [], "rows": [], "failed": []}
    if not resume:
        raise SystemExit(f"{path.name} exists: pass --resume")
    payload = read_json(path)
    if payload["identity"] != identity:
        raise SystemExit("checkpoint identity changed: resume refused")
    return payload


def run(arm: str, resume: bool) -> None:
    """Score one arm document by document."""
    current = plan()
    verify_freeze()
    rows = eligible()
    exp38_plan = read_json(EXP38 / "plan.json")
    if arm == "a":
        signal = EXP38 / "candidate_a.py"
        committed = read_json(EXP38 / "output" / "candidate_a.json")["identity"]["signal_sha256"]
        if sha256(signal) != committed or version("wordfreq") != "3.1.1":
            raise SystemExit("candidate A code or wordfreq pin differs from Experiment 38")
        rule = load_module(
            EXP38.parent / "33-ocr-routing-natural-positive-2026-09-17" / "build_labels.py",
            "exp33_rule",
        )
        module = load_module(signal, "exp38_candidate_a")
        identity = {"arm": "A", "signal_sha256": sha256(signal), "wordfreq": version("wordfreq")}

        def score(text: str) -> dict:
            started = time.perf_counter()
            result = module.score_a(text, rule)
            return {
                "score": result["score"],
                "A1": result["A1"],
                "A2": result["A2"],
                "wall_seconds": time.perf_counter() - started,
            }
    else:
        check = read_json(OUTPUT / "runtime_check.json")
        if not check["passed"]:
            raise SystemExit("runtime_check.json did not pass")
        static = llama_server.static_checks(current["arms"]["treatment"]["model_sha256"])
        if not all(c["pass"] for c in static.values()):
            raise SystemExit("static runtime check failed")
        hosted = load_module(EXP38 / "jev_hosted.py", "exp38_jev_hosted")
        wordings = load_module(EXP38 / "score_wordings.py", "exp38_score_wordings")
        scorer = wordings.scorer("clefgguf", exp38_plan["wordings"]["W1"], exp38_plan)
        identity = {
            "arm": "clef_flash_q8_0_w1",
            "client_sha256": {n: sha256(EXP38 / n) for n in ("score_wordings.py", "jev_hosted.py")},
            "build": static["llama_cpp_build"]["value"],
            "model_sha256": static["model_sha256"]["value"],
            "head_characters": hosted.HEAD_CHARACTERS,
            "batch": llama_server.BATCH,
        }

        def score(text: str) -> dict:
            return scorer([text[: hosted.HEAD_CHARACTERS]])[0]

    identity |= {
        "labels_sha256": sha256(OUTPUT / "labels.json"),
        "runner_sha256": sha256(Path(__file__)),
    }
    payload = checkpoint(TARGETS[arm], identity, resume)
    process = None
    if arm == "clef":
        process = llama_server.start(OUTPUT / "llamacpp_server_scoring.log")
        addresses = llama_server.listen_addresses(process.pid)
        if not addresses or not all(a.startswith("127.0.0.1:") for a in addresses):
            llama_server.stop(process)
            raise SystemExit(f"server not bound to 127.0.0.1 only: {addresses}")
    cache: dict = {}
    try:
        for doc_id in dict.fromkeys(r["doc_id"] for r in rows):
            if doc_id in payload["completed_documents"]:
                continue
            for row in (r for r in rows if r["doc_id"] == doc_id):
                text = page_text(doc_id, row["page"], row["tier"], row["text_sha256"], cache)
                try:
                    payload["rows"].append({**row, **score(text)})
                except RuntimeError as exc:
                    payload["failed"].append(
                        {k: row[k] for k in ("doc_id", "page", "tier")} | {"error": str(exc)[:200]}
                    )
            payload["completed_documents"].append(doc_id)
            atomic_json(TARGETS[arm], payload)
            print(
                f"[{arm}] {doc_id} ({len(payload['rows'])} scored, "
                f"{len(payload['failed'])} failed)",
                flush=True,
            )
            if len(payload["failed"]) > FAIL_SHARE * len(rows):
                raise SystemExit("more than 1% of requests failed: stop")
    finally:
        if process is not None:
            llama_server.stop(process)
    if arm == "clef":
        write_speed(payload)


def write_speed(payload: dict) -> None:
    """Task 5.3: D7 timing from the scoring run, two warm-up requests excluded."""
    times = [r["wall_seconds"] for r in payload["rows"]][2:]
    ordered = sorted(times)
    atomic_json(
        OUTPUT / "speed.json",
        {
            "method": "wall time per /v1/systemone request in the main scoring run, one request "
            "at a time (workers=1), first two requests excluded as warm-up, no OCR job running",
            "n": len(times),
            "mean_s": statistics.mean(times),
            "median_s": statistics.median(times),
            "p95_s": ordered[int(len(ordered) * 0.95) - 1],
        },
    )


def main() -> None:
    """Parse arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--arm", required=True, choices=sorted(TARGETS))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.arm, args.resume)


if __name__ == "__main__":
    main()
