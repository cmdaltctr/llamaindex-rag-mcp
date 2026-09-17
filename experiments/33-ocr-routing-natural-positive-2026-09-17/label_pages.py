"""Experiment 33 page evidence for independent labels (task 1.1 rule, tasks 2.x labels).

For every page of every natural document this script:

1. renders the page with poppler ``pdftoppm`` (150 dpi, 1600 px long side);
2. extracts the text layer with poppler ``pdftotext -layout`` and with pypdf;
3. asks a vision model on OpenRouter for a reference transcription of the
   page image as JSON ``{legibility, transcription}``.

Everything is stored locally under ``output/.pages/`` and
``output/.transcripts/`` (gitignored: derived document content). One page is
one checkpoint: a page whose transcript file exists is skipped, so a rerun
resumes. ``build_labels.py`` turns this evidence into labels.

pdf-inspector is never called. ``OPENROUTER_API_KEY`` is read from the
environment only and is never written anywhere.

    # cost probe: a seeded sample of 20 pages (4 per stratum)
    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/label_pages.py --probe 20
    # every page
    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/label_pages.py
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
SOURCES = EXP_DIR / "sources.json"
PAGES_DIR = EXP_DIR / "output" / ".pages"
TRANSCRIPTS_DIR = EXP_DIR / "output" / ".transcripts"

#: Pinned before the first call (plan.json labels.reference_transcription).
MODEL = "google/gemini-3.8-flash"
MAX_OUTPUT_TOKENS = 8192
ATTEMPTS = 3
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

PROMPT = (
    "Transcribe all readable text on this page image exactly as it appears, in reading "
    "order, in the original language and script. Do not translate, summarise, correct or "
    "describe images. Write mathematical notation as plain Unicode characters, never "
    "LaTeX. Return only JSON of the form "
    '{"legibility": "legible" | "illegible" | "no_text", "transcription": "..."}. '
    'Use "no_text" when the page carries no text (for example a blank page, or a '
    'photograph or illustration without words). Use "illegible" when the page carries '
    "text that cannot be read (for example heavy noise, blur, damage or an extreme "
    'angle); then leave transcription empty. Otherwise use "legible": if only part of '
    "the page is unreadable, transcribe the readable part."
)


def _render(pdf: Path, page: int, out_base: Path) -> Path:
    png = out_base.with_suffix(".png")
    if not png.exists():
        subprocess.run(  # noqa: S603 - poppler is the intended binary
            [  # noqa: S607
                "pdftoppm",
                "-r",
                "150",
                "-scale-to",
                "1600",
                "-f",
                str(page),
                "-l",
                str(page),
                "-png",
                "-singlefile",
                str(pdf),
                str(out_base),
            ],
            check=True,
            capture_output=True,
        )
    return png


def _text_layers(pdf: Path, page: int, out_base: Path, reader) -> None:
    poppler = out_base.with_suffix(".pdftotext.txt")
    if not poppler.exists():
        text = subprocess.run(  # noqa: S603
            ["pdftotext", "-layout", "-f", str(page), "-l", str(page), str(pdf), "-"],  # noqa: S607
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        ).stdout
        poppler.write_text(text, encoding="utf-8")
    pypdf_path = out_base.with_suffix(".pypdf.txt")
    if not pypdf_path.exists():
        try:
            text = reader.pages[page - 1].extract_text() or ""
        except Exception as exc:  # noqa: BLE001 - an extractor failure is evidence, not a crash
            text = ""
            out_base.with_suffix(".pypdf.error").write_text(type(exc).__name__, encoding="utf-8")
        pypdf_path.write_text(text, encoding="utf-8")


def _call_model(png: Path, api_key: str) -> dict:
    image = base64.b64encode(png.read_bytes()).decode("ascii")
    body = {
        "model": MODEL,
        "temperature": 0,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "response_format": {"type": "json_object"},
        "reasoning": {"effort": "low", "exclude": True},
        "usage": {"include": True},
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{image}"}},
                ],
            }
        ],
    }
    request = urllib.request.Request(  # noqa: S310 - fixed https endpoint
        ENDPOINT,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        return json.loads(response.read())


def _transcribe(png: Path, api_key: str) -> dict:
    record: dict = {"model_requested": MODEL, "attempts": 0}
    for attempt in range(1, ATTEMPTS + 1):
        record["attempts"] = attempt
        try:
            payload = _call_model(png, api_key)
            choice = payload["choices"][0]
            content = choice["message"]["content"] or ""
            parsed = json.loads(content.strip().removeprefix("```json").removesuffix("```"))
            record.update(
                model=payload.get("model"),
                finish_reason=choice.get("finish_reason"),
                usage=payload.get("usage"),
                legibility=parsed.get("legibility"),
                transcription=parsed.get("transcription") or "",
                label_error=None,
            )
            if record["legibility"] not in {"legible", "illegible", "no_text"}:
                raise ValueError(f"unexpected legibility {record['legibility']!r}")
            return record
        except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as exc:
            # json.JSONDecodeError is a ValueError; truncated JSON lands here too.
            record["label_error"] = type(exc).__name__
            if isinstance(exc, urllib.error.HTTPError):
                record["label_error"] = f"HTTPError {exc.code}"
            time.sleep(2 * attempt)
    return record


def _work_items(documents: list[dict], probe: int | None) -> list[tuple[dict, int]]:
    items = [(doc, page) for doc in documents for page in range(1, doc["page_count"] + 1)]
    if probe is None:
        return items
    rng = random.Random(33)  # noqa: S311 - reproducible sampling, not security
    strata = sorted({doc["stratum"] for doc in documents})
    per_stratum = max(1, probe // len(strata))
    chosen: list[tuple[dict, int]] = []
    for stratum in strata:
        pool = [item for item in items if item[0]["stratum"] == stratum]
        chosen += rng.sample(pool, min(per_stratum, len(pool)))
    return chosen


def _process(doc: dict, page: int, api_key: str, readers: dict) -> dict:
    pdf = EXP_DIR / doc["local_path"]
    page_dir = PAGES_DIR / doc["doc_id"]
    page_dir.mkdir(parents=True, exist_ok=True)
    base = page_dir / f"p{page:03d}"
    png = _render(pdf, page, base)
    _text_layers(pdf, page, base, readers[doc["doc_id"]])
    out = TRANSCRIPTS_DIR / doc["doc_id"] / f"p{page:03d}.json"
    record = _transcribe(png, api_key)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(out)
    return record


def main() -> int:
    """Collect page evidence, checkpointing one transcript file per page."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=int, help="seeded page sample size for the cost probe")
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        print("OPENROUTER_API_KEY is not set", file=sys.stderr)
        return 1

    from pypdf import PdfReader

    documents = json.loads(SOURCES.read_text(encoding="utf-8"))["documents"]
    items = [
        (doc, page)
        for doc, page in _work_items(documents, args.probe)
        if not (TRANSCRIPTS_DIR / doc["doc_id"] / f"p{page:03d}.json").exists()
    ]
    readers = {
        doc["doc_id"]: PdfReader(str(EXP_DIR / doc["local_path"]))
        for doc in {d["doc_id"]: d for d, _ in items}.values()
    }
    print(f"[label] {len(items)} pages to transcribe with {MODEL}", flush=True)

    cost = 0.0
    errors = 0
    done = 0
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(_process, doc, page, api_key, readers): (doc, page) for doc, page in items
        }
        for future in as_completed(futures):
            doc, page = futures[future]
            record = future.result()
            done += 1
            cost += float((record.get("usage") or {}).get("cost") or 0.0)
            errors += bool(record.get("label_error"))
            if done % 25 == 0 or done == len(items) or record.get("label_error"):
                print(
                    f"[label] {done}/{len(items)} {doc['doc_id']} p{page} "
                    f"legibility={record.get('legibility')} finish={record.get('finish_reason')} "
                    f"error={record.get('label_error')} cost_so_far=${cost:.4f}",
                    flush=True,
                )
    print(f"[label] complete: {done} pages, {errors} errors, cost ${cost:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
