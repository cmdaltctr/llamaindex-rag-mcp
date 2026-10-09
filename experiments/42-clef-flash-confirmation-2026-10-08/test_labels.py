"""Tasks 3.3 to 3.5: class boundaries and the junk-layer rule."""

from __future__ import annotations

import pytest
from build_labels import junk_text_layer
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


@pytest.mark.parametrize("frozen", ["ambiguous", "unrecoverable"])
def test_ambiguous_or_unrecoverable_page_is_excluded(frozen: str) -> None:
    text = " ".join(REFERENCE)
    assert SCORING.classify_page(text, REFERENCE, frozen, RULE)["class"] == "excluded"


def test_junk_text_layer_needs_ten_percent_of_pages() -> None:
    assert junk_text_layer(2, 20)
    assert not junk_text_layer(1, 20)
