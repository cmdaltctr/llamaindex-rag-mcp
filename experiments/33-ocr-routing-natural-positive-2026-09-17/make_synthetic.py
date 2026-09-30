"""Experiment 33 synthetic degraded set (tasks 5.1-5.2).

Builds clearly labelled synthetic scans for Stage B character error rate and
evidence recovery. Synthetic documents never enter natural held-out scoring.

For each clean CC BY source PDF, the first ``PAGES_PER_DOC`` pages are:

1. extracted as reference text with poppler ``pdftotext -layout`` (the CER
   reference, stored locally);
2. rendered with poppler ``pdftoppm`` at 200 dpi;
3. degraded with ImageMagick, per page from a seeded generator: skew
   0.5-2.0 degrees (random sign), Gaussian noise (attenuate 0.2-0.6), blur
   sigma 0.3-0.8, JPEG quality 40-60;
4. re-wrapped as an image-only PDF.

Writes ``corpus/synthetic/<doc_id>.pdf`` (gitignored),
``output/.synthetic/<doc_id>/ref_pNNN.txt`` (gitignored) and the committed
manifest ``synthetic.json`` with source identity, per-page parameters, seeds
and output hashes.

    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/make_synthetic.py
"""

from __future__ import annotations

import hashlib
import json
import random
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
OUT_DIR = EXP_DIR / "corpus" / "synthetic"
REF_DIR = EXP_DIR / "output" / ".synthetic"
MANIFEST = EXP_DIR / "synthetic.json"
PAGES_PER_DOC = 10
BASE_SEED = 33
USER_AGENT = "Mozilla/5.0 (experiment-33 synthetic set)"

#: Clean born-digital sources, CC BY 4.0 confirmed by arXiv OAI-PMH <license>.
SOURCES = [
    {
        "doc_id": "sy01",
        "arxiv_id": "2401.00632",
        "licence": "http://creativecommons.org/licenses/by/4.0/",
    },
    {
        "doc_id": "sy02",
        "arxiv_id": "2308.13049",
        "licence": "http://creativecommons.org/licenses/by/4.0/",
    },
]


def _run(*cmd: str) -> str:
    return subprocess.run(  # noqa: S603 - poppler and ImageMagick are the intended binaries
        list(cmd), capture_output=True, text=True, errors="replace", check=True
    ).stdout


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fetch(arxiv_id: str, dest: Path) -> None:
    if dest.exists():
        return
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310 - fixed https
        data = response.read()
    if not data.startswith(b"%PDF"):
        raise SystemExit(f"{arxiv_id}: download is not a PDF")
    dest.write_bytes(data)


def _page_params(rng: random.Random) -> dict:
    return {
        "skew_degrees": round(rng.choice((-1, 1)) * rng.uniform(0.5, 2.0), 3),
        "noise_attenuate": round(rng.uniform(0.2, 0.6), 3),
        "blur_sigma": round(rng.uniform(0.3, 0.8), 3),
        "jpeg_quality": rng.randint(40, 60),
    }


def _build(source: dict, index: int) -> dict:
    doc_id = source["doc_id"]
    seed = BASE_SEED + index
    rng = random.Random(seed)  # noqa: S311 - reproducible degradation, not security
    clean_dir = OUT_DIR / "clean"
    clean_dir.mkdir(parents=True, exist_ok=True)
    clean = clean_dir / f"{source['arxiv_id']}.pdf"
    _fetch(source["arxiv_id"], clean)
    ref_dir = REF_DIR / doc_id
    ref_dir.mkdir(parents=True, exist_ok=True)

    pages = []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        jpegs = []
        for page in range(1, PAGES_PER_DOC + 1):
            reference = ref_dir / f"ref_p{page:03d}.txt"
            reference.write_text(
                _run("pdftotext", "-layout", "-f", str(page), "-l", str(page), str(clean), "-"),
                encoding="utf-8",
            )
            png = work / f"p{page:03d}"
            _run("pdftoppm", "-r", "200", "-f", str(page), "-l", str(page), "-png",
                 "-singlefile", str(clean), str(png))  # fmt: skip
            params = _page_params(rng)
            jpeg = work / f"p{page:03d}.jpg"
            _run(
                "magick",
                f"{png}.png",
                "-colorspace", "Gray",
                "-background", "white",
                "-rotate", str(params["skew_degrees"]),
                "-seed", str(seed * 1000 + page),
                "-attenuate", str(params["noise_attenuate"]),
                "+noise", "Gaussian",
                "-blur", f"0x{params['blur_sigma']}",
                "-quality", str(params["jpeg_quality"]),
                str(jpeg),
            )  # fmt: skip
            jpegs.append(str(jpeg))
            pages.append({"page": page, **params, "reference_sha256": _sha256(reference)})
        out = OUT_DIR / f"{doc_id}.pdf"
        _run("magick", *jpegs, "-density", "200", "-units", "PixelsPerInch", str(out))

    return {
        "doc_id": doc_id,
        "stratum": "synthetic",
        "split": "synthetic (never held_out)",
        "source": {
            "arxiv_id": source["arxiv_id"],
            "url": f"https://arxiv.org/abs/{source['arxiv_id']}",
            "licence": source["licence"],
            "sha256": _sha256(clean),
            "pages_used": PAGES_PER_DOC,
        },
        "seed": seed,
        "local_path": f"corpus/synthetic/{doc_id}.pdf",
        "sha256": _sha256(OUT_DIR / f"{doc_id}.pdf"),
        "pages": pages,
    }


def main() -> int:
    """Build every synthetic document and write the manifest."""
    documents = [_build(source, i) for i, source in enumerate(SOURCES)]
    manifest = {
        "description": (
            "Synthetic degraded scans for Stage B CER and evidence recovery. Never counted "
            "as natural held-out evidence (spec: synthetic degraded documents are reported "
            "apart)."
        ),
        "recipe": {
            "render": "pdftoppm -r 200 -png",
            "degrade": "magick -colorspace Gray -rotate <skew> -attenuate <n> +noise Gaussian "
            "-blur 0x<sigma> -quality <q> (JPEG)",
            "rewrap": "magick <jpegs> -density 200 out.pdf (image-only, no text layer)",
            "ranges": {
                "skew_degrees": "±0.5-2.0",
                "noise_attenuate": "0.2-0.6",
                "blur_sigma": "0.3-0.8",
                "jpeg_quality": "40-60",
            },
            "reference_text": "pdftotext -layout on the clean source page",
            "tools": {
                "imagemagick": _run("magick", "-version").splitlines()[0],
                "poppler": subprocess.run(  # noqa: S603
                    ["pdftotext", "-v"],  # noqa: S607
                    capture_output=True,
                    text=True,
                    check=False,
                ).stderr.splitlines()[0],
            },
        },
        "print_and_rescan_tier": "not built (optional task 5.3; needs the operator)",
        "documents": documents,
    }
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    for doc in documents:
        source = doc["source"]["arxiv_id"]
        print(f"[synthetic] {doc['doc_id']} <- arXiv {source} ({doc['sha256'][:12]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
