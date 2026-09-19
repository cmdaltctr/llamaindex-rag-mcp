# ruff: noqa: E501
#!/usr/bin/env python3
"""Build the Experiment 34 review page (task 2.3).

One self-contained HTML file: for every sampled page, the original page
image on the left and the worker's extracted Markdown on the right,
with a per-page checklist the operator fills in. Verdicts persist to
browser localStorage and export as ``review_verdicts.json`` (download
button), which is committed unchanged as the experiment's result.

Copies the needed page images from the Experiment 33 worktree into
``output/pages/`` (relative references keep the HTML movable).

Usage:
    python3 make_review.py
"""

from __future__ import annotations

import html
import json
import shutil
from pathlib import Path

EXP_DIR = Path(__file__).resolve().parent
OUT_PAGES = EXP_DIR / "output" / "pages"
REVIEW = EXP_DIR / "output" / "review.html"

ISSUE = {
    "io06": "Old book: language/typography + structure",
    "io04": "Triple column with images",
    "bd01": "Two column (worker vs pdf-inspector fast path)",
    "bd02": "Two column (worker vs pdf-inspector fast path)",
    "tl03": "Tables",
}

#: Column headers for the reader panes (operator request: show the real
#: output of every engine, per page).
PANE_PDFI = "pdf-inspector (fast path)"
PANE_LITEPARSE = "LiteParse (fixed join, rescue tier)"
PANE_WORKER = "OCR worker (PaddleOCR-VL)"

CHECKLIST = """
<div class="checks">
  <label>Text accuracy:
    <select data-k="accuracy">
      <option value="">—</option><option>all correct</option><option>most correct</option>
      <option>some correct</option><option>mostly wrong</option>
    </select>
  </label>
  <label>Column order:
    <select data-k="columns">
      <option value="">—</option><option>correct</option><option>wrong</option><option>n/a</option>
    </select>
  </label>
  <label>Headings/structure:
    <select data-k="headings">
      <option value="">—</option><option>preserved</option><option>lost/garbled</option><option>n/a</option>
    </select>
  </label>
  <label>Table:
    <select data-k="table">
      <option value="">—</option><option>readable</option><option>broken</option><option>n/a</option>
    </select>
  </label>
  <label>Ready for an LLM:
    <select data-k="llm">
      <option value="">—</option><option>yes</option><option>no</option>
    </select>
  </label>
  <label class="note">Note: <textarea data-k="note" rows="2"></textarea></label>
</div>
"""

PAGE_TMPL = """
<section class="page" data-doc="{doc}" data-page="{page}">
  <h3>{doc} — page {page}
    <span class="role {role}">{role}</span>
    <span class="issue">{issue}</span>
    <span class="status" id="status-{doc}-{page}"></span>
  </h3>
  <div class="panes">
    <div class="pane"><h4>Original</h4><img loading="lazy" src="pages/{doc}/p{page:03d}.png" alt="{doc} page {page}"></div>
    <div class="pane"><h4>{pdfi_label}</h4><div class="md">{pdfi_html}</div></div>
    <div class="pane"><h4>{lp_label}</h4><div class="md">{lp_html}</div></div>
    <div class="pane"><h4>{worker_label}</h4><div class="md">{md_html}</div>
      <details><summary>raw markdown</summary><pre>{md_raw}</pre></details>
    </div>
  </div>
  {checklist}
</section>
"""


def _mini_markdown(text: str) -> str:
    """Tiny Markdown-to-HTML for review purposes only (headings, lists, tables stay text-safe)."""
    out: list[str] = []
    in_code = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
            out.append(f"<pre>{html.escape(line)}</pre>" if not in_code else "<pre>")
            continue
        if in_code:
            out.append(html.escape(line))
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            out.append(
                f"<h{min(level + 2, 6)}>{html.escape(stripped[level:].strip())}</h{min(level + 2, 6)}>"
            )
        else:
            out.append(f"<p>{html.escape(line)}</p>")
    return "\n".join(out)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="render only these doc:page pairs, e.g. 'io06:28,io06:53'")
    parser.add_argument("--out", default="review.html", help="output file name under output/")
    args = parser.parse_args()

    sample = json.loads((EXP_DIR / "sample.json").read_text(encoding="utf-8"))
    exp33 = Path(sample["exp33_dir"])
    images_src = exp33 / "output" / ".pages"

    only = None
    if args.only:
        only = {tuple(item.strip().partition(":")[::2]) for item in args.only.split(",")}

    sections: list[str] = []
    for row in sorted(sample["pages"], key=lambda r: (r["doc_id"], r["page"])):
        if only is not None and (row["doc_id"], str(row["page"])) not in only:
            continue
        doc, page = row["doc_id"], row["page"]
        md_file = EXP_DIR / "output" / "worker" / doc / f"p{page:03d}.md"
        md = (
            md_file.read_text(encoding="utf-8")
            if md_file.exists()
            else (
                "PENDING — the worker run has not reached this page yet. "
                "Re-run make_review.py as the run progresses to fill it in."
            )
        )
        pdfi_file = EXP_DIR / "output" / "pdf_inspector" / doc / f"p{page:03d}.md"
        pdfi = pdfi_file.read_text(encoding="utf-8") if pdfi_file.exists() else "(not extracted)"
        if not pdfi.strip():
            pdfi = "(empty — pdf-inspector extracted no text from this page)"
        lp_file = EXP_DIR / "output" / "liteparse" / doc / f"p{page:03d}.md"
        lp = lp_file.read_text(encoding="utf-8") if lp_file.exists() else "(not extracted)"
        if not lp.strip():
            lp = "(empty — LiteParse extracted no text from this page)"
        dst = OUT_PAGES / doc / f"p{page:03d}.png"
        if not dst.exists():
            src = images_src / doc / f"p{page:03d}.png"
            if not src.is_file():
                raise SystemExit(f"missing page image: {src}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        sections.append(
            PAGE_TMPL.format(
                doc=doc,
                page=page,
                role=row["role"],
                issue=ISSUE.get(doc, "Clean control"),
                pdfi_label=PANE_PDFI,
                pdfi_html=_mini_markdown(pdfi),
                lp_label=PANE_LITEPARSE,
                lp_html=_mini_markdown(lp),
                worker_label=PANE_WORKER,
                md_html=_mini_markdown(md),
                md_raw=html.escape(md),
                checklist=CHECKLIST,
            )
        )

    REVIEW.parent.mkdir(parents=True, exist_ok=True)
    out_path = EXP_DIR / "output" / args.out
    out_path.write_text(HTML_HEAD + "\n".join(sections) + HTML_TAIL, encoding="utf-8")
    print(f"wrote {out_path} ({len(sections)} pages)")
    return 0


HTML_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<title>Experiment 34 — worker sample review</title>
<style>
 body{font-family:system-ui;margin:0;padding:1rem;background:#f6f6f6}
 h1{font-size:1.3rem} h3{margin:0 0 .5rem;font-size:1.05rem;display:flex;gap:.6rem;align-items:center}
 .role{font-size:.75rem;padding:.1rem .5rem;border-radius:1rem;color:#fff}
 .role.problem{background:#b3392c}.role.control{background:#2c7ab3}
 .issue{font-size:.8rem;color:#555}
 .page{background:#fff;border:1px solid #ddd;border-radius:8px;padding:1rem;margin:1rem 0}
 .panes{display:flex;gap:1rem;align-items:flex-start}
 .pane{flex:1;min-width:0}
 .pane img{width:100%;border:1px solid #ccc}
 .pane h4{margin:.2rem 0 .4rem;font-size:.85rem;color:#444}
 .md{max-height:70vh;overflow:auto;border:1px solid #eee;padding:.5rem;background:#fafafa}
 .md p{margin:.15rem 0;font-size:.85rem}
 details summary{cursor:pointer;font-size:.8rem;color:#555;margin-top:.4rem}
 pre{white-space:pre-wrap;font-size:.75rem;max-height:40vh;overflow:auto}
 .checks{display:flex;flex-wrap:wrap;gap:1rem;margin-top:.8rem;border-top:1px solid #eee;padding-top:.8rem}
 .checks label{font-size:.85rem;display:flex;gap:.4rem;align-items:center}
 .checks select,.checks textarea{font:inherit}
 .note{flex-basis:100%} .note textarea{flex:1}
 .bar{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:.6rem 1rem;display:flex;gap:1rem;align-items:center;z-index:9}
 .status{font-size:.75rem;color:#2c7a4b}
</style></head><body>
<div class="bar"><strong>Experiment 34 — worker sample review</strong>
 <button id="save">Save verdicts (download JSON)</button>
 <button id="wipe">Clear all choices</button>
 <span id="progress"></span></div>
<h1 style="margin-left:1rem">PaddleOCR-VL on the three named issues, plus a clean control. Left: original. Right: worker Markdown.</h1>
"""

HTML_TAIL = """
<script>
const KEY='exp34_review_verdicts_v1';
const state=JSON.parse(localStorage.getItem(KEY)||'{}');
function keyOf(sec){return sec.dataset.doc+'/'+sec.dataset.page}
function refresh(){let n=0;for(const s of document.querySelectorAll('.page')){
  const k=keyOf(s),v=state[k]||{};let filled=false;
  for(const el of s.querySelectorAll('[data-k]')){el.value=v[el.dataset.k]||'';if(el.value)filled=true}
  const st=s.querySelector('.status');st.textContent=filled?'reviewed':'';
  if(filled)n++}
  document.getElementById('progress').textContent=n+' / '+document.querySelectorAll('.page').length+' reviewed';}
document.addEventListener('change',e=>{const el=e.target.closest('[data-k]');if(!el)return;
  const sec=el.closest('.page');const k=keyOf(sec);state[k]=state[k]||{};
  if(el.value)state[k][el.dataset.k]=el.value;else delete state[k][el.dataset.k];
  if(!Object.keys(state[k]).length)delete state[k];
  localStorage.setItem(KEY,JSON.stringify(state));refresh();});
document.getElementById('save').onclick=()=>{
  const blob=new Blob([JSON.stringify(state,null,1)],{type:'application/json'});
  const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='review_verdicts.json';a.click();};
document.getElementById('wipe').onclick=()=>{if(confirm('Clear all choices?')){localStorage.removeItem(KEY);location.reload()}};
refresh();
</script></body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
