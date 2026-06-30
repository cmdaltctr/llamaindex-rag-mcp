"""Prepare Qasper corpus for Experiment 13.

Downloads the Qasper dev set from HuggingFace (allenai/qasper) and exports
queries and PDFs for use in the mixed-corpus evaluation.
"""

from __future__ import annotations

import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
CORPUS_DIR = SCRIPT_DIR / "corpus"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CORPUS_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from datasets import load_dataset
    except ImportError:
        raise SystemExit(
            "datasets library not installed. Run: uv pip install datasets"
        )

    print("Loading allenai/qasper dev split...", flush=True)
    ds = load_dataset("allenai/qasper", split="dev")

    queries: list[dict] = []
    qrels: dict[str, dict[str, int]] = {}
    doc_count = 0

    for article in ds:
        article_id = article.get("id", f"qasper_{doc_count}")
        title = article.get("title", "")
        abstract = article.get("abstract", "")
        full_text = article.get("full_text", {})
        paragraphs = full_text.get("paragraphs", [])

        # Write document text as markdown
        doc_text = f"# {title}\n\n{abstract}\n\n"
        for para in paragraphs:
            doc_text += para + "\n\n"

        doc_path = CORPUS_DIR / f"{article_id}.md"
        doc_path.write_text(doc_text, encoding="utf-8")
        doc_count += 1

        # Extract questions and answers
        qa_pairs = article.get("qas", [])
        for qa in qa_pairs:
            question = qa.get("question", "")
            question_id = qa.get("question_id", f"q_{len(queries)}")

            queries.append({
                "id": question_id,
                "text": question,
                "is_identifier_heavy": False,
                "query_type": "semantic",
                "source": "qasper",
            })

            # Build qrels from answers
            answers = qa.get("answers", [])
            if isinstance(answers, dict):
                answers = [answers]
            for ans in answers:
                if isinstance(ans, dict):
                    answer_text = ans.get("text", "")
                    if answer_text:
                        qrels.setdefault(question_id, {})[article_id] = 1

    # Write ground truth
    gt_path = OUTPUT_DIR / "qasper_qrels.json"
    gt_path.write_text(
        json.dumps({"queries": queries, "qrels": qrels}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Exported {doc_count} documents, {len(queries)} queries", flush=True)
    print(f"Ground truth written to {gt_path}", flush=True)


if __name__ == "__main__":
    main()
