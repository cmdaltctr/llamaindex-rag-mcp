#!/usr/bin/env python3
"""Deterministically regenerate the Experiment 5b heterogeneous longevity schedule.

The schedule is the immutable pre-registered input for longevity and
fragmentation evidence (protocol section 5).  It fixes request strata
(candidate count and approximate per-candidate token length) plus burst
grouping.  The harness materialises exact text deterministically from this
file using the recorded seeds; the JSON is the complete immutable content.

Run from the experiment directory:

    uv run --no-sync python generate_longevity_schedule.py

Output is byte-stable for a fixed ``SEED``.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

SEED = 20260821
MAX_TOKENS_PER_REQUEST = 65_536
CANDIDATE_COUNTS = (10, 25, 50, 100, 200)
TOKEN_LENGTHS = (32, 128, 256, 512)
REPLICATES_PER_STRATUM = 12
BURST_GROUPS = 8
BURST_DEPTH = 16
OUTPUT = Path(__file__).with_name("longevity_schedule.json")


def main() -> None:
    """Write the schedule JSON for the fixed seed."""
    strata = [
        (count, tokens)
        for count in CANDIDATE_COUNTS
        for tokens in TOKEN_LENGTHS
        if count * tokens <= MAX_TOKENS_PER_REQUEST
    ]
    # Deterministic schedule generation only; never used for cryptography.
    rng = random.Random(SEED)  # noqa: S311
    requests: list[dict[str, object]] = [
        {"stratum_candidate_count": count, "stratum_approx_tokens_per_candidate": tokens}
        for count, tokens in strata
        for _ in range(REPLICATES_PER_STRATUM)
    ]
    rng.shuffle(requests)
    for index, request in enumerate(requests):
        request["request_index"] = index
        request["text_materialisation_seed"] = SEED + index

    total = len(requests)
    burst_starts = [
        round(i * (total - BURST_DEPTH) / (BURST_GROUPS - 1)) for i in range(BURST_GROUPS)
    ]
    burst_of: dict[int, int] = {}
    for burst_id, start in enumerate(burst_starts):
        for offset in range(BURST_DEPTH):
            burst_of[start + offset] = burst_id
    for index, request in enumerate(requests):
        request["burst_id"] = burst_of.get(index)

    payload = {
        "schedule_seed": SEED,
        "total_requests": total,
        "strata": [
            {"candidate_count": count, "approx_tokens_per_candidate": tokens}
            for count, tokens in strata
        ],
        "replicates_per_stratum": REPLICATES_PER_STRATUM,
        "max_tokens_per_request": MAX_TOKENS_PER_REQUEST,
        "burst_groups": BURST_GROUPS,
        "burst_depth": BURST_DEPTH,
        "burst_window_starts": burst_starts,
        "materialisation_rule": (
            "harness synthesises query and candidate text from a fixed 512-word "
            "vocabulary using random.Random(text_materialisation_seed); word counts "
            "equal the stratum approximate token length (1 word ~= 1 token)"
        ),
        "requests": requests,
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT} with {total} requests from {len(strata)} strata")


if __name__ == "__main__":
    main()
