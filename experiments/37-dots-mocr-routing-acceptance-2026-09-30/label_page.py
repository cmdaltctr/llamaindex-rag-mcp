"""Experiment 37 maths labelling page (Gate B).

Two modes:

    # write output/maths_labels.html (local only: shows page images)
    uv run python experiments/37-.../label_page.py
    # merge labels downloaded from that page into maths_labels.json
    uv run python experiments/37-.../label_page.py --merge ~/Downloads/maths_labels_download.json

The page shows page images only. It shows no detector flag and no OCR
output, so the operator labels blind. Render the images first with
``render_pages.py --labelled``. Pages listed with ``--extra doc:4,6`` join
the page in a separate section (for example D-neg flagged pages).
"""

# ruff: noqa: E501 - embedded HTML/CSS/JS strings are kept on one line each
from __future__ import annotations

import argparse
import hashlib
import html
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
PAGE = EXP_DIR / "output" / "maths_labels.html"
LABELS_FILE = EXP_DIR / "maths_labels.json"
LABELS = ("maths", "no_maths")


def page_entries(extra: list[str]) -> list[tuple[str, str, int]]:
    """Return ``(section, doc_id, page)`` for every page to label."""
    sources = json.loads((EXP_DIR / "sources.json").read_text(encoding="utf-8"))["documents"]
    entries = []
    for doc in sources:
        if doc.get("label_pages"):
            entries += [("documents", doc["doc_id"], n) for n in range(1, doc["page_count"] + 1)]
    for spec in extra:
        doc_id, _, pages = spec.partition(":")
        entries += [("extra", doc_id, int(p)) for p in pages.split(",")]
    return entries


def card(doc_id: str, page: int) -> str:
    """One page card: image, two labels, a note."""
    key = f"{doc_id}:{page}"
    image = f".pages/{doc_id}/p{page:03d}.png"
    missing = "" if (EXP_DIR / "output" / image).is_file() else ' <b class="warn">image missing</b>'
    radios = "".join(
        f'<label><input type="radio" name="{key}" value="{v}"> {v}</label> ' for v in LABELS
    )
    return (
        f'<section class="card" data-key="{key}"><h3>{html.escape(key)}{missing}</h3>'
        f'<img loading="lazy" src="{image}" alt="{html.escape(key)}">'
        f'<div class="ctl">{radios}<input class="note" placeholder="note (optional)"></div></section>'
    )


def write_page(extra: list[str], remaining: bool = False) -> None:
    """Write the labelling page next to the page images.

    With *remaining*, the page lists only pages that ``maths_labels.json``
    does not hold yet, and uses its own browser storage and download name,
    so it cannot touch labels already given.
    """
    entries = page_entries(extra)
    page_file, store, download = PAGE, "exp37-maths-labels", "maths_labels_download.json"
    if remaining:
        done = _existing_labels()
        entries = [e for e in entries if str(e[2]) not in done.get(e[1], {})]
        page_file = PAGE.with_name("maths_labels_remaining.html")
        store, download = "exp37-maths-labels-remaining", "maths_labels_remaining_download.json"
    sections = {"documents": [], "extra": []}
    for section, doc_id, page in entries:
        sections[section].append(card(doc_id, page))
    extra_html = (
        "<h2>Extra pages</h2><p>Same rule. These pages come from outside the maths set.</p>"
        + "\n".join(sections["extra"])
        if sections["extra"]
        else ""
    )
    rule = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))["labels"]["maths_rule"]
    page_file.write_text(
        f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Experiment 37 maths labels</title>
<style>
:root {{ --bg:#fff; --fg:#1a1a1a; --muted:#666; --line:#ddd; --mark:#e8f0ff; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161616; --fg:#eee; --muted:#aaa; --line:#333; --mark:#1d2a40; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.4 system-ui, sans-serif; margin:0 16px 80px; }}
header {{ position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line); padding:8px 0; z-index:1; }}
.card {{ border:1px solid var(--line); border-radius:6px; margin:16px 0; padding:8px; max-width:900px; }}
.card.done {{ background:var(--mark); }}
.card img {{ width:100%; height:auto; border:1px solid var(--line); background:#fff; }}
.ctl {{ display:flex; gap:16px; align-items:center; flex-wrap:wrap; padding-top:6px; }}
.note {{ flex:1; min-width:180px; }}
.warn {{ color:#c00; }} .muted {{ color:var(--muted); }}
</style></head><body>
<header><b>Experiment 37 maths labels</b> · <span id="count"></span> ·
<button id="dl">Download labels</button> <span id="save" class="muted"></span>
<div class="muted">Rule: {html.escape(rule)}. Keys: <b>m</b> maths, <b>n</b> no_maths on the card nearest the top.</div></header>
{"".join(sections["documents"])}
{extra_html}
<script>
const STORE='{store}';
const cards=[...document.querySelectorAll('.card')];
function collect(){{ return cards.map(c=>{{ const k=c.dataset.key; const r=c.querySelector('input[type=radio]:checked');
  return {{key:k, label:r?r.value:null, note:c.querySelector('.note').value}}; }}); }}
function refresh(){{ let n=0; cards.forEach(c=>{{ const on=!!c.querySelector('input[type=radio]:checked'); c.classList.toggle('done',on); if(on) n++; }});
  document.getElementById('count').textContent=n+' / '+cards.length+' labelled';
  try {{ localStorage.setItem(STORE, JSON.stringify(collect())); document.getElementById('save').textContent='autosaved'; }}
  catch(e) {{ document.getElementById('save').textContent='(autosave unavailable: download often)'; }} }}
function apply(saved){{ const by=Object.fromEntries(saved.map(s=>[s.key,s])); cards.forEach(c=>{{ const s=by[c.dataset.key]; if(!s) return;
  if(s.label) {{ const r=c.querySelector('input[value='+s.label+']'); if(r) r.checked=true; }} c.querySelector('.note').value=s.note||''; }}); }}
try {{ const kept=localStorage.getItem(STORE); if(kept) apply(JSON.parse(kept)); }} catch(e) {{}}
document.addEventListener('change', refresh); document.addEventListener('input', refresh);
document.addEventListener('keydown', e=>{{ if(e.target.classList.contains('note')) return; const v={{m:'maths',n:'no_maths'}}[e.key]; if(!v) return;
  const c=cards.find(c=>c.getBoundingClientRect().bottom>120); if(!c) return; c.querySelector('input[value='+v+']').checked=true; refresh();
  const next=cards[cards.indexOf(c)+1]; if(next) next.scrollIntoView({{block:'start'}}); window.scrollBy(0,-90); }});
document.getElementById('dl').onclick=()=>{{ const blob=new Blob([JSON.stringify(collect(),null,1)],{{type:'application/json'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='{download}'; a.click(); }};
refresh();
</script></body></html>
""",
        encoding="utf-8",
    )
    print(f"[labels] {len(entries)} pages -> {page_file}", flush=True)


def _existing_labels() -> dict[str, dict[str, dict[str, str]]]:
    """Return the labels already merged, or an empty mapping."""
    if not LABELS_FILE.is_file():
        return {}
    return json.loads(LABELS_FILE.read_text(encoding="utf-8"))["documents"]


def merge(download: Path, labeller: str) -> int:
    """Check the download is complete, add it to maths_labels.json and print its SHA-256."""
    rows = json.loads(download.read_text(encoding="utf-8"))
    missing = [r["key"] for r in rows if r["label"] not in LABELS]
    if missing:
        print(
            f"{len(missing)} pages have no label, first: {missing[:10]}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    pages: dict[str, dict[str, dict[str, str]]] = _existing_labels()
    for row in rows:
        doc_id, _, page = row["key"].partition(":")
        entry = {"label": row["label"]}
        if row.get("note"):
            entry["note"] = row["note"]
        previous = pages.get(doc_id, {}).get(page)
        if previous and previous["label"] != entry["label"]:
            print(
                f"{row['key']}: {previous['label']} -> {entry['label']} (download wins)", flush=True
            )
        pages.setdefault(doc_id, {})[page] = entry
    plan = json.loads((EXP_DIR / "plan.json").read_text(encoding="utf-8"))
    data = {
        "rule": plan["labels"]["maths_rule"],
        "labeller": labeller,
        "merged_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "operator labels from page images (output/maths_labels.html), detector flags hidden",
        "documents": pages,
    }
    tmp = LABELS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(LABELS_FILE)
    digest = hashlib.sha256(LABELS_FILE.read_bytes()).hexdigest()
    counts = {v: sum(e["label"] == v for d in pages.values() for e in d.values()) for v in LABELS}
    expected = {(doc_id, str(n)) for _, doc_id, n in page_entries([])}
    pending = sorted(expected - {(d, n) for d, entries in pages.items() for n in entries})
    total = sum(len(d) for d in pages.values())
    print(
        f"[labels] {len(rows)} pages merged, {total} held, {len(pending)} of {len(expected)} still unlabelled",
        flush=True,
    )
    print(f"[labels] {counts} -> {LABELS_FILE.name} sha256 {digest}", flush=True)
    return 0


def main() -> int:
    """Write the page, or merge a download."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--extra", nargs="*", default=[], help="extra pages, doc_id:1,2")
    parser.add_argument(
        "--remaining", action="store_true", help="page of pages not yet in maths_labels.json"
    )
    parser.add_argument("--merge", type=Path, help="labels JSON downloaded from the page")
    parser.add_argument("--labeller", default="operator (Dr Muhammad Aizat Bin Md Hawari)")
    args = parser.parse_args()
    if args.merge:
        return merge(args.merge, args.labeller)
    write_page(args.extra, remaining=args.remaining)
    return 0


if __name__ == "__main__":
    sys.exit(main())
