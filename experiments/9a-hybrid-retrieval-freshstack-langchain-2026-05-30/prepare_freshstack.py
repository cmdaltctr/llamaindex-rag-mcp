"""Prepare FreshStack LangChain data for Experiment 9a.

The experiment keeps the exported corpus under ``corpus/`` and writes result
artefacts under ``output/``.  The corpus export is metadata preserving: every
FreshStack parent document is represented as Markdown front matter and also as
a JSONL manifest consumed by the direct Chroma ingestion helper.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_SEED = 20260530


IDENTIFIER_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("backtick_code", re.compile(r"`[^`\n]{2,}`")),
    ("slash_path", re.compile(r"\b[\w.-]+/[\w./-]+\b")),
    ("dotted_path", re.compile(r"\b[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\b")),
    ("camel_case", re.compile(r"\b[a-z]+[A-Z][A-Za-z0-9]*\b")),
    ("snake_case", re.compile(r"\b[A-Za-z]+_[A-Za-z0-9_]+\b")),
    ("all_caps_constant", re.compile(r"\b[A-Z][A-Z0-9_]{2,}\b")),
    ("exception_or_error", re.compile(r"\b[A-Za-z_]*(?:Exception|Error)\b")),
    ("version_string", re.compile(r"\bv?\d+(?:\.\d+){1,3}\b")),
    (
        "explicit_package_or_api",
        re.compile(
            r"(?:@langchain|langchain\.js|langchain_[a-z0-9_]+|"
            r"llama_index|pydantic|fastapi|chromadb|ChromaDB|OpenAI|"
            r"ChatOpenAI|JSONLoader|DirectoryLoader|VectorStore|Retriever)",
            re.IGNORECASE,
        ),
    ),
]


def _safe_name(doc_id: str, index: int) -> str:
    digest = hashlib.sha1(doc_id.encode("utf-8")).hexdigest()[:12]
    return f"{index:05d}_{digest}.md"


def _yaml_scalar(value: Any) -> str:
    text = "" if value is None else str(value)
    return json.dumps(text, ensure_ascii=False)


def _write_markdown(path: Path, metadata: dict[str, Any], text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            lines.append(f"{key}: {value}")
        else:
            lines.append(f"{key}: {_yaml_scalar(value)}")
    lines.extend(["---", "", text.rstrip(), ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def _combined_query(row: dict[str, Any]) -> str:
    title = (row.get("query_title") or "").strip()
    body = (row.get("query_text") or "").strip()
    return f"{title}\n\n{body}".strip()


def _identifier_hits(text: str) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for name, pattern in IDENTIFIER_RULES:
        seen: set[str] = set()
        for match in pattern.finditer(text):
            token = match.group(0)
            if token not in seen:
                hits.append({"rule": name, "match": token[:160]})
                seen.add(token)
            if len(seen) >= 8:
                break
    return hits


def _extract_qrels(query_rows: list[dict[str, Any]]) -> tuple[list[dict], set[str]]:
    queries: list[dict] = []
    all_relevant: set[str] = set()
    for row in query_rows:
        nuggets: list[dict] = []
        query_relevant: set[str] = set()
        for nugget in row.get("nuggets") or []:
            relevant = list(nugget.get("relevant_corpus_ids") or [])
            non_relevant = list(nugget.get("non_relevant_corpus_ids") or [])
            query_relevant.update(relevant)
            all_relevant.update(relevant)
            nuggets.append({
                "nugget_id": nugget.get("_id"),
                "text": nugget.get("text"),
                "relevant_corpus_ids": relevant,
                "non_relevant_corpus_ids": non_relevant,
            })

        text = _combined_query(row)
        hits = _identifier_hits(text)
        queries.append({
            "query_id": str(row.get("query_id")),
            "query_title": row.get("query_title") or "",
            "query_text": row.get("query_text") or "",
            "query": text,
            "answer_id": str(row.get("answer_id")),
            "answer_text": row.get("answer_text") or "",
            "metadata": row.get("metadata") or {},
            "category": "identifier-heavy" if hits else "semantic",
            "identifier_rule_hits": hits,
            "relevant_parent_ids": sorted(query_relevant),
            "nuggets": nuggets,
            "source_kind": "freshstack-query",
        })
    return queries, all_relevant


def _load_exp9_continuity(exp9_dir: Path) -> tuple[list[dict], list[dict]]:
    gt_path = exp9_dir / "ground-truth.json"
    corpus_dir = exp9_dir / "corpus"
    if not gt_path.exists() or not corpus_dir.exists():
        return [], []

    with gt_path.open(encoding="utf-8") as f:
        exp9_gt = json.load(f)

    docs: list[dict] = []
    seen_files: set[str] = set()
    for query in exp9_gt.get("queries", []):
        source = query.get("expected_source")
        if not source or source in seen_files:
            continue
        matches = list(corpus_dir.rglob(source))
        if not matches:
            continue
        path = matches[0]
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        doc_id = f"continuity/{source}"
        docs.append({
            "_id": doc_id,
            "text": text,
            "metadata": {
                "url": str(path),
                "start_byte": 0,
                "end_byte": len(text.encode("utf-8")),
            },
            "source_kind": "continuity-parent",
            "original_file": source,
        })
        seen_files.add(source)

    queries: list[dict] = []
    for idx, query in enumerate(exp9_gt.get("queries", []), start=1):
        source = query.get("expected_source")
        if not source:
            continue
        doc_id = f"continuity/{source}"
        nugget_id = f"continuity_{idx:03d}"
        queries.append({
            "query_id": nugget_id,
            "query_title": query.get("query"),
            "query_text": "",
            "query": query.get("query"),
            "answer_id": None,
            "answer_text": query.get("expected_answer"),
            "metadata": {"named_case": query.get("named_case")},
            "category": "continuity",
            "identifier_rule_hits": [],
            "relevant_parent_ids": [doc_id],
            "nuggets": [{
                "nugget_id": nugget_id,
                "text": query.get("expected_answer") or query.get("query"),
                "relevant_corpus_ids": [doc_id],
                "non_relevant_corpus_ids": [],
            }],
            "source_kind": "continuity-query",
            "named_case": query.get("named_case"),
        })
    return docs, queries


def _select_corpus_ids(
    corpus_ids: list[str],
    qrel_ids: set[str],
    *,
    min_parent_docs: int,
    max_parent_docs: int | None,
    prefer_full_corpus: bool,
    seed: int,
) -> tuple[list[str], dict[str, Any]]:
    available = set(corpus_ids)
    required = sorted(qrel_ids & available)
    missing = sorted(qrel_ids - available)

    if prefer_full_corpus and max_parent_docs is None:
        return list(corpus_ids), {
            "selection_mode": "full-corpus",
            "rng_seed": seed,
            "missing_qrel_ids": missing,
        }

    target = max_parent_docs or min_parent_docs
    target = max(target, min_parent_docs, len(required))
    distractor_pool = [doc_id for doc_id in corpus_ids if doc_id not in set(required)]
    rng = random.Random(seed)
    rng.shuffle(distractor_pool)
    selected = required + distractor_pool[: max(0, target - len(required))]
    return selected, {
        "selection_mode": "qrels-plus-distractors-subset",
        "rng_seed": seed,
        "target_parent_docs": target,
        "required_qrel_docs": len(required),
        "sampled_distractors": max(0, len(selected) - len(required)),
        "missing_qrel_ids": missing,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", default="langchain")
    parser.add_argument("--queries-repo", default="freshstack/queries-oct-2024")
    parser.add_argument("--corpus-repo", default="freshstack/corpus-oct-2024")
    parser.add_argument("--output-dir", type=Path, default=SCRIPT_DIR)
    parser.add_argument("--min-parent-docs", type=int, default=10_000)
    parser.add_argument("--max-parent-docs", type=int, default=None)
    parser.add_argument("--prefer-full-corpus", action="store_true")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args()

    from datasets import load_dataset

    exp_dir = args.output_dir.resolve()
    corpus_root = exp_dir / "corpus"
    langchain_dir = corpus_root / args.topic
    continuity_dir = corpus_root / "continuity"
    output_dir = exp_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.clean:
        shutil.rmtree(langchain_dir, ignore_errors=True)
        shutil.rmtree(continuity_dir, ignore_errors=True)

    print(f"Loading FreshStack queries: {args.queries_repo}/{args.topic}")
    query_rows = [dict(row) for row in load_dataset(args.queries_repo, args.topic, split="test")]
    queries, qrel_ids = _extract_qrels(query_rows)

    identifier_count = sum(1 for q in queries if q["category"] == "identifier-heavy")
    semantic_count = sum(1 for q in queries if q["category"] == "semantic")
    if identifier_count < 30:
        raise SystemExit(
            f"Only {identifier_count} identifier-heavy queries found; "
            "protocol requires adding Angular rather than weakening rules."
        )

    print(f"Loading FreshStack corpus: {args.corpus_repo}/{args.topic}")
    corpus = load_dataset(args.corpus_repo, args.topic, split="train")
    corpus_ids = [str(row["_id"]) for row in corpus]
    selected_ids, selection = _select_corpus_ids(
        corpus_ids,
        qrel_ids,
        min_parent_docs=args.min_parent_docs,
        max_parent_docs=args.max_parent_docs,
        prefer_full_corpus=args.prefer_full_corpus,
        seed=args.seed,
    )
    selected_set = set(selected_ids)
    if len(selected_ids) < args.min_parent_docs:
        raise SystemExit(
            f"Selected corpus too small: {len(selected_ids)} < {args.min_parent_docs}"
        )

    langchain_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = corpus_root / f"{args.topic}_manifest.jsonl"
    written = 0
    with manifest_path.open("w", encoding="utf-8") as manifest:
        for index, row in enumerate(corpus):
            doc_id = str(row["_id"])
            if doc_id not in selected_set:
                continue
            meta = row.get("metadata") or {}
            file_path = langchain_dir / _safe_name(doc_id, written)
            front_matter = {
                "freshstack_id": doc_id,
                "source_url": meta.get("url"),
                "topic": args.topic,
                "source_kind": "freshstack-parent",
                "start_byte": meta.get("start_byte"),
                "end_byte": meta.get("end_byte"),
            }
            text = row.get("text") or ""
            _write_markdown(file_path, front_matter, text)
            manifest.write(json.dumps({
                "freshstack_id": doc_id,
                "text": text,
                "metadata": front_matter | {
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                },
            }, ensure_ascii=False) + "\n")
            written += 1

    exp9_dir = exp_dir.parent / "9-hybrid-retrieval-2026-05-27"
    continuity_docs, continuity_queries = _load_exp9_continuity(exp9_dir)
    continuity_dir.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as manifest:
        for index, doc in enumerate(continuity_docs):
            doc_id = doc["_id"]
            file_path = continuity_dir / _safe_name(doc_id, index)
            meta = doc.get("metadata") or {}
            front_matter = {
                "freshstack_id": doc_id,
                "source_url": meta.get("url"),
                "topic": "continuity",
                "source_kind": "continuity-parent",
                "original_file": doc.get("original_file"),
                "start_byte": meta.get("start_byte"),
                "end_byte": meta.get("end_byte"),
            }
            _write_markdown(file_path, front_matter, doc.get("text") or "")
            manifest.write(json.dumps({
                "freshstack_id": doc_id,
                "text": doc.get("text") or "",
                "metadata": front_matter | {
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                },
            }, ensure_ascii=False) + "\n")

    all_queries = queries + continuity_queries
    qrels = {
        q["query_id"]: {
            "nuggets": q["nuggets"],
            "relevant_parent_ids": q["relevant_parent_ids"],
            "category": q["category"],
        }
        for q in all_queries
    }
    ground_truth = {
        "experiment": "9a-hybrid-retrieval-freshstack-langchain-2026-05-30",
        "topic": args.topic,
        "corpus": {
            "source_repo": args.corpus_repo,
            "source_split": "train",
            "source_parent_docs": len(corpus_ids),
            "selected_freshstack_parent_docs": written,
            "continuity_parent_docs": len(continuity_docs),
            "total_parent_docs": written + len(continuity_docs),
            "manifest_path": str(manifest_path),
            **selection,
        },
        "identifier_classifier": {
            "identifier_heavy_queries": identifier_count,
            "semantic_queries": semantic_count,
            "rules": [name for name, _ in IDENTIFIER_RULES],
            "note": "Stack Overflow tags are recorded as metadata only; rules inspect title/body text.",
        },
        "queries": all_queries,
    }

    for base in (exp_dir, output_dir):
        (base / "ground-truth.json").write_text(
            json.dumps(ground_truth, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        (base / "freshstack-qrels.json").write_text(
            json.dumps(qrels, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print(f"Wrote {written} FreshStack docs to {langchain_dir}")
    print(f"Wrote {len(continuity_docs)} continuity docs to {continuity_dir}")
    print(f"Manifest: {manifest_path}")
    print(f"Ground truth: {output_dir / 'ground-truth.json'}")
    print(f"Identifier-heavy queries: {identifier_count}; semantic: {semantic_count}")


if __name__ == "__main__":
    main()
