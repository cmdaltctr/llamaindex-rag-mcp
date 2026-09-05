"""Run Experiment 10.1: DOC_SIMILARITY_THRESHOLD calibration.

Sweeps threshold values {0.70, 0.75, 0.80, 0.85, 0.90} and builds the document
graph for each, recording structural metrics (edge count, cluster count, mean
cluster size, modularity). Also samples 10 random edges per threshold for
manual false-positive rating.

Migrated to the v2 surface (add-chroma-cloud-backend): collection reads
go through the production VectorStore ABC (``CollectionReader`` from
``experiments/_lib/storage.py``) — no direct chromadb usage.  Works in
local and cloud Chroma modes.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from typing import Any

import networkx as nx
from dotenv import load_dotenv

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def _compute_modularity(graph: nx.Graph) -> float:
    """Compute Louvain modularity of the graph."""
    if graph.number_of_nodes() < 5 or graph.number_of_edges() == 0:
        return 0.0
    try:
        communities = nx.algorithms.community.louvain_communities(graph)
        return nx.algorithms.community.modularity(graph, communities)
    except Exception:
        return 0.0


def _community_stats(graph: nx.Graph) -> dict[str, Any]:
    """Compute community detection statistics."""
    if graph.number_of_nodes() < 5:
        return {
            "cluster_count": 1 if graph.number_of_nodes() > 0 else 0,
            "mean_cluster_size": graph.number_of_nodes(),
            "modularity": 0.0,
        }
    try:
        communities = list(nx.algorithms.community.louvain_communities(graph))
        sizes = [len(c) for c in communities]
        modularity = nx.algorithms.community.modularity(graph, communities)
        return {
            "cluster_count": len(communities),
            "mean_cluster_size": sum(sizes) / len(sizes) if sizes else 0.0,
            "modularity": round(modularity, 6),
        }
    except Exception as exc:
        return {
            "cluster_count": 0,
            "mean_cluster_size": 0.0,
            "modularity": 0.0,
            "error": str(exc),
        }


def _sample_edges_for_rating(
    graph: nx.Graph, threshold: float, n: int, seed: int
) -> list[dict[str, Any]]:
    """Sample n random similarity edges for manual rating."""
    rng = random.Random(seed)
    sim_edges = [
        (u, v, data) for u, v, data in graph.edges(data=True) if data.get("relation") == "similar"
    ]
    if len(sim_edges) <= n:
        sampled = sim_edges
    else:
        sampled = rng.sample(sim_edges, n)

    ratings = []
    for u, v, data in sampled:
        meta_u = graph.nodes[u].get("file_path", u)
        meta_v = graph.nodes[v].get("file_path", v)
        ratings.append(
            {
                "source": u,
                "target": v,
                "source_file": meta_u,
                "target_file": meta_v,
                "weight": data.get("weight", 0.0),
                "threshold": threshold,
                "rating": None,
            }
        )
    return ratings


def _evaluate_threshold(
    collection,
    threshold: float,
    seed: int,
) -> dict[str, Any]:
    """Build document graph at a given threshold and compute metrics."""
    from omrg.core.documents.doc_graph import build_document_graph

    started = time.perf_counter()
    graph = build_document_graph(collection, threshold=threshold)
    elapsed = time.perf_counter() - started

    stats = _community_stats(graph)
    edges_for_rating = _sample_edges_for_rating(graph, threshold, n=10, seed=seed)

    # Count edges by type
    edge_types: dict[str, int] = {}
    for _u, _v, data in graph.edges(data=True):
        relation = data.get("relation", "unknown")
        edge_types[relation] = edge_types.get(relation, 0) + 1

    return {
        "threshold": threshold,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
        "similarity_edge_count": edge_types.get("similar", 0),
        "metadata_edge_count": edge_types.get("category", 0) + edge_types.get("keyword", 0),
        "heading_edge_count": edge_types.get("heading_child", 0),
        "edge_types": edge_types,
        "cluster_count": stats["cluster_count"],
        "mean_cluster_size": round(stats["mean_cluster_size"], 2),
        "modularity": stats["modularity"],
        "build_time_seconds": round(elapsed, 4),
        "edges_for_rating": edges_for_rating,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Experiment 10.1: DOC_SIMILARITY_THRESHOLD calibration",
    )
    parser.add_argument("--experiment-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument(
        "--thresholds", nargs="+", type=float, default=[0.70, 0.75, 0.80, 0.85, 0.90]
    )
    parser.add_argument("--collection-name", default=None)
    parser.add_argument("--seed", type=int, default=20260629)
    args = parser.parse_args()

    load_dotenv(PROJECT_ROOT / ".env")
    exp_dir = args.experiment_dir.resolve()
    output_dir = exp_dir / "output"
    chroma_dir = output_dir / "chroma_mixed"

    if not chroma_dir.exists() and not os.getenv("CHROMA_MODE", "local") == "cloud":
        raise SystemExit(
            f"Chroma index not found: {chroma_dir}\n"
            f"Run build_corpus.py first:\n"
            f"  uv run python {exp_dir}/build_corpus.py"
        )

    from experiments._lib.storage import CollectionReader, experiment_storage_config

    model = os.getenv("EMBED_MODEL", "unknown")
    storage = experiment_storage_config(
        experiment_id="exp10-1",
        corpus="repo-mixed",
        provider="ollama",
        model=model,
        persist_dir=str(chroma_dir),
    )
    collection_name = args.collection_name or storage.collection_name
    store = storage.build_store()
    doc_count = store.count(collection_name)
    print(f"Collection '{collection_name}' has {doc_count} documents", flush=True)

    if doc_count < 50:
        raise SystemExit(f"Corpus too small: {doc_count} < 50 documents")

    results: list[dict[str, Any]] = []
    all_edges_for_rating: list[dict[str, Any]] = []

    for threshold in args.thresholds:
        print(f"Evaluating threshold={threshold:.2f}...", flush=True)
        reader = CollectionReader(store, collection_name)
        result = _evaluate_threshold(reader, threshold, seed=args.seed)
        results.append(result)
        all_edges_for_rating.extend(result["edges_for_rating"])
        print(
            f"  nodes={result['node_count']}, edges={result['edge_count']}, "
            f"sim_edges={result['similarity_edge_count']}, "
            f"clusters={result['cluster_count']}, "
            f"modularity={result['modularity']:.4f}",
            flush=True,
        )

    payload = {
        "experiment": "10.1-doc-similarity-threshold-calibration-2026-06-29",
        "created_at_unix": time.time(),
        "settings": {
            "thresholds": args.thresholds,
            "collection_name": collection_name,
            "seed": args.seed,
            "doc_count": doc_count,
            "embed_model": os.getenv("EMBED_MODEL"),
        },
        "results": results,
    }

    output_path = output_dir / "eval_results.json"
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Results saved to {output_path}", flush=True)

    # Write manual ratings template
    ratings_path = output_dir / "manual_ratings.json"
    ratings_template = {
        "instructions": "Rate each edge as 'meaningful' or 'noise' based on whether the two files are semantically related.",
        "edges": all_edges_for_rating,
    }
    ratings_path.write_text(
        json.dumps(ratings_template, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Manual ratings template saved to {ratings_path}", flush=True)
    print(f"Total edges to rate: {len(all_edges_for_rating)}", flush=True)


if __name__ == "__main__":
    main()
