"""The Studio hybrid switch adds the same steps as the canonical template.

The web workspace turns hybrid retrieval on and off with a pure draft
transform (``web/src/studio/hybrid.ts``). It reads the steps and connections
to add from ``web/src/studio/hybridShape.json``. These tests compare that file
with the difference between the hybrid and the plain template graphs in
``omrg.pipeline_templates``. When a test fails, update the JSON file so that
it matches the template (studio-full-settings, design D1).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from omrg.pipeline_templates import _answer_graph, _search_graph

_SHAPE_FILE = Path(__file__).resolve().parents[2] / "web" / "src" / "studio" / "hybridShape.json"

_BUILDERS = {"search": _search_graph, "answer": _answer_graph}


def _shape() -> dict[str, Any]:
    assert _SHAPE_FILE.is_file(), f"Missing {_SHAPE_FILE}; the Studio hybrid switch reads it."
    return json.loads(_SHAPE_FILE.read_text(encoding="utf-8"))


def _graphs(name: str) -> tuple[dict[str, Any], dict[str, Any]]:
    build = _BUILDERS[name]
    return build(None, hybrid=False, rerank=True), build(None, hybrid=True, rerank=True)


def _edge_key(edge: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        edge["source"]["node"],
        edge["source"]["port"],
        edge["target"]["node"],
        edge["target"]["port"],
    )


@pytest.mark.parametrize("name", sorted(_BUILDERS))
def test_added_steps_match_template(name: str) -> None:
    shape = _shape()
    plain, hybrid = _graphs(name)
    plain_ids = {node["id"] for node in plain["nodes"]}
    added = {
        node["id"]: node["operation"] for node in hybrid["nodes"] if node["id"] not in plain_ids
    }
    expected = {step: shape["steps"][step] for step in shape["added"]}
    assert added == expected, f"Update {_SHAPE_FILE.name}: added steps differ from the template."


@pytest.mark.parametrize("name", sorted(_BUILDERS))
def test_added_connections_match_template(name: str) -> None:
    shape = _shape()
    plain, hybrid = _graphs(name)
    plain_edges = {_edge_key(edge) for edge in plain["edges"]}
    move = shape["move"]
    moved_from = (move["from"]["node"], move["from"]["port"])
    moved_to = (move["to"]["node"], move["to"]["port"])
    rewired = {(*moved_to, key[2], key[3]) for key in plain_edges if key[:2] == moved_from}
    added = {_edge_key(edge) for edge in hybrid["edges"]} - plain_edges
    expected = {_edge_key(edge) for edge in shape["edges"]} | rewired
    assert added == expected, (
        f"Update {_SHAPE_FILE.name}: added connections differ from the template."
    )


@pytest.mark.parametrize("name", sorted(_BUILDERS))
def test_only_moved_connections_are_removed(name: str) -> None:
    shape = _shape()
    plain, hybrid = _graphs(name)
    move = shape["move"]
    moved_from = (move["from"]["node"], move["from"]["port"])
    removed = {_edge_key(edge) for edge in plain["edges"]} - {
        _edge_key(edge) for edge in hybrid["edges"]
    }
    assert removed, "The hybrid template must move at least one connection."
    assert all(key[:2] == moved_from for key in removed), (
        f"Update {_SHAPE_FILE.name}: the move rule differs."
    )
    operations = {node["id"]: node["operation"] for node in hybrid["nodes"]}
    assert all(operations.get(step) == op for step, op in shape["steps"].items())
