#!/usr/bin/env python3
"""Generate the committed namespace fixtures for Example Experiment 4.

Writes (deterministically, pure standard library):

- ``fixtures/docs.json`` — the namespace corpus: three stable documents
  per namespace (a rare mutually exclusive token carrier plus two
  fillers; three documents keep rare-token BM25 IDF positive), the
  direct-store mutation document, and the orchestration node with its
  precomputed embedding.
- ``fixtures/queries.json`` — the rare-token query battery.
- ``fixtures/qrels.json`` — the pre-registered expected outcomes: per
  (namespace, token) result ids with phase-dependent mutation states,
  exactly-once generation arithmetic per mutation type, cache-build
  expectations, and the zero stale-row rule.

Every rare token appears in exactly one document of one namespace —
validated at generation time so the protocol §13 abort criterion
("query token appears in more than its intended namespace") cannot be
triggered by the fixtures themselves.

Run from the repository root:

    uv run --no-sync python \\
        experiments/example/experiment-4-bm25-cache-isolation/make_fixtures.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SCRIPT_DIR / "fixtures"

DIM = 4


def _vec(index: int) -> list[float]:
    """Deterministic one-hot unit vector (never embedded, only stored)."""
    vector = [0.0] * DIM
    vector[index % DIM] = 1.0
    return vector


NAMESPACES: dict[str, dict[str, Any]] = {
    "A/documents": {
        "store": "A",
        "collection": "documents",
        "docs": {
            "a_d_alpha": {
                "text": "alpha_only calibration record for the A documents namespace.",
                "token": "alpha_only",
                "vector": _vec(0),
            },
            "a_d_f1": {"text": "background context filler passage one.", "vector": _vec(1)},
            "a_d_f2": {"text": "background context filler passage two.", "vector": _vec(2)},
        },
    },
    "B/documents": {
        "store": "B",
        "collection": "documents",
        "docs": {
            "b_d_beta": {
                "text": "beta_only calibration record for the B documents namespace.",
                "token": "beta_only",
                "vector": _vec(0),
            },
            "b_d_f1": {"text": "unrelated neutral filler passage three.", "vector": _vec(1)},
            "b_d_f2": {"text": "unrelated neutral filler passage four.", "vector": _vec(2)},
        },
    },
    "A/other": {
        "store": "A",
        "collection": "other",
        "docs": {
            "a_o_gamma": {
                "text": "gamma_only calibration record for the A other namespace.",
                "token": "gamma_only",
                "vector": _vec(0),
            },
            "a_o_f1": {"text": "quiet marginal filler passage five.", "vector": _vec(1)},
            "a_o_f2": {"text": "quiet marginal filler passage six.", "vector": _vec(2)},
        },
    },
}

MUTATION_DOCS: dict[str, Any] = {
    "direct_upsert": {
        "id": "a_d_delta",
        "namespace": "A/documents",
        "text": "delta_only mutation passage added by the direct store upsert.",
        "token": "delta_only",
        "vector": _vec(3),
        "metadata": {
            "namespace": "A/documents",
            "exp4_role": "temp_delta",
            "file_path": "exp4://A/documents/delta",
        },
        "delete_where": {"exp4_role": {"$eq": "temp_delta"}},
    },
    "orchestration_node": {
        "id": "orch_eps_1",
        "namespace": "A/documents",
        "text": "epsilon_only orchestration passage added via the ingestion writer.",
        "token": "epsilon_only",
        "vector": _vec(3),
        "metadata": {
            "namespace": "A/documents",
            "exp4_role": "orch_temp",
            "file_path": "exp4://orch/epsilon",
        },
        "remove_document_file_path": "exp4://orch/epsilon",
    },
}

RARE_TOKENS = ["alpha_only", "beta_only", "gamma_only", "delta_only", "epsilon_only"]


def _metadata_for(namespace: str, doc_id: str) -> dict[str, str]:
    return {
        "namespace": namespace,
        "exp4_role": "stable_token" if doc_id.endswith(("alpha", "beta", "gamma")) else "filler",
        "file_path": f"exp4://{namespace}/{doc_id}",
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)

    corpus: dict[str, Any] = {
        "dimension": DIM,
        "namespaces": {},
        "mutation_docs": MUTATION_DOCS,
    }
    for namespace, spec in NAMESPACES.items():
        corpus["namespaces"][namespace] = {
            "store": spec["store"],
            "collection": spec["collection"],
            "documents": [
                {
                    "id": doc_id,
                    "text": doc["text"],
                    "metadata": _metadata_for(namespace, doc_id),
                    "embedding": doc["vector"],
                }
                for doc_id, doc in sorted(spec["docs"].items())
            ],
        }

    # Fixture self-validation: every rare token lives in exactly one
    # document of one namespace, counting stable AND mutation
    # documents (protocol §13 abort guard).
    all_docs: dict[str, str] = {}
    for namespace, spec in NAMESPACES.items():
        for doc_id, doc in spec["docs"].items():
            all_docs[f"{namespace}:{doc_id}"] = doc["text"]
    for doc in MUTATION_DOCS.values():
        all_docs[f"{doc['namespace']}:{doc['id']}"] = doc["text"]
    carrier_by_token: dict[str, str] = {}
    for token in RARE_TOKENS:
        found = [key for key, text in all_docs.items() if token in text]
        if len(found) != 1:
            raise SystemExit(
                f"rare token {token!r} must appear in exactly one document; found {found}"
            )
        carrier_by_token[token] = found[0]

    queries = {
        token: {
            "query_id": f"token::{token}",
            "text": token,
            "carrier": carrier_by_token[token],
        }
        for token in RARE_TOKENS
    }

    stable_expected: dict[str, dict[str, list[str]]] = {}
    for token in ("alpha_only", "beta_only", "gamma_only"):
        stable_expected[token] = {
            namespace: (
                [doc_id for doc_id, doc in spec["docs"].items() if token in doc["text"]]
                if any(token in d["text"] for d in spec["docs"].values())
                else []
            )
            for namespace, spec in NAMESPACES.items()
        }
    qrels = {
        "namespaces": {
            namespace: {
                "store": spec["store"],
                "collection": spec["collection"],
                "stable_ids": sorted(spec["docs"]),
                "expected_generation_after_setup": 1,
            }
            for namespace, spec in NAMESPACES.items()
        },
        "stable_token_expected_ids": stable_expected,
        "mutation_token_expected_ids": {
            "delta_only": {
                "A/documents": {
                    "pre_mutation": [],
                    "post_direct_upsert": ["a_d_delta"],
                    "post_filtered_delete": [],
                },
                "B/documents": [],
                "A/other": [],
            },
            "epsilon_only": {
                "A/documents": {
                    "pre_orchestration": [],
                    "post_orchestration_write": ["orch_eps_1"],
                    "post_orchestration_remove": [],
                },
                "B/documents": [],
                "A/other": [],
            },
        },
        "generation_arithmetic": {
            "expected_delta_per_successful_mutation": 1,
            "mutations": [
                "setup upsert (per namespace)",
                "direct upsert_precomputed",
                "direct delete_where",
                "orchestration embed_and_write_async",
                "orchestration remove_document",
                "direct delete_collection",
                "recreate upsert_precomputed",
            ],
        },
        "cache_build_expectations": {
            "first_query_per_namespace": 1,
            "repeated_query_without_mutation": 0,
            "unaffected_namespace_after_mutation": 0,
            "affected_namespace_after_mutation": 1,
            "affected_namespace_after_collection_drop": 1,
            "affected_namespace_after_recreate": 1,
        },
        "stale_row_count_after_rebuild": 0,
        "contamination_tolerance": 0,
    }

    _write_json(FIXTURES_DIR / "docs.json", corpus)
    _write_json(FIXTURES_DIR / "queries.json", queries)
    _write_json(FIXTURES_DIR / "qrels.json", qrels)
    total = sum(len(n["documents"]) for n in corpus["namespaces"].values())
    print(f"wrote {total} stable documents across 3 namespaces + 2 mutation docs to {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
