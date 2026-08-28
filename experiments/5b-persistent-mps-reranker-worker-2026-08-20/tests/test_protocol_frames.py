"""Fast tests for protocol_frames (OpenSpec task 4.1).

Pure stdlib contract checks against the committed module: encode/decode
round-trips, both-direction size bounds, malformed input classes, every
validator's happy path and each violation class, error-frame guards and
the registered token estimator.  No network, no model, no torch.
"""

from __future__ import annotations

import json

import protocol_frames as pf


def _valid_hello() -> dict:
    return {
        "type": "hello",
        "protocol_version": pf.PROTOCOL_VERSION,
        "pid": 4242,
        "python_version": "3.12.10",
    }


def _valid_ready() -> dict:
    return {
        "type": "ready",
        "protocol_version": pf.PROTOCOL_VERSION,
        "pid": 4242,
        "model_id": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "model_revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        "model_file_sha256": {
            "config.json": "a" * 64,
            "model.safetensors": "b" * 64,
        },
        "stack_versions": {"python": "3.12.10", "torch": "2.9.1"},
        "requested_device": "mps",
        "effective_device": "mps:0",
        "mps_available": True,
        "pytorch_enable_mps_fallback": "0",
    }


def _valid_rerank(n_candidates: int = 2) -> dict:
    return {
        "type": "rerank",
        "request_id": 7,
        "generation": 0,
        "query": "probe query",
        "candidates": [
            {"doc_id": f"c{i}", "text": f"passage number {i}"} for i in range(n_candidates)
        ],
        "top_k": 5,
    }


def _valid_result() -> dict:
    return {
        "type": "result",
        "request_id": 7,
        "generation": 0,
        "model_id": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "model_revision": "233902d25c440f23af6f7d6e94d2946bac0bee0a",
        "backend": "torch",
        "device": "cpu",
        "reranked": True,
        "ranking": ["c1", "c0"],
        "scores": {"c1": 0.9, "c0": 0.1},
        "inference_ms": 1.5,
    }


# ── encode/decode round-trip and size bounds ──────────────────────────


def test_encode_decode_round_trip() -> None:
    """A frame survives encode -> decode unchanged."""
    frame = _valid_result()
    decoded = pf.decode_frame(pf.encode_frame(frame))
    assert decoded == frame


def test_encode_oversized_rejected() -> None:
    """Encoding a frame above MAX_FRAME_BYTES raises FrameError."""
    huge = {
        "type": "hello",
        "protocol_version": "1.0",
        "pid": 1,
        "python_version": "x" * (pf.MAX_FRAME_BYTES + 1024),
    }
    try:
        pf.encode_frame(huge)
        raise AssertionError("oversized frame must raise")
    except pf.FrameError as exc:
        assert "oversized" in str(exc)


def test_decode_oversized_rejected_before_parsing() -> None:
    """An oversized line is rejected on size alone, even when not JSON."""
    line = b"x" * (pf.MAX_FRAME_BYTES + 100)
    try:
        pf.decode_frame(line)
        raise AssertionError("oversized line must raise")
    except pf.FrameError as exc:
        assert "oversized" in str(exc)


def test_decode_malformed_json_rejected() -> None:
    """Non-JSON input raises a malformed FrameError."""
    for bad in (b"this-is-not-json{", b'{"type": "hello",}', b""):
        try:
            pf.decode_frame(bad)
            raise AssertionError(f"{bad!r} must raise")
        except pf.FrameError as exc:
            assert "malformed" in str(exc)


def test_decode_non_object_root_rejected() -> None:
    """JSON roots other than objects are malformed frames."""
    for bad in (b"[1, 2, 3]", b'"a string"', b"42", b"true", b"null"):
        try:
            pf.decode_frame(bad)
            raise AssertionError(f"root {bad!r} must raise")
        except pf.FrameError as exc:
            assert "malformed" in str(exc)


def test_decode_unknown_or_missing_type_rejected() -> None:
    """Frames must carry a registered type."""
    for bad in ({}, {"type": "mystery"}, {"type": 7}):
        try:
            pf.decode_frame(json.dumps(bad).encode())
            raise AssertionError(f"{bad!r} must raise")
        except pf.FrameError as exc:
            assert "unknown frame type" in str(exc)


# ── validate_hello ────────────────────────────────────────────────────


def test_validate_hello_happy() -> None:
    assert pf.validate_hello(_valid_hello()) == []


def test_validate_hello_violations() -> None:
    bad = _valid_hello() | {"protocol_version": "0.9", "pid": 0}
    errors = pf.validate_hello(bad)
    assert any("protocol_version" in e for e in errors)
    assert any("pid" in e for e in errors)

    errors = pf.validate_hello(_valid_hello() | {"pid": "7"})
    assert any("pid" in e for e in errors)
    errors = pf.validate_hello(_valid_hello() | {"python_version": ""})
    assert any("python_version" in e for e in errors)
    errors = pf.validate_hello(_valid_hello() | {"type": "ready"})
    assert any("type" in e for e in errors)


# ── validate_ready ────────────────────────────────────────────────────


def test_validate_ready_happy() -> None:
    assert pf.validate_ready(_valid_ready()) == []


def test_validate_ready_violations() -> None:
    base = _valid_ready()

    errors = pf.validate_ready(base | {"protocol_version": "2.0"})
    assert any("protocol_version" in e for e in errors)

    errors = pf.validate_ready(base | {"model_revision": ""})
    assert any("model_revision" in e for e in errors)

    # wrong-length digest values are rejected (64 characters required)
    bad_digests = dict(base["model_file_sha256"])
    bad_digests["config.json"] = "a" * 63
    errors = pf.validate_ready(base | {"model_file_sha256": bad_digests})
    assert any("model_file_sha256" in e for e in errors)
    bad_digests["config.json"] = 42
    errors = pf.validate_ready(base | {"model_file_sha256": bad_digests})
    assert any("model_file_sha256" in e for e in errors)
    errors = pf.validate_ready(base | {"model_file_sha256": {}})
    assert any("model_file_sha256" in e for e in errors)

    errors = pf.validate_ready(base | {"stack_versions": {}})
    assert any("stack_versions" in e for e in errors)

    errors = pf.validate_ready(base | {"requested_device": ""})
    assert any("requested_device" in e for e in errors)

    errors = pf.validate_ready(base | {"mps_available": "yes"})
    assert any("mps_available" in e for e in errors)

    # fallback policy must be exactly the string "0"
    errors = pf.validate_ready(base | {"pytorch_enable_mps_fallback": "1"})
    assert any("pytorch_enable_mps_fallback" in e for e in errors)


# ── validate_rerank ───────────────────────────────────────────────────


def test_validate_rerank_happy() -> None:
    assert pf.validate_rerank(_valid_rerank()) == []
    assert pf.validate_rerank(_valid_rerank(n_candidates=200)) == []


def test_validate_rerank_candidate_count_bound() -> None:
    errors = pf.validate_rerank(_valid_rerank(n_candidates=201))
    assert any("exceeds" in e and "200" in e for e in errors)


def test_validate_rerank_token_budget_bound() -> None:
    frame = _valid_rerank(n_candidates=8)
    for candidate in frame["candidates"]:
        candidate["text"] = "z" * 40_000  # 8 x 40_000 bytes / 4 = 80_000 tokens
    errors = pf.validate_rerank(frame)
    assert any("token budget" in e and "exceeds" in e for e in errors)


def test_validate_rerank_duplicate_doc_id() -> None:
    frame = _valid_rerank()
    frame["candidates"][1]["doc_id"] = frame["candidates"][0]["doc_id"]
    errors = pf.validate_rerank(frame)
    assert any("duplicates doc_id" in e for e in errors)


def test_validate_rerank_bad_request_id_and_empty_candidates() -> None:
    errors = pf.validate_rerank(_valid_rerank() | {"request_id": -1})
    assert any("request_id" in e for e in errors)
    errors = pf.validate_rerank(_valid_rerank() | {"request_id": True})
    assert any("request_id" in e for e in errors)
    errors = pf.validate_rerank(_valid_rerank() | {"candidates": []})
    assert any("not be empty" in e for e in errors)


def test_validate_rerank_bad_top_k() -> None:
    for bad in (0, -3, True, "5", 2.5):
        errors = pf.validate_rerank(_valid_rerank() | {"top_k": bad})
        assert any("top_k" in e for e in errors), f"top_k={bad!r} must be rejected"


def test_validate_rerank_bad_query_rejected() -> None:
    """A non-string query is reported as a violation."""
    errors = pf.validate_rerank(_valid_rerank() | {"query": 42})
    assert any("query must be a string" in e for e in errors)


# ── validate_result ───────────────────────────────────────────────────


def test_validate_result_happy() -> None:
    assert pf.validate_result(_valid_result()) == []


def test_validate_result_violations() -> None:
    base = _valid_result()

    errors = pf.validate_result(base | {"reranked": "yes"})
    assert any("reranked" in e for e in errors)

    # ranking/scores cardinality mismatch
    errors = pf.validate_result(base | {"ranking": ["c1", "c0", "c2"]})
    assert any("cardinality" in e for e in errors)

    errors = pf.validate_result(base | {"model_id": ""})
    assert any("model_id" in e for e in errors)

    errors = pf.validate_result(base | {"inference_ms": -0.1})
    assert any("inference_ms" in e for e in errors)

    errors = pf.validate_result(base | {"ranking": ["c1", 7]})
    assert any("ranking" in e for e in errors)

    errors = pf.validate_result(base | {"generation": "0"})
    assert any("generation" in e for e in errors)


# ── error_frame ───────────────────────────────────────────────────────


def test_error_frame_unknown_code_raises() -> None:
    try:
        pf.error_frame(1, "not_a_registered_code", "boom")
        raise AssertionError("unknown error code must raise")
    except pf.FrameError as exc:
        assert "unknown error code" in str(exc)


def test_error_frame_shape_and_detail_truncation() -> None:
    frame = pf.error_frame(None, "malformed_frame", "d" * 5000)
    assert frame["type"] == "error"
    assert frame["request_id"] is None
    assert frame["code"] == "malformed_frame"
    assert len(frame["detail"]) == 2000
    # every registered code round-trips through encode/decode
    for code in (
        "malformed_frame",
        "oversized_frame",
        "unknown_frame",
        "duplicate_request",
        "wrong_generation",
        "late_response",
        "bound_violation",
        "model_error",
        "stub_behaviour",
    ):
        assert pf.decode_frame(pf.encode_frame(pf.error_frame(3, code, "x")))


# ── token estimator ───────────────────────────────────────────────────


def test_estimate_tokens_known_values() -> None:
    assert pf.estimate_tokens("") == 1  # max(1, ceil(0/4))
    assert pf.estimate_tokens("abcd") == 1
    assert pf.estimate_tokens("abcde") == 2
    assert pf.estimate_tokens("a" * 100) == 25
    assert pf.estimate_tokens("😀") == 1  # 4 utf-8 bytes
    assert pf.estimate_tokens("Ω" * 3) == 2  # 6 utf-8 bytes


def test_request_token_budget_sums_query_and_candidates() -> None:
    budget = pf.request_token_budget(
        "abcd",  # 1 token
        [{"text": "a" * 8}, {"text": "b" * 9}],  # 2 + 3 tokens
    )
    assert budget == 6


# ── read_jsonl ────────────────────────────────────────────────────────


def test_read_jsonl_round_trip(tmp_path) -> None:
    path = tmp_path / "rows.jsonl"
    rows = [_valid_result(), _valid_hello()]
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n\n", encoding="utf-8")
    assert pf.read_jsonl(path) == rows
