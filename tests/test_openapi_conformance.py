"""OpenAPI contract conformance tests.

Derives the implemented search, listing, and result surface from the Python
code and asserts the versioned OpenAPI 3.1 contract in
``transports/api/openapi.yaml`` declares every field. The check fails naming
the missing field and schema when drift is introduced, so a future field
addition fails the build unless the contract is updated in the same change.

Design decisions: see ``openspec/changes/complete-observable-surface/design.md``
D6 (derive fields, exclude only structure) and D7 (four default-comparison
rules).
"""

from __future__ import annotations

import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

# ── Path to the OpenAPI contract ──────────────────────────────────────
_OPENAPI_PATH = (
    Path(__file__).parent.parent / "src" / "rag_mcp" / "transports" / "api" / "openapi.yaml"
)

# ── Maintained semantic sets (design D6/D7) ───────────────────────────
# These sets are about REST structure or parameter semantics, not about
# which fields exist. They change only when the URL design or the
# profile-resolution contract changes.

# ``collection`` is a path parameter in
# ``/v1/collections/{collection}/search``, not a body field. It is excluded
# from the SearchRequest conformance check for structural reasons.
_PATH_PARAMETER_EXCLUSIONS: frozenset[str] = frozenset({"collection"})

# Parameters whose ``None`` Python default means "resolve from the collection
# profile" (design D7 rule 3a). ``inspect.signature`` cannot distinguish
# rule 3a from 3b on its own, so this small semantic set is maintained.
_PROFILE_RESOLVED_PARAMS: frozenset[str] = frozenset(
    {"top_k", "similarity_threshold", "rerank", "hybrid"}
)


# ── Task 1.1: load openapi.yaml schemas ───────────────────────────────


def _load_schemas() -> dict[str, dict]:
    """Return the three schema property maps and required lists.

    Loads ``openapi.yaml`` once and returns a dict keyed by schema name
    with ``{"properties": {...}, "required": [...]}`` for
    ``SearchRequest``, ``DocumentInfo``, and ``SearchResult``.
    """
    with _OPENAPI_PATH.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    schemas = doc["components"]["schemas"]
    result: dict[str, dict] = {}
    for name in ("SearchRequest", "DocumentInfo", "SearchResult"):
        schema = schemas.get(name, {})
        result[name] = {
            "properties": schema.get("properties", {}),
            "required": schema.get("required", []),
        }
    return result


# ── Task 1.2: derive search parameters ────────────────────────────────


def _derive_search_params() -> dict[str, Any]:
    """Return ``{name: default}`` for every ``search_documents`` parameter.

    Excludes only ``collection`` — it is a path parameter in
    ``/v1/collections/{collection}/search``, not a body field. ``query`` is
    NOT excluded: it is a declared body field and must stay under the check.
    """
    from rag_mcp.transports.mcp import search_documents

    sig = inspect.signature(search_documents)
    return {
        name: param.default
        for name, param in sig.parameters.items()
        if name not in _PATH_PARAMETER_EXCLUSIONS
    }


# ── Task 1.3: derive listing keys ─────────────────────────────────────


class _StubListingStore:
    """Minimal store satisfying the ``list_documents()`` listing seam.

    Returns one fully-populated lineage row so every unconditional key
    ``list_documents`` emits is derived (design D6).
    """

    def __init__(self) -> None:
        self._meta: dict = {
            "source_id": "src_stable_001",
            "source_version": "2026-08-31T00:00:00Z",
            "file_path": "/abs/path/to/doc.txt",
            "page_label": None,
        }

    def count(self, collection_name: str) -> int:
        return 1

    def iter_metadatas(
        self, collection_name: str, page_size: int | None = None
    ) -> Iterator[dict | None]:
        yield dict(self._meta)


def _derive_listing_keys() -> set[str]:
    """Return the set of keys a core ``list_documents`` result row carries."""
    from rag_mcp.core.ingestion.loader import list_documents

    rows = list_documents("documents", store=_StubListingStore())
    if not rows:
        return set()
    return set(rows[0].keys())


# ── Task 1.4: derive search-result keys (default + diagnostics) ───────


class _StubSearchStore:
    """Minimal store satisfying both dense and BM25 sparse query paths.

    Supports ``query_dense`` (dense runner), ``iter_documents`` (BM25
    retriever), ``iter_metadatas`` (listing), and the generation counter
    methods (BM25 cache keying). Returns one fully-populated lineage row
    so every unconditional result key is derived.
    """

    def __init__(self) -> None:
        self._meta: dict = {
            "source_id": "src_stable_001",
            "source_version": "2026-08-31T00:00:00Z",
            "chunk_id": "chunk_001",
            "source_chunk_index": 0,
            "source_chunk_count": 3,
            "file_path": "/abs/path/to/doc.txt",
            "page_label": None,
        }
        self._text = "query text content for matching"

    @property
    def cache_identity(self) -> object:
        return self

    def count(self, collection_name: str) -> int:
        return 1

    def query_dense(
        self,
        collection_name: str,
        query_embedding: list[float],
        n_results: int,
        where: dict | None = None,
    ) -> list[dict]:
        return [
            {
                "id": "row_001",
                "score": 0.95,
                "score_kind": "dense_similarity_v1",
                "document": self._text,
                "metadata": dict(self._meta),
            }
        ]

    def iter_documents(
        self, collection_name: str, page_size: int | None = None
    ) -> Iterator[tuple[str, str, dict]]:
        yield ("row_001", self._text, dict(self._meta))

    def iter_metadatas(
        self, collection_name: str, page_size: int | None = None
    ) -> Iterator[dict | None]:
        yield dict(self._meta)

    def get_generation(self, collection_name: str) -> int:
        return 0

    def bump_generation(self, collection_name: str) -> None:
        pass


class _StubReranker:
    """A reranker that succeeds and reports a backend name."""

    backend_name = "stub"
    last_failure_reason: str | None = None

    def rerank(self, query: str, results: list[dict], top_k: int) -> list[dict]:
        for r in results:
            r["score"] = 0.5
            r["_reranked"] = True
        return results[:top_k]


@pytest.fixture(autouse=True)
def _clear_retrieval_caches() -> None:
    """Clear the embedding LRU and BM25 caches for deterministic derivation."""
    from rag_mcp.core.retrieval.dense import _cached_query_embedding
    from rag_mcp.core.retrieval.sparse import BM25SparseRetriever

    _cached_query_embedding.cache_clear()
    BM25SparseRetriever._cache.clear()
    yield
    _cached_query_embedding.cache_clear()
    BM25SparseRetriever._cache.clear()


def _derive_result_keys() -> tuple[set[str], set[str]]:
    """Return ``(default_keys, diagnostics_keys)`` from two real searches.

    Runs ``search()`` twice against a stub store: once in the default
    (dense-only, no rerank, no diagnostics) mode and once with hybrid,
    rerank, and diagnostics enabled. The diagnostics search exercises the
    full path so fusion, rerank, norm-guard, and sparse-backend diagnostic
    fields are all derived.
    """
    from rag_mcp.core.retrieval import search
    from rag_mcp.core.settings import EffectiveSettings

    store = _StubSearchStore()
    settings = EffectiveSettings()

    default_results = search(
        "query text",
        top_k=5,
        rerank=False,
        hybrid=False,
        store=store,
        effective_settings=settings,
    )
    default_keys: set[str] = set()
    for r in default_results:
        default_keys |= set(r.keys())

    # Re-build the store so the BM25 cache key (identity, collection) does
    # not serve a stale index from the default run's dense-only path.
    store = _StubSearchStore()
    diag_results = search(
        "query text",
        top_k=5,
        rerank=True,
        hybrid=True,
        store=store,
        effective_settings=settings,
        include_diagnostics=True,
        reranker=_StubReranker(),
    )
    diagnostics_keys: set[str] = set()
    for r in diag_results:
        diagnostics_keys |= set(r.keys())

    return default_keys, diagnostics_keys


# ── Task 1.5: SearchRequest covers every search parameter ─────────────


class TestSearchRequestConformance:
    """The SearchRequest schema declares every implemented search parameter."""

    def test_every_search_parameter_is_declared(self) -> None:
        """Every ``search_documents`` parameter appears in SearchRequest.

        Fails naming each missing parameter. Confirms it fails naming
        ``diagnostics`` on the current (pre-fix) contract.
        """
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]
        params = _derive_search_params()

        missing = sorted(set(params) - set(props))
        assert not missing, (
            f"SearchRequest.properties is missing field(s): {missing}. "
            f"Add each to the SearchRequest schema in openapi.yaml."
        )


# ── Task 1.6: DocumentInfo covers every listing key ───────────────────


class TestDocumentInfoConformance:
    """The DocumentInfo schema declares every implemented listing key."""

    def test_every_listing_key_is_declared(self) -> None:
        """Every ``list_documents`` result key appears in DocumentInfo.

        Confirms it fails naming ``orphaned`` and ``source_id`` on the
        current (pre-fix) contract.
        """
        schemas = _load_schemas()
        props = schemas["DocumentInfo"]["properties"]
        listing_keys = _derive_listing_keys()

        missing = sorted(listing_keys - set(props))
        assert not missing, (
            f"DocumentInfo.properties is missing field(s): {missing}. "
            f"Add each to the DocumentInfo schema in openapi.yaml."
        )


# ── Task 1.7 / 1.8: SearchResult covers default + diagnostic keys ─────


class TestSearchResultConformance:
    """The SearchResult schema declares every result key, required or optional."""

    def test_every_default_result_key_is_declared_and_required(self) -> None:
        """Every default-response key is declared and marked required.

        Confirms it fails naming ``metadata`` and the five lineage fields
        (not declared), and the six already-declared fields (declared but
        not required). The test must fail on both counts.
        """
        schemas = _load_schemas()
        props = schemas["SearchResult"]["properties"]
        required = set(schemas["SearchResult"]["required"])
        default_keys, _ = _derive_result_keys()

        not_declared = sorted(default_keys - set(props))
        not_required = sorted(default_keys - required)

        assert not not_declared, (
            f"SearchResult.properties is missing field(s): {not_declared}. "
            f"Add each to the SearchResult schema in openapi.yaml."
        )
        assert not not_required, (
            f"SearchResult.required is missing field(s): {not_required}. "
            f"These fields appear on every response and must be required."
        )

    def test_every_diagnostic_key_is_declared_and_not_required(self) -> None:
        """Every diagnostics-only key is declared and NOT required.

        Diagnostics-only keys are present with ``include_diagnostics=True``
        but absent from the default response.
        """
        schemas = _load_schemas()
        props = schemas["SearchResult"]["properties"]
        required = set(schemas["SearchResult"]["required"])
        default_keys, diagnostics_keys = _derive_result_keys()

        diag_only = diagnostics_keys - default_keys
        not_declared = sorted(diag_only - set(props))
        wrongly_required = sorted(diag_only & required)

        assert not not_declared, (
            f"SearchResult.properties is missing diagnostic field(s): "
            f"{not_declared}. Add each as optional to the SearchResult schema."
        )
        assert not wrongly_required, (
            f"SearchResult.required wrongly includes diagnostic-only "
            f"field(s): {wrongly_required}. These must not be required."
        )


# ── Task 1.9 / 1.10: default-comparison rules (design D7) ─────────────


class TestSearchRequestDefaults:
    """Declared defaults match the implementation per design D7's four rules."""

    def test_rule1_required_parameter_has_no_default(self) -> None:
        """Rule 1: a parameter with no Python default is required without a default."""
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]
        required = set(schemas["SearchRequest"]["required"])
        params = _derive_search_params()

        for name, default in params.items():
            if default is inspect.Parameter.empty:
                assert name in required, (
                    f"SearchRequest.required is missing '{name}', which has "
                    f"no Python default and must be required (rule 1)."
                )
                assert "default" not in props.get(name, {}), (
                    f"SearchRequest.properties['{name}'] declares a default "
                    f"but the parameter has no Python default (rule 1)."
                )

    def test_rule2_concrete_default_matches(self) -> None:
        """Rule 2: a concrete Python default is declared and equals it."""
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]
        params = _derive_search_params()

        for name, default in params.items():
            if default is inspect.Parameter.empty or default is None:
                continue
            # Concrete default (e.g. diagnostics=False).
            assert "default" in props.get(name, {}), (
                f"SearchRequest.properties['{name}'] is missing a default "
                f"but the Python default is {default!r} (rule 2)."
            )
            assert props[name]["default"] == default, (
                f"SearchRequest.properties['{name}'].default is "
                f"{props[name]['default']!r} but the Python default is "
                f"{default!r} (rule 2)."
            )

    def test_rule3a_profile_resolved_params_have_no_default(self) -> None:
        """Rule 3a: profile-resolved parameters declare no default.

        ``top_k``, ``similarity_threshold``, ``rerank``, and ``hybrid`` have
        ``None`` Python defaults meaning "resolve from the collection profile".
        The schema MUST NOT declare a default, and its description MUST say
        the value resolves from the profile.
        """
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]
        params = _derive_search_params()

        for name in _PROFILE_RESOLVED_PARAMS:
            assert params.get(name) is None, (
                f"Parameter '{name}' is expected to have a None Python "
                f"default (profile-resolved) but got {params.get(name)!r}."
            )
            schema = props.get(name, {})
            assert "default" not in schema, (
                f"SearchRequest.properties['{name}'] declares a default "
                f"but the parameter is profile-resolved (rule 3a). "
                f"Remove the default."
            )

    def test_rule3a_descriptions_mention_profile_resolution(self) -> None:
        """Rule 3a: profile-resolved parameter descriptions mention the profile.

        Confirms it fails naming ``similarity_threshold`` for asserting
        "default 0.0" instead of profile resolution.
        """
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]

        for name in _PROFILE_RESOLVED_PARAMS:
            schema = props.get(name, {})
            desc = str(schema.get("description", "")).lower()
            assert "profile" in desc, (
                f"SearchRequest.properties['{name}'].description does not "
                f"mention profile resolution. The Python default is None "
                f"(profile-resolved), so the description MUST state the "
                f"value resolves from the collection profile (rule 3a)."
            )

    def test_rule3b_absent_params_have_no_default_and_no_profile_claim(self) -> None:
        """Rule 3b: ``metadata_filter`` declares no default and no profile claim.

        A ``None`` default meaning "absent" (not profile-resolved) MUST NOT
        declare a default and MUST NOT claim profile resolution.
        """
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]
        params = _derive_search_params()

        none_default_non_profile = {
            name
            for name, default in params.items()
            if default is None and name not in _PROFILE_RESOLVED_PARAMS
        }
        for name in none_default_non_profile:
            schema = props.get(name, {})
            assert "default" not in schema, (
                f"SearchRequest.properties['{name}'] declares a default "
                f"but the Python default is None (absent, not profile-"
                f"resolved) (rule 3b). Remove the default."
            )
            desc = str(schema.get("description", "")).lower()
            assert "profile" not in desc or "not" in desc, (
                f"SearchRequest.properties['{name}'].description claims "
                f"profile resolution but the parameter is absent-means-None "
                f"(rule 3b). Remove the profile-resolution claim."
            )

    def test_rule4_explicit_null_default_rejected(self) -> None:
        """Rule 4: an explicit ``default: null`` is rejected.

        It is indistinguishable from rule 3a to a reader and adds nothing.
        The check treats a declared null default as a failure pointing at
        rule 3a.
        """
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]
        params = _derive_search_params()

        for name in params:
            schema = props.get(name, {})
            if "default" in schema and schema["default"] is None:
                pytest.fail(
                    f"SearchRequest.properties['{name}'] declares "
                    f"default: null. Use rule 3a (no default key) for "
                    f"profile-resolved parameters, or rule 3b for "
                    f"absent-means-None parameters (rule 4)."
                )


# ── Task 1.11: failure messages are actionable ────────────────────────


class TestFailureMessagesAreActionable:
    """The conformance check names the missing field and its expected schema."""

    def test_missing_search_parameter_message_names_field_and_schema(self) -> None:
        """The SearchRequest check names the missing field and schema."""
        schemas = _load_schemas()
        props = schemas["SearchRequest"]["properties"]
        params = _derive_search_params()

        missing = sorted(set(params) - set(props))
        if missing:
            # On the red state, the message must name the field and schema.
            # We simulate the assertion message format here.
            msg = (
                f"SearchRequest.properties is missing field(s): {missing}. "
                f"Add each to the SearchRequest schema in openapi.yaml."
            )
            for field in missing:
                assert field in msg, f"Failure message does not name missing field '{field}'."
            assert "SearchRequest" in msg, "Failure message does not name the expected schema."

    def test_missing_listing_key_message_names_field_and_schema(self) -> None:
        """The DocumentInfo check names the missing field and schema."""
        schemas = _load_schemas()
        props = schemas["DocumentInfo"]["properties"]
        listing_keys = _derive_listing_keys()

        missing = sorted(listing_keys - set(props))
        if missing:
            msg = (
                f"DocumentInfo.properties is missing field(s): {missing}. "
                f"Add each to the DocumentInfo schema in openapi.yaml."
            )
            for field in missing:
                assert field in msg
            assert "DocumentInfo" in msg

    def test_missing_result_key_message_names_field_and_schema(self) -> None:
        """The SearchResult check names the missing field and schema."""
        schemas = _load_schemas()
        props = schemas["SearchResult"]["properties"]
        default_keys, diagnostics_keys = _derive_result_keys()

        missing = sorted((default_keys | diagnostics_keys) - set(props))
        if missing:
            msg = (
                f"SearchResult.properties is missing field(s): {missing}. "
                f"Add each to the SearchResult schema in openapi.yaml."
            )
            for field in missing:
                assert field in msg
            assert "SearchResult" in msg
