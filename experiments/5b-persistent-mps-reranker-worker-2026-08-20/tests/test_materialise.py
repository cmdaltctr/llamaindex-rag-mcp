"""Fast tests for materialise (OpenSpec task 4.1) — RED until implemented.

Checks the fixed 512-word vocabulary and the deterministic schedule-row ->
request materialisation: identical rows produce identical text, different
seeds produce different text, candidate counts follow the stratum, and each
candidate carries approximately the stratum's word budget (±1).  Pure
stdlib; no model, no network.
"""

from __future__ import annotations

from _lazy_module import LazyModule

mat = LazyModule("materialise")  # RED (ModuleNotFoundError) until implemented

SCHEDULE_ROW = {
    "stratum_candidate_count": 10,
    "stratum_approx_tokens_per_candidate": 128,
    "request_index": 0,
    "text_materialisation_seed": 20260821,
    "burst_id": 0,
}


def another_row(**overrides) -> dict:
    row = dict(SCHEDULE_ROW)
    row.update(overrides)
    return row


# ── vocabulary ────────────────────────────────────────────────────────


def test_vocabulary_shape_and_determinism() -> None:
    assert mat.VOCAB_SIZE == 512
    assert mat.QUERY_WORDS == 8

    first = mat.build_vocabulary()
    second = mat.build_vocabulary()
    assert isinstance(first, tuple)
    assert first == second  # deterministic across calls
    assert len(first) == mat.VOCAB_SIZE
    assert len(set(first)) == mat.VOCAB_SIZE  # unique words
    assert all(isinstance(word, str) and word for word in first)


# ── materialisation determinism ───────────────────────────────────────


def test_materialise_deterministic_same_row() -> None:
    request_a = mat.materialise_request(dict(SCHEDULE_ROW))
    request_b = mat.materialise_request(dict(SCHEDULE_ROW))
    assert request_a == request_b


def test_materialise_different_seed_differs() -> None:
    base = mat.materialise_request(dict(SCHEDULE_ROW))
    altered = mat.materialise_request(another_row(text_materialisation_seed=1))
    assert base != altered


def test_materialise_request_shape() -> None:
    request = mat.materialise_request(dict(SCHEDULE_ROW))
    assert set(request) >= {"query", "candidates"}
    assert isinstance(request["query"], str) and request["query"]
    assert isinstance(request["candidates"], list)
    assert len(request["candidates"]) == SCHEDULE_ROW["stratum_candidate_count"]

    expected_ids = [
        f"r{SCHEDULE_ROW['request_index']}_c{i}"
        for i in range(SCHEDULE_ROW["stratum_candidate_count"])
    ]
    assert [c["doc_id"] for c in request["candidates"]] == expected_ids
    assert all(isinstance(c["text"], str) and c["text"] for c in request["candidates"])


def test_materialise_candidate_word_counts_match_stratum() -> None:
    target = SCHEDULE_ROW["stratum_approx_tokens_per_candidate"]
    request = mat.materialise_request(dict(SCHEDULE_ROW))
    for candidate in request["candidates"]:
        words = len(candidate["text"].split())
        assert target - 1 <= words <= target + 1, (
            f"doc_id {candidate['doc_id']!r}: {words} words vs target {target}"
        )


def test_materialise_candidate_count_follows_stratum() -> None:
    for count in (10, 25, 200):
        request = mat.materialise_request(another_row(stratum_candidate_count=count))
        assert len(request["candidates"]) == count
