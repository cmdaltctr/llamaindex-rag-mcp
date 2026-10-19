"""The in-house JSONC editor keeps comments and layout (task 4.1, design D4)."""

from __future__ import annotations

import copy
import json
import random
import re
from typing import Any

import pytest

from omrg.config.jsonc_edit import JsoncEditError, remove_value, set_value
from omrg.config.user_config import parse_jsonc

# ── Set an existing value ────────────────────────────────────────────────


def test_set_existing_value_changes_only_that_span() -> None:
    text = '{\n  // keep\n  "a": 1, // note\n  "b": "x" /* tail */\n}\n'
    out = set_value(text, ("a",), 2)
    assert out == '{\n  // keep\n  "a": 2, // note\n  "b": "x" /* tail */\n}\n'


def test_set_existing_nested_value() -> None:
    text = '{\n  "answer": {\n    "provider": "ollama",\n    "model": "m"\n  }\n}\n'
    out = set_value(text, ("answer", "model"), "claude-x")
    assert out == text.replace('"model": "m"', '"model": "claude-x"')


def test_set_replaces_a_whole_object_value_with_a_scalar() -> None:
    assert parse_jsonc(set_value('{"a": {"b": [1, {"c": 2}]}}', ("a",), 5)) == {"a": 5}


def test_strings_with_comment_markers_and_braces_do_not_confuse_the_scanner() -> None:
    text = '{\n  "u": "http://x//y /* } */",\n  "a": 1\n}\n'
    assert parse_jsonc(set_value(text, ("a",), 2)) == {"u": "http://x//y /* } */", "a": 2}


# ── Insert ───────────────────────────────────────────────────────────────


def test_insert_into_a_multiline_object_matches_the_indent() -> None:
    text = '{\n    "a": 1\n}\n'
    assert set_value(text, ("b",), "x") == '{\n    "a": 1,\n    "b": "x"\n}\n'


def test_insert_keeps_a_trailing_comma_style() -> None:
    text = '{\n  "a": 1,\n}\n'
    assert set_value(text, ("b",), 2) == '{\n  "a": 1,\n  "b": 2,\n}\n'


def test_insert_goes_before_a_closing_comment_and_after_a_same_line_note() -> None:
    text = '{\n  "a": 1 // note\n  // end\n}\n'
    out = set_value(text, ("b",), 2)
    assert out == '{\n  "a": 1, // note\n  "b": 2\n  // end\n}\n'


def test_insert_into_an_empty_multiline_object() -> None:
    assert set_value("{\n}\n", ("a",), 1) == '{\n  "a": 1\n}\n'


def test_insert_into_an_empty_inline_object() -> None:
    assert set_value("{}", ("a",), 1) == '{ "a": 1 }'


def test_insert_into_a_header_only_file() -> None:
    text = "// omrg settings\n{\n  // nothing yet\n}\n"
    out = set_value(text, ("a",), 1)
    assert out == '// omrg settings\n{\n  // nothing yet\n  "a": 1\n}\n'


def test_insert_into_an_inline_object_stays_inline() -> None:
    assert set_value('{ "a": 1 }', ("b",), 2) == '{ "a": 1, "b": 2 }'


def test_insert_creates_a_nested_object() -> None:
    text = '{\n  "a": 1\n}\n'
    out = set_value(text, ("retrieval", "top_k"), 7)
    assert out == '{\n  "a": 1,\n  "retrieval": {\n    "top_k": 7\n  }\n}\n'
    assert parse_jsonc(out) == {"a": 1, "retrieval": {"top_k": 7}}


def test_insert_into_an_existing_nested_object() -> None:
    text = '{\n  "answer": {\n    "provider": "ollama"\n  }\n}\n'
    out = set_value(text, ("answer", "model"), "m")
    assert out == '{\n  "answer": {\n    "provider": "ollama",\n    "model": "m"\n  }\n}\n'


def test_insert_creates_a_nested_object_inline() -> None:
    assert set_value("{}", ("retrieval", "top_k"), 7) == '{ "retrieval": { "top_k": 7 } }'


def test_crlf_files_keep_crlf() -> None:
    out = set_value('{\r\n  "a": 1\r\n}\r\n', ("b",), 2)
    assert out == '{\r\n  "a": 1,\r\n  "b": 2\r\n}\r\n'


def test_values_are_written_as_json() -> None:
    out = set_value("{}", ("a",), 'he said "hi" \\ é')
    assert parse_jsonc(out) == {"a": 'he said "hi" \\ é'}
    assert parse_jsonc(set_value("{}", ("on",), True)) == {"on": True}


# ── Remove ───────────────────────────────────────────────────────────────


def test_remove_a_middle_member_takes_its_line_and_comma() -> None:
    text = '{\n  "a": 1,\n  "b": 2,\n  "c": 3\n}\n'
    assert remove_value(text, ("b",)) == '{\n  "a": 1,\n  "c": 3\n}\n'


def test_remove_the_last_member_takes_the_comma_before_it() -> None:
    text = '{\n  "a": 1,\n  "b": 2\n}\n'
    assert remove_value(text, ("b",)) == '{\n  "a": 1\n}\n'


def test_remove_the_last_member_with_a_trailing_comma() -> None:
    text = '{\n  "a": 1,\n  "b": 2,\n}\n'
    assert remove_value(text, ("b",)) == '{\n  "a": 1,\n}\n'


def test_remove_the_only_member() -> None:
    assert remove_value('{\n  "a": 1\n}\n', ("a",)) == "{\n}\n"


def test_remove_inline_members() -> None:
    assert remove_value('{ "a": 1, "b": 2 }', ("b",)) == '{ "a": 1 }'
    assert remove_value('{ "a": 1, "b": 2 }', ("a",)) == '{ "b": 2 }'


def test_remove_keeps_every_comment() -> None:
    text = '{\n  // about a\n  "a": 1, // trailing a\n  "b": 2 /* b */\n}\n'
    out = remove_value(text, ("a",))
    for comment in ("// about a", "// trailing a", "/* b */"):
        assert comment in out
    assert parse_jsonc(out) == {"b": 2}


def test_remove_a_nested_member() -> None:
    text = '{\n  "answer": {\n    "provider": "o",\n    "model": "m"\n  }\n}\n'
    out = remove_value(text, ("answer", "model"))
    assert out == '{\n  "answer": {\n    "provider": "o"\n  }\n}\n'


def test_removing_the_last_member_of_a_block_removes_the_empty_block() -> None:
    text = '{\n  "a": 1,\n  "retrieval": {\n    "top_k": 7\n  }\n}\n'
    assert remove_value(text, ("retrieval", "top_k")) == '{\n  "a": 1\n}\n'


def test_a_block_with_a_comment_is_kept_when_emptied() -> None:
    text = '{\n  "retrieval": {\n    // tuned in May\n    "top_k": 7\n  }\n}\n'
    out = remove_value(text, ("retrieval", "top_k"))
    assert "// tuned in May" in out
    assert parse_jsonc(out) == {"retrieval": {}}


def test_remove_a_missing_key_changes_nothing() -> None:
    text = '{\n  "a": 1\n}\n'
    assert remove_value(text, ("zzz",)) == text
    assert remove_value(text, ("a", "b")) == text
    assert remove_value(text, ("x", "y")) == text


# ── Refusals ─────────────────────────────────────────────────────────────


def test_a_duplicate_target_key_is_refused() -> None:
    text = '{\n  "a": 1,\n  "a": 2\n}\n'
    with pytest.raises(JsoncEditError):
        set_value(text, ("a",), 3)
    with pytest.raises(JsoncEditError):
        remove_value(text, ("a",))


def test_a_duplicate_parent_key_is_refused() -> None:
    text = '{"r": {"x": 1}, "r": {"y": 2}}'
    with pytest.raises(JsoncEditError):
        set_value(text, ("r", "z"), 3)


def test_a_parent_that_is_not_an_object_is_refused() -> None:
    with pytest.raises(JsoncEditError):
        set_value('{"answer": "x"}', ("answer", "model"), "m")


def test_text_that_is_not_an_object_is_refused() -> None:
    for bad in ("[1]", '{"a": 1', "", "// only a comment\n", '{"a" 1}', "{ /* open"):
        with pytest.raises(JsoncEditError):
            set_value(bad, ("a",), 1)


def test_an_empty_path_is_refused() -> None:
    with pytest.raises(JsoncEditError):
        set_value("{}", (), 1)


# ── Property test: random edit sequences keep every comment ──────────────

FLAT = ("a", "b", "c", "d")
BLOCKS = ("retrieval", "answer")
LEAVES = ("x", "y", "z")


def render(rng: random.Random, model: dict[str, Any], counter: list[int]) -> str:
    """Render *model* as JSONC with random layout and fresh numbered comments."""
    multiline = rng.random() < 0.7
    unit = rng.choice(["  ", "    ", "\t"])

    def comment(kind: str) -> str:
        counter[0] += 1
        return f"{kind} c{counter[0]}" + (" */" if kind == "/*" else "")

    def body(obj: dict[str, Any], depth: int) -> str:
        pad = unit * (depth + 1)
        items = []
        for key, value in obj.items():
            text = f"{json.dumps(key)}: " + (
                body(value, depth + 1) if isinstance(value, dict) else json.dumps(value)
            )
            lead = f"{pad}{comment('//')}\n" if multiline and rng.random() < 0.3 else ""
            items.append((lead, text))
        if not items:
            return "{}"
        trailing = rng.random() < 0.3
        if not multiline:
            return "{ " + ", ".join(t for _, t in items) + " }"
        lines = []
        for i, (lead, text) in enumerate(items):
            comma = "," if i < len(items) - 1 or trailing else ""
            note = f" {comment('//')}" if rng.random() < 0.3 else ""
            lines.append(f"{lead}{pad}{text}{comma}{note}")
        return "{\n" + "\n".join(lines) + "\n" + unit * depth + "}"

    head = f"{comment('//')}\n" if rng.random() < 0.5 else ""
    return head + body(model, 0) + "\n"


def random_model(rng: random.Random) -> dict[str, Any]:
    model: dict[str, Any] = {}
    for key in rng.sample(FLAT, rng.randint(0, len(FLAT))):
        model[key] = rng.randint(0, 99)
    for block in rng.sample(BLOCKS, rng.randint(0, len(BLOCKS))):
        leaves = rng.sample(LEAVES, rng.randint(1, len(LEAVES)))
        model[block] = {leaf: rng.choice([rng.randint(0, 99), "s", True]) for leaf in leaves}
    return model


def apply_to_model(model: dict[str, Any], path: tuple[str, ...], value: Any, remove: bool) -> None:
    node = model
    for key in path[:-1]:
        node = node.setdefault(key, {}) if not remove else node.get(key, {})
    if remove:
        node.pop(path[-1], None)
    else:
        node[path[-1]] = value


COMMENT = re.compile(r"(?://[^\n]*|/\*.*?\*/)")


def without_empty_blocks(data: dict[str, Any]) -> dict[str, Any]:
    """An emptied block may stay (it holds a comment) or go; both are fine."""
    return {k: v for k, v in data.items() if v != {}}


def all_paths() -> list[tuple[str, ...]]:
    return [(k,) for k in FLAT] + [(b, leaf) for b in BLOCKS for leaf in LEAVES]


@pytest.mark.parametrize("seed", range(200))
def test_random_edits_keep_every_comment_and_the_data(seed: int) -> None:
    rng = random.Random(seed)  # noqa: S311 - a test generator, not a secret
    counter = [0]
    model = random_model(rng)
    text = render(rng, model, counter)
    comments = COMMENT.findall(text)
    for _ in range(12):
        path = rng.choice(all_paths())
        remove = rng.random() < 0.4
        value = rng.choice([rng.randint(0, 99), "s", False])
        before = text
        text = remove_value(text, path) if remove else set_value(text, path, value)
        apply_to_model(model, path, value, remove)
        assert without_empty_blocks(parse_jsonc(text)) == without_empty_blocks(model), (
            f"seed {seed}\n--- before\n{before}\n--- after\n{text}"
        )
        for comment in comments:
            assert comment in text, f"seed {seed}: lost {comment!r}\n{before}\n--- after\n{text}"


def test_an_edit_does_not_touch_the_input_object() -> None:
    model = {"a": 1}
    original = copy.deepcopy(model)
    set_value(json.dumps(model), ("b",), 2)
    assert model == original
