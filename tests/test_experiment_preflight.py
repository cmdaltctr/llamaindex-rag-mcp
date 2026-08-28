"""Fast tests for the Stage 4 shared preflight assertions (task 4.2)."""

from __future__ import annotations

import pytest
from experiments._lib.preflight import (
    PreflightError,
    assert_controlled_constant,
    assert_distinct_values,
    assert_manifest,
    assert_no_fallback,
    assert_parser_invoked_before_embeddings,
    assert_policy_rerank_mode,
    assert_policy_vector_store,
    evaluate_assertions,
    manifest_field,
)


def _manifest() -> dict:
    return {
        "retrieval": {"fetch_k": 100, "top_k": 50},
        "embedding": {"requested_provider": "ollama", "effective_provider": "ollama"},
        "reranker": {"requested_backend": "onnx", "effective_backend": "onnx"},
        "chunker": {"requested": "sentence", "effective": "sentence", "fallback_reason": None},
        "document_backend": {"requested": "auto", "effective": "auto"},
    }


def test_manifest_field_resolves_dotted_and_missing_paths() -> None:
    manifest = _manifest()

    assert manifest_field(manifest, "retrieval.fetch_k") == 100
    assert manifest_field(manifest, "retrieval.absent") is None
    assert manifest_field(manifest, "absent.entirely") is None


def test_evaluate_assertions_eq_ne_in_not_in() -> None:
    manifest = _manifest()

    assert (
        evaluate_assertions(
            manifest, [{"manifest_field": "retrieval.fetch_k", "operator": "eq", "expected": 100}]
        )
        == []
    )
    assert (
        "retrieval.fetch_k"
        in evaluate_assertions(
            manifest, [{"manifest_field": "retrieval.fetch_k", "operator": "eq", "expected": 50}]
        )[0]
    )

    assert (
        evaluate_assertions(
            manifest, [{"manifest_field": "retrieval.fetch_k", "operator": "ne", "expected": 50}]
        )
        == []
    )
    assert evaluate_assertions(
        manifest, [{"manifest_field": "retrieval.fetch_k", "operator": "ne", "expected": 100}]
    )

    levels = ["dense", "hybrid"]
    assert evaluate_assertions(
        manifest, [{"manifest_field": "retrieval.mode", "operator": "in", "expected": levels}]
    )
    manifest["retrieval"]["mode"] = "dense"
    assert (
        evaluate_assertions(
            manifest, [{"manifest_field": "retrieval.mode", "operator": "in", "expected": levels}]
        )
        == []
    )
    assert evaluate_assertions(
        manifest,
        [{"manifest_field": "retrieval.mode", "operator": "not_in", "expected": levels}],
    )


def test_evaluate_assertions_null_and_contains_operators() -> None:
    manifest = _manifest()

    not_null = {"manifest_field": "retrieval.fetch_k", "operator": "not_null"}
    is_null = {"manifest_field": "retrieval.absent", "operator": "is_null"}

    # not_null catches both an explicit None and a missing key.
    assert evaluate_assertions(manifest, [not_null]) == []
    assert evaluate_assertions(manifest, [is_null]) == []
    manifest["retrieval"]["absent"] = None
    assert evaluate_assertions(manifest, [not_null | {"manifest_field": "retrieval.absent"}])
    assert evaluate_assertions(manifest, [is_null]) == []
    manifest["retrieval"]["absent"] = "set"
    assert evaluate_assertions(manifest, [is_null])

    # contains works on lists and on strings.
    manifest["reranker"]["variants"] = ["onnx", "torch"]
    assert (
        evaluate_assertions(
            manifest,
            [{"manifest_field": "reranker.variants", "operator": "contains", "expected": "onnx"}],
        )
        == []
    )
    assert evaluate_assertions(
        manifest,
        [{"manifest_field": "reranker.variants", "operator": "contains", "expected": "cuda"}],
    )
    manifest["embedding"]["model"] = "gte-small-v1"
    assert (
        evaluate_assertions(
            manifest,
            [{"manifest_field": "embedding.model", "operator": "contains", "expected": "gte"}],
        )
        == []
    )
    assert evaluate_assertions(
        manifest,
        [{"manifest_field": "embedding.model", "operator": "contains", "expected": "bge"}],
    )


def test_evaluate_assertions_reports_unknown_operator() -> None:
    failures = evaluate_assertions(
        _manifest(),
        [{"manifest_field": "retrieval.fetch_k", "operator": "approximately", "expected": 100}],
    )

    assert len(failures) == 1
    assert "unknown operator" in failures[0]
    assert "approximately" in failures[0]


def test_assert_manifest_aggregates_all_failures() -> None:
    with pytest.raises(PreflightError) as excinfo:
        assert_manifest(
            _manifest(),
            [
                {"manifest_field": "retrieval.fetch_k", "operator": "eq", "expected": 50},
                {"manifest_field": "retrieval.top_k", "operator": "eq", "expected": 10},
            ],
        )

    message = str(excinfo.value)
    assert "retrieval.fetch_k" in message
    assert "retrieval.top_k" in message
    assert message.count("\n") == 1


def test_assert_no_fallback_accepts_clean_manifest() -> None:
    assert_no_fallback(_manifest())


def test_assert_no_fallback_names_each_fallback_field() -> None:
    # Reranker: requested onnx, effective torch.
    manifest = _manifest()
    manifest["reranker"]["effective_backend"] = "torch"
    with pytest.raises(PreflightError, match="reranker.requested_backend.*onnx.*torch"):
        assert_no_fallback(manifest)

    # Chunker: any recorded fallback reason.
    manifest = _manifest()
    manifest["chunker"]["fallback_reason"] = "codesplitter unavailable"
    with pytest.raises(PreflightError, match=r"chunker\.fallback_reason"):
        assert_no_fallback(manifest)

    # Document backend: auto resolved to a different effective reader.
    manifest = _manifest()
    manifest["document_backend"]["effective"] = "liteparse"
    with pytest.raises(PreflightError, match=r"document_backend\.requested.*auto.*liteparse"):
        assert_no_fallback(manifest)

    # Embedding provider mismatch.
    manifest = _manifest()
    manifest["embedding"]["effective_provider"] = "openai"
    with pytest.raises(PreflightError, match=r"embedding\.requested_provider.*ollama.*openai"):
        assert_no_fallback(manifest)


def test_assert_distinct_values_detects_collisions() -> None:
    with pytest.raises(PreflightError) as excinfo:
        assert_distinct_values({"a": 50, "b": 100, "c": 50}, "retrieval.fetch_k")

    message = str(excinfo.value)
    assert "retrieval.fetch_k" in message
    assert "'a'" in message and "'c'" in message
    assert "50" in message


def test_assert_distinct_values_accepts_all_distinct() -> None:
    assert_distinct_values({"a": 50, "b": 100, "c": 150}, "retrieval.fetch_k")


def test_assert_distinct_values_treats_none_as_collision() -> None:
    with pytest.raises(PreflightError, match="None"):
        assert_distinct_values({"a": None, "b": None}, "retrieval.fetch_k")


def test_assert_controlled_constant_accepts_identical_cells() -> None:
    manifests = {
        "cell_a": {"embedding": {"model": "bge-m3"}},
        "cell_b": {"embedding": {"model": "bge-m3"}},
    }

    assert_controlled_constant(manifests, ["embedding.model"])


def test_assert_controlled_constant_rejects_differing_values() -> None:
    manifests = {
        "cell_a": {"embedding": {"model": "bge-m3"}},
        "cell_b": {"embedding": {"model": "gte-small"}},
    }

    with pytest.raises(PreflightError) as excinfo:
        assert_controlled_constant(manifests, ["embedding.model"])

    message = str(excinfo.value)
    assert "embedding.model" in message
    assert "bge-m3" in message and "gte-small" in message
    assert "cell_a" in message and "cell_b" in message


def test_assert_controlled_constant_rejects_unobserved_field() -> None:
    manifests = {
        "cell_a": {"embedding": {"model": None}},
        "cell_b": {"embedding": {"model": None}},
    }

    with pytest.raises(PreflightError, match="must be observed"):
        assert_controlled_constant(manifests, ["embedding.model"])


def _parser_events() -> list[dict]:
    return [
        {"event": "parse_start", "parser": "pypdf", "timestamp": 1.0},
        {"event": "parse_end", "parser": "pypdf", "timestamp": 2.0},
        {"event": "parse_start", "parser": "liteparse", "timestamp": 3.0},
        {"event": "parse_end", "parser": "liteparse", "timestamp": 4.0},
        {"event": "embed_start", "parser": None, "timestamp": 5.0},
    ]


def test_assert_parser_invoked_before_embeddings_accepts_ordered_run() -> None:
    assert_parser_invoked_before_embeddings(_parser_events(), ["pypdf", "liteparse"])


def test_assert_parser_invoked_before_embeddings_rejects_missing_parser() -> None:
    with pytest.raises(PreflightError, match="docling"):
        assert_parser_invoked_before_embeddings(_parser_events(), ["pypdf", "liteparse", "docling"])


def test_assert_parser_invoked_before_embeddings_rejects_late_parser() -> None:
    events = [
        {"event": "parse_start", "parser": "pypdf", "timestamp": 1.0},
        {"event": "embed_start", "parser": None, "timestamp": 10.0},
        {"event": "parse_start", "parser": "liteparse", "timestamp": 12.0},
    ]

    with pytest.raises(PreflightError, match="liteparse"):
        assert_parser_invoked_before_embeddings(events, ["pypdf", "liteparse"])


def test_assert_parser_invoked_before_embeddings_rejects_undeclared_parser() -> None:
    events = _parser_events()
    events.append({"event": "parse_start", "parser": "magic", "timestamp": 6.0})

    with pytest.raises(PreflightError, match="undeclared parser.*magic"):
        assert_parser_invoked_before_embeddings(events, ["pypdf", "liteparse"])


def test_assert_policy_rerank_mode_accepts_recorded_none() -> None:
    assert_policy_rerank_mode({"retrieval": {"rerank_requested": None}})


@pytest.mark.parametrize("value", [True, False])
def test_assert_policy_rerank_mode_rejects_force_overrides(value: bool) -> None:
    with pytest.raises(PreflightError, match="rerank_requested"):
        assert_policy_rerank_mode({"retrieval": {"rerank_requested": value}})


def test_assert_policy_rerank_mode_rejects_absent_key() -> None:
    with pytest.raises(PreflightError, match="absent"):
        assert_policy_rerank_mode({"retrieval": {}})

    with pytest.raises(PreflightError, match="absent"):
        assert_policy_rerank_mode({})


def test_assert_policy_vector_store_accepts_lancedb_with_identity() -> None:
    """A qualified LanceDB row with an index identity passes (task 6.3)."""
    assert_policy_vector_store(
        {"vector_store": {"backend": "lancedb", "index_identity": "qual-doc-v1"}}
    )


def test_assert_policy_vector_store_accepts_declared_manipulated_factor() -> None:
    """A declared manipulated-factor row passes without an index identity."""
    assert_policy_vector_store({"vector_store": {"manipulated_factor": True}})


@pytest.mark.parametrize(
    ("manifest", "match"),
    [
        ({"vector_store": {"backend": "chroma", "index_identity": "x"}}, "LanceDB"),
        ({"vector_store": {"backend": "lancedb"}}, "index_identity"),
        ({}, "vector_store"),
    ],
)
def test_assert_policy_vector_store_rejects_unqualified_rows(manifest: dict, match: str) -> None:
    """Chroma, identity-less LanceDB, and absent records all fail closed."""
    with pytest.raises(PreflightError, match=match):
        assert_policy_vector_store(manifest)
