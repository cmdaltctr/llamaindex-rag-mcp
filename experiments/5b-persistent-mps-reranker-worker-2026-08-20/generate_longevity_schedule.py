#!/usr/bin/env python3
"""Deterministically regenerate the Experiment 5b heterogeneous longevity schedule.

The schedule is the immutable pre-registered input for longevity and
fragmentation evidence (protocol section 5).  It fixes request strata
(candidate count and approximate per-candidate token length) plus burst
grouping.  The harness materialises exact text deterministically from this
file using the recorded seeds; the JSON is the complete immutable content.

Protocol v1.1 amendment (2026-08-22): strata are filtered by the section 11
token-budget estimator (``ceil(utf-8 bytes / 4)``) applied to each
replicate's materialised text, replacing the v1.0 nominal ``count x tokens``
filter which assumed 1 word ~= 1 token.  The synthesised vocabulary averages
~2.04 estimated tokens per word, so strata 100x512 and 200x256 (and 200x512)
cannot fit the 65,536 budget and are excluded.  Seeds travel with each
(stratum, replicate) pair so the evaluated text equals the emitted text.

Run from the experiment directory:

    uv run --no-sync python generate_longevity_schedule.py

Output is byte-stable for a fixed ``SEED``.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

import materialise
import protocol_frames as pf

SEED = 20260821
MAX_TOKENS_PER_REQUEST = 65_536
CANDIDATE_COUNTS = (10, 25, 50, 100, 200)
TOKEN_LENGTHS = (32, 128, 256, 512)
REPLICATES_PER_STRATUM = 12
BURST_GROUPS = 8
BURST_DEPTH = 16
OUTPUT = Path(__file__).with_name("longevity_schedule.json")


def _estimated_budget(request: dict[str, object]) -> int:
    """Section 11 estimator on the materialised text for one request."""
    materialised = materialise.materialise_request({**request, "request_index": 0})
    return pf.request_token_budget(materialised["query"], materialised["candidates"])


def main() -> None:
    """Write the schedule JSON for the fixed seed."""
    strata = [(count, tokens) for count in CANDIDATE_COUNTS for tokens in TOKEN_LENGTHS]
    # Seeds travel with each (stratum, replicate) pair: assigned over the
    # full unshuffled pool, then carried through the shuffle and the stratum
    # filter, so every emitted request keeps the seed it was evaluated with.
    unshuffled = [
        (count, tokens) for count, tokens in strata for _ in range(REPLICATES_PER_STRATUM)
    ]
    requests: list[dict[str, object]] = [
        {
            "stratum_candidate_count": count,
            "stratum_approx_tokens_per_candidate": tokens,
            "text_materialisation_seed": SEED + i,
        }
        for i, (count, tokens) in enumerate(unshuffled)
    ]
    # Deterministic schedule generation only; never used for cryptography.
    rng = random.Random(SEED)  # noqa: S311
    rng.shuffle(requests)

    # Section 11 budget filter: a stratum is kept only when every replicate's
    # materialised text fits the token budget under the frame-guard estimator.
    failing_strata: set[tuple[int, int]] = set()
    for request in requests:
        stratum = (
            int(request["stratum_candidate_count"]),
            int(request["stratum_approx_tokens_per_candidate"]),
        )
        if stratum in failing_strata:
            continue
        if _estimated_budget(request) > MAX_TOKENS_PER_REQUEST:
            failing_strata.add(stratum)
    kept_strata = [s for s in strata if s not in failing_strata]
    requests = [
        request
        for request in requests
        if (
            int(request["stratum_candidate_count"]),
            int(request["stratum_approx_tokens_per_candidate"]),
        )
        not in failing_strata
    ]
    for index, request in enumerate(requests):
        request["request_index"] = index

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
            for count, tokens in kept_strata
        ],
        "replicates_per_stratum": REPLICATES_PER_STRATUM,
        "max_tokens_per_request": MAX_TOKENS_PER_REQUEST,
        "budget_filter": (
            "stratum kept only when every replicate's materialised text fits "
            "max_tokens_per_request under the protocol section 11 estimator "
            "(ceil of utf-8 bytes / 4); nominal count x token products are not "
            "used (protocol v1.1 amendment, 2026-08-22)"
        ),
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
    dropped = sorted(failing_strata)
    print(f"wrote {OUTPUT} with {total} requests from {len(kept_strata)} strata")
    print(f"dropped strata (over section 11 budget): {dropped}")


if __name__ == "__main__":
    main()
