"""Measure reader-output normalisation on Experiment 34 page Markdown."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from omrg.core.ingestion.normalise import NORMALISER_VERSION, normalise_reader_text  # noqa: E402

SOURCE = ROOT / "experiments/34-worker-sample-review-2026-09-19/output"
OUTPUT = Path(__file__).resolve().parent / "output"
_CHECKPOINT = OUTPUT / "checkpoint.json"
_TAG = re.compile(r"</?[A-Za-z][\w-]*\b[^>]*>")
_DIV = re.compile(r"<div\b[^>]*>(?:(?!</?div\b).)*?</div\s*>", re.I | re.S)
_IMG = re.compile(r"<img\b[^>]*>", re.I | re.S)
_TABLE_TAG = re.compile(r"<(?:table|thead|tbody|tr|td|th)\b[^>]*>", re.I)
_FORMAT = {
    name: re.compile(rf"</?{name}\b[^>]*>", re.I)
    for name in ("u", "span", "font", "center", "b", "strong", "i", "em", "br")
}


def _atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _image_blocks(text: str) -> list[str]:
    return [match.group(0) for match in _DIV.finditer(text) if _IMG.search(match.group(0))]


def _visible(text: str) -> str:
    """Keep visible characters after entity decoding and removal of HTML tags."""
    return "".join(char for char in html.unescape(_TAG.sub("", text)) if not char.isspace())


def _measure(raw: str, clean: str, key: str, engine: str) -> dict:
    # Normaliser version 2 unwraps image blocks and keeps their text (A2), so
    # the comparison covers every visible character: nothing is excluded.
    unwrapped = [block for block in _image_blocks(raw) if block not in clean]
    before = raw
    after = clean
    rules = {
        name: max(0, len(regex.findall(raw)) - len(regex.findall(clean)))
        for name, regex in _FORMAT.items()
    }
    rules["image_blocks"] = len(unwrapped)
    rules["text_divs_unwrapped"] = max(
        0, len(_DIV.findall(before)) - len(_DIV.findall(after)) - len(unwrapped)
    )
    rules["bare_images"] = max(
        0,
        len(_IMG.findall(raw))
        - len(_IMG.findall(clean))
        - sum(len(_IMG.findall(block)) for block in unwrapped),
    )
    rules["table_presentation_attributes"] = sum(
        len(re.findall(r"\b(?!colspan\b|rowspan\b)[\w-]+\s*=", tag, re.I))
        for tag in _TABLE_TAG.findall(raw)
    ) - sum(
        len(re.findall(r"\b(?!colspan\b|rowspan\b)[\w-]+\s*=", tag, re.I))
        for tag in _TABLE_TAG.findall(clean)
    )
    added_emphasis = 2 * (rules["b"] + rules["strong"]) + rules["i"] + rules["em"]
    before_count = len(_visible(before))
    after_count = len(_visible(after)) - added_emphasis
    return {
        "engine": engine,
        "page": key,
        "rules": rules,
        "visible_before": before_count,
        "visible_after": after_count,
        "visible_delta": after_count - before_count,
        "image_block_texts_kept": [
            " ".join(html.unescape(_TAG.sub("", block)).split()) for block in unwrapped
        ],
    }


def main() -> int:
    """Record per-page rule counts and text loss, with resumable checkpoints."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    files = sorted(
        path
        # local_ocr and dots_mocr joined in amendment A1: the review pages normalise them too.
        for engine in ("pdf_inspector", "liteparse", "worker", "local_ocr", "dots_mocr")
        for path in (SOURCE / engine).glob("*/p[0-9][0-9][0-9].md")
    )
    if not files:
        raise RuntimeError(f"No Experiment 34 reader pages under {SOURCE}")
    records: dict[str, dict] = {}
    if args.resume and _CHECKPOINT.exists():
        checkpoint = json.loads(_CHECKPOINT.read_text())
        if checkpoint.get("normaliser_version") == NORMALISER_VERSION:
            records = checkpoint.get("pages", {})
    for path in files:
        key = str(path.relative_to(SOURCE))
        raw_bytes = path.read_bytes()
        digest = hashlib.sha256(raw_bytes).hexdigest()
        if key in records and records[key]["source_sha256"] == digest:
            continue
        raw = raw_bytes.decode("utf-8")
        measured = _measure(raw, normalise_reader_text(raw), key, path.parts[-3])
        records[key] = {**measured, "source_sha256": digest}
        _atomic_json(_CHECKPOINT, {"normaliser_version": NORMALISER_VERSION, "pages": records})
        print(f"Measured {key}", flush=True)
    if any(
        hashlib.sha256(SOURCE.joinpath(key).read_bytes()).hexdigest() != record["source_sha256"]
        for key, record in records.items()
    ):
        raise RuntimeError("Experiment 34 raw output changed during measurement")
    totals = Counter()
    kept_texts = []
    for record in records.values():
        totals.update(record["rules"])
        kept_texts.extend(
            {"page": record["page"], "text": text}
            for text in record["image_block_texts_kept"]
            if text
        )
    summary = {
        "normaliser_version": NORMALISER_VERSION,
        "source": str(SOURCE.relative_to(ROOT)),
        "page_count": len(records),
        "rule_totals": dict(sorted(totals.items())),
        "image_block_texts_kept": kept_texts,
        "pages": records,
    }
    _atomic_json(OUTPUT / "summary.json", summary)
    losses = [r["page"] for r in records.values() if r["visible_delta"] != 0]
    print(f"Measured {len(records)} pages; {len(losses)} visible-character deltas", flush=True)
    if losses:
        print("Pages with deltas: " + ", ".join(losses), flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
