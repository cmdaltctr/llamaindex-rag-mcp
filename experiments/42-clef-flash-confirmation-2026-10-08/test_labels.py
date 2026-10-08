"""Tasks 3.3 to 3.5: class boundaries, body-text rule and the junk-layer rule."""

from __future__ import annotations

import pytest
from build_labels import body_text, junk_text_layer, legibility
from exp42_io import EXP33, EXP38, load_module

RULE = load_module(EXP33 / "build_labels.py", "exp33_build_labels")
SCORING = load_module(EXP38 / "score_candidates.py", "exp38_score_candidates")
REFERENCE = [f"word{i:02d}" for i in range(100)]


def classify(found: int) -> str:
    """Class of a rescue text holding the first *found* of 100 reference tokens."""
    text = " ".join(REFERENCE[:found]) or "zz"
    return SCORING.classify_page(text, REFERENCE, "usable", RULE)["class"]


@pytest.mark.parametrize(
    ("found", "label"),
    [(1, "junk"), (49, "junk"), (50, "grey"), (79, "grey"), (80, "healthy"), (100, "healthy")],
)
def test_class_boundaries_at_050_and_080(found: int, label: str) -> None:
    assert classify(found) == label


def test_table_tags_are_not_reference_tokens() -> None:
    tokens = RULE.tokens(body_text("<table><tr><td>alpha</td></tr></table>"))
    assert tokens == ["alpha"]


def test_empty_reference_with_rescue_text_is_illegible() -> None:
    assert legibility([], [12, 0]) == "illegible"
    assert legibility([], [3, 9]) == "no_text"
    assert legibility(["alpha"], [12, 12]) is None


def test_junk_text_layer_needs_ten_percent_of_pages() -> None:
    assert junk_text_layer(2, 20)
    assert not junk_text_layer(1, 20)
