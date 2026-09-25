# ruff: noqa: E501
#!/usr/bin/env python3
"""Build the Experiment 34 review page (task 2.3).

One self-contained HTML file. Every sampled page is a collapsible row.
Inside, the original page image stays pinned on the left (click it to
open a zoomable viewer: pinch, scroll or double-click), and each engine
(pdf-inspector, LiteParse, and where they ran the local OCR tier, the OCR worker and the dots.mocr probe) has its own collapsible panel on
the right with its output and its own selectable checklist. A short
page-level block records the page layout and the best engine. No free
text: every answer is a choice.

Verdicts persist to browser localStorage and export as
``review_verdicts.json`` (download button), which is committed unchanged
as the experiment's result. The export can be loaded back.

Copies the needed page images from the Experiment 33 worktree into
``output/pages/`` (relative references keep the HTML movable).

Usage:
    python3 make_review.py
    python3 make_review.py --only bd03:1,bd03:2,io06:28,io06:53,eq01:11 --out review_small.html
"""

from __future__ import annotations

import html
import json
import re
import shutil
from pathlib import Path

from extra_pages import EXTRA_PAGES

EXP_DIR = Path(__file__).resolve().parent
OUT_PAGES = EXP_DIR / "output" / "pages"

ISSUE = {
    "io06": "Old book: language/typography + structure",
    "io04": "Triple column with images",
    "bd01": "Two column (worker vs pdf-inspector fast path)",
    "bd02": "Two column (worker vs pdf-inspector fast path)",
    "tl03": "Tables",
    "eq01": "Display equations (outside the sample, A4)",
}

#: (key, label, output folder under output/, optional) — key is the verdict JSON key.
#: An optional engine (a probe on a few pages) never blocks a page from counting as reviewed.
ENGINES = [
    ("pdf_inspector", "pdf-inspector (text layer, fast path)", "pdf_inspector", False),
    ("liteparse", "LiteParse (fixed join, rescue tier)", "liteparse", False),
    ("local_ocr", "pdf-inspector OCR (local OCR tier, PP-OCRv6 Small)", "local_ocr", True),
    ("worker", "OCR worker (PaddleOCR-VL)", "worker", False),
    ("dots_mocr", "dots.mocr (probe, 3B, MPS)", "dots_mocr", True),
]

#: Per-engine checklist: (key, label, single|multi, [(value, label), ...]).
#: When ``output`` is not "text", the other questions are hidden and not required.
ENGINE_QUESTIONS = [
    (
        "output",
        "Output produced",
        "single",
        [
            ("text", "Text output"),
            ("empty", "Empty / no text"),
            ("junk", "Only noise or placeholders"),
        ],
    ),
    (
        "accuracy",
        "Text accuracy",
        "single",
        [
            ("all", "All correct"),
            ("most", "Most correct (minor typos)"),
            ("some", "Some correct"),
            ("wrong", "Mostly wrong"),
        ],
    ),
    (
        "order",
        "Reading order",
        "single",
        [
            ("correct", "Correct"),
            ("minor", "Minor jumps"),
            ("scrambled", "Scrambled (columns mixed)"),
            ("na", "n/a (single block)"),
        ],
    ),
    (
        "structure",
        "Headings and structure",
        "single",
        [
            ("kept", "Preserved"),
            ("partial", "Partly preserved"),
            ("lost", "Lost or garbled"),
            ("na", "n/a (none on page)"),
        ],
    ),
    (
        "table",
        "Tables",
        "single",
        [
            ("ok", "Readable table"),
            ("flat", "Text kept, grid lost"),
            ("broken", "Missing or broken"),
            ("na", "n/a (no table)"),
        ],
    ),
    (
        "issues",
        "Problems seen (pick all that apply)",
        "multi",
        [
            ("none", "None"),
            ("missing", "Missing text"),
            ("invented", "Invented text"),
            ("repeated", "Repeated text"),
            ("chars", "Wrong characters or diacritics"),
            ("breaks", "Broken words or hyphenation"),
            ("furniture", "Headers, footers or page numbers mixed in"),
            ("captions", "Captions misplaced"),
            ("noise", "Image or markup noise"),
        ],
    ),
    (
        "llm",
        "Ready for an LLM",
        "single",
        [("yes", "Yes, as is"), ("cleanup", "Yes, after light cleanup"), ("no", "No")],
    ),
]

#: Pages the optional engines cover: the dots.mocr probe (A2; mirrors DEFAULT_PAGES in
#: probe_dots_mocr.py) and the local OCR tier (A5; local_ocr_pages.py).
PROBE_PAGES = {("bd03", 1), ("bd03", 2), ("io06", 28), ("io06", 53), ("eq01", 11)}
#: Script that fills each optional engine, and the amendment that scopes it.
OPTIONAL_SOURCES = {
    "dots_mocr": ("probe_dots_mocr.py", "A2"),
    "local_ocr": ("local_ocr_pages.py", "A5"),
}
#: Pages outside the frozen sample (extra_pages.py) render only when named in ``--only``,
#: so the full review keeps the frozen sample. The dots.mocr probe writes their page images.

PAGE_QUESTIONS = [
    (
        "layout",
        "Layout of the original PDF page (pick all that apply)",
        "multi",
        [
            ("one", "Single column"),
            ("two", "Two columns"),
            ("three", "Three or more columns"),
            ("tables", "Tables"),
            ("figures", "Figures or images"),
            ("old", "Old typography"),
            ("blank", "Near-blank"),
        ],
    ),
    (
        "best",
        "Best output on this page (pick every engine that is equally best)",
        "multi",
        [
            ("pdf_inspector", "pdf-inspector"),
            ("liteparse", "LiteParse"),
            ("local_ocr", "pdf-inspector OCR"),
            ("worker", "OCR worker"),
            ("dots_mocr", "dots.mocr"),
            ("none", "None usable"),
        ],
    ),
]

_TABLE_TAG = re.compile(r"</?(table|thead|tbody|tr|td|th)\b([^>]*)>", re.IGNORECASE)
_SPAN_ATTR = re.compile(r"\b(colspan|rowspan)\s*=\s*['\"]?(\d+)", re.IGNORECASE)
_BOLD = re.compile(r"\*\*(?=[^*\s])(.+?)(?<=[^*\s])\*\*")
_ITALIC = re.compile(r"(?<![*\w])\*(?=[^*\s])(.+?)(?<=[^*\s])\*(?![*\w])")


def _inline(text: str) -> str:
    """Escape, then render **bold** and *italic* so the operator can see which engine marked emphasis."""
    return _ITALIC.sub(r"<em>\1</em>", _BOLD.sub(r"<strong>\1</strong>", html.escape(text)))


def _safe_table_html(line: str) -> str:
    """Keep only table structure tags (with colspan/rowspan) from worker HTML; escape the rest."""
    out: list[str] = []
    for token in re.split(r"(<[^>]+>)", line):
        match = _TABLE_TAG.fullmatch(token)
        if match:
            closing = "/" if token.startswith("</") else ""
            attrs = "".join(f' {k.lower()}="{v}"' for k, v in _SPAN_ATTR.findall(match.group(2)))
            out.append(f"<{closing}{match.group(1).lower()}{'' if closing else attrs}>")
        else:
            out.append(html.escape(token))
    return "".join(out)


def _pipe_row(line: str, cell: str) -> str:
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    return "<tr>" + "".join(f"<{cell}>{_inline(c)}</{cell}>" for c in cells) + "</tr>"


def _mini_markdown(text: str) -> str:
    """Small Markdown-to-HTML for review only: headings, pipe tables, worker HTML tables, code."""
    out: list[str] = []
    lines = text.splitlines()
    in_code = False
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if stripped.startswith("$$") and not in_code:
            # Keep a display-maths block in one element so KaTeX auto-render sees both delimiters.
            block = [line]
            closed = len(stripped) > 2 and stripped.endswith("$$")
            while not closed and i + 1 < len(lines):
                i += 1
                block.append(lines[i])
                closed = lines[i].strip().endswith("$$")
            out.append(f'<div class="math">{html.escape(chr(10).join(block))}</div>')
        elif stripped.startswith("```"):
            out.append("</pre>" if in_code else "<pre>")
            in_code = not in_code
        elif in_code:
            out.append(html.escape(line))
        elif not stripped:
            pass
        elif "<table" in stripped.lower():
            out.append(f'<div class="tbl">{_safe_table_html(stripped)}</div>')
        elif stripped.startswith("|"):
            rows: list[str] = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                row = lines[i].strip()
                if not re.fullmatch(r"\|[\s:|-]+\|?", row):
                    rows.append(_pipe_row(row, "th" if not rows else "td"))
                i += 1
            out.append('<div class="tbl"><table>' + "".join(rows) + "</table></div>")
            continue
        elif stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            tag = f"h{min(level + 2, 6)}"
            out.append(f"<{tag}>{_inline(stripped[level:].strip())}</{tag}>")
        else:
            out.append(f"<p>{_inline(line)}</p>")
        i += 1
    if in_code:
        out.append("</pre>")
    return "\n".join(out)


def _questions_html(questions: list, name_prefix: str) -> str:
    blocks = []
    for key, label, kind, options in questions:
        input_type = "radio" if kind == "single" else "checkbox"
        chips = "".join(
            f'<label class="chip"><input type="{input_type}" name="{name_prefix}-{key}" value="{value}">'
            f"<span>{html.escape(text)}</span></label>"
            for value, text in options
        )
        blocks.append(
            f'<div class="q {kind}" data-q="{key}" data-type="{kind}">'
            f'<div class="ql">{html.escape(label)}</div><div class="opts">{chips}</div></div>'
        )
    return "".join(blocks)


def _read_output(folder: str, doc: str, page: int, engine_label: str) -> tuple[str | None, str]:
    """Return (text or None when not extracted, a short size badge)."""
    path = EXP_DIR / "output" / folder / doc / f"p{page:03d}.md"
    if not path.exists():
        return None, "not run"
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        return f"(empty — {engine_label} extracted no text from this page)", "empty"
    return text, f"{len(text):,} chars"


def _page_section(doc: str, page: int, role: str) -> str:
    key = f"{doc}/{page}"
    engines = []
    for eng_key, eng_label, folder, optional in ENGINES:
        text, badge = _read_output(folder, doc, page, eng_label)
        pending = text is None
        if pending and any(r["doc_id"] == doc and r["page"] == page for r in EXTRA_PAGES):
            optional = True
            badge = "not run"
            body = '<div class="pending">Page outside the frozen sample; this engine has not run on it yet.</div>'
        elif pending and optional and (doc, page) in PROBE_PAGES:
            script, _ = OPTIONAL_SOURCES[eng_key]
            badge = "not finished"
            body = (
                f'<div class="pending">This engine covers this page but has no output yet. '
                f"Re-run <code>make_review.py</code> when <code>{script}</code> finishes.</div>"
            )
        elif pending and optional:
            _, amendment = OPTIONAL_SOURCES[eng_key]
            badge = "not run here"
            body = (
                '<div class="pending">This engine ran only on the reviewed set '
                f"(bd03 p1, p2; io06 p28, p53), protocol amendment {amendment}.</div>"
            )
        elif pending:
            # A1 scoped the runs to the reviewed pages, so a missing output is
            # a page the engine was not run on, not a run still in progress.
            optional = True
            badge = "not run"
            body = (
                '<div class="pending">This engine was not run on this page. Protocol amendment A1 '
                "scoped the runs to the reviewed pages; see the protocol for each engine's pages.</div>"
            )
        else:
            body = (
                f'<div class="outwrap"><div class="viewbar"><button type="button" class="vt on" data-v="md">Rendered</button>'
                f'<button type="button" class="vt" data-v="raw">Raw</button></div>'
                f'<div class="md">{_mini_markdown(text)}</div><pre class="raw" hidden>{html.escape(text)}</pre></div>'
            )
        engines.append(
            f'<details class="engine" name="eng-{doc}-{page}" data-engine="{eng_key}">'
            f'<summary><span class="en">{html.escape(eng_label)}</span><span class="badge">{badge}</span>'
            f'<span class="estat"></span></summary>{body}'
            f'<fieldset class="form" data-scope="{eng_key}"{(" disabled data-optional=1" if optional else " disabled data-pending=1") if pending else ""}>'
            f"{_questions_html(ENGINE_QUESTIONS, f'{doc}-{page}-{eng_key}')}"
            f'<button type="button" class="clear">Clear this engine</button></fieldset></details>'
        )
    return f"""
<details class="page" data-key="{key}" data-doc="{doc}" data-page="{page}">
  <summary><span class="pt">{doc} · page {page}</span><span class="role {role}">{role}</span>
    <span class="issue">{html.escape(ISSUE.get(doc, "Clean control"))}</span><span class="pstat"></span></summary>
  <div class="body">
    <div class="orig"><div class="stick">
      <button type="button" class="zoom" data-src="pages/{doc}/p{page:03d}.png" data-cap="{doc} · page {page}" aria-label="Open zoomable view">
        <img loading="lazy" src="pages/{doc}/p{page:03d}.png" alt="{doc} page {page}">
        <span class="mag" aria-hidden="true"><svg viewBox="0 0 24 24" width="20" height="20"><circle cx="10.5" cy="10.5" r="6.5" fill="none" stroke="currentColor" stroke-width="2"/><path d="M15.5 15.5 21 21M10.5 7.5v6M7.5 10.5h6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></span>
      </button>
      <div class="hint">Click to zoom · pinch or ⌘/Ctrl-scroll inside the viewer</div>
    </div></div>
    <div class="right">
      {"".join(engines)}
      <fieldset class="form pageform" data-scope="page"><legend>This page <span class="estat"></span></legend>
        {_questions_html(PAGE_QUESTIONS, f"{doc}-{page}-page")}
        <button type="button" class="clear">Clear page answers</button></fieldset>
    </div>
  </div>
</details>"""


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="render only these doc:page pairs, e.g. 'io06:28,io06:53'")
    parser.add_argument("--out", default="review.html", help="output file name under output/")
    args = parser.parse_args()

    sample = json.loads((EXP_DIR / "sample.json").read_text(encoding="utf-8"))
    images_src = Path(sample["exp33_dir"]) / "output" / ".pages"

    only = None
    if args.only:
        only = {tuple(item.strip().partition(":")[::2]) for item in args.only.split(",")}

    rows = sample["pages"] + (EXTRA_PAGES if only is not None else [])
    sections: list[str] = []
    for row in sorted(rows, key=lambda r: (r["doc_id"], r["page"])):
        doc, page = row["doc_id"], row["page"]
        if only is not None and (doc, str(page)) not in only:
            continue
        dst = OUT_PAGES / doc / f"p{page:03d}.png"
        if row in EXTRA_PAGES and not dst.exists():
            raise SystemExit(
                f"missing page image: {dst} (run probe_dots_mocr.py --only {doc}:{page} first)"
            )
        if not dst.exists():
            src = images_src / doc / f"p{page:03d}.png"
            if not src.is_file():
                raise SystemExit(f"missing page image: {src}")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        sections.append(_page_section(doc, page, row["role"]))

    out_path = EXP_DIR / "output" / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(HTML_HEAD + "\n".join(sections) + HTML_TAIL, encoding="utf-8")
    print(f"wrote {out_path} ({len(sections)} pages)")
    return 0


HTML_HEAD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Worker Sample Review</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/contrib/auto-render.min.js"
 onload="renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},{left:'$',right:'$',display:false}],ignoredClasses:['raw'],throwOnError:false})"></script>
<style>
:root{--bg:#f4f4f2;--card:#fff;--ink:#1d1d1b;--muted:#64645f;--line:#dcdcd6;--soft:#f8f8f5;--accent:#2f5fd0;--ok:#23864f;--part:#b7791f;--prob:#b3392c;--ctrl:#2c7ab3}
@media (prefers-color-scheme:dark){:root{--bg:#161615;--card:#1f1f1d;--ink:#ecece8;--muted:#a3a39c;--line:#34342f;--soft:#262623;--accent:#7a9cff;--ok:#4cc27f;--part:#e3a84a}}
*{box-sizing:border-box}
body{font:15px/1.45 system-ui,-apple-system,sans-serif;margin:0;background:var(--bg);color:var(--ink)}
.bar{position:sticky;top:0;z-index:20;background:var(--card);border-bottom:1px solid var(--line);padding:.55rem 1rem;display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;height:auto}
.bar strong{margin-right:auto}
.bar button,.bar label.btn{font:inherit;font-size:.85rem;padding:.35rem .75rem;border:1px solid var(--line);border-radius:6px;background:var(--soft);color:var(--ink);cursor:pointer}
#progress{font-size:.85rem;color:var(--muted)}
main{max-width:1500px;margin:0 auto;padding:1rem}
.intro{color:var(--muted);font-size:.9rem;margin:.2rem 0 1rem}
details.page{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:.6rem 0}
details.page>summary{list-style:none;cursor:pointer;padding:.75rem 1rem;display:flex;flex-wrap:wrap;gap:.6rem;align-items:center}
details.page>summary::-webkit-details-marker,details.engine>summary::-webkit-details-marker{display:none}
details.page>summary::before,details.engine>summary::before{content:'▸';color:var(--muted);transition:transform .15s}
details[open]>summary::before{transform:rotate(90deg)}
.pt{font-weight:600}
.role{font-size:.72rem;padding:.1rem .55rem;border-radius:1rem;color:#fff}
.role.problem{background:var(--prob)}.role.control{background:var(--ctrl)}.role.extra{background:var(--muted)}
.issue{font-size:.82rem;color:var(--muted)}
.pstat{margin-left:auto;font-size:.78rem;font-weight:600}
.ok{color:var(--ok)}.part{color:var(--part)}
.body{display:grid;grid-template-columns:minmax(0,5fr) minmax(0,7fr);gap:1rem;padding:0 1rem 1rem;border-top:1px solid var(--line);padding-top:1rem}
.stick{position:sticky;top:4rem}
.zoom{position:relative;display:block;width:100%;padding:0;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:zoom-in;overflow:auto;max-height:calc(100vh - 6.5rem)}
.zoom img{display:block;width:100%;height:auto}
.mag{position:absolute;top:.5rem;right:.5rem;background:rgba(20,20,20,.72);color:#fff;border-radius:50%;width:36px;height:36px;display:grid;place-items:center;opacity:.55;transition:opacity .15s}
.zoom:hover .mag,.zoom:focus-visible .mag{opacity:1}
.hint{font-size:.75rem;color:var(--muted);margin-top:.3rem;text-align:center}
details.engine{border:1px solid var(--line);border-radius:8px;margin-bottom:.6rem;background:var(--soft)}
details.engine>summary{list-style:none;cursor:pointer;padding:.6rem .8rem;display:flex;gap:.6rem;align-items:center}
.en{font-weight:600;font-size:.92rem}
.badge{font-size:.72rem;color:var(--muted);border:1px solid var(--line);border-radius:1rem;padding:0 .5rem}
.estat{margin-left:auto;font-size:.75rem;font-weight:600;color:var(--muted)}
.outwrap{padding:0 .8rem}
.viewbar{display:flex;gap:.3rem;margin-bottom:.35rem}
.vt{font:inherit;font-size:.75rem;padding:.15rem .6rem;border:1px solid var(--line);border-radius:5px;background:var(--card);color:var(--muted);cursor:pointer}
.vt.on{background:var(--ink);color:var(--card)}
.md,.raw{max-height:55vh;overflow:auto;border:1px solid var(--line);border-radius:6px;padding:.6rem .8rem;background:var(--card);margin:0}
.md p{margin:.2rem 0;font-size:.88rem}
.md h3,.md h4,.md h5,.md h6{margin:.6rem 0 .25rem}
.raw{white-space:pre-wrap;font-size:.78rem}
.md .math{margin:.4rem 0;overflow-x:auto}
.tbl{overflow-x:auto;margin:.4rem 0}
.tbl table{border-collapse:collapse;font-size:.82rem}
.tbl td,.tbl th{border:1px solid var(--line);padding:.2rem .45rem;vertical-align:top}
.pending{margin:0 .8rem;padding:.7rem;border:1px dashed var(--line);border-radius:6px;color:var(--muted);font-size:.85rem}
fieldset.form{border:0;margin:0;padding:.7rem .8rem .8rem;display:grid;gap:.7rem}
fieldset.form[disabled]{opacity:.45}
fieldset.pageform{border:1px solid var(--line);border-radius:8px}
fieldset.pageform legend{font-weight:600;font-size:.92rem;padding:0 .3rem;display:flex;gap:.5rem;align-items:center}
.q[hidden]{display:none}
.ql{font-size:.8rem;font-weight:600;color:var(--muted);margin-bottom:.3rem}
.opts{display:flex;flex-wrap:wrap;gap:.35rem}
.chip{position:relative}
.chip input{position:absolute;opacity:0;width:1px;height:1px}
.chip span{display:inline-block;padding:.32rem .7rem;border:1px solid var(--line);border-radius:999px;background:var(--card);font-size:.82rem;cursor:pointer;user-select:none}
.multi .chip span{border-radius:6px}
.chip:hover span{border-color:var(--accent)}
.chip input:checked+span{background:var(--accent);border-color:var(--accent);color:#fff}
.multi .chip input:checked+span::before{content:'✓ '}
.chip input:focus-visible+span{outline:2px solid var(--accent);outline-offset:2px}
.clear{justify-self:start;font:inherit;font-size:.75rem;color:var(--muted);background:none;border:0;text-decoration:underline;cursor:pointer;padding:0}
#lb{position:fixed;inset:0;z-index:50;background:rgba(10,10,10,.92);display:none;flex-direction:column}
#lb.open{display:flex}
#lb .tools{display:flex;gap:.4rem;align-items:center;padding:.5rem .8rem;color:#eee}
#lb .tools .cap{margin-right:auto;font-weight:600}
#lb .tools button,#lb .tools a{font:inherit;font-size:.85rem;min-width:2.2rem;padding:.3rem .6rem;border:1px solid #555;border-radius:6px;background:#222;color:#eee;cursor:pointer;text-decoration:none}
#lb .stage{flex:1;overflow:hidden;display:flex;align-items:center;justify-content:center;cursor:grab;touch-action:none}
#lb .stage.drag{cursor:grabbing}
#lb .stage img{max-width:100%;max-height:100%;transform-origin:center center;user-select:none;-webkit-user-drag:none;background:#fff}
@media (max-width:900px){.body{grid-template-columns:1fr}.stick{position:static}.zoom{max-height:60vh}}
</style></head><body>
<div class="bar"><strong>Experiment 34 — worker sample review</strong>
 <span id="progress"></span>
 <button id="next" type="button">Next unreviewed</button>
 <button id="collapse" type="button">Collapse all</button>
 <button id="save" type="button">Save verdicts (JSON)</button>
 <label class="btn">Load JSON<input id="load" type="file" accept="application/json" hidden></label>
 <button id="wipe" type="button">Clear all</button></div>
<main>
<p class="intro">Open a page. The original stays pinned on the left; click it to zoom. Each engine on the right has its own checklist. A page counts as reviewed when every engine that ran and the page block are answered (a probe engine that skipped the page does not count). If an engine produced no text, choose that under “Output produced” and the rest is skipped.</p>
"""

HTML_TAIL = """
</main>
<div id="lb" role="dialog" aria-modal="true" aria-label="Zoomable page image">
 <div class="tools"><span class="cap"></span><button data-z="out" aria-label="Zoom out">−</button><span class="zl">100%</span>
  <button data-z="in" aria-label="Zoom in">+</button><button data-z="fit">Fit</button><a class="newtab" target="_blank" rel="noopener">Open image</a><button data-z="close" aria-label="Close">✕</button></div>
 <div class="stage"><img alt=""></div>
</div>
<script>
const KEY='exp34_review_verdicts_v2';
let state={};try{state=JSON.parse(localStorage.getItem(KEY)||'{}')||{}}catch(e){state={}}
const persist=()=>{try{localStorage.setItem(KEY,JSON.stringify(state))}catch(e){}};
const pages=[...document.querySelectorAll('details.page')];
function read(form){const o={};for(const q of form.querySelectorAll('.q')){const v=[...q.querySelectorAll('input:checked')].map(i=>i.value);if(v.length)o[q.dataset.q]=q.dataset.type==='multi'?v:v[0]}return o}
function write(form,o){for(const q of form.querySelectorAll('.q')){const vs=[].concat(o[q.dataset.q]??[]);for(const i of q.querySelectorAll('input'))i.checked=vs.includes(i.value)}}
function skipRest(form,o){return form.dataset.scope!=='page'&&o.output&&o.output!=='text'}
function visibility(form,o){const hide=skipRest(form,o);for(const q of form.querySelectorAll('.q:not([data-q=output])'))if(form.dataset.scope!=='page')q.hidden=hide}
function status(form){const o=read(form);const req=skipRest(form,o)?['output']:[...form.querySelectorAll('.q')].map(q=>q.dataset.q);return[req.filter(k=>o[k]!=null).length,req.length]}
function refresh(){let n=0;
 for(const p of pages){let all=true,any=false,pending=false;
  for(const form of p.querySelectorAll('.form')){const chip=(form.closest('details.engine')||form).querySelector('.estat');
   if(form.dataset.optional){chip.textContent='—';chip.className='estat';continue}
   if(form.dataset.pending){pending=true;all=false;chip.textContent='pending';chip.className='estat';continue}
   const[d,t]=status(form);if(d)any=true;if(d<t)all=false;chip.textContent=d===t?'✓ done':d+' / '+t;chip.className='estat'+(d===t?' ok':d?' part':'')}
  const s=p.querySelector('.pstat');s.textContent=all?'✓ reviewed':pending?(any?'in progress · engine pending':'engine pending'):any?'in progress':'';
  s.className='pstat'+(all?' ok':any?' part':'');p.dataset.done=all?'1':'';if(all)n++}
 document.getElementById('progress').textContent=n+' / '+pages.length+' pages reviewed'}
function store(form){const p=form.closest('details.page'),k=p.dataset.key,o=read(form);state[k]=state[k]||{};
 if(Object.keys(o).length)state[k][form.dataset.scope]=o;else delete state[k][form.dataset.scope];
 if(!Object.keys(state[k]).length)delete state[k];visibility(form,o);persist();refresh()}
function load(){for(const p of pages)for(const form of p.querySelectorAll('.form')){const o=(state[p.dataset.key]||{})[form.dataset.scope]||{};write(form,o);visibility(form,o)}refresh()}
document.addEventListener('change',e=>{const i=e.target;if(!i.matches('.q input'))return;const q=i.closest('.q');
 if(q.dataset.type==='multi'&&i.checked){if(i.value==='none')q.querySelectorAll('input').forEach(x=>{if(x!==i)x.checked=false});else{const n=q.querySelector('input[value=none]');if(n)n.checked=false}}
 store(i.closest('.form'))});
document.addEventListener('click',e=>{const c=e.target.closest('.clear');if(c){const f=c.closest('.form');write(f,{});store(f);return}
 const v=e.target.closest('.vt');if(v){const w=v.closest('.outwrap');w.querySelectorAll('.vt').forEach(b=>b.classList.toggle('on',b===v));w.querySelector('.md').hidden=v.dataset.v!=='md';w.querySelector('.raw').hidden=v.dataset.v!=='raw'}});
for(const p of pages)p.addEventListener('toggle',()=>{if(p.open&&!p.querySelector('details.engine[open]')){const first=[...p.querySelectorAll('details.engine')].find(d=>{const[dd,t]=status(d.querySelector('.form'));const f=d.querySelector('.form');return!f.dataset.pending&&!f.dataset.optional&&dd<t})||p.querySelector('details.engine');first.open=true}});
document.getElementById('next').onclick=()=>{const p=pages.find(x=>!x.dataset.done&&!x.querySelector('.form[data-pending]'))||pages.find(x=>!x.dataset.done);if(!p)return alert('All pages reviewed.');p.open=true;p.scrollIntoView({behavior:'smooth',block:'start'})};
document.getElementById('collapse').onclick=()=>pages.forEach(p=>p.open=false);
document.getElementById('save').onclick=()=>{const out={schema:'exp34-review-v2',exported_at:new Date().toISOString(),pages:state};
 const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(out,null,1)],{type:'application/json'}));a.download='review_verdicts.json';a.click()};
document.getElementById('load').onchange=async e=>{const f=e.target.files[0];if(!f)return;try{const d=JSON.parse(await f.text());state=d.pages||d;persist();load()}catch(err){alert('Could not read that file: '+err.message)}e.target.value=''};
document.getElementById('wipe').onclick=()=>{if(confirm('Clear every answer on every page?')){state={};persist();load()}};
load();
// Zoomable viewer: pinch (trackpad or Safari gestures), Ctrl/Cmd-scroll, double-click, drag to pan.
const lb=document.getElementById('lb'),stage=lb.querySelector('.stage'),img=stage.querySelector('img');let z=1,x=0,y=0,gz=1,inGesture=false;
function apply(){img.style.transform='translate('+x+'px,'+y+'px) scale('+z+')';lb.querySelector('.zl').textContent=Math.round(z*100)+'%'}
function fit(){z=1;x=0;y=0;apply()}
function zoomAt(f,cx,cy){const r=stage.getBoundingClientRect();if(cx==null){cx=r.left+r.width/2;cy=r.top+r.height/2}
 const nz=Math.min(10,Math.max(1,z*f)),px=cx-r.left-r.width/2,py=cy-r.top-r.height/2;x=px-(px-x)*nz/z;y=py-(py-y)*nz/z;z=nz;if(z===1){x=0;y=0}apply()}
document.addEventListener('click',e=>{const b=e.target.closest('.zoom');if(!b)return;img.src=b.dataset.src;lb.querySelector('.cap').textContent=b.dataset.cap;lb.querySelector('.newtab').href=b.dataset.src;fit();lb.classList.add('open');document.body.style.overflow='hidden'});
function close(){lb.classList.remove('open');document.body.style.overflow=''}
lb.querySelector('.tools').addEventListener('click',e=>{const a=e.target.closest('[data-z]')?.dataset.z;if(a==='in')zoomAt(1.4);if(a==='out')zoomAt(1/1.4);if(a==='fit')fit();if(a==='close')close()});
stage.addEventListener('wheel',e=>{e.preventDefault();if(e.ctrlKey||e.metaKey){if(!inGesture)zoomAt(Math.exp(-e.deltaY*.01),e.clientX,e.clientY)}else{x-=e.deltaX;y-=e.deltaY;apply()}},{passive:false});
stage.addEventListener('gesturestart',e=>{e.preventDefault();inGesture=true;gz=z});
stage.addEventListener('gesturechange',e=>{e.preventDefault();zoomAt(gz*e.scale/z,e.clientX,e.clientY)});
stage.addEventListener('gestureend',e=>{e.preventDefault();inGesture=false});
stage.addEventListener('dblclick',e=>{z>1?fit():zoomAt(2.5,e.clientX,e.clientY)});
let drag=null;stage.addEventListener('pointerdown',e=>{drag={px:e.clientX,py:e.clientY,x,y};stage.setPointerCapture(e.pointerId);stage.classList.add('drag')});
stage.addEventListener('pointermove',e=>{if(!drag)return;x=drag.x+e.clientX-drag.px;y=drag.y+e.clientY-drag.py;apply()});
stage.addEventListener('pointerup',()=>{drag=null;stage.classList.remove('drag')});
stage.addEventListener('click',e=>{if(e.target===stage&&z===1)close()});
document.addEventListener('keydown',e=>{if(!lb.classList.contains('open'))return;if(e.key==='Escape')close();if(e.key==='+'||e.key==='=')zoomAt(1.4);if(e.key==='-')zoomAt(1/1.4);if(e.key==='0')fit()});
</script></body></html>
"""

if __name__ == "__main__":
    raise SystemExit(main())
