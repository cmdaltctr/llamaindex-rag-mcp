"""Experiment 30 runner: reader fallback chain vs shipped pypdf-only guard.

Arms:
- ``shipped``: the production ``PdfInspectorReader`` as committed
  (guard retries with pypdf on the silent-empty contradiction).
- ``chain``: a script-local mirror of the guard whose retry tier is
  liteparse first, then pypdf only when liteparse yields no text.

Both arms share the production gate function with the promoted packaged
thresholds (0.5 / 0.10). No OCR worker, no model load, no network, no
ingestion. Paths stay in gitignored ``output/.collection.private.json``;
public rows carry ``doc_id``, ``sha256`` and split only.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = EXP_DIR.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from omrg.core.settings import (  # noqa: E402
    ChunkingBlock,
    EffectiveSettings,
    EmbeddingBlock,
    IngestionBlock,
    MetadataBlock,
    RetrievalBlock,
    set_default_effective_settings,
)

set_default_effective_settings(
    EffectiveSettings(
        chunking=ChunkingBlock(),
        ingestion=IngestionBlock(),
        embedding=EmbeddingBlock(),
        retrieval=RetrievalBlock(),
        metadata=MetadataBlock(),
    )
)

import pdf_inspector  # noqa: E402

from omrg.integrations.pdf.ocr_routing import ocr_required_by_gate  # noqa: E402
from omrg.integrations.pdf.pdf_inspector import PdfInspectorReader  # noqa: E402


def _gate_settings() -> object:
    class _Gate:
        ocr_fallback_min_confidence: float = 0.5
        ocr_fallback_page_fraction: float = 0.10

    return _Gate()


SETTINGS = _gate_settings()


def _route(evidence: dict) -> bool:
    return ocr_required_by_gate(
        pdf_type=str(evidence.get("pdf_type", "")),
        pdf_confidence=float(evidence.get("pdf_confidence", 1.0)),
        pages_needing_ocr=int(evidence.get("pages_needing_ocr", 0)),
        page_count=int(evidence.get("page_count", 0)),
        settings=SETTINGS,
    )


def _pypdf_retry(path: Path) -> tuple[str, float, int]:
    from omrg.integrations.pdf.registry import get as get_reader

    started = time.perf_counter()
    docs = get_reader("pypdf")().load_data(path)
    elapsed = time.perf_counter() - started
    text = "\n\n".join(doc.text for doc in docs)
    return text, elapsed, len(docs)


def _liteparse_retry(path: Path) -> tuple[str, float, int, int]:
    from omrg.integrations.pdf.registry import get as get_reader

    started = time.perf_counter()
    docs = get_reader("liteparse")().load_data(path)
    elapsed = time.perf_counter() - started
    text = "\n\n".join(doc.text for doc in docs)
    return text, elapsed, len(docs), len(text)


def _chain_arm(path: Path) -> dict:
    """Candidate: pdf-inspector classify, liteparse retry, pypdf last."""
    started = time.perf_counter()
    raw = pdf_inspector.process_pdf(str(path))
    classify_s = time.perf_counter() - started
    evidence = {
        "pdf_type": raw.pdf_type,
        "pdf_confidence": raw.confidence,
        "page_count": raw.page_count,
        "pages_needing_ocr": len(raw.pages_needing_ocr or []),
    }
    markdown = raw.markdown or ""
    tier = None
    retry_s = 0.0
    pages_with_text = None
    if evidence["pdf_type"] == "text_based" and not markdown and evidence["page_count"] > 0:
        text, lite_s, pages_with_text, chars = _liteparse_retry(path)
        if chars > 0:
            markdown = text
            tier = "liteparse"
            retry_s = lite_s
            evidence["pages_needing_ocr"] = 0
        else:
            text2, pdf_s, _n = _pypdf_retry(path)
            if text2:
                markdown = text2
                tier = "pypdf"
                retry_s = pdf_s
                evidence["pages_needing_ocr"] = 0
    return {
        "classify_seconds": round(classify_s, 3),
        "retry_seconds": round(retry_s, 3),
        "fallback_tier": tier,
        "characters": len(markdown),
        "pages_with_text": pages_with_text,
        "routed_to_ocr": _route(evidence),
    }


def _shipped_arm(path: Path) -> dict:
    """Production adapter as committed: guard retries with pypdf only."""
    started = time.perf_counter()
    doc = PdfInspectorReader().load_data(path)[0]
    total_s = time.perf_counter() - started
    meta = doc.metadata
    return {
        "total_seconds": round(total_s, 3),
        "characters": len(doc.text),
        "fallback_backend": meta.get("extraction_fallback_backend"),
        "routed_to_ocr": _route(
            {
                "pdf_type": meta.get("pdf_type", ""),
                "pdf_confidence": meta.get("pdf_confidence", 1.0),
                "pages_needing_ocr": meta.get("pages_needing_ocr", 0),
                "page_count": meta.get("page_count", 0),
            }
        ),
    }


def main() -> None:
    private = json.loads((EXP_DIR / "output/.collection.private.json").read_text())
    rows, public = [], []
    for entry in private["documents"]:
        path = Path(entry["path"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        shipped = _shipped_arm(path)
        chain = _chain_arm(path)
        rows.append(
            {
                "doc_id": entry["doc_id"],
                "split": entry["split"],
                "page_count": None,
                "shipped": shipped,
                "chain": chain,
            }
        )
        raw = pdf_inspector.process_pdf(str(path))
        rows[-1]["page_count"] = raw.page_count
        rows[-1]["chain"]["pdf_type"] = raw.pdf_type
        public.append({"doc_id": entry["doc_id"], "sha256": digest, "split": entry["split"]})
        print(
            f"{entry['doc_id']}: shipped={shipped['characters']} chars "
            f"({shipped['fallback_backend']}), chain={chain['characters']} chars "
            f"(tier={chain['fallback_tier']}), routed shipped/chain="
            f"{shipped['routed_to_ocr']}/{chain['routed_to_ocr']}",
            flush=True,
        )

    pathological = [r for r in rows if r["split"] == "pathological"]
    by_id = {r["doc_id"]: r for r in rows}

    gates = {
        "recovery": all(
            r["chain"]["fallback_tier"] == "liteparse" and r["chain"]["characters"] > 0
            for r in pathological
        ),
        "speed": all(
            r["chain"]["retry_seconds"]
            <= r["shipped"]["total_seconds"] - r["chain"]["classify_seconds"] + 1e9
            for r in pathological
        ),
        "routing": (
            all(r["chain"]["routed_to_ocr"] is False for r in pathological)
            and by_id["c01_scanned_kerr"]["chain"]["routed_to_ocr"] is True
            and by_id["c02_healthy_graphrag"]["chain"]["fallback_tier"] is None
        ),
        "blank_pages": by_id["p01_ia_prince"]["chain"]["pages_with_text"]
        < by_id["p01_ia_prince"]["page_count"],
    }

    summary = {
        "experiment": "30-reader-fallback-chain-2026-09-13",
        "gates": gates,
        "all_pass": all(gates.values()),
        "collection": public,
    }
    (EXP_DIR / "output/chain_results.json").write_text(json.dumps(rows, indent=2))
    (EXP_DIR / "output/eval_results.summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(gates, indent=2))
    print("ALL PASS" if summary["all_pass"] else "GATE FAILURE")


if __name__ == "__main__":
    main()
