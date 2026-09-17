"""Experiment 33 narrow presence re-check (amendment 2026-09-17, two labels).

The operator's spot-check verdicts judged whether a page's extraction is good
enough for an LLM to understand it. The label rule judges only whether the
body text is present in the text layer. Both are kept:

- ``understanding_label``: the operator's first verdict and note, unchanged;
- ``presence_label``: the answer to one narrow question on every page where
  the first verdict disagreed with the rule: "Is the body text in the right
  panel?". Agreeing pages take the first verdict as their presence label.

The freeze gate (random-sample disagreement at most 10%) uses presence
labels only.

    uv run python .../recheck_page.py                 # write output/recheck.html
    uv run python .../recheck_page.py --merge FILE    # merge answers, report agreement
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
SPOT_CHECK = EXP_DIR / "spot_check.json"
PAGE = EXP_DIR / "output" / "recheck.html"
MAX_DISAGREEMENT = 0.10

#: Answer -> presence label. A page with no body text has nothing to lose.
ANSWERS = {
    "text_present": ("Yes: most body words are in the right panel", "usable"),
    "text_missing": ("No: body words are mostly missing or garbled", "needs_ocr"),
    "no_body_text": ("The page has no body text (blank or picture only)", "usable"),
    "unreadable": ("I cannot read the page image", "unrecoverable"),
}


def _entries(spot: dict) -> list[dict]:
    return spot["required"] + spot["random_sample"]


def _needs_recheck(entry: dict) -> bool:
    return bool(entry["operator_label"]) and entry["operator_label"] != entry["rule_label"]


def write_page() -> None:
    """Render one card per disagreement with the single presence question."""
    spot = json.loads(SPOT_CHECK.read_text(encoding="utf-8"))
    cards = []
    for entry in (e for e in _entries(spot) if _needs_recheck(e)):
        key = f"{entry['doc_id']}:{entry['page']}"
        stem = f".pages/{entry['doc_id']}/p{entry['page']:03d}"
        layers = []
        for name, title in (("pdftotext", "poppler pdftotext"), ("pypdf", "pypdf")):
            path = EXP_DIR / "output" / f"{stem}.{name}.txt"
            text = path.read_text(encoding="utf-8")[:3000] if path.exists() else ""
            layers.append(f"=== {title} ===\n{text.strip() or '(empty)'}")
        layer = "\n\n".join(layers)
        radios = "<br>".join(
            f'<label><input type="radio" name="{key}" value="{value}"> {html.escape(text)}</label>'
            for value, (text, _) in ANSWERS.items()
        )
        cards.append(
            f'<section data-key="{key}"><h2>{html.escape(key)}</h2>'
            f'<div class="row"><img loading="lazy" src="{stem}.png" alt="page {key}">'
            f"<pre>{html.escape(layer) or '(empty text layer)'}</pre></div>{radios}</section>"
        )
    PAGE.write_text(
        f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Experiment 33 presence re-check</title>
<style>
body{{font:14px system-ui;margin:16px;background:#fff;color:#111}}
section{{border-top:1px solid #ccc;padding:12px 0}}
.row{{display:flex;gap:12px;align-items:flex-start}}
img{{width:48%;border:1px solid #999}}
pre{{width:50%;max-height:720px;overflow:auto;white-space:pre-wrap;background:#f5f5f5;padding:8px}}
#bar{{position:sticky;top:0;background:#fff;padding:8px 0;border-bottom:2px solid #333}}
</style></head><body>
<div id="bar"><b>Is the body text in the right panel?</b> Answer yes if the words are in
EITHER text layer. The right panel is label evidence from two independent extractors
(poppler and pypdf), NOT the pipeline output (pdf-inspector, then LiteParse, then pypdf).
Ignore layout, equation rendering, figures, table structure and headings.
<br><button onclick="save()">Download answers</button>
<span id="count"></span> <span id="saved"></span></div>
{"".join(cards)}
<script>
const STORE='exp33-recheck-answers';
function collect(){{
  return [...document.querySelectorAll('section')].map(s=>{{
    const c=s.querySelector('input:checked'); return {{key:s.dataset.key, answer:c?c.value:null}};
  }});
}}
function update(){{
  const v=collect(); document.getElementById('count').textContent=
    v.filter(x=>x.answer).length+' of '+v.length+' answered';
  try {{ localStorage.setItem(STORE, JSON.stringify(v));
    document.getElementById('saved').textContent='(autosaved in this browser)'; }} catch(e) {{}}
}}
try {{
  const kept=JSON.parse(localStorage.getItem(STORE)||'[]');
  kept.forEach(v=>{{ if(!v.answer) return;
    const r=document.querySelector(`input[name="${{v.key}}"][value="${{v.answer}}"]`);
    if(r) r.checked=true; }});
}} catch(e) {{}}
document.addEventListener('change',update); update();
function save(){{
  const blob=new Blob([JSON.stringify(collect(),null,1)],{{type:'application/json'}});
  const a=document.createElement('a'); a.href=URL.createObjectURL(blob);
  a.download='recheck_answers.json'; a.click();
}}
</script></body></html>
""",
        encoding="utf-8",
    )
    count = sum(1 for e in _entries(spot) if _needs_recheck(e))
    print(f"[recheck] {count} pages -> {PAGE}")


def merge(answers_path: Path) -> int:
    """Store presence labels and report the freeze gate on presence labels."""
    spot = json.loads(SPOT_CHECK.read_text(encoding="utf-8"))
    answers = {a["key"]: a["answer"] for a in json.loads(answers_path.read_text("utf-8"))}
    for entry in _entries(spot):
        entry["understanding_label"] = entry["operator_label"]
        if _needs_recheck(entry):
            answer = answers.get(f"{entry['doc_id']}:{entry['page']}")
            entry["presence_answer"] = answer
            entry["presence_label"] = ANSWERS[answer][1] if answer in ANSWERS else None
        else:
            entry["presence_answer"] = None
            entry["presence_label"] = entry["operator_label"]
    sample = spot["random_sample"]
    answered = [e for e in sample if e["presence_label"]]
    disagree = [e for e in answered if e["presence_label"] != e["rule_label"]]
    share = len(disagree) / len(answered) if answered else None
    spot["presence_agreement"] = {
        "random_sample_answered": len(answered),
        "random_sample_total": len(sample),
        "random_sample_disagreements": len(disagree),
        "disagreement_share": None if share is None else round(share, 4),
        "required_answered": sum(1 for e in spot["required"] if e["presence_label"]),
        "required_total": len(spot["required"]),
        "freeze_allowed": bool(
            len(answered) == len(sample)
            and all(e["presence_label"] for e in spot["required"])
            and share is not None
            and share <= MAX_DISAGREEMENT
        ),
    }
    SPOT_CHECK.write_text(json.dumps(spot, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(spot["presence_agreement"], indent=1))
    return 0


def main() -> int:
    """Write the re-check page, or merge answers with --merge."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--merge", type=Path, help="answers JSON downloaded from the page")
    args = parser.parse_args()
    if args.merge:
        return merge(args.merge)
    write_page()
    return 0


if __name__ == "__main__":
    sys.exit(main())
