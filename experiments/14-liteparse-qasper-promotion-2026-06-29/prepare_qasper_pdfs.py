"""Prepare the Qasper PDF corpus for Experiment 14 (protocol v2.1).

Downloads REAL immutable PDF bytes — the v1 stub exported markdown text
and no PDFs at all, which cannot exercise the parser A/B/C. The Qasper
dev (validation) split is fetched as the pinned HF parquet conversion
(the original ``datasets`` loader script is no longer supported), article
IDs are arXiv IDs, and the first ``--target`` articles (sorted by ID,
deterministic) whose PDFs download successfully become the frozen corpus.

Outputs:
- ``qasper_pdfs/<arxiv-id>.pdf`` — immutable bytes (gitignored)
- ``qasper_qrels.json`` — queries + qrels restricted to downloaded
  articles (gitignored runtime input)
- ``output/qasper_corpus_freeze.json`` — freeze record (task 6.3.2):
  parquet provenance sha256, per-PDF sha256, and the corpus identity in
  the SAME scheme as ``build_indexes.corpus_identity`` so preflight and
  freeze agree byte-for-byte.

Run ephemerally (pyarrow ships with the base install):
    uv run python prepare_qasper_pdfs.py [--target 35]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
PDF_DIR = SCRIPT_DIR / "qasper_pdfs"

PARQUET_URL = (
    "https://huggingface.co/api/datasets/allenai/qasper/parquet/qasper/validation/0.parquet"
)
MIN_PDFS = 30
MIN_QUERIES = 100
ARXIV_SLEEP_SECONDS = 3.0


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fetch(url: str, timeout: float = 60.0) -> bytes:
    if not url.startswith("https://"):
        raise ValueError(f"Refusing non-https URL: {url!r}")
    request = urllib.request.Request(  # noqa: S310 — scheme guarded above
        url, headers={"User-Agent": "rag-mcp-exp14/2.1"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def load_articles(cache: Path) -> list[dict[str, Any]]:
    """Fetch (and cache) the Qasper validation parquet, return articles."""
    import pyarrow.parquet as pq

    if not cache.exists():
        data = _fetch(PARQUET_URL, timeout=120.0)
        tmp = cache.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(cache)
    table = pq.read_table(cache)
    return table.to_pylist()


def download_corpus(articles: list[dict[str, Any]], target: int) -> tuple[list[str], list[str]]:
    """Download ``target`` PDFs in deterministic (sorted-ID) order.

    Returns ``(downloaded_ids, skipped_ids)``. A PDF is accepted only if
    the response body starts with ``%PDF``; anything else (missing paper,
    HTML error page) is recorded as skipped.
    """
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    downloaded: list[str] = []
    skipped: list[str] = []

    for article in sorted(articles, key=lambda row: row["id"]):
        if len(downloaded) >= target:
            break
        article_id = article["id"]
        destination = PDF_DIR / f"{article_id}.pdf"
        if destination.exists():
            downloaded.append(article_id)
            continue
        try:
            data = _fetch(f"https://arxiv.org/pdf/{article_id}", timeout=90.0)
        except Exception as exc:  # noqa: BLE001 — record and move on
            print(f"  skip {article_id}: fetch failed ({exc})", flush=True)
            skipped.append(article_id)
            time.sleep(ARXIV_SLEEP_SECONDS)
            continue
        if not data.startswith(b"%PDF"):
            print(f"  skip {article_id}: response is not a PDF", flush=True)
            skipped.append(article_id)
            time.sleep(ARXIV_SLEEP_SECONDS)
            continue
        tmp = destination.with_suffix(".tmp")
        tmp.write_bytes(data)
        tmp.replace(destination)
        downloaded.append(article_id)
        print(f"  ok {article_id} ({len(data) / 1_000_000:.1f} MB)", flush=True)
        time.sleep(ARXIV_SLEEP_SECONDS)

    return downloaded, skipped


def build_queries_and_qrels(
    articles: list[dict[str, Any]], downloaded_ids: list[str]
) -> dict[str, Any]:
    """Queries + qrels restricted to articles whose PDFs were frozen.

    The parquet conversion normalises the Qasper ``qas`` struct-list into
    parallel column arrays (``question``, ``question_id``, ``answers``);
    each ``answers[i]["answer"]`` is a list of answer objects with
    ``unanswerable`` / ``extractive_spans`` / ``free_form_answer`` /
    ``yes_no`` fields. A question is relevant to its article when any
    answer is answerable and carries content.
    """
    keep = set(downloaded_ids)
    queries: list[dict[str, Any]] = []
    qrels: dict[str, dict[str, int]] = {}
    for article in articles:
        article_id = article["id"]
        if article_id not in keep:
            continue
        qas = article.get("qas", {})
        questions = qas.get("question", [])
        question_ids = qas.get("question_id", [])
        answers_lists = qas.get("answers", [])
        for question, question_id, answers_entry in zip(
            questions, question_ids, answers_lists, strict=False
        ):
            if not question:
                continue
            queries.append({"id": question_id, "text": question, "source": "qasper"})
            answer_objects = (
                answers_entry.get("answer", []) if isinstance(answers_entry, dict) else []
            )
            for answer in answer_objects:
                if not isinstance(answer, dict) or answer.get("unanswerable"):
                    continue
                content = (
                    answer.get("extractive_spans")
                    or answer.get("free_form_answer")
                    or answer.get("yes_no") is not None
                )
                if content:
                    qrels.setdefault(question_id, {})[article_id] = 1
    return {"queries": queries, "qrels": qrels}


def freeze(downloaded_ids: list[str], skipped_ids: list[str], parquet_sha: str) -> dict[str, Any]:
    """Corpus identity in the build_indexes.corpus_identity scheme."""
    sha_by_file = {
        f"{article_id}.pdf": _sha256_hex((PDF_DIR / f"{article_id}.pdf").read_bytes())
        for article_id in sorted(downloaded_ids)
    }
    concatenated = "".join(sha_by_file[name] for name in sorted(sha_by_file)).encode("utf-8")
    return {
        "frozen_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": {"parquet_url": PARQUET_URL, "parquet_sha256": parquet_sha},
        "selection_rule": "first N articles by sorted arXiv ID whose PDF downloads",
        "target": len(downloaded_ids),
        "skipped_ids": skipped_ids,
        "files": list(sorted(sha_by_file)),
        "sha256_by_file": sha_by_file,
        "corpus_sha256": f"sha256:{_sha256_hex(concatenated)}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Experiment 14 Qasper PDF corpus (v2.1)")
    parser.add_argument("--target", type=int, default=35, help="number of PDFs to freeze")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    cache = OUTPUT_DIR / "qasper_validation.parquet"

    print("Fetching Qasper validation split (pinned parquet)...", flush=True)
    articles = load_articles(cache)
    parquet_sha = _sha256_hex(cache.read_bytes())
    print(f"{len(articles)} articles (parquet sha256 {parquet_sha[:12]}…)", flush=True)

    delay = f"{ARXIV_SLEEP_SECONDS:.0f}s"
    print(f"Downloading {args.target} PDFs from arXiv ({delay} politeness delay)...", flush=True)
    downloaded, skipped = download_corpus(articles, args.target)
    print(f"Downloaded {len(downloaded)}, skipped {len(skipped)}", flush=True)

    gt = build_queries_and_qrels(articles, downloaded)
    (SCRIPT_DIR / "qasper_qrels.json").write_text(
        json.dumps(gt, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Ground truth: {len(gt['queries'])} queries, {len(gt['qrels'])} with qrels", flush=True)

    freeze_record = freeze(downloaded, skipped, parquet_sha)
    freeze_path = OUTPUT_DIR / "qasper_corpus_freeze.json"
    freeze_path.write_text(
        json.dumps(freeze_record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"Freeze record: {freeze_path}", flush=True)
    print(f"corpus_sha256: {freeze_record['corpus_sha256']}", flush=True)

    if len(downloaded) < MIN_PDFS:
        print(f"WARNING: only {len(downloaded)} PDFs (minimum {MIN_PDFS})", flush=True)
    if len(gt["queries"]) < MIN_QUERIES:
        print(f"WARNING: only {len(gt['queries'])} queries (minimum {MIN_QUERIES})", flush=True)


if __name__ == "__main__":
    main()
