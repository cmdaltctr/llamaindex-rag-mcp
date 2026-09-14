"""Experiment 30 runner: reader fallback chain vs shipped pypdf-only guard.

Arms:
- ``shipped``: a script-local mirror of the historical pypdf-only
  guard (commit 928f030) — the production ``PdfInspectorReader`` now
  carries the chain itself (ADR-066), so calling it here would no
  longer measure the pre-chain baseline.
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
    text = "\n\n".join(doc.text for doc in docs if doc.text and doc.text.strip())
    return text, elapsed, len(docs)


def _liteparse_retry(path: Path) -> tuple[str, float, int, int]:
    from omrg.integrations.pdf.registry import get as get_reader

    started = time.perf_counter()
    docs = get_reader("liteparse")().load_data(path)
    elapsed = time.perf_counter() - started
    text = "\n\n".join(doc.text for doc in docs)
    return text, elapsed, len(docs), len(text)


def _measured(fn, path: Path, repeats: int = 3) -> tuple:
    """Return (first-run result, median seconds) over *repeats* runs.

    Single-shot wall-clock timings on small files are noise: p03's
    liteparse retry measured 0.072–0.379 s across identical runs, enough
    to flip the frozen speed gate. The median keeps the comparison
    stable without changing the gate's terms.
    """
    first = None
    times = []
    for _ in range(repeats):
        result = fn(path)
        if first is None:
            first = result
        times.append(result[1])
    times.sort()
    return first, times[len(times) // 2]


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
        result, lite_s = _measured(_liteparse_retry, path)
        text, pages_with_text, chars = result[0], result[2], result[3]
        if chars > 0:
            markdown = text
            tier = "liteparse"
            retry_s = lite_s
            evidence["pages_needing_ocr"] = 0
        else:
            result, pdf_s = _measured(_pypdf_retry, path)
            if result[0]:
                markdown = result[0]
                tier = "pypdf"
                retry_s = pdf_s
                evidence["pages_needing_ocr"] = 0
    return {
        "classify_seconds": classify_s,
        "retry_seconds": retry_s,
        "fallback_tier": tier,
        "characters": len(markdown),
        "pages_with_text": pages_with_text,
        "routed_to_ocr": _route(evidence),
    }


def _shipped_arm(path: Path) -> dict:
    """Historical pypdf-only guard, mirrored script-locally.

    Reproduces the shipped guard exactly (commit 928f030): pdf-inspector
    classify, then a single pypdf retry on the silent-empty
    contradiction with the same evidence correction. The pypdf retry is
    timed directly and repeated — the speed gate compares medians.
    """
    started = time.perf_counter()
    raw = pdf_inspector.process_pdf(str(path))
    classify_s = time.perf_counter() - started
    markdown = raw.markdown or ""
    evidence = {
        "pdf_type": raw.pdf_type,
        "pdf_confidence": raw.confidence,
        "page_count": raw.page_count,
        "pages_needing_ocr": len(raw.pages_needing_ocr or []),
    }
    backend = None
    retry_s = 0.0
    if evidence["pdf_type"] == "text_based" and not markdown and evidence["page_count"] > 0:
        result, retry_s = _measured(_pypdf_retry, path)
        if result[0]:
            markdown = result[0]
            backend = "pypdf"
            evidence["pages_needing_ocr"] = 0
    return {
        "classify_seconds": classify_s,
        "retry_seconds": retry_s,
        "total_seconds": classify_s + retry_s,
        "characters": len(markdown),
        "fallback_backend": backend,
        "pdf_type": raw.pdf_type,
        "page_count": raw.page_count,
        "routed_to_ocr": _route(evidence),
    }


def _round(value: object) -> object:
    """Round every float leaf to three decimals for serialisation."""
    if isinstance(value, float):
        return round(value, 3)
    if isinstance(value, dict):
        return {k: _round(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_round(v) for v in value]
    return value


def main() -> None:
    private = json.loads((EXP_DIR / "output/.collection.private.json").read_text())
    rows, public = [], []
    for entry in private["documents"]:
        path = Path(entry["path"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        shipped = _shipped_arm(path)
        chain = _chain_arm(path)
        chain["pdf_type"] = shipped["pdf_type"]
        rows.append(
            {
                "doc_id": entry["doc_id"],
                "split": entry["split"],
                "page_count": shipped["page_count"],
                "shipped": shipped,
                "chain": chain,
            }
        )
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
        # H2: the liteparse retry must not be slower than the pypdf retry
        # the shipped guard would have spent — median of three direct
        # measurements on the same document.
        "speed": all(
            r["chain"]["retry_seconds"] <= r["shipped"]["retry_seconds"] + 1e-9
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
    (EXP_DIR / "output/chain_results.json").write_text(
        json.dumps([_round(r) for r in rows], indent=2)
    )
    (EXP_DIR / "output/eval_results.summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(gates, indent=2))
    print("ALL PASS" if summary["all_pass"] else "GATE FAILURE")


if __name__ == "__main__":
    main()
