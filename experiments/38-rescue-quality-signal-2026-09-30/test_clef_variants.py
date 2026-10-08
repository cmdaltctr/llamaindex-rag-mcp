"""Tests for the Clef-flash variant comparison."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))

from compare_clef_variants import compare, pearson  # noqa: E402


def rows(scores, seconds=0.5):
    return [
        {"doc_id": "d", "page": i, "tier": "liteparse", "score": s, "wall_seconds": seconds}
        for i, s in enumerate(scores)
    ]


def test_identical_scores_agree_perfectly():
    result = compare(rows([0.1, 0.5, 0.9, 0.3]), rows([0.1, 0.5, 0.9, 0.3]))
    assert result["pearson"] == pytest.approx(1.0)
    assert result["max_abs_diff"] == 0
    assert result["side_flips"] == 0


def test_largest_difference_and_threshold_count_are_reported():
    result = compare(rows([0.1, 0.5, 0.9, 0.3]), rows([0.1, 0.62, 0.9, 0.3]))
    assert result["max_abs_diff"] == pytest.approx(0.12)
    assert result["pages_over_0_10"] == 1


def test_a_page_crossing_one_half_counts_as_a_flip():
    result = compare(rows([0.45, 0.8, 0.2]), rows([0.55, 0.8, 0.2]))
    assert result["side_flips"] == 1


def test_local_pages_missing_from_hosted_are_left_out():
    hosted = rows([0.1, 0.9])
    local = rows([0.1, 0.9, 0.5, 0.7])
    assert compare(hosted, local)["pairs"] == 2


def test_common_keys_keeps_only_pages_every_run_scored():
    from compare_clef_variants import common_keys

    keys = common_keys(rows([0.1, 0.2, 0.3, 0.4]), rows([0.1, 0.2, 0.3]), rows([0.1, 0.2]))
    assert keys == {("d", 0, "liteparse"), ("d", 1, "liteparse")}


def test_pearson_detects_a_reversed_ranking():
    assert pearson([0.1, 0.5, 0.9], [0.9, 0.5, 0.1]) == pytest.approx(-1.0)


def test_by_wording_uses_only_complete_score_files(tmp_path, monkeypatch):
    import json

    import compare_clef_variants as ccv

    def write(name, scores, documents):
        body = {"completed_documents": [f"d{i}" for i in range(documents)], "rows": rows(scores)}
        (tmp_path / name).write_text(json.dumps(body))

    write("wording_clefflash_w1.json", [0.1, 0.9, 0.5], 40)
    write("wording_clefmlx_w1.json", [0.1, 0.9, 0.5], 40)
    write("wording_clefgguf_w1.json", [0.1, 0.9, 0.5], 12)
    monkeypatch.setattr(ccv, "OUTPUT", tmp_path)
    result = ccv.by_wording()
    assert set(result) == {"MLX 4-bit (I)"}
    assert result["MLX 4-bit (I)"]["W1"]["pairs"] == 3
