"""Task 3.1: build the seeded candidate lists, download the corpus, write sources.json.

Follows plan.json sourcing.procedure (seed 42). Metadata only: no page text is
read for selection. Candidate lists are saved before any download
(output/candidates.json) and taken in order.

    uv run --no-sync python prepare_corpus.py --lists      # build and save the ordered lists
    uv run --no-sync python prepare_corpus.py --download   # download until each quota is met
    uv run --no-sync python prepare_corpus.py --extend born_digital=5 old_ocr_layer=6
"""

from __future__ import annotations

import argparse
import json
import random
import time
import urllib.parse
import urllib.request
from pathlib import Path

from exp42_io import EXP33, EXP_DIR, OUTPUT, atomic_json, plan, read_json, sha256

CORPUS = EXP_DIR / "corpus"
SOURCES = EXP_DIR / "sources.json"
CANDIDATES = OUTPUT / "candidates.json"
SOURCING = EXP_DIR / "SOURCING.md"
SEED = 42
USER_AGENT = "experiment-42 corpus preparation (research; mailto:aizat@praxis.my)"
PREFIX = {
    "born_digital": "bd",
    "mixed": "mx",
    "scan_with_text_layer": "st",
    "old_ocr_layer": "oo",
}
IA_GROUPS = {
    "arabic": "language:(ara OR Arabic)",
    "urdu": "language:(urd OR Urdu)",
    "persian": "language:(per OR fas OR Persian)",
    "hindi": "language:(hin OR Hindi)",
    "bengali": "language:(ben OR Bengali)",
    "handwriting": "subject:(manuscript OR manuscripts OR handwriting OR handwritten OR letters)",
}
NTRS_LICENCE = "NTRS public distribution; no author, contractor, publisher or third-party copyright"
NTRS_EXCLUDED_TYPES = {"PRESENTATION", "POSTER", "ABSTRACT"}
NTRS_COPYRIGHT_FLAGS = (
    "belongsToAuthors",
    "belongsToContractor",
    "belongsToPublisher",
    "containsThirdPartyMaterial",
)


def _get(url: str, timeout: int = 120) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return response.read()


def _json(url: str) -> dict:
    return json.loads(_get(url))


def exp33_exclusions() -> tuple[set[str], set[str]]:
    """Return Experiment 33 SHA-256 values and source identifiers."""
    docs = read_json(EXP33 / "sources.json")["documents"]
    return {d["sha256"] for d in docs}, {str(d["source_identifier"]).lower() for d in docs}


def is_excluded(sha: str, identifier: str, exclusions: tuple[set[str], set[str]]) -> bool:
    """True when a document overlaps Experiment 33 by hash or identifier."""
    hashes, identifiers = exclusions
    return sha in hashes or identifier.lower() in identifiers


# ── Candidate lists (metadata only) ─────────────────────────────────


def openalex_list() -> list[dict]:
    """OpenAlex seeded sample of CC BY articles 2021-2025 with a PDF URL."""
    query = urllib.parse.urlencode(
        {
            "filter": "best_oa_location.license:cc-by,type:article,"
            "publication_year:2021-2025,has_content.pdf:true",
            "sample": 200,
            "seed": SEED,
            "per-page": 200,
            "select": "id,doi,title,publication_year,best_oa_location",
        }
    )
    out = []
    for work in _json(f"https://api.openalex.org/works?{query}")["results"]:
        location = work.get("best_oa_location") or {}
        if not location.get("pdf_url") or not work.get("doi"):
            continue
        doi = work["doi"].removeprefix("https://doi.org/")
        out.append(
            {
                "source": "doi",
                "source_identifier": doi,
                "title": work.get("title") or "",
                "year": work.get("publication_year"),
                "landing_url": work["doi"],
                "pdf_url": location["pdf_url"],
                "licence": location.get("license"),
                "licence_evidence": f"OpenAlex best_oa_location.license for doi:{doi}",
            }
        )
    return out


def ntrs_list(start: str, end: str) -> list[dict]:
    """First 300 NTRS records for query 'report' in a date window, id ascending, shuffled."""
    records = []
    for page_from in (0, 100, 200):
        query = urllib.parse.urlencode(
            {
                "q": "report",
                "published.gte": start,
                "published.lte": end,
                "page.size": 100,
                "page.from": page_from,
            }
        )
        records += _json(f"https://ntrs.nasa.gov/api/citations/search?{query}")["results"]
        time.sleep(1)
    out = []
    for r in sorted({str(r["id"]): r for r in records}.values(), key=lambda r: int(r["id"])):
        pdfs = [
            d["links"]["pdf"] for d in r.get("downloads") or [] if d.get("links", {}).get("pdf")
        ]
        rights = r.get("copyright") or {}
        if (
            r.get("stiType") in NTRS_EXCLUDED_TYPES
            or not pdfs
            or r.get("distribution") != "PUBLIC"
            or not rights
            or any(rights.get(flag) for flag in NTRS_COPYRIGHT_FLAGS)
        ):
            continue
        date = (r.get("publications") or [{}])[0].get("publicationDate") or ""
        out.append(
            {
                "source": "ntrs",
                "source_identifier": str(r["id"]),
                "title": r.get("title") or "",
                "year": int(date[:4]) if date[:4].isdigit() else None,
                "landing_url": f"https://ntrs.nasa.gov/citations/{r['id']}",
                "pdf_url": "https://ntrs.nasa.gov" + pdfs[0],
                "licence": NTRS_LICENCE,
                "licence_evidence": "NTRS citation record distribution and copyright fields",
            }
        )
    random.Random(SEED).shuffle(out)  # noqa: S311 - seeded selection, not security
    return out


def ia_list(group: str, clause: str) -> list[dict]:
    """First 200 Archive.org identifiers (ascending) for one group, shuffled with seed 42."""
    query = f"mediatype:texts AND licenseurl:*publicdomain* AND imagecount:[4 TO 30] AND {clause}"
    params = urllib.parse.urlencode(
        {
            "q": query,
            "fl[]": ["identifier", "title", "year", "licenseurl", "language"],
            "rows": 200,
            "output": "json",
            "sort[]": "identifier asc",
        },
        doseq=True,
    )
    docs = _json(f"https://archive.org/advancedsearch.php?{params}")["response"]["docs"]
    out = [
        {
            "source": "ia",
            "group": group,
            "source_identifier": d["identifier"],
            "title": str(d.get("title") or "")[:200],
            "year": d.get("year"),
            "landing_url": f"https://archive.org/details/{d['identifier']}",
            "pdf_url": None,
            "licence": d.get("licenseurl"),
            "licence_evidence": "Archive.org item metadata licenseurl (uploader-declared)",
        }
        for d in docs
    ]
    random.Random(SEED).shuffle(out)  # noqa: S311 - seeded selection, not security
    return out


def ia_round_robin(lists: dict[str, list[dict]]) -> list[dict]:
    """Interleave the IA groups so quotas fill evenly across scripts."""
    out, index = [], 0
    while any(index < len(v) for v in lists.values()):
        out += [v[index] for v in lists.values() if index < len(v)]
        index += 1
    return out


def build_lists() -> dict:
    """Build every ordered candidate list."""
    ia = {g: ia_list(g, c) for g, c in IA_GROUPS.items()}
    return {
        "seed": SEED,
        "built_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lists": {
            "born_digital": openalex_list(),
            "mixed": ntrs_list("2010-01-01", "2024-12-31"),
            "scan_with_text_layer": ntrs_list("1955-01-01", "1985-12-31"),
            "old_ocr_layer": ia_round_robin(ia),
        },
    }


# ── Download ────────────────────────────────────────────────────────


def ia_text_pdf(identifier: str) -> str | None:
    """Return the download URL of the item's 'Text PDF' file, if any."""
    meta = _json(f"https://archive.org/metadata/{urllib.parse.quote(identifier)}")
    for f in meta.get("files", []):
        if f.get("format") == "Text PDF":
            return f"https://archive.org/download/{identifier}/{urllib.parse.quote(f['name'])}"
    return None


def page_count(path: Path) -> int:
    """Count pages with pypdf; -1 when the file does not parse."""
    from pypdf import PdfReader

    try:
        return len(PdfReader(str(path)).pages)
    except Exception:  # noqa: BLE001 - any parse failure skips the document
        return -1


def try_candidate(
    candidate: dict, stratum: str, doc_id: str, state: dict
) -> tuple[dict | None, str]:
    """Download one candidate; return (document, reason)."""
    low, high = plan()["sourcing"]["procedure"]["strata"][stratum]["pages"]
    url = candidate["pdf_url"]
    if candidate["source"] == "ia":
        url = ia_text_pdf(candidate["source_identifier"])
        if url is None:
            return None, "no Text PDF file"
    dest = CORPUS / f"{doc_id}.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = _get(url)
    except Exception as exc:  # noqa: BLE001 - every failure is logged and skipped
        return None, f"download failed: {type(exc).__name__} {getattr(exc, 'code', '')}".strip()
    if not data.startswith(b"%PDF"):
        return None, "not a PDF"
    tmp = dest.with_suffix(".pdf.tmp")
    tmp.write_bytes(data)
    pages = page_count(tmp)
    digest = sha256(tmp)
    reason = ""
    if not low <= pages <= high:
        reason = f"page count {pages} outside {low}-{high}"
    elif is_excluded(digest, candidate["source_identifier"], state["exclusions"]):
        reason = "overlaps Experiment 33"
    elif digest in state["hashes"]:
        reason = "duplicate SHA-256"
    if reason:
        tmp.unlink()
        return None, reason
    tmp.replace(dest)
    state["hashes"].add(digest)
    return {
        "doc_id": doc_id,
        "stratum": stratum,
        **{k: v for k, v in candidate.items() if k != "pdf_url"},
        "pdf_url": url,
        "page_count": pages,
        "sha256": digest,
        "bytes": len(data),
        "local_path": f"corpus/{doc_id}.pdf",
    }, "kept"


def download(quotas: dict[str, int]) -> None:
    """Take candidates in list order until each stratum reaches its quota."""
    lists = read_json(CANDIDATES)["lists"]
    sources = read_json(SOURCES) if SOURCES.exists() else {"documents": [], "log": []}
    state = {
        "exclusions": exp33_exclusions(),
        "hashes": {d["sha256"] for d in sources["documents"]},
    }
    tried = {(e["stratum"], e["source_identifier"]) for e in sources["log"]}
    for stratum, quota in quotas.items():
        have = [d for d in sources["documents"] if d["stratum"] == stratum]
        for candidate in lists[stratum]:
            if len(have) >= quota:
                break
            if (stratum, candidate["source_identifier"]) in tried:
                continue
            doc_id = f"{PREFIX[stratum]}{len(have) + 1:02d}"
            document, reason = try_candidate(candidate, stratum, doc_id, state)
            sources["log"].append(
                {
                    "stratum": stratum,
                    "source_identifier": candidate["source_identifier"],
                    "doc_id": doc_id if document else None,
                    "result": reason,
                }
            )
            if document:
                have.append(document)
                sources["documents"].append(document)
            atomic_json(SOURCES, sources)
            print(f"[{stratum}] {candidate['source_identifier']}: {reason}", flush=True)
            time.sleep(1)
        print(f"[{stratum}] {len(have)}/{quota}", flush=True)
    write_sourcing(sources)


def write_sourcing(sources: dict) -> None:
    """Write SOURCING.md from sources.json."""
    docs = sources["documents"]
    lines = [
        "# Experiment 42 sourcing log",
        "",
        "Generated by `prepare_corpus.py` from `sources.json`. Do not edit by hand.",
        "Procedure: `plan.json` `sourcing.procedure` (seed 42).",
        "Ordered lists: `output/candidates.json`.",
        "",
        f"{len(docs)} documents, {sum(d['page_count'] for d in docs)} pages.",
        "",
        "## Counts by stratum",
        "",
        "| Stratum | Documents | Pages |",
        "| --- | ---: | ---: |",
    ]
    for stratum in PREFIX:
        group = [d for d in docs if d["stratum"] == stratum]
        lines.append(f"| `{stratum}` | {len(group)} | {sum(d['page_count'] for d in group)} |")
    removed = [e for e in sources["log"] if e["result"] != "kept"]
    lines += [
        "",
        "## Removed or skipped candidates",
        "",
        "| Stratum | Identifier | Reason |",
        "| --- | --- | --- |",
    ]
    lines += [f"| `{e['stratum']}` | `{e['source_identifier']}` | {e['result']} |" for e in removed]
    lines += [
        "",
        "## Documents",
        "",
        "| doc_id | Stratum | Group | Year | Pages | Licence | Source | SHA-256 |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- |",
    ]
    for d in docs:
        lines.append(
            f"| `{d['doc_id']}` | `{d['stratum']}` | {d.get('group', '')} | {d.get('year') or ''} "
            f"| {d['page_count']} | {d.get('licence') or ''} "
            f"| [{d['source_identifier']}]({d['landing_url']}) "
            f"| `{d['sha256'][:16]}…` |"
        )
    SOURCING.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    """Parse arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lists", action="store_true")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--extend", nargs="*", default=[], help="stratum=extra_documents")
    args = parser.parse_args()
    procedure = plan()["sourcing"]["procedure"]
    if args.lists:
        if CANDIDATES.exists():
            raise SystemExit("candidates.json exists; the lists are fixed")
        atomic_json(CANDIDATES, build_lists())
    if args.download:
        download({s: v["quota"] for s, v in procedure["strata"].items()})
    if args.extend:
        sources = read_json(SOURCES)
        quotas = {}
        for item in args.extend:
            stratum, extra = item.split("=")
            have = sum(d["stratum"] == stratum for d in sources["documents"])
            quotas[stratum] = have + int(extra)
        download(quotas)


if __name__ == "__main__":
    main()
