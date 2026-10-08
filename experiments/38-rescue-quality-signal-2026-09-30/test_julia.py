"""Synthetic tests for Julia's numpy request encoder and parity gate."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import numpy as np
import pytest
from tokenizers import Tokenizer, models, pre_tokenizers

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture
def julia():
    return importlib.import_module("julia_onnx")


@pytest.fixture
def tokenizer():
    words = [
        "<bos>",
        "<pad>",
        "<eos>",
        "<mask>",
        "noul",
        "question:",
        "readable",
        "no",
        "yes",
        "body",
        "<unk>",
    ]
    result = Tokenizer(
        models.WordLevel({word: i for i, word in enumerate(words)}, unk_token="<unk>")  # noqa: S106
    )
    result.pre_tokenizer = pre_tokenizers.WhitespaceSplit()
    return result


@pytest.fixture
def decision_request():
    return {"type": "noul", "question": "readable", "options": ["no", "yes"], "state": "body"}


def test_encoder_matches_reference_marker_order_and_padding(julia, tokenizer, decision_request):
    feed = julia.encode_request(tokenizer, decision_request)
    np.testing.assert_array_equal(
        feed["input_ids"], [[0, 4, 5, 6, 2, 3, 7, 3, 8, 2, 9, 2, 1, 1, 1, 1]]
    )
    np.testing.assert_array_equal(feed["marker_pos"], [[5, 7]])
    np.testing.assert_array_equal(feed["attention_mask"], [[1] * 12 + [0] * 4])
    np.testing.assert_array_equal(feed["qtype"], [2])
    assert feed["marker_mask"].dtype == np.bool_
    assert feed["input_ids"].dtype == np.int64


@pytest.mark.parametrize("field", ["state", "question"])
def test_strict_encoder_rejects_reserved_marker(julia, tokenizer, decision_request, field):
    decision_request[field] = "<mask>"
    with pytest.raises(ValueError, match="Reserved"):
        julia.encode_request(tokenizer, decision_request)


def test_strict_encoder_rejects_long_state_without_truncating(julia, tokenizer, decision_request):
    decision_request["state"] = "body " * 40
    with pytest.raises(ValueError, match="context budget"):
        julia.encode_request(tokenizer, decision_request, max_length=32, head_length=16)


def test_strict_encoder_rejects_lossy_option(julia, tokenizer, decision_request):
    decision_request["options"][0] = "no " * 49
    with pytest.raises(ValueError, match="48-token"):
        julia.encode_request(tokenizer, decision_request)


def test_strict_encoder_rejects_lossy_question(julia, tokenizer, decision_request):
    decision_request["question"] = "readable " * 600
    with pytest.raises(ValueError, match="head budget"):
        julia.encode_request(tokenizer, decision_request)


@pytest.mark.parametrize(
    "matches,total,error,expected",
    [
        (99, 100, 0.01, True),
        (98, 100, 0.0, False),
        (100, 99, 0.0, False),
        (100, 100, 0.01001, False),
        (100, 100, float("nan"), False),
    ],
)
def test_p0_bounds_are_unchanged(julia, matches, total, error, expected):
    assert julia.parity_passes(matches, total, error) is expected


def test_raw_yes_probability_does_not_round_display_values(julia):
    assert julia.yes_probability(np.array([0.0, 0.0])) == 0.5
    assert julia.yes_probability(np.array([0.0, 4.0])) == pytest.approx(0.9820137900)
