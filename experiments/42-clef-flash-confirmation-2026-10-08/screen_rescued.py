"""Amendment A8: screen new documents and keep those the shipped chain rescues.

    uv run --no-sync python -u screen_rescued.py --lists    # build and save the ordered lists
    uv run --no-sync python -u screen_rescued.py --screen   # download, read once, keep rescued

Selection uses only the shipped reader's routing output
(``extraction_fallback_backend``). No label, reference or score is read.
Kept documents are appended to sources.json with stratum ``rescue_screen``.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import re
import time
import urllib.parse

import prepare_corpus as pc
from exp42_io import EXP_DIR, OUTPUT, atomic_json, plan, read_json

LISTS = OUTPUT / "candidates_rescue.json"
ACL_VOLUMES = (
    "P89-1",
    "P90-1",
    "P91-1",
    "H89-1",
    "H90-1",
    "H91-1",
    "E89-1",
    "E91-1",
    "C90-1",
    "C90-2",
    "C90-3",
)
IA_QUERY = (
    "collection:(archivo-historico-universidad-sevilla OR bibliotecauniversitariadesevilla) "
    "AND imagecount:[4 TO 30] AND licenseurl:*publicdomain*"
)
PAGES = {"acl": (3, 30), "ia_sevilla": (4, 30), "ntrs_scans": (4, 30)}
TARGET, PER_LIST, MINUTES = 60, 30, 90


def acl_list() -> list[dict]:
    """Paper ids from the fixed ACL volumes, front matter excluded, shuffled with seed 42."""
    ids = []
    for volume in ACL_VOLUMES:
        try:
            html = pc._get(f"https://aclanthology.org/volumes/{volume}/").decode()  # noqa: SLF001
        except Exception:  # noqa: BLE001 - a missing volume is skipped and logged
            print(f"[lists] volume {volume} unavailable", flush=True)
            continue
        ids += sorted(
            {i for i in re.findall(r"/([A-Z]\d\d-\d{4})\.pdf", html) if not i.endswith("000")}
        )
    random.Random(42).shuffle(ids)  # noqa: S311 - seeded selection, not security
    return [
        {
            "source": "acl",
            "source_identifier": i,
            "title": "",
            "year": 1900 + int(i[1:3]),
            "landing_url": f"https://aclanthology.org/{i}/",
            "pdf_url": f"https://aclanthology.org/{i}.pdf",
            "licence": "CC BY-NC-SA 3.0",
            "licence_evidence": "ACL Anthology licence for pre-2016 papers",
        }
        for i in ids
    ]


def ia_list() -> list[dict]:
    """First 300 Sevilla identifiers ascending, shuffled with seed 42."""
    params = urllib.parse.urlencode(
        {
            "q": IA_QUERY,
            "fl[]": ["identifier", "title", "year", "licenseurl"],
            "rows": 300,
            "output": "json",
            "sort[]": "identifier asc",
        },
        doseq=True,
    )
    docs = pc._json(f"https://archive.org/advancedsearch.php?{params}")["response"]["docs"]  # noqa: SLF001
    out = [
        {
            "source": "ia",
            "group": "sevilla",
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
    random.Random(42).shuffle(out)  # noqa: S311 - seeded selection, not security
    return out


def ntrs_list() -> list[dict]:
    """The untried remainder of the saved NTRS scan list, in saved order."""
    tried = {e["source_identifier"] for e in read_json(EXP_DIR / "sources.json")["log"]}
    saved = read_json(OUTPUT / "candidates.json")["lists"]["scan_with_text_layer"]
    return [c for c in saved if c["source_identifier"] not in tried]


def rescued_backend(path) -> str | None:
    """Read once with the shipped chain; return the rescue tier or None."""
    from omrg.compose import settings_to_effective
    from omrg.config import Settings
    from omrg.core.ingestion.backends.local import read_documents

    effective = settings_to_effective(Settings())
    documents = asyncio.run(read_documents(path, settings=effective, ocr_client=None))
    meta = documents[0].metadata if documents else {}
    if meta.get("ocr_used"):
        raise SystemExit("stage separation violated: ocr_used=True")
    return meta.get("extraction_fallback_backend")


def screen() -> None:
    """Round-robin the lists until a stop rule fires."""
    lists = read_json(LISTS)["lists"]
    sources = read_json(EXP_DIR / "sources.json")
    state = {
        "exclusions": pc.exp33_exclusions(),
        "hashes": {d["sha256"] for d in sources["documents"]},
    }
    kept = {name: 0 for name in lists}
    kept_total = sum(d["stratum"] == "rescue_screen" for d in sources["documents"])
    position = {name: 0 for name in lists}
    started = time.monotonic()
    current = plan()
    # try_candidate reads page limits from plan(); point it at this list's limits.
    pc.plan = lambda: current
    pc.PREFIX["rescue_screen"] = "rs"
    while kept_total < TARGET and time.monotonic() - started < MINUTES * 60:
        active = [n for n in lists if kept[n] < PER_LIST and position[n] < len(lists[n])]
        if not active:
            break
        for name in active:
            if kept_total >= TARGET:
                break
            candidate = lists[name][position[name]]
            position[name] += 1
            doc_id = f"rs{kept_total + 1:02d}"
            current["sourcing"]["procedure"]["strata"]["rescue_screen"] = {
                "pages": list(PAGES[name])
            }
            document, reason = pc.try_candidate(candidate, "rescue_screen", doc_id, state)
            if document:
                path = EXP_DIR / document["local_path"]
                backend = rescued_backend(path)
                if backend is None:
                    path.unlink()
                    state["hashes"].discard(document["sha256"])
                    document, reason = None, "not rescued (pdf-inspector text kept or OCR routed)"
                else:
                    document.update(screen_list=name, screen_backend=backend)
                    reason = f"kept: rescued by {backend}"
            sources["log"].append(
                {
                    "stratum": "rescue_screen",
                    "list": name,
                    "source_identifier": candidate["source_identifier"],
                    "doc_id": doc_id if document else None,
                    "result": reason,
                }
            )
            if document:
                sources["documents"].append(document)
                kept[name] += 1
                kept_total += 1
            atomic_json(EXP_DIR / "sources.json", sources)
            print(f"[{name}] {candidate['source_identifier']}: {reason} ({kept_total})", flush=True)
            time.sleep(1)
    print(f"[screen] kept {kept_total}: {kept}", flush=True)
    pc.write_sourcing(sources)


def main() -> None:
    """Parse arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lists", action="store_true")
    parser.add_argument("--screen", action="store_true")
    args = parser.parse_args()
    plan()
    if args.lists:
        if LISTS.exists():
            raise SystemExit("candidates_rescue.json exists; the lists are fixed")
        payload = {"acl": acl_list(), "ia_sevilla": ia_list(), "ntrs_scans": ntrs_list()}
        atomic_json(LISTS, {"seed": 42, "lists": payload})
        print({k: len(v) for k, v in payload.items()}, flush=True)
    if args.screen:
        screen()


if __name__ == "__main__":
    main()
