# ruff: noqa: E501
# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#   "torch>=2.7",
#   "torchvision",
#   "transformers==4.57.6",
#   "accelerate",
#   "qwen_vl_utils",
#   "huggingface_hub",
#   "pypdfium2",
#   "pillow",
# ]
# ///
"""Probe dots.mocr on Apple Silicon (MPS): timing and output on the review pages.

Operator request 2026-09-24: check whether dots.mocr (3B, rednote-hilab) is usable
on this machine before any wider comparison. It runs in its own throwaway uv
environment (PEP 723 inline dependencies), never in the omrg install, because it
needs PyTorch.

Upstream targets CUDA: ``modeling_dots_vision.py`` imports ``flash_attn`` at module
top level. The probe patches the downloaded copy so that import is optional and
switches the vision tower to PyTorch SDPA attention. Both patches are idempotent
and recorded in the state file.

Pages are rendered from the source PDFs at 200 DPI (the upstream parser's default),
so the model sees the same resolution it was evaluated at. The prompt is upstream
``prompt_layout_all_en``; the JSON layout is converted to Markdown here, keeping
page headers and footers (the upstream default ``.md``, not the ``_nohf`` variant).

Usage:
    uv run --script experiments/34-worker-sample-review-2026-09-19/probe_dots_mocr.py
    uv run --script .../probe_dots_mocr.py --only bd03:1 --max-new-tokens 4096
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
OUT_DIR = EXP_DIR / "output" / "dots_mocr"
STATE = EXP_DIR / "output" / "dots_mocr_state.json"
#: Upstream warns against periods in the model folder name (dynamic-module naming).
MODEL_DIR = Path.home() / ".cache" / "omrg-exp34" / "DotsMOCR"
REPO_ID = "rednote-hilab/dots.mocr"
#: The operator's review set (commit 46147e1 scoped the review to these pages).
DEFAULT_PAGES = "bd03:1,bd03:2,io06:28,io06:53,eq01:11"
#: Pages outside the frozen sample, keyed by doc id. The review set has no display
#: equations, so ``eq01`` tests the formula claim in the dots.mocr demo.
#: eq01 = Kingma & Welling, "Auto-Encoding Variational Bayes", arXiv 1312.6114v11
#: (https://arxiv.org/pdf/1312.6114v11); page 11 is appendix B-C, display maths only.
#: ``corpus/`` is gitignored: download the PDF there before the first run.
EXTRA_SOURCES = {"eq01": EXP_DIR / "corpus" / "eq01.pdf"}
PAGES_DIR = EXP_DIR / "output" / "pages"

PROMPT = """Please output the layout information from the PDF image, including each layout element's bbox, its category, and the corresponding text content within the bbox.

1. Bbox format: [x1, y1, x2, y2]

2. Layout Categories: The possible categories are ['Caption', 'Footnote', 'Formula', 'List-item', 'Page-footer', 'Page-header', 'Picture', 'Section-header', 'Table', 'Text', 'Title'].

3. Text Extraction & Formatting Rules:
    - Picture: For the 'Picture' category, the text field should be omitted.
    - Formula: Format its text as LaTeX.
    - Table: Format its text as HTML.
    - All Others (Text, Title, etc.): Format their text as Markdown.

4. Constraints:
    - The output text must be the original text from the image, with no translation.
    - All layout elements must be sorted according to human reading order.

5. Final Output: The entire output must be a single JSON object.
"""


def ensure_model() -> list[str]:
    """Download the weights once and apply the Apple Silicon patches; return the patches applied."""
    from huggingface_hub import snapshot_download

    snapshot_download(REPO_ID, local_dir=MODEL_DIR)
    applied = []
    vision = MODEL_DIR / "modeling_dots_vision.py"
    src = vision.read_text(encoding="utf-8")
    # Anchor at line start: the patched copy keeps the import, indented, so a plain
    # substring test would wrap it again on every run.
    hard_import = re.compile(r"^from flash_attn import flash_attn_varlen_func\n", re.MULTILINE)
    if hard_import.search(src):
        src = hard_import.sub(
            "try:\n    from flash_attn import flash_attn_varlen_func\nexcept ImportError:  # omrg exp34: no CUDA on Apple Silicon\n    flash_attn_varlen_func = None\n",
            src,
        )
        vision.write_text(src, encoding="utf-8")
    applied.append("flash_attn import optional")
    cfg_path = MODEL_DIR / "config.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    if cfg["vision_config"].get("attn_implementation") != "sdpa":
        cfg["vision_config"]["attn_implementation"] = "sdpa"
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    applied.append("vision attn_implementation=sdpa")
    return applied


def render_page(pdf: Path, page: int, dpi: int = 200, min_long_side: int = 1600):
    """Render at *dpi*, raised so the long side reaches *min_long_side* px.

    Scanned books (``io06``) have tiny page boxes: 200 DPI gives 384 x 624 px,
    far below the embedded scan (the review image is 983 x 1600).
    """
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(pdf))
    try:
        pg = doc[page - 1]
        scale = max(dpi / 72, min_long_side / max(pg.get_size()))
        return pg.render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()


def layout_to_markdown(raw: str) -> tuple[str, bool]:
    """Convert the layout JSON to Markdown; return (markdown, parsed_ok)."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        cells = json.loads(text)
    except json.JSONDecodeError:
        return raw, False
    if isinstance(cells, dict):
        cells = cells.get("layout") or cells.get("elements") or [cells]
    out = []
    for cell in cells:
        if not isinstance(cell, dict):
            continue
        cat, body = cell.get("category", ""), (cell.get("text") or "").strip()
        if cat == "Picture" or not body:
            continue
        if cat in ("Title", "Section-header"):
            body = body.lstrip("#").strip()  # the model sometimes emits its own heading marks
        if cat == "Title":
            out.append(f"# {body}")
        elif cat == "Section-header":
            out.append(f"## {body}")
        elif cat == "Formula":
            body = re.sub(r"^\$\$\s*|\s*\$\$$", "", body)  # the model often adds its own delimiters
            out.append(f"$$\n{body}\n$$")
        else:
            out.append(body)
    return "\n\n".join(out) + "\n", True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", default=DEFAULT_PAGES, help="doc:page pairs, comma-separated")
    parser.add_argument("--max-new-tokens", type=int, default=8192)
    parser.add_argument(
        "--min-long-side", type=int, default=1600, help="minimum rendered long side, px"
    )
    parser.add_argument("--dtype", choices=["bfloat16", "float16", "float32"], default="bfloat16")
    args = parser.parse_args()

    import torch
    from qwen_vl_utils import process_vision_info
    from transformers import AutoModelForCausalLM, AutoProcessor

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    sample = json.loads((EXP_DIR / "sample.json").read_text(encoding="utf-8"))
    exp33 = Path(sample["exp33_dir"])
    sources = {
        d["doc_id"]: d for d in json.loads((exp33 / "sources.json").read_text())["documents"]
    }
    pairs = [(d, int(p)) for d, _, p in (x.strip().partition(":") for x in args.only.split(","))]

    state = json.loads(STATE.read_text()) if STATE.exists() else {"pages": {}}
    t0 = time.perf_counter()
    state["patches"] = ensure_model()
    state["download_seconds"] = round(time.perf_counter() - t0, 1)

    t0 = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_DIR,
        attn_implementation="sdpa",
        torch_dtype=getattr(torch, args.dtype),
        trust_remote_code=True,
    ).to(device)
    processor = AutoProcessor.from_pretrained(MODEL_DIR, trust_remote_code=True)
    state.update(
        device=device,
        dtype=args.dtype,
        torch=torch.__version__,
        load_seconds=round(time.perf_counter() - t0, 1),
        max_new_tokens=args.max_new_tokens,
        min_long_side=args.min_long_side,
    )
    print(f"model loaded on {device} ({args.dtype}) in {state['load_seconds']} s", flush=True)

    for doc, page in pairs:
        pdf = EXTRA_SOURCES[doc] if doc in EXTRA_SOURCES else exp33 / sources[doc]["local_path"]
        image = render_page(pdf, page, min_long_side=args.min_long_side)
        if doc in EXTRA_SOURCES:  # the review page needs an image; Experiment 33 has none for it
            (PAGES_DIR / doc).mkdir(parents=True, exist_ok=True)
            image.save(PAGES_DIR / doc / f"p{page:03d}.png")
        messages = [
            {
                "role": "user",
                "content": [{"type": "image", "image": image}, {"type": "text", "text": PROMPT}],
            }
        ]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = processor(
            text=[text], images=image_inputs, videos=video_inputs, padding=True, return_tensors="pt"
        ).to(device)
        t0 = time.perf_counter()
        error = None
        try:
            with torch.inference_mode():
                ids = model.generate(**inputs, max_new_tokens=args.max_new_tokens, do_sample=False)
            new_ids = ids[:, inputs.input_ids.shape[1] :]
            raw = processor.batch_decode(
                new_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
            )[0]
            tokens = int(new_ids.shape[1])
        except Exception as exc:  # noqa: BLE001 — a probe records failures, it does not stop on them
            raw, tokens, error = "", 0, f"{type(exc).__name__}: {exc}"
        seconds = round(time.perf_counter() - t0, 1)
        md, parsed = layout_to_markdown(raw) if raw else ("", False)
        dest = OUT_DIR / doc
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"p{page:03d}.raw.txt").write_text(raw, encoding="utf-8")
        (dest / f"p{page:03d}.md").write_text(md, encoding="utf-8")
        state["pages"][f"{doc}/{page}"] = {
            "seconds": seconds,
            "new_tokens": tokens,
            "hit_token_cap": tokens >= args.max_new_tokens,
            "json_parsed": parsed,
            "image_px": list(image.size),
            "error": error,
        }
        if device == "mps":
            state["mps_driver_gb"] = round(torch.mps.driver_allocated_memory() / 2**30, 2)
        STATE.write_text(json.dumps(state, indent=1), encoding="utf-8")
        print(
            f"{doc} p{page}: {seconds} s, {tokens} tokens, parsed={parsed}, error={error}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
