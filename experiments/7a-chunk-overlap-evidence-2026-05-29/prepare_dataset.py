"""Prepare Experiment 7a's evidence-dense Qasper corpus and QA labels.

This script is copied from Experiment 6b so 7a remains self-contained and can
regenerate its local ``corpus/`` and ``ground-truth.json`` without depending on
another experiment directory. The default path downloads and normalises the
Qasper dev split used by Experiments 6b/6c.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import tarfile
import tempfile
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# ``HF_TOKEN`` is read at runtime; load it from a project ``.env`` so the
# adapter works without the operator manually exporting the variable.
load_dotenv()


EXPERIMENT_DIR = Path(__file__).parent
RAW_DIR = EXPERIMENT_DIR / "data" / "hicbench_raw"
QASPER_RAW_DIR = EXPERIMENT_DIR / "data" / "qasper_raw"
CORPUS_DIR = EXPERIMENT_DIR / "corpus"
GROUND_TRUTH = EXPERIMENT_DIR / "ground-truth.json"

HICBENCH_REPO_ID = "Youtu-RAG/HiCBench"
HICBENCH_PAPER_DOI = "10.48550/arXiv.2509.11552"
HICBENCH_HF_URL = f"https://huggingface.co/datasets/{HICBENCH_REPO_ID}"
HICBENCH_GITHUB_URL = "https://github.com/TencentCloudADP/HiChunk.git"

# Qasper (Dasigi et al. 2021, NAACL) — public, ungated, evidence-bearing QA over
# NLP research papers.  The HiChunk paper uses Qasper as one of its in-domain
# evaluation corpora, so it is a faithful Experiment 6b stand-in for the
# unobtainable HiCBench dataset (the URL printed in the paper currently 404s).
QASPER_TRAIN_DEV_URL = (
    "https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-train-dev-v0.3.tgz"
)
QASPER_TEST_URL = (
    "https://qasper-dataset.s3.us-west-2.amazonaws.com/qasper-test-and-evaluator-v0.3.tgz"
)

# HiChunk QA schema (per the public README of TencentCloudADP/HiChunk):
#
#   {
#     "input":       "str. Question",
#     "answers":     "list[str]. All true answers",
#     "facts":       "list[str]. Facts mentioned in answers",
#     "evidences":   "list[str]. Sentences from the original document related to the question",
#     "all_classes": "list[str]. Used to compute subset metric in eval.py",
#     "_id":         "str. {doc_id}"
#   }
#
# Documents live in ``dataset/doc/{dataset}/{doc_id}.txt``.  HiCBench reuses
# the same layout — we expect either a ``dataset/`` directory mirroring the
# repo, or a flat ``doc/`` + ``qas/`` pair pointing at the same files.
QA_QUESTION_FIELDS = ("input", "question", "query", "q")
QA_ANSWER_FIELDS = ("answers", "answer", "expected_answer", "gold_answer")
QA_EVIDENCE_FIELDS = (
    "evidences", "evidence", "evidence_snippets", "evidence_spans",
    "positive_ctxs", "supports",
)
QA_DOC_ID_FIELDS = ("_id", "doc_id", "document_id", "source", "title", "file_name")
QA_HIERARCHY_FIELDS = ("hierarchy", "hierarchy_path", "section_path", "all_classes", "facts")
QA_SECTION_FIELDS = ("section", "heading", "header", "topic")


def _download_hicbench_via_hf(target_dir: Path) -> Path:
    """Snapshot HiCBench from Hugging Face into ``target_dir`` using HF auth.

    Reads ``HF_TOKEN`` (or ``HUGGINGFACE_HUB_TOKEN``) from the environment
    and refuses to proceed without one — Hugging Face's API for this dataset
    returns 401 without authentication. Returns the resolved snapshot path
    so the rest of the adapter can ingest from it.
    """
    token = os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_HUB_TOKEN")
    if not token:
        raise SystemExit(
            "HiCBench is gated on Hugging Face. Set HF_TOKEN (or "
            "HUGGINGFACE_HUB_TOKEN) in your environment after accepting the "
            f"dataset terms at {HICBENCH_HF_URL}.\n"
            "Alternatively, manually clone the dataset into "
            f"{target_dir} and rerun prepare_dataset.py without --hf-download."
        )
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is required for --hf-download. Install with: "
            "uv add --dev huggingface_hub"
        ) from exc
    target_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=HICBENCH_REPO_ID,
        repo_type="dataset",
        local_dir=str(target_dir),
        local_dir_use_symlinks=False,
        token=token,
    )
    return target_dir


def _slug(value: str, fallback: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
    return slug or fallback


def _read_jsonish(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        rows: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                rows.append(json.loads(line))
        return rows

    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    for key in ("data", "documents", "qas", "questions", "examples"):
        if isinstance(data.get(key), list):
            return [x for x in data[key] if isinstance(x, dict)]
    return [data] if isinstance(data, dict) else []


def _pick(row: dict[str, Any], names: tuple[str, ...]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, "", []):
            return row[name]
    return None


def _normalise_snippets(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        snippets: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                snippets.append(item)
            elif isinstance(item, dict):
                text = _pick(item, ("text", "snippet", "evidence", "content", "span"))
                if isinstance(text, str) and text.strip():
                    snippets.append(text)
        return snippets
    return []


def _walk_doc_dir(raw_dir: Path) -> dict[str, str]:
    """Map HiChunk-style ``dataset/doc/.../{doc_id}.txt`` files into memory."""
    doc_root_candidates = [
        raw_dir / "dataset" / "doc",
        raw_dir / "doc",
        raw_dir,
    ]
    for root in doc_root_candidates:
        if not root.exists():
            continue
        text_files = [p for p in root.rglob("*.txt") if p.is_file()]
        if not text_files:
            continue
        documents: dict[str, str] = {}
        for path in text_files:
            doc_id = path.stem
            documents[doc_id] = path.read_text(encoding="utf-8", errors="replace")
        if documents:
            return documents
    return {}


def _walk_qa_files(raw_dir: Path) -> list[dict[str, Any]]:
    """Collect QA records from JSON/JSONL files under the dataset directory."""
    qa_root_candidates = [
        raw_dir / "dataset" / "qas",
        raw_dir / "qas",
        raw_dir,
    ]
    rows: list[dict[str, Any]] = []
    for root in qa_root_candidates:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.suffix.lower() in {".json", ".jsonl"} and path.is_file():
                rows.extend(_read_jsonish(path))
        if rows:
            break
    return rows


def _normalise_hicbench(raw_dir: Path) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Normalise HiCBench / HiChunk-style data into corpus + ground-truth.

    Layout supported:

        raw_dir/
          dataset/doc/{dataset}/{doc_id}.txt
          dataset/qas/{dataset}.jsonl

    or any flat layout containing ``doc/`` text files and ``qas/`` JSON / JSONL
    files.  Documents are written to ``corpus/`` as Markdown (a single ``# {doc_id}``
    heading is added when the document has no leading heading) and QA rows are
    normalised to this repository's evaluation schema.
    """
    if not raw_dir.exists():
        raise FileNotFoundError(
            f"HiCBench directory not found: {raw_dir}\n"
            "Place the dataset under data/hicbench_raw/ or run with "
            "--hf-download (and HF_TOKEN), or use "
            "--allow-synthetic-fallback for a labelled fallback corpus."
        )

    documents = _walk_doc_dir(raw_dir)
    qa_rows = _walk_qa_files(raw_dir)
    if not documents or not qa_rows:
        raise ValueError(
            "Could not recognise HiCBench/HiChunk layout under "
            f"{raw_dir}. Expected dataset/doc/.../<doc_id>.txt files and "
            "dataset/qas/<dataset>.jsonl QA files. See "
            f"{HICBENCH_GITHUB_URL} for the canonical layout."
        )

    doc_files: dict[str, str] = {}
    docs_out: list[tuple[str, str]] = []
    for i, (doc_id, text) in enumerate(sorted(documents.items()), start=1):
        file_name = f"{i:03d}-{_slug(doc_id, f'doc-{i}')}.md"
        doc_files[doc_id] = file_name
        body = text.strip()
        if not body.lstrip().startswith("#"):
            body = f"# {doc_id}\n\n{body}\n"
        docs_out.append((file_name, body))

    queries: list[dict[str, Any]] = []
    for i, row in enumerate(qa_rows, start=1):
        question = _pick(row, QA_QUESTION_FIELDS)
        if not isinstance(question, str) or not question.strip():
            continue
        doc_id = str(_pick(row, QA_DOC_ID_FIELDS) or "")
        evidence_value = _pick(row, QA_EVIDENCE_FIELDS)
        evidence_snippets = _normalise_snippets(evidence_value)
        answers_value = _pick(row, QA_ANSWER_FIELDS)
        answers = _normalise_snippets(answers_value)
        # Hierarchy: prefer a list-typed field; fall back to single section.
        hierarchy: list[str] = []
        for field in QA_HIERARCHY_FIELDS:
            value = row.get(field)
            if isinstance(value, list):
                hierarchy = [str(v) for v in value if str(v).strip()]
                if hierarchy:
                    break
        section_value = _pick(row, QA_SECTION_FIELDS)
        if not hierarchy and isinstance(section_value, str):
            hierarchy = [section_value]
        queries.append({
            "id": str(_pick(row, ("id", "qid", "question_id", "_id")) or f"q-{i}"),
            "query": question,
            "category": "hierarchy-targeted" if hierarchy else "general",
            "expected_source": doc_files.get(doc_id, doc_id),
            "expected_section": hierarchy[-1] if hierarchy else None,
            "expected_answer": answers[0] if answers else (evidence_snippets[0] if evidence_snippets else ""),
            "evidence_ids": _normalise_snippets(_pick(row, ("evidence_ids", "evidence_id"))),
            "evidence_snippets": evidence_snippets or answers,
            "hierarchy_path": hierarchy,
        })

    if not queries:
        raise ValueError(
            "Found documents but no QA rows with a recognised question field "
            f"({QA_QUESTION_FIELDS}). Check {HICBENCH_GITHUB_URL} for the "
            "canonical schema."
        )

    return docs_out, queries


def _synthetic() -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    docs = [
        ("retrieval-architecture.md", """# Retrieval Architecture

## Dense Candidate Search
The dense candidate search embeds the user query once and asks ChromaDB for a vector-nearest candidate pool. Evidence marker RA-DENSE-POOL says the candidate pool is intentionally broader when a downstream filter will rerank it.

## Metadata Filtering
Metadata filtering is applied inside ChromaDB with a where clause before result formatting. Evidence marker RA-METADATA-WHERE states that filtered and unfiltered paths must share the same distance-to-score conversion.

## Result Formatting
Result formatting returns source, score, page label, and chunk text so evaluators can inspect the evidence directly. Evidence marker RA-RESULT-TEXT states that chunk text is mandatory for evidence-level evaluation.
"""),
        ("ingestion-architecture.md", """# Ingestion Architecture

## Markdown Branch
Markdown files first pass through a heading-aware parser and then through a sentence splitter. Evidence marker IA-MARKDOWN-CHAIN states that heading boundaries are preserved when the section fits under the configured chunk size.

## Long Section Cap
Long heading-bounded sections are split again by the sentence splitter. Evidence marker IA-LONG-CAP states that MarkdownNodeParser alone is not sufficient because a single long H2 can become an oversized node.

## Metadata Attachment
Document-level metadata is flattened before being copied onto every chunk. Evidence marker IA-METADATA-FLAT says list metadata is joined into comma-separated strings before storage.
"""),
        ("evaluation-method.md", """# Evaluation Method

## Evidence Density
Evidence-dense evaluation labels the concrete snippets needed to answer each query. Evidence marker EM-EVIDENCE-DENSE states that source-file Hit@K alone cannot evaluate chunking quality.

## Section Metrics
Section metrics compare the retrieved chunk's heading or hierarchy label with the expected section. Evidence marker EM-SECTION-MATCH states that section match is useful only when the query has a hierarchy target.

## Graded Ranking
Graded ranking uses nDCG so exact evidence outranks same-document but wrong-section chunks. Evidence marker EM-NDCG-GRADE states that exact evidence receives grade two and same-document evidence receives grade one.
"""),
    ]
    queries = [
        ("q1", "Which pipeline preserves heading boundaries before applying the size cap?", "ingestion-architecture.md", "Markdown Branch", "IA-MARKDOWN-CHAIN", "hierarchy-targeted"),
        ("q2", "Why is a heading parser alone insufficient for long H2 content?", "ingestion-architecture.md", "Long Section Cap", "IA-LONG-CAP", "hierarchy-targeted"),
        ("q3", "Where is metadata filtering applied before formatting results?", "retrieval-architecture.md", "Metadata Filtering", "RA-METADATA-WHERE", "hierarchy-targeted"),
        ("q4", "What result field is mandatory for evidence-level evaluation?", "retrieval-architecture.md", "Result Formatting", "RA-RESULT-TEXT", "hierarchy-targeted"),
        ("q5", "What kind of labels prevent source-file Hit@K from being the only signal?", "evaluation-method.md", "Evidence Density", "EM-EVIDENCE-DENSE", "hierarchy-targeted"),
        ("q6", "How should exact evidence compare with same-document wrong-section chunks?", "evaluation-method.md", "Graded Ranking", "EM-NDCG-GRADE", "hierarchy-targeted"),
        ("q7", "What is copied onto every chunk after being flattened?", "ingestion-architecture.md", "Metadata Attachment", "IA-METADATA-FLAT", "general"),
        ("q8", "When is section match useful as an evaluation signal?", "evaluation-method.md", "Section Metrics", "EM-SECTION-MATCH", "general"),
    ]
    gt = []
    for qid, query, source, section, marker, category in queries:
        gt.append({
            "id": qid,
            "query": query,
            "category": category,
            "expected_source": source,
            "expected_section": section,
            "expected_answer": marker,
            "evidence_ids": [marker],
            "evidence_snippets": [marker],
            "hierarchy_path": [source.removesuffix(".md"), section],
        })
    return docs, gt


def _download_qasper(target_dir: Path, *, split: str) -> Path:
    """Download Qasper train+dev or test tarball into ``target_dir``.

    Returns the path to the extracted JSON for ``split``.
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    if split in {"train", "dev"}:
        url = QASPER_TRAIN_DEV_URL
        json_name = f"qasper-{split}-v0.3.json"
    elif split == "test":
        url = QASPER_TEST_URL
        json_name = "qasper-test-v0.3.json"
    else:
        raise ValueError(f"unknown qasper split: {split!r}")
    json_path = target_dir / json_name
    if json_path.exists():
        return json_path
    print(f"Downloading {url} …")
    with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
        with urllib.request.urlopen(url, timeout=300) as resp:  # nosec B310
            shutil.copyfileobj(resp, tmp)
        tarball_path = Path(tmp.name)
    try:
        with tarfile.open(tarball_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith(".json"):
                    out_path = target_dir / Path(member.name).name
                    with tar.extractfile(member) as src, out_path.open("wb") as dst:
                        shutil.copyfileobj(src, dst)
    finally:
        tarball_path.unlink(missing_ok=True)
    if not json_path.exists():
        raise FileNotFoundError(
            f"Expected {json_name} inside the Qasper tarball at {url}; "
            f"contents were extracted to {target_dir} instead."
        )
    return json_path


def _qasper_paragraphs(paper: dict[str, Any]) -> list[tuple[str, str]]:
    """Flatten a Qasper paper into ``(section_label, paragraph_text)`` pairs.

    The section label uses the section name where present and a parent path for
    nested sections so retrieved chunks carry an unambiguous hierarchy.
    """
    pairs: list[tuple[str, str]] = []
    abstract = paper.get("abstract") or ""
    if isinstance(abstract, str) and abstract.strip():
        pairs.append(("Abstract", abstract.strip()))

    def _walk(section: dict[str, Any], parents: list[str]) -> None:
        name = section.get("section_name") or "Body"
        path = parents + [str(name)]
        label = " / ".join(path)
        for paragraph in section.get("paragraphs", []) or []:
            if isinstance(paragraph, str) and paragraph.strip():
                pairs.append((label, paragraph.strip()))
        for child in section.get("subsections", []) or []:
            if isinstance(child, dict):
                _walk(child, path)

    for section in paper.get("full_text", []) or []:
        if isinstance(section, dict):
            _walk(section, [])
    return pairs


def _qasper_markdown(paper_id: str, paper: dict[str, Any]) -> str:
    """Render a Qasper paper into Markdown with H1/H2/H3 hierarchy.

    The first H1 is the paper title; sections become H2; subsections H3.  The
    HiChunk-aware chunker can then split on these heading boundaries.
    """
    lines: list[str] = []
    title = paper.get("title") or paper_id
    lines.append(f"# {title}\n")
    abstract = paper.get("abstract") or ""
    if isinstance(abstract, str) and abstract.strip():
        lines.append("## Abstract\n")
        lines.append(abstract.strip() + "\n")

    def _emit(section: dict[str, Any], depth: int) -> None:
        name = section.get("section_name") or "Body"
        prefix = "#" * min(depth, 6)
        lines.append(f"{prefix} {name}\n")
        for paragraph in section.get("paragraphs", []) or []:
            if isinstance(paragraph, str) and paragraph.strip():
                lines.append(paragraph.strip() + "\n")
        for child in section.get("subsections", []) or []:
            if isinstance(child, dict):
                _emit(child, depth + 1)

    for section in paper.get("full_text", []) or []:
        if isinstance(section, dict):
            _emit(section, depth=2)
    return "\n".join(lines).strip() + "\n"


def _section_for_evidence(evidence_text: str, sections: list[tuple[str, str]]) -> str | None:
    """Find the section label whose paragraph best contains ``evidence_text``."""
    target = evidence_text.strip().lower()
    if not target:
        return None
    for label, body in sections:
        if target in body.lower():
            return label
    # Fallback: longest paragraph that shares the most characters in common.
    best_label: str | None = None
    best_overlap = 0
    for label, body in sections:
        overlap = sum(1 for token in target.split() if token in body.lower())
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = label
    return best_label


def _normalise_qasper(
    raw_dir: Path,
    *,
    split: str,
    max_papers: int | None,
    max_queries: int | None,
) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Normalise an Allen AI Qasper split into Experiment 6b inputs."""
    json_path = _download_qasper(raw_dir, split=split)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Unexpected Qasper schema in {json_path}")

    docs_out: list[tuple[str, str]] = []
    queries: list[dict[str, Any]] = []
    paper_count = 0
    for paper_id, paper in payload.items():
        if not isinstance(paper, dict):
            continue
        full_text = paper.get("full_text") or []
        if not full_text:
            continue
        paper_count += 1
        if max_papers is not None and paper_count > max_papers:
            break

        slug = _slug(paper_id, f"paper-{paper_count}")
        file_name = f"{paper_count:03d}-{slug}.md"
        markdown = _qasper_markdown(paper_id, paper)
        docs_out.append((file_name, markdown))
        sections = _qasper_paragraphs(paper)
        if not sections:
            continue

        for qa in paper.get("qas", []) or []:
            question = qa.get("question")
            if not isinstance(question, str) or not question.strip():
                continue

            evidences: list[str] = []
            answers: list[str] = []
            for ann in qa.get("answers") or []:
                inner = ann.get("answer") if isinstance(ann, dict) else None
                if not isinstance(inner, dict):
                    continue
                # Free-form / extractive answers.
                free_form = inner.get("free_form_answer")
                if isinstance(free_form, str) and free_form.strip():
                    answers.append(free_form.strip())
                for span in inner.get("extractive_spans") or []:
                    if isinstance(span, str) and span.strip():
                        answers.append(span.strip())
                for item in inner.get("evidence") or []:
                    if isinstance(item, str) and item.strip():
                        evidences.append(item.strip())

            if not evidences:
                # Skip QAs without evidence — they would re-introduce evidence
                # sparsity and undermine the experiment's primary signal.
                continue

            primary_evidence = evidences[0]
            section_label = _section_for_evidence(primary_evidence, sections)
            hierarchy = section_label.split(" / ") if section_label else []
            queries.append({
                "id": str(qa.get("question_id") or f"{paper_id}-{len(queries)}"),
                "query": question.strip(),
                "category": "hierarchy-targeted" if hierarchy else "general",
                "expected_source": file_name,
                "expected_section": hierarchy[-1] if hierarchy else None,
                "expected_answer": answers[0] if answers else primary_evidence,
                "evidence_ids": [],
                "evidence_snippets": evidences,
                "hierarchy_path": hierarchy,
            })

            if max_queries is not None and len(queries) >= max_queries:
                break
        if max_queries is not None and len(queries) >= max_queries:
            break

    if not docs_out or not queries:
        raise ValueError(
            f"Qasper {split!r} split yielded no usable corpus/QA pairs from "
            f"{json_path}. Verify the download and try again."
        )
    return docs_out, queries


def write_prepared(docs: list[tuple[str, str]], queries: list[dict[str, Any]], *, source: str) -> None:
    if CORPUS_DIR.exists():
        shutil.rmtree(CORPUS_DIR)
    CORPUS_DIR.mkdir(parents=True)
    for file_name, text in docs:
        (CORPUS_DIR / file_name).write_text(text.strip() + "\n", encoding="utf-8")
    GROUND_TRUTH.write_text(json.dumps({"dataset_source": source, "queries": queries}, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=("hicbench", "qasper"),
        default="qasper",
        help=(
            "Which dataset to use. ``qasper`` (default) downloads "
            "Allen AI's Qasper, the public, evidence-bearing in-domain "
            "dataset that the HiChunk paper itself uses. ``hicbench`` "
            "expects a local HiCBench mirror; the upstream HF dataset "
            "URL printed in the paper is currently 404."
        ),
    )
    parser.add_argument("--hicbench-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--qasper-dir", type=Path, default=QASPER_RAW_DIR)
    parser.add_argument(
        "--qasper-split",
        choices=("train", "dev", "test"),
        default="dev",
        help="Qasper split to use (default: dev).",
    )
    parser.add_argument(
        "--qasper-max-papers",
        type=int,
        default=20,
        help="Cap on the number of papers normalised into the corpus.",
    )
    parser.add_argument(
        "--qasper-max-queries",
        type=int,
        default=80,
        help="Cap on the number of evidence-bearing QA records used.",
    )
    parser.add_argument("--allow-synthetic-fallback", action="store_true")
    parser.add_argument(
        "--hf-download",
        action="store_true",
        help="Pull the HiCBench dataset from Hugging Face using HF_TOKEN.",
    )
    args = parser.parse_args()

    if args.hf_download and args.source == "hicbench":
        print(f"Downloading {HICBENCH_REPO_ID} via Hugging Face Hub …")
        _download_hicbench_via_hf(args.hicbench_dir)

    if args.source == "qasper":
        docs, queries = _normalise_qasper(
            args.qasper_dir,
            split=args.qasper_split,
            max_papers=args.qasper_max_papers,
            max_queries=args.qasper_max_queries,
        )
        source = f"qasper-{args.qasper_split}"
    else:
        try:
            docs, queries = _normalise_hicbench(args.hicbench_dir)
            source = "hicbench"
        except Exception as exc:
            if not args.allow_synthetic_fallback:
                raise SystemExit(str(exc)) from exc
            print(f"HiCBench unavailable/unrecognised: {exc}")
            print("Generating synthetic fallback corpus; results must be labelled fallback-only.")
            docs, queries = _synthetic()
            source = "synthetic-fallback"

    write_prepared(docs, queries, source=source)
    print(f"Prepared {len(docs)} documents and {len(queries)} QA records from {source}.")
    print(f"  corpus: {CORPUS_DIR}")
    print(f"  ground truth: {GROUND_TRUTH}")


if __name__ == "__main__":
    main()
