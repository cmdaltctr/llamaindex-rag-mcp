"""Task 3.1 check: Experiment 33 documents cannot enter the set."""

from __future__ import annotations

from exp42_io import EXP33, EXP_DIR, read_json
from prepare_corpus import exp33_exclusions, is_excluded

EXP33_DOCS = read_json(EXP33 / "sources.json")["documents"]


def test_known_exp33_hash_is_excluded() -> None:
    assert is_excluded(EXP33_DOCS[0]["sha256"], "new-id", exp33_exclusions())


def test_known_exp33_identifier_is_excluded() -> None:
    assert is_excluded("0" * 64, EXP33_DOCS[-1]["source_identifier"].upper(), exp33_exclusions())


def test_new_document_is_kept() -> None:
    assert not is_excluded("0" * 64, "never-seen-identifier", exp33_exclusions())


def test_frozen_set_has_no_exp33_overlap() -> None:
    path = EXP_DIR / "sources.json"
    if not path.exists():
        return
    exclusions = exp33_exclusions()
    for doc in read_json(path)["documents"]:
        assert not is_excluded(doc["sha256"], doc["source_identifier"], exclusions)
