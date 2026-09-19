#!/usr/bin/env python3
"""Write the "today" pipeline text for every sampled page (review column 2).

Per page class, what the pipeline produces today on the page unit:

- born-digital fast-path pages (bd01/bd02/bd03): pdf-inspector's native
  per-page Markdown, regenerated in seconds through extract_pages_markdown;
- flagged/needs_ocr pages (io06/io04/tl03): the local OCR tier text
  measured in Experiment 33 task 6.7, copied from its worktree.

Output: output/today/<doc>/pNNN.md beside the worker output, so the
review page can render original | today | worker.

Usage (from the repository root):
    uv run python experiments/34-worker-sample-review-2026-09-19/extract_today.py
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
TODAY = EXP_DIR / "output" / "today"

#: Documents whose pages the fast path reads natively today.
FAST_PATH_DOCS = {"bd01", "bd02", "bd03"}


def main() -> int:
    sample = json.loads((EXP_DIR / "sample.json").read_text(encoding="utf-8"))
    exp33 = Path(sample["exp33_dir"])
    sources = {
        d["doc_id"]: d for d in json.loads((exp33 / "sources.json").read_text())["documents"]
    }
    local_ocr_text = exp33 / "output" / ".local_ocr_text"

    import pdf_inspector

    for doc_id in sorted({row["doc_id"] for row in sample["pages"]}):
        pages = sorted(r["page"] for r in sample["pages"] if r["doc_id"] == doc_id)
        out_dir = TODAY / doc_id
        out_dir.mkdir(parents=True, exist_ok=True)
        if doc_id in FAST_PATH_DOCS:
            scan = pdf_inspector.extract_pages_markdown(str(exp33 / sources[doc_id]["local_path"]))
            native = {page.page + 1: page.markdown or "" for page in scan.pages}
            for page in pages:
                (out_dir / f"p{page:03d}.md").write_text(native.get(page, ""), encoding="utf-8")
            print(f"[today] {doc_id}: pdf-inspector native, {len(pages)} pages")
        else:
            for page in pages:
                src = local_ocr_text / doc_id / f"p{page:03d}.md"
                if src.is_file():
                    shutil.copy2(src, out_dir / f"p{page:03d}.md")
                else:
                    (out_dir / f"p{page:03d}.md").write_text("", encoding="utf-8")
            print(f"[today] {doc_id}: local OCR tier (exp 33 task 6.7), {len(pages)} pages")
    print(f"wrote {TODAY}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
