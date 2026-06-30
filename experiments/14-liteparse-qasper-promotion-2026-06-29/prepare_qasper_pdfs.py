"""Prepare Qasper PDF corpus for Experiment 14.

Downloads Qasper dev set from HuggingFace and exports PDFs and queries.
Targets ≥ 30 PDFs and ≥ 100 queries for statistical validity.
"""

from __future__ import annotations

import json
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = SCRIPT_DIR / "output"
PDF_DIR = SCRIPT_DIR / "qasper_pdfs"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

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
    pdf_count = 0

    for article in ds:
        article_id = article.get("id", f"qasper_{pdf_count}")
        title = article.get("title", "")

        # Export full text as markdown for ingestion
        full_text = article.get("full_text", {})
        paragraphs = full_text.get("paragraphs", [])
        doc_text = f"# {title}\n\n"
        for para in paragraphs:
            doc_text += para + "\n\n"

        doc_path = PDF_DIR / f"{article_id}.md"
        doc_path.write_text(doc_text, encoding="utf-8")
        pdf_count += 1

        # Extract questions and answers
        qa_pairs = article.get("qas", [])
        for qa in qa_pairs:
            question = qa.get("question", "")
            question_id = qa.get("question_id", f"q_{len(queries)}")

            queries.append({
                "id": question_id,
                "text": question,
                "source": "qasper",
            })

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

    print(f"Exported {pdf_count} documents, {len(queries)} queries", flush=True)
    print(f"Ground truth written to {gt_path}", flush=True)
    if pdf_count < 30:
        print(f"WARNING: Only {pdf_count} PDFs (minimum is 30)", flush=True)
    if len(queries) < 100:
        print(f"WARNING: Only {len(queries)} queries (minimum is 100)", flush=True)


if __name__ == "__main__":
    main()
