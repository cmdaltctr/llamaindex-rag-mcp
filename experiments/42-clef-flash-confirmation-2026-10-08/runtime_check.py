"""Tasks 4.2 and 4.3: runtime checks and the 40-page Experiment 38 reproduction.

Writes output/runtime_check.json. Any failed check exits non-zero; scoring
(score_clef.py) refuses to start unless every check passed.

    uv run --no-sync python runtime_check.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

import llama_server
from exp42_io import EXP38, OUTPUT, V3_EXP38, atomic_json, load_module, plan, read_json

TOLERANCE = 0.01


def reproduction_pages() -> list[dict]:
    """The 40 fixed Experiment 38 speed pages (measure_speed.py rule)."""
    rows = read_json(V3_EXP38 / "output" / "wording_clefflash_w1.json")["rows"]
    return [r for r in rows if r["tier"] == "liteparse"][::16][:40]


def main() -> int:
    """Run every D7 check; stop at the first failure."""
    current = plan()
    checks = llama_server.static_checks(current["arms"]["treatment"]["model_sha256"])
    result = {"utc": datetime.now(UTC).isoformat(timespec="seconds"), "checks": checks}
    target = OUTPUT / "runtime_check.json"
    if not all(c["pass"] for c in checks.values()):
        atomic_json(target, {**result, "passed": False})
        print("static runtime check failed", flush=True)
        return 1
    hosted = load_module(EXP38 / "jev_hosted.py", "exp38_jev_hosted")
    wordings = load_module(EXP38 / "score_wordings.py", "exp38_score_wordings")
    exp38_plan = read_json(EXP38 / "plan.json")
    process = llama_server.start(OUTPUT / "llamacpp_server.log")
    try:
        addresses = llama_server.listen_addresses(process.pid)
        checks["bind"] = {
            "value": addresses,
            "pass": bool(addresses) and all(a.startswith("127.0.0.1:") for a in addresses),
        }
        checks["concurrency"] = {
            "value": "score_many(workers=1) for clefgguf (Experiment 38 score_wordings.scorer)",
            "pass": hosted.OPENJEV_ENDPOINT == "http://127.0.0.1:3000/v1/systemone",
        }
        score = wordings.scorer("clefgguf", exp38_plan["wordings"]["W1"], exp38_plan)
        committed = {
            (r["doc_id"], r["page"], r["tier"]): r["score"]
            for r in read_json(EXP38 / "output" / "wording_clefgguf_w1.json")["rows"]
        }
        sample = reproduction_pages()
        texts = {}
        for r in sample:
            if r["doc_id"] not in texts:
                texts[r["doc_id"]] = read_json(
                    V3_EXP38 / "output" / ".rescue_text" / r["doc_id"] / "liteparse.json"
                )
        heads = [texts[r["doc_id"]][r["page"] - 1][: hosted.HEAD_CHARACTERS] for r in sample]
        scores = score(heads)
        diffs = [
            {
                "doc_id": r["doc_id"],
                "page": r["page"],
                "committed": committed[(r["doc_id"], r["page"], "liteparse")],
                "now": s["score"],
            }
            for r, s in zip(sample, scores, strict=True)
        ]
        worst = max(abs(d["committed"] - d["now"]) for d in diffs)
        checks["reproduction"] = {
            "pages": len(diffs),
            "max_abs_difference": worst,
            "tolerance": TOLERANCE,
            "rows": diffs,
            "pass": len(diffs) == 40 and worst <= TOLERANCE,
        }
    finally:
        llama_server.stop(process)
    passed = all(c["pass"] for c in checks.values())
    atomic_json(target, {**result, "passed": passed})
    for name, check in checks.items():
        print(f"{name}: {'pass' if check['pass'] else 'FAIL'}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
