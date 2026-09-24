"""Pages outside the frozen sample (protocol amendment A4).

The reviewed set has no display equations, so ``eq01`` tests formula
extraction. Every engine script resolves these pages from here; they run
only when named in ``--only``, so a full run keeps the frozen sample.

eq01 = Kingma & Welling, "Auto-Encoding Variational Bayes", arXiv
1312.6114v11 (https://arxiv.org/pdf/1312.6114v11); page 11 is appendix
B-D, display maths only. ``corpus/`` is gitignored: download the PDF
there before the first run.
"""

from __future__ import annotations

from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent

EXTRA_SOURCES = {"eq01": EXP_DIR / "corpus" / "eq01.pdf"}
EXTRA_PAGES = [{"doc_id": "eq01", "page": 11, "role": "extra"}]


def parse_only(spec: str) -> set[tuple[str, int]]:
    """Parse ``doc:page,doc:page`` into a set of (doc, page) pairs."""
    pairs = set()
    for item in spec.split(","):
        doc, _, page = item.strip().partition(":")
        pairs.add((doc, int(page)))
    return pairs


def source_pdf(doc_id: str, exp33: Path, sources: dict) -> Path:
    """Return the PDF for *doc_id*: an extra page's corpus file, else the Experiment 33 source."""
    if doc_id in EXTRA_SOURCES:
        return EXTRA_SOURCES[doc_id]
    return exp33 / sources[doc_id]["local_path"]
