"""Fixed-string tests for the preregistered deterministic quality signal."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))


@pytest.fixture
def candidate():
    return importlib.import_module("candidate_a")


@pytest.fixture
def rule():
    from experiment_io import load_token_rule

    return load_token_rule(EXP.parent / "33-ocr-routing-natural-positive-2026-09-17")


def test_clean_spanish_scores_at_least_point_eight(candidate, rule):
    result = candidate.score_a(
        "El estudiante lee un libro en la biblioteca de la universidad.", rule
    )
    assert result["score"] >= 0.8
    assert result["score"] == min(result["A1"], result["A2"])


def test_mixed_cjk_latin_junk_scores_below_point_five(candidate, rule):
    assert candidate.score_a("龘齉麤 漢謎 zzqxxv qqxzz", rule)["score"] < 0.5


def test_real_word_ratio_counts_each_frozen_token(candidate):
    assert candidate.real_word_ratio(["the", "the", "qzxqzxqz"]) == pytest.approx(2 / 3)


def test_script_consistency_counts_letters_only(candidate):
    assert candidate.script_consistency("ab αβвг 123 !?")[0] == pytest.approx(1 / 3)


def test_common_and_inherited_are_excluded(candidate):
    assert candidate.script_consistency("abー\u0345")[0] == 1.0


@pytest.mark.parametrize("text", ["हिन्दी", "বাংলা", "مرحبا", "தமிழ்", "Հայերեն"])
def test_script_consistency_supports_unicode_scripts(candidate, text):
    assert candidate.script_consistency(text)[0] == 1.0


def test_no_letters_or_tokens_scores_zero(candidate, rule):
    result = candidate.score_a(" ! ", rule)
    assert result["A1"] == result["A2"] == result["score"] == 0.0


def test_frequency_boundary_is_at_least_one(candidate):
    from wordfreq import zipf_frequency

    word = "zipf"
    expected = float(any(zipf_frequency(word, lang) >= 1.0 for lang in candidate.LANGUAGES))
    assert candidate.real_word_ratio([word]) == expected
