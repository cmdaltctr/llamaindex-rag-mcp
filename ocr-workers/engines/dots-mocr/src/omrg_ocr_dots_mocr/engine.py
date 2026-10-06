"""The dots-mocr OCR engine: the primary route (design D4).

The engine renders each requested page, asks dots.mocr for its layout
JSON, and converts that to Markdown with :mod:`.layout`. Everything
else (framing, validation, the capability command) is the worker core.

Runtime rules:

- ``HF_HUB_OFFLINE=1`` and ``TRANSFORMERS_OFFLINE=1`` are set before any
  Hugging Face import, so a parse never downloads;
- the code-file hashes recorded at provisioning are checked before the
  model loads, because ``trust_remote_code`` executes those files;
- MPS when available, else CPU; bfloat16; greedy decoding;
  ``max_new_tokens`` :data:`MAX_NEW_TOKENS`;
- pages render with pypdfium2 at :data:`RENDER_DPI`, raised so the long
  side reaches :data:`MIN_LONG_SIDE_PX`.

PyTorch, transformers and pypdfium2 are imported lazily, inside the
methods that need them, so the capability command and the tests never
import them.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omrg_ocr_worker_core.engine import WorkerParseError

from .fetch import REPO_ID, REVISION
from .layout import CONVERTER_VERSION, page_markdown
from .patches import PATCH_SET, CodeHashMismatchError, verify_hashes
from .paths import ENGINE_NAME, cache_dir, model_dir

logger = logging.getLogger("omrg_ocr_dots_mocr")

RENDER_DPI = 200
MIN_LONG_SIDE_PX = 1600
MAX_NEW_TOKENS = 8192

#: Upstream ``prompt_layout_all_en`` (the prompt Experiment 34 measured).
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
"""  # noqa: E501 - upstream prompt text, kept verbatim


def apply_offline_env() -> None:
    """Force offline Hugging Face access and the engine-owned cache.

    Assignment, not ``setdefault``: an inherited value would let a parse
    download or read a cache outside the engine's model folder.
    """
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HOME"] = str(cache_dir())


class DotsMocrEngine:
    """dots.mocr on MPS or CPU, one page at a time."""

    name = ENGINE_NAME
    backend_id = "dots_mocr"
    declared_packages: tuple[str, ...] = (
        "omrg-ocr-worker-core",
        "omrg-ocr-dots-mocr",
        "torch",
        "torchvision",
        "transformers",
        "accelerate",
        "qwen-vl-utils",
        "pypdfium2",
        "pillow",
    )
    pipeline = ("dots-mocr-layout", f"prompt_layout_all_en+{PATCH_SET}+layout-{CONVERTER_VERSION}")
    model = (REPO_ID, REVISION)

    def __init__(self) -> None:
        self._runtime: dict[str, Any] | None = None

    # ── Engine contract ──────────────────────────────────────────────

    def parse(self, pdf: Path, pages: Sequence[int] | None) -> list[str]:
        """Return one Markdown string per parsed page.

        A page that reaches the token cap, or whose layout JSON does not
        parse, yields ``""``; the reason goes to standard error.
        """
        numbers = list(pages) if pages is not None else self._all_pages(pdf)
        out: list[str] = []
        for number in numbers:
            image = self.render_page(pdf, number)
            raw, new_tokens = self.generate(image)
            markdown, reason = page_markdown(raw, hit_token_cap=new_tokens >= MAX_NEW_TOKENS)
            if reason is not None:
                logger.warning("page %d of %s gives no text: %s", number, pdf.name, reason)
            out.append(markdown)
        return out

    # ── Seams (tests stub these) ─────────────────────────────────────

    def render_page(self, pdf: Path, page: int) -> Any:
        """Render one 1-based page to an RGB image."""
        import pypdfium2 as pdfium  # engine environment only

        document = pdfium.PdfDocument(str(pdf))
        try:
            page_obj = document[page - 1]
            scale = max(RENDER_DPI / 72, MIN_LONG_SIDE_PX / max(page_obj.get_size()))
            return page_obj.render(scale=scale).to_pil().convert("RGB")
        finally:
            document.close()

    def generate(self, image: Any) -> tuple[str, int]:
        """Run the model on one page image; return ``(raw text, new tokens)``."""
        runtime = self._load_runtime()
        torch = runtime["torch"]
        processor = runtime["processor"]
        messages = [
            {
                "role": "user",
                "content": [{"type": "image", "image": image}, {"type": "text", "text": PROMPT}],
            }
        ]
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = runtime["process_vision_info"](messages)
        inputs = processor(
            text=[text], images=image_inputs, videos=video_inputs, padding=True, return_tensors="pt"
        ).to(runtime["device"])
        with torch.inference_mode():
            ids = runtime["model"].generate(
                **inputs, max_new_tokens=MAX_NEW_TOKENS, do_sample=False
            )
        new_ids = ids[:, inputs.input_ids.shape[1] :]
        raw = processor.batch_decode(
            new_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        return raw, int(new_ids.shape[1])

    # ── Internals ────────────────────────────────────────────────────

    def _all_pages(self, pdf: Path) -> list[int]:
        """Return every 1-based page number of *pdf*."""
        from omrg_ocr_worker_core.pages import document_page_count

        return list(range(1, document_page_count(pdf) + 1))

    def _load_runtime(self) -> dict[str, Any]:
        """Load the model once per process, offline, after the hash check.

        Raises:
            WorkerParseError: If the model folder is missing, a code file
                changed since provisioning, or the runtime cannot load.
        """
        if self._runtime is not None:
            return self._runtime
        apply_offline_env()
        folder = model_dir()
        if not folder.is_dir():
            raise WorkerParseError(
                "model_missing",
                f"no dots.mocr model at {folder}; run "
                "`python3 ocr-workers/provision.py dots-mocr --accept-model-licence`",
            )
        try:
            verify_hashes(folder)
        except CodeHashMismatchError as exc:
            raise WorkerParseError("model_code_changed", str(exc)) from exc
        try:
            import torch
            from qwen_vl_utils import process_vision_info
            from transformers import AutoModelForCausalLM, AutoProcessor
        except ImportError as exc:
            raise WorkerParseError("runtime_unavailable", f"import failed: {exc}") from exc
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        model = AutoModelForCausalLM.from_pretrained(
            folder,
            attn_implementation="sdpa",
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
            local_files_only=True,
        ).to(device)
        processor = AutoProcessor.from_pretrained(
            folder, trust_remote_code=True, local_files_only=True
        )
        logger.info("dots.mocr %s loaded on %s", REVISION[:12], device)
        self._runtime = {
            "torch": torch,
            "model": model,
            "processor": processor,
            "process_vision_info": process_vision_info,
            "device": device,
        }
        return self._runtime


#: The object the ``omrg.ocr_engine`` entry point names.
ENGINE = DotsMocrEngine()
