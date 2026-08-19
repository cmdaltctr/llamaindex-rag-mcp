"""Deterministic fixed-workload generator for Experiment 5.

Protocol section 9 (workload identity): the complete query/candidate
text workload is committed with its SHA-256 and never regenerated from
a different seed.  This script exists only to (a) build the committed
``workload.json`` once and (b) prove byte-level determinism afterwards
via ``--check``.

Workload shape (protocol section 3): 24 queries x 50 candidate
passages, mixing ordinary natural passages with deliberately
near-tied examples, pre-labelled by score-margin class (protocol
section 6): 8 wide, 8 medium, 8 near_tie.

Usage::

    uv run --no-sync python make_workload.py            # write workload.json
    uv run --no-sync python make_workload.py --check    # verify byte identity
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

SEED = 20260819
NUM_QUERIES = 24
CANDIDATES_PER_QUERY = 50
WORKLOAD_PATH = Path(__file__).resolve().parent / "workload.json"

# Field groups give "medium" cells a same-field-but-different-subtopic mix.
_FIELDS: dict[str, list[str]] = {
    "retrieval": [
        "dense retrieval",
        "sparse retrieval",
        "hybrid search",
        "query expansion",
        "relevance feedback",
    ],
    "infrastructure": [
        "vector databases",
        "caching",
        "batch inference",
        "model serving",
        "container orchestration",
    ],
    "machine_learning": [
        "cross-encoders",
        "quantisation",
        "distillation",
        "embedding models",
        "fine-tuning",
    ],
}

_TOPIC_SENTENCES = {
    "dense retrieval": "Dense retrieval maps queries and documents into a shared embedding space.",
    "sparse retrieval": "Sparse retrieval scores documents by exact term overlap statistics.",
    "hybrid search": "Hybrid search fuses dense and sparse rankings with reciprocal rank fusion.",
    "query expansion": "Query expansion adds synonyms to a query before retrieval runs.",
    "relevance feedback": "Relevance feedback adjusts the query vector using judged results.",
    "vector databases": "Vector databases store embeddings and answer nearest-neighbour queries.",
    "caching": "Caching keeps hot query results in memory to cut tail latency.",
    "batch inference": "Batch inference groups many requests into one model call.",
    "model serving": "Model serving exposes a trained model behind a stable endpoint.",
    "container orchestration": "Container orchestration schedules services across a cluster.",
    "cross-encoders": "A cross-encoder scores one query-document pair jointly.",
    "quantisation": "Quantisation stores weights in eight-bit integers to shrink models.",
    "distillation": "Distillation trains a small student model from a larger teacher.",
    "embedding models": "Embedding models compress text into fixed-length vectors.",
    "fine-tuning": "Fine-tuning adapts pretrained weights to a downstream task.",
}

_ALL_TOPICS = sorted(_TOPIC_SENTENCES)
_MARGIN_CLASSES = ("wide", "medium", "near_tie")

# Synonym pairs used to build near-tie perturbations: swapping one word
# keeps meaning (and reranker scores) close without changing the passage.
_SYNONYMS = {
    "maps": "projects",
    "scores": "ranks",
    "stores": "keeps",
    "answers": "serves",
    "adds": "appends",
    "exposes": "offers",
    "trains": "teaches",
    "compress": "encode",
    "cut": "reduce",
    "jointly": "together",
}


def _passage(rng: random.Random, topic: str) -> str:
    """Build one 2-3 sentence passage about *topic*."""
    body = _TOPIC_SENTENCES[topic]
    filler = [
        "Engineers measure the effect on latency and quality.",
        "The approach trades compute cost for accuracy.",
        "Teams deploy it behind an internal service boundary.",
        "Results vary with corpus size and query mix.",
        "Careful evaluation avoids overfitting to benchmarks.",
    ]
    tail = rng.choice(filler)
    prefix = rng.choice(["", "In practice, ", "Notably, "])
    return f"{prefix}{body} {tail}"


def _perturb(text: str, rng: random.Random) -> str:
    """Swap one synonym in *text* to create a near-tie candidate."""
    for word, synonym in sorted(_SYNONYMS.items()):
        if word in text:
            return text.replace(word, synonym, 1)
    # No synonym present: append a short neutral clause instead.
    return f"{text} This remains an active research area."


def _candidates_for(rng: random.Random, topic: str, margin_class: str) -> list[str]:
    """Build the fixed ordered candidate pool for one query.

    wide: one on-topic passage among 49 off-topic ones.
    medium: five same-field sibling topics mixed with off-topic ones.
    near_tie: ten perturbed near-duplicates of the on-topic passage.
    """
    field = next(f for f, members in _FIELDS.items() if topic in members)
    siblings = [t for t in _FIELDS[field] if t != topic]
    others = [t for t in _ALL_TOPICS if t != topic and t not in siblings]

    on_topic = _passage(rng, topic)
    texts: list[str] = [on_topic]

    if margin_class == "near_tie":
        # Ten perturbed near-duplicates of the same on-topic passage:
        # deliberately near-tied scores for precision-sensitivity probes.
        base = on_topic
        for _ in range(10):
            variant = _perturb(base, rng)
            base = variant
            texts.append(variant)
        rng.shuffle(others)
        for off in others[: CANDIDATES_PER_QUERY - len(texts)]:
            texts.append(_passage(rng, off))
    elif margin_class == "medium":
        rng.shuffle(siblings)
        for sibling in siblings:
            texts.append(_passage(rng, sibling))
        rng.shuffle(others)
        for off in others[: CANDIDATES_PER_QUERY - len(texts)]:
            texts.append(_passage(rng, off))
    else:  # wide
        rng.shuffle(others)
        for off in others[: CANDIDATES_PER_QUERY - 1]:
            texts.append(_passage(rng, off))

    # Deduplicate while preserving order, then pad from the filler pool if
    # near-tie perturbations collapsed into identical strings.
    seen: set[str] = set()
    unique: list[str] = []
    for text in texts:
        if text not in seen:
            seen.add(text)
            unique.append(text)
    filler_idx = 0
    while len(unique) < CANDIDATES_PER_QUERY:
        candidate = _passage(rng, others[filler_idx % len(others)])
        filler_idx += 1
        if candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique[:CANDIDATES_PER_QUERY]


def build_workload() -> dict[str, object]:
    """Return the complete fixed workload structure (deterministic)."""
    queries: list[dict[str, object]] = []
    topic_cycle = _ALL_TOPICS * 2  # 24 queries over 15 topics
    for i in range(NUM_QUERIES):
        margin_class = _MARGIN_CLASSES[i % 3]
        topic = topic_cycle[i]
        rng = random.Random(f"{SEED}:q{i:03d}")  # noqa: S311 — workload synthesis, not crypto
        query_text = f"What is {topic}?"
        candidates = _candidates_for(rng, topic, margin_class)
        queries.append(
            {
                "query_id": f"q{i:03d}",
                "text": query_text,
                "topic": topic,
                "margin_class": margin_class,
                "candidates": [
                    {"doc_id": f"q{i:03d}_c{j:02d}", "text": text}
                    for j, text in enumerate(candidates)
                ],
            }
        )
    return {
        "workload_version": "1.0",
        "generator": "make_workload.py (committed; seed 20260819)",
        "model_id": "cross-encoder/ms-marco-MiniLM-L-6-v2",
        "num_queries": NUM_QUERIES,
        "candidates_per_query": CANDIDATES_PER_QUERY,
        "margin_class_counts": {
            name: sum(1 for q in queries if q["margin_class"] == name) for name in _MARGIN_CLASSES
        },
        "queries": queries,
    }


def serialise(workload: dict[str, object]) -> str:
    """Canonical byte serialisation (sorted keys, fixed indentation)."""
    return json.dumps(workload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed workload.json regenerates byte-identically",
    )
    args = parser.parse_args()
    payload = serialise(build_workload())
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    if args.check:
        if not WORKLOAD_PATH.exists():
            print("FAIL: workload.json is missing", file=sys.stderr)
            return 1
        current = WORKLOAD_PATH.read_text(encoding="utf-8")
        if current != payload:
            print(
                "FAIL: workload.json does not match the deterministic generator",
                file=sys.stderr,
            )
            return 1
        print(f"OK: workload.json byte-identical (sha256:{digest})")
        return 0

    tmp = WORKLOAD_PATH.with_suffix(".json.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(WORKLOAD_PATH)
    print(f"wrote {WORKLOAD_PATH} (sha256:{digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
