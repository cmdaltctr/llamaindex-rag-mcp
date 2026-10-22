"""Secret redaction, bounded previews and private artefacts (task 5.3)."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from omrs.core.workspace import (
    MAX_PREVIEW_ROWS,
    MAX_SUMMARY_BYTES,
    MAX_TEXT_BYTES,
    REDACTED,
    ArtefactStore,
    bound_preview,
    contains_secret,
    redact,
    redact_text,
    to_jsonable,
)

SECRET = "sk-test0123456789abcdefSECRET"  # noqa: S105 - fake credential


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


# --- redaction ----------------------------------------------------------------


@pytest.mark.parametrize(
    "key",
    [
        "api_key",
        "openrouter_api_key",
        "azure_doc_intelligence_key",
        "apiKey",
        "Authorization",
        "password",
        "client-secret",
        "access_token",
        "token",
        "credentials",
        "cookie",
    ],
)
def test_secret_keys_are_redacted(key: str) -> None:
    assert redact({"outer": {key: "value-123"}}) == {"outer": {key: REDACTED}}


@pytest.mark.parametrize("key", ["max_output_tokens", "top_k", "keyword_rules", "chunk_size"])
def test_ordinary_keys_are_kept(key: str) -> None:
    assert redact({key: 5}) == {key: 5}


@pytest.mark.parametrize(
    ("text", "leak"),
    [
        ("Authorization: Bearer abc.DEF-123_xyz", "abc.DEF-123_xyz"),
        ("https://user:hunter2@example.com/db", "hunter2"),
        ("postgres://admin:pw0rd@localhost:5432/x", "pw0rd"),
        ("https://api.example.com/v1?api_key=k123&q=ok", "k123"),
        ("https://api.example.com/v1?q=ok&token=t999", "t999"),
        (f"key is {SECRET} here", SECRET),
        ("hf_abcdefghijklmnopqrstuvwxyz", "hf_abcdefghijklmnopqrstuvwxyz"),
        ("ghp_abcdefghijklmnopqrstuvwxyz0123", "ghp_abcdefghijklmnopqrstuvwxyz0123"),
        ("AKIAABCDEFGHIJKLMNOP", "AKIAABCDEFGHIJKLMNOP"),
        ("password=s3cret!", "s3cret!"),
    ],
)
def test_secret_values_are_redacted_in_text(text: str, leak: str) -> None:
    cleaned = redact_text(text)
    assert leak not in cleaned
    assert REDACTED in cleaned
    assert contains_secret(text)


def test_plain_text_is_unchanged() -> None:
    text = "Token limits apply; see https://example.com/docs?q=bearer for max_output_tokens: 5"
    assert redact_text(text) == text
    assert not contains_secret(text)
    assert not contains_secret({"query": "what is a token?", "top_k": 3})


def test_redaction_walks_lists_and_keeps_types() -> None:
    value = {"items": [f"Bearer {SECRET}", 3, None, True, {"token": "x"}]}
    assert redact(value) == {"items": [f"Bearer {REDACTED}", 3, None, True, {"token": REDACTED}]}


# --- JSON conversion and bounds ---------------------------------------------


def test_to_jsonable_omits_vectors_and_converts_objects() -> None:
    value = {
        "embedding": [0.1] * 8,
        "nested": {"vectors": [[0.2] * 3]},
        "scores": [0.5] * 200,
        "path": Path("a/b"),
        "nan": float("nan"),
        "tuple": (1, 2),
    }
    converted = to_jsonable(value)
    assert converted["embedding"] == {"omitted": "vector data", "length": 8}
    assert converted["nested"]["vectors"] == {"omitted": "vector data", "length": 1}
    assert converted["scores"] == {"omitted": "vector data", "length": 200}
    assert converted["path"] == "a/b"
    assert converted["nan"] == "nan"
    assert converted["tuple"] == [1, 2]
    json.dumps(converted, allow_nan=False)


def test_long_text_is_truncated_to_four_kib() -> None:
    preview, truncated = bound_preview({"text": "é" * 5000})
    assert truncated
    assert MAX_TEXT_BYTES == 4096
    assert len(preview["text"].encode("utf-8")) <= MAX_TEXT_BYTES


def test_rows_are_limited_to_one_hundred() -> None:
    preview, truncated = bound_preview({"rows": list(range(250)), "small": [1, 2]})
    assert truncated
    assert MAX_PREVIEW_ROWS == 100
    assert preview["rows"] == list(range(100))
    assert preview["small"] == [1, 2]
    _, small_truncated = bound_preview({"rows": list(range(100))})
    assert not small_truncated


# --- private artefacts -------------------------------------------------------


def test_artefacts_are_owner_only(tmp_path: Path) -> None:
    store = ArtefactStore(tmp_path / "ws" / "artefacts")
    ref = store.write_json("run1", "result", {"answer": "x"})
    path = store.path(ref)
    assert path.is_relative_to(store.root)
    assert _mode(store.root) == 0o700
    assert _mode(path.parent) == 0o700
    assert _mode(path) == 0o600
    assert store.read_json(ref) == {"answer": "x"}
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("ref", ["../x.json", "run1/../../x.json", "/etc/passwd", "run1/a b"])
def test_artefact_references_cannot_escape_the_root(tmp_path: Path, ref: str) -> None:
    store = ArtefactStore(tmp_path / "artefacts")
    with pytest.raises(ValueError):
        store.path(ref)


@pytest.mark.parametrize(("run_id", "name"), [("../x", "a"), ("run", "../a"), ("", "a")])
def test_artefact_names_are_validated(tmp_path: Path, run_id: str, name: str) -> None:
    store = ArtefactStore(tmp_path / "artefacts")
    with pytest.raises(ValueError):
        store.write_json(run_id, name, {})


def test_safe_summary_keeps_small_values_inline(tmp_path: Path) -> None:
    store = ArtefactStore(tmp_path / "artefacts")
    summary = store.safe_summary("run1", "event", {"message": "ok", "count": 2})
    assert summary == {"message": "ok", "count": 2}
    assert not store.root.exists() or not any(store.root.iterdir())


def test_safe_summary_truncates_with_a_protected_reference(tmp_path: Path) -> None:
    store = ArtefactStore(tmp_path / "artefacts")
    text = "x" * 10_000
    summary = store.safe_summary("run1", "event", {"text": text, "token": SECRET})
    assert summary["truncated"] is True
    assert len(summary["text"]) == MAX_TEXT_BYTES
    assert summary["token"] == REDACTED
    full = store.read_json(summary["artefact_ref"])
    assert full["text"] == text
    assert full["token"] == REDACTED
    assert SECRET not in store.path(summary["artefact_ref"]).read_text()


def test_safe_summary_caps_total_size(tmp_path: Path) -> None:
    store = ArtefactStore(tmp_path / "artefacts")
    value = {f"field{i}": "y" * 3000 for i in range(20)}
    summary = store.safe_summary("run1", "event", value)
    assert summary["truncated"] is True
    assert len(json.dumps(summary).encode("utf-8")) <= MAX_SUMMARY_BYTES
    assert store.read_json(summary["artefact_ref"]) == value


def test_to_jsonable_serialises_graph_port_dataclasses() -> None:
    """Ranked-evidence style port values keep their rows, not a text dump."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class _Bundle:
        rows: tuple
        score_kind: str

        def public_rows(self) -> list[dict]:
            return [{"id": r["id"], "score": r["score"]} for r in self.rows]

    @dataclass(frozen=True)
    class _Evidence:
        rows: tuple
        reranked: bool

    internal = {"id": "c1", "score": 0.9, "_internal": 1, "embedding": [0.1] * 8}
    assert to_jsonable(_Bundle(rows=(internal,), score_kind="rrf_v1")) == {
        "rows": [{"id": "c1", "score": 0.9}],
        "score_kind": "rrf_v1",
    }
    evidence = to_jsonable(_Evidence(rows=(internal,), reranked=False))
    assert evidence["reranked"] is False
    assert evidence["rows"][0]["id"] == "c1"
    assert not isinstance(evidence["rows"][0]["embedding"], list)
