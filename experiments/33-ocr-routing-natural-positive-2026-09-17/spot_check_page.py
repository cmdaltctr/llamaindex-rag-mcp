"""Experiment 33 operator spot-check helper (label freeze step).

Two modes:

    # write output/spot_check.html from spot_check.json (local only: shows page text)
    uv run python experiments/33-ocr-routing-natural-positive-2026-09-17/spot_check_page.py
    # merge verdicts downloaded from that page back into spot_check.json and report agreement
    uv run python .../spot_check_page.py --merge ~/Downloads/spot_check_verdicts.json

Open ``output/spot_check.html`` in a browser, set a verdict for every page,
press "Download verdicts", then run ``--merge``.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
SPOT_CHECK = EXP_DIR / "spot_check.json"
EVIDENCE = EXP_DIR / "output" / "page_evidence.json"
PAGE = EXP_DIR / "output" / "spot_check.html"
LABELS = ("usable", "needs_ocr", "unrecoverable", "ambiguous")
MAX_DISAGREEMENT = 0.10


def _entries(spot: dict) -> list[tuple[str, dict]]:
    return [("required", e) for e in spot["required"]] + [
        ("random_sample", e) for e in spot["random_sample"]
    ]


def _card(group: str, entry: dict, evidence: dict) -> str:
    key = f"{entry['doc_id']}:{entry['page']}"
    stem = f".pages/{entry['doc_id']}/p{entry['page']:03d}"
    layer_path = EXP_DIR / "output" / f"{stem}.pypdf.txt"
    layer = layer_path.read_text(encoding="utf-8")[:3000] if layer_path.exists() else ""
    ev = evidence[key]
    options = "".join(
        f'<option value="{label}"{" selected" if entry["operator_label"] == label else ""}>'
        f"{label}</option>"
        for label in ("",) + LABELS
    )
    return (
        f'<section data-key="{key}" data-group="{group}">'
        f"<h2>{html.escape(key)} <small>{group} · rule: <b>{entry['rule_label']}</b> · "
        f"R_best {ev['r_best']} · legibility {ev['legibility']}</small></h2>"
        f'<div class="row"><img loading="lazy" src="{stem}.png" alt="page {key}">'
        f"<pre>{html.escape(layer) or '(empty text layer)'}</pre></div>"
        f'<label>Your label <select name="label">{options}</select></label> '
        f'<label>Note <input name="note" size="60" value="{html.escape(entry["note"] or "")}">'
        f"</label></section>"
    )


def write_page() -> None:
    """Render the review page next to the local page images."""
    spot = json.loads(SPOT_CHECK.read_text(encoding="utf-8"))
    evidence = {
        f"{p['doc_id']}:{p['page']}": p
        for p in json.loads(EVIDENCE.read_text(encoding="utf-8"))["pages"]
    }
    cards = "\n".join(_card(g, e, evidence) for g, e in _entries(spot))
    PAGE.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Experiment 33 spot check</title>
<style>
body{{font:14px system-ui;margin:16px;background:#fff;color:#111}}
section{{border-top:1px solid #ccc;padding:12px 0}}
.row{{display:flex;gap:12px;align-items:flex-start}}
img{{width:48%;border:1px solid #999}}
pre{{width:50%;max-height:720px;overflow:auto;white-space:pre-wrap;background:#f5f5f5;padding:8px}}
#bar{{position:sticky;top:0;background:#fff;padding:8px 0;border-bottom:2px solid #333}}
</style></head><body>
<div id="bar"><b>Experiment 33 spot check</b> — {html.escape(spot["instructions"])}
<br><button onclick="save()">Download verdicts</button> <span id="count"></span></div>
{cards}
<script>
function collect(){{
  return [...document.querySelectorAll('section')].map(s=>({{
    key:s.dataset.key, group:s.dataset.group,
    operator_label:s.querySelector('select').value||null,
    note:s.querySelector('input').value||null}}));
}}
function update(){{
  const v=collect(); document.getElementById('count').textContent=
    v.filter(x=>x.operator_label).length+' of '+v.length+' reviewed';
}}
document.addEventListener('change',update); update();
function save(){{
  const blob=new Blob([JSON.stringify(collect(),null,1)],{{type:'application/json'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='spot_check_verdicts.json'; a.click();
}}
</script></body></html>
""",
        encoding="utf-8",
    )
    print(f"[spot] {len(spot['required']) + len(spot['random_sample'])} pages -> {PAGE}")


def merge(verdicts_path: Path) -> int:
    """Merge downloaded verdicts and report random-sample disagreement."""
    spot = json.loads(SPOT_CHECK.read_text(encoding="utf-8"))
    verdicts = {v["key"]: v for v in json.loads(verdicts_path.read_text(encoding="utf-8"))}
    for _, entry in _entries(spot):
        verdict = verdicts.get(f"{entry['doc_id']}:{entry['page']}")
        if verdict and verdict["operator_label"] in LABELS:
            entry["operator_label"] = verdict["operator_label"]
            entry["note"] = verdict["note"]
    sample = spot["random_sample"]
    reviewed = [e for e in sample if e["operator_label"]]
    disagree = [e for e in reviewed if e["operator_label"] != e["rule_label"]]
    share = len(disagree) / len(reviewed) if reviewed else None
    spot["agreement"] = {
        "random_sample_reviewed": len(reviewed),
        "random_sample_total": len(sample),
        "random_sample_disagreements": len(disagree),
        "disagreement_share": None if share is None else round(share, 4),
        "required_reviewed": sum(1 for e in spot["required"] if e["operator_label"]),
        "required_total": len(spot["required"]),
        "freeze_allowed": bool(
            reviewed
            and len(reviewed) == len(sample)
            and all(e["operator_label"] for e in spot["required"])
            and share is not None
            and share <= MAX_DISAGREEMENT
        ),
    }
    SPOT_CHECK.write_text(json.dumps(spot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(spot["agreement"], indent=1))
    return 0


def main() -> int:
    """Write the review page, or merge verdicts when --merge is given."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merge", type=Path, help="verdicts JSON downloaded from the page")
    args = parser.parse_args()
    if args.merge:
        return merge(args.merge)
    write_page()
    return 0


if __name__ == "__main__":
    sys.exit(main())
