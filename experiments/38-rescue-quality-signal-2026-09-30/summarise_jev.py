"""Summarise hosted Jev (arm C) beside A and Julia without touching the frozen verdict."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from experiment_io import OUTPUT, approved_plan, atomic_json, read_json, sha256, verify_freeze
from score_local_text import followup_metrics
from score_signals import eligible_rows, verify_coverage
from signal_stats import mcnemar
from summarise_eval import candidate_summary


def jev_summary(rows: list[dict], baseline: list[dict], labels: dict, costs: dict) -> dict:
    """Run the main operating-point summary on C; CPU time is not meaningful for an API call."""
    result = candidate_summary(
        [{**row, "cpu_seconds": 0.0} for row in rows], baseline, labels, costs
    )
    result.pop("timing", None)
    wall = [row["wall_seconds"] for row in rows]
    result["request_usage"] = {
        "pages_and_tiers": len(rows),
        "models": sorted({row["model"] for row in rows}),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "mean_wall_seconds_per_request": float(np.mean(wall)),
    }
    return result


def paired(
    first: list[dict], second: list[dict], first_summary: dict, second_summary: dict
) -> dict:
    """Exact one-sided McNemar for the second signal catching more junk, LiteParse tier."""
    pick = lambda rows: [row for row in rows if row["tier"] == "liteparse"]  # noqa: E731
    return mcnemar(
        pick(first),
        pick(second),
        first_summary["equal_cost_threshold"],
        second_summary["equal_cost_threshold"],
    )


def run(source: Path) -> None:
    """Require complete C scores, then save a separate post-verdict report."""
    plan = approved_plan()
    verify_freeze(source)
    summary = read_json(OUTPUT / "summary.json")
    rescue = read_json(OUTPUT / "rescue_text.json")
    labels = read_json(source / "labels.json")["documents"]
    baseline = read_json(source / "output" / "arm_sampled_baseline" / "routing.json")["rows"]
    scored = {name: read_json(OUTPUT / f"candidate_{name.lower()}.json") for name in "ABC"}
    expected = eligible_rows(rescue["rows"])
    for payload in scored.values():
        verify_coverage(expected, payload["rows"])
    c_rows = scored["C"]["rows"]
    result = jev_summary(c_rows, baseline, labels, plan["false_positive_cost"])
    result["g1_to_g3_pass_at_equal_cost"] = all(
        result["operating_points"]["equal_cost"]["gates"].values()
    )
    measured = {
        name: summary["candidates"][name]["operating_points"]["equal_cost"]["populations"][
            "liteparse"
        ]
        for name in "AB"
    }
    measured["C"] = result["operating_points"]["equal_cost"]["populations"]["liteparse"]
    junk = measured["C"]["junk_pages"]
    result["versus"] = {
        name: {
            "delta_junk_recall": (measured["C"]["junk_flagged"] - measured[name]["junk_flagged"])
            / junk,
            "mcnemar": paired(scored[name]["rows"], c_rows, summary["candidates"][name], result),
        }
        for name in "AB"
    }
    report = {
        "experiment": plan["experiment_id"],
        "amendment": "A3",
        "status": "post-verdict arm; main verdict in summary.json is unchanged",
        "main_verdict": summary["status"],
        "c": result,
        "artefact_sha256": {
            name: sha256(OUTPUT / name) for name in ("candidate_c.json", "summary.json")
        },
    }
    local = OUTPUT / "jev_local_text.json"
    if local.exists():
        payload = read_json(local)
        if len(payload["rows"]) != 464:
            raise ValueError("Jev local follow-up is incomplete")
        report["local_text_followup"] = followup_metrics(payload)["C"]
        report["artefact_sha256"]["jev_local_text.json"] = sha256(local)
    atomic_json(OUTPUT / "jev_summary.json", report)
    print("[jev summary] saved", flush=True)


def main() -> None:
    """Read source location argument."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    run(parser.parse_args().source_exp.resolve())


if __name__ == "__main__":
    main()
