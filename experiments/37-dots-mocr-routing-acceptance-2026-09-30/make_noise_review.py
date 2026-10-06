"""Experiment 37 noise screen and review page (Gate D, gate G3).

Two modes:

    # screen E-maths and E-scan for both engines, write output/noise_screen.json
    # and output/noise_review.html (local only: shows page images and engine text)
    uv run python experiments/37-.../make_noise_review.py
    # merge verdicts downloaded from that page into noise_verdicts.json
    uv run python experiments/37-.../make_noise_review.py --merge ~/Downloads/noise_verdicts_download.json

The screen (plan.json decision DR-4, fixed before any result was seen):
- reference text: the page text layer (pypdf) for E-maths pages; the
  Experiment 33 reference transcription (all text) for E-scan pages;
- engine text: the page Markdown with formulas ($$...$$, $...$), HTML tags and
  image links removed, so only prose is compared;
- tokens: Experiment 33 ``build_labels.tokens`` (imported);
- unsupported tokens: engine tokens beyond their count in the reference;
- a page is on an engine's noise list when unsupported tokens >= 10 and
  >= 15 % of its tokens, or when one line of 20+ characters repeats 3+ times;
- plus an audit sample: 5 unflagged pages per engine (seed 37), so the
  operator can see whether the screen misses noise;
- plus io06 p53, which the protocol names (Experiment 34 bleed-through).
Pages that returned no text (timeout, empty) are listed in the summary, not
reviewed: they emit no text, so they cannot carry invented text.
"""

# ruff: noqa: E501 - embedded HTML/CSS/JS strings are kept on one line each
from __future__ import annotations

import argparse
import html
import json
import random
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader

EXP_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP_DIR.parent / "33-ocr-routing-natural-positive-2026-09-17"))
sys.path.insert(0, str(EXP_DIR.parent / "34-worker-sample-review-2026-09-19"))
from build_labels import tokens  # noqa: E402
from make_review import _mini_markdown  # noqa: E402  (Experiment 34 review renderer, reused)

OUT = EXP_DIR / "output"
PAGE = OUT / "noise_review.html"
SCREEN = OUT / "noise_screen.json"
VERDICTS = EXP_DIR / "noise_verdicts.json"
ENGINES = ("dots-mocr", "paddleocr-vl")
RUNS = ("E-maths", "E-scan")
MIN_UNSUPPORTED = 10
MIN_SHARE = 0.15
REPEAT_MIN_CHARS = 20
REPEAT_MIN_COUNT = 3
AUDIT_PER_ENGINE = 5
#: Pages the protocol names as known noise cases (Experiment 34: io06 p53
#: bleed-through). Listed for every engine with output, after the audit draw.
PROTOCOL_PAGES = ("io06:53",)
SEED = 37
VERDICT_VALUES = ("noise", "clean")

_FORMULA = re.compile(r"\$\$[\s\S]*?\$\$|(?<![\\$])\$[^$\n]+?\$(?!\$)")
_HTML = re.compile(r"<[^>]+>")
_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
_WORD = re.compile(r"\w+", re.UNICODE)


def prose(markdown: str) -> str:
    """Return the engine text with formulas, HTML tags and image links removed."""
    return _HTML.sub(" ", _IMAGE.sub(" ", _FORMULA.sub(" ", markdown)))


def repeated_lines(markdown: str) -> list[str]:
    """Return lines of 20+ characters that occur 3+ times (generation loops)."""
    counts = Counter(
        line.strip() for line in markdown.splitlines() if len(line.strip()) >= REPEAT_MIN_CHARS
    )
    return [line[:120] for line, n in counts.items() if n >= REPEAT_MIN_COUNT]


def reference_text(run: str, doc_path: Path, doc_id: str, page: int) -> str:
    """Return the reference text for one page."""
    if run == "E-maths":
        return PdfReader(str(doc_path)).pages[page - 1].extract_text() or ""
    record = json.loads(
        (EXP_DIR / "corpus" / "exp33_transcripts" / doc_id / f"p{page:03d}.json").read_text("utf-8")
    )
    return record.get("transcription") or ""


def screen() -> dict[str, Any]:
    """Screen every finished E-maths and E-scan page of both engines."""
    sources = {
        d["doc_id"]: EXP_DIR / d["local_path"]
        for d in json.loads((EXP_DIR / "sources.json").read_text("utf-8"))["documents"]
    }
    states = {
        e: json.loads((OUT / f"ocr_state_{e}.json").read_text("utf-8"))["engines"][e]["runs"]
        for e in ENGINES
    }
    pages: dict[str, Any] = {}
    no_output: dict[str, list[str]] = {e: [] for e in ENGINES}
    for run in RUNS:
        for key in states["dots-mocr"][run]["pages"]:
            doc_id, page_s = key.split(":")
            page = int(page_s)
            ref = Counter(tokens(reference_text(run, sources[doc_id], doc_id, page)))
            entry: dict[str, Any] = {
                "run": run,
                "doc_id": doc_id,
                "page": page,
                "reference_tokens": sum(ref.values()),
                "engines": {},
            }
            for engine in ENGINES:
                status = states[engine][run]["pages"].get(key, {})
                md_path = OUT / engine / doc_id / f"p{page:03d}.md"
                if status.get("status") != "ok" or not md_path.is_file():
                    no_output[engine].append(f"{key} ({status.get('code', 'missing')})")
                    continue
                text = md_path.read_text("utf-8")
                have = Counter(tokens(prose(text)))
                unsupported = Counter({t: n - ref[t] for t, n in have.items() if n > ref[t]})
                total = sum(have.values())
                n_un = sum(unsupported.values())
                loops = repeated_lines(text)
                share = n_un / total if total else 0.0
                entry["engines"][engine] = {
                    "tokens": total,
                    "unsupported": n_un,
                    "unsupported_share": round(share, 4),
                    "repeated_lines": loops,
                    "flagged": (n_un >= MIN_UNSUPPORTED and share >= MIN_SHARE) or bool(loops),
                    "unsupported_sample": [t for t, _ in unsupported.most_common(40)],
                }
            pages[key] = entry
    rng = random.Random(SEED)  # noqa: S311 - seeded audit sample, not security
    for engine in ENGINES:
        unflagged = sorted(
            k
            for k, v in pages.items()
            if engine in v["engines"] and not v["engines"][engine]["flagged"]
        )
        for key in rng.sample(unflagged, min(AUDIT_PER_ENGINE, len(unflagged))):
            pages[key]["engines"][engine]["audit"] = True
    for key in PROTOCOL_PAGES:
        for e in pages.get(key, {}).get("engines", {}).values():
            e["protocol_named"] = True
    noise_list = {
        e: sorted(
            k
            for k, v in pages.items()
            if e in v["engines"]
            and (
                v["engines"][e]["flagged"]
                or v["engines"][e].get("audit")
                or v["engines"][e].get("protocol_named")
            )
        )
        for e in ENGINES
    }
    # DR-4 amendment (operator, 2026-10-05): on every page that is on either
    # engine's list, every engine with output gets a verdict, so both engines
    # are judged on the same pages and the screen's misses become visible.
    review_pages = set(noise_list["dots-mocr"]) | set(noise_list["paddleocr-vl"])
    for key in review_pages:
        for engine, e in pages[key]["engines"].items():
            if key not in noise_list[engine]:
                e["paired"] = True
                noise_list[engine].append(key)
    noise_list = {e: sorted(v) for e, v in noise_list.items()}
    return {
        "rule": "DR-4: unsupported >= 10 and share >= 0.15, or a 20+ char line repeated 3+ times; plus 5 audit pages per engine (seed 37); plus protocol-named io06:53; plus every other engine with output on those pages (paired)",
        "screened_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "flagged_count": {
            e: sum(1 for v in pages.values() if v["engines"].get(e, {}).get("flagged"))
            for e in ENGINES
        },
        "review_list": noise_list,
        "no_output": no_output,
        "pages": pages,
    }


_MATH_SPAN = re.compile(r"\$\$[\s\S]*?\$\$|(?<![\\$])\$[^$\n]+?\$(?!\$)")


_IMG_TAG = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
_LAYOUT_TAG = re.compile(r"</?(?!(?:table|thead|tbody|tr|td|th)\b)[A-Za-z][^>]*>")


def strip_layout_html(text: str) -> str:
    """Drop layout tags (div, span, center, img ...) but keep every word inside them.

    The ingestion normaliser would also delete text inside image blocks, which
    could hide noise, so it is not used here. Table tags stay for the renderer.
    """
    return _LAYOUT_TAG.sub("", _IMG_TAG.sub("[image]", text))


def render_markdown(text: str) -> str:
    """Render with the Experiment 34 renderer, keeping inline maths away from it.

    That renderer turns ``*...*`` into italics before KaTeX runs, which eats
    the ``*`` in formulas such as ``$\\theta^*$``. Inline spans are swapped
    for placeholders first and put back escaped; display blocks it already
    keeps whole.
    """
    spans: list[str] = []

    def hold(match: re.Match[str]) -> str:
        if match.group(0).startswith("$$"):
            return match.group(0)
        spans.append(match.group(0))
        return f"\x00{len(spans) - 1}\x00"

    rendered = _mini_markdown(strip_layout_html(_MATH_SPAN.sub(hold, text)))
    return re.sub("\x00(\\d+)\x00", lambda m: html.escape(spans[int(m.group(1))]), rendered)


def highlight(text: str, unsupported: set[str]) -> str:
    """Escape *text* and mark words whose token form is unsupported."""
    out, last = [], 0
    for m in _WORD.finditer(text):
        out.append(html.escape(text[last : m.start()]))
        word = m.group(0)
        tok = tokens(word)
        out.append(
            f"<mark>{html.escape(word)}</mark>"
            if tok and tok[0] in unsupported
            else html.escape(word)
        )
        last = m.end()
    out.append(html.escape(text[last:]))
    return "".join(out)


def _exp34_parts() -> tuple[str, str, str]:
    """Return Experiment 34's review-page style, zoom viewer markup and zoom script.

    Reused, not copied, so both review pages look and behave the same.
    """
    import make_review as m34

    style = m34.HTML_HEAD[
        m34.HTML_HEAD.index("<style>") : m34.HTML_HEAD.index("</style>") + len("</style>")
    ]
    tail = m34.HTML_TAIL
    viewer = tail[tail.index('<div id="lb"') : tail.index("<script>")]
    zoom_js = tail[tail.index("// Zoomable viewer") : tail.index("</script>")]
    return style, viewer, zoom_js


def card(key: str, entry: dict[str, Any]) -> str:
    """One page in the Experiment 34 layout: image pinned left, one panel per engine right."""
    doc_id, page = entry["doc_id"], entry["page"]
    image = f".pages/{doc_id}/p{page:03d}.png"
    panels, listed_names = [], []
    for engine in ENGINES:
        e = entry["engines"].get(engine)
        if e is None:
            panels.append(
                f'<details class="engine" data-engine="{engine}"><summary><span class="en">{engine}</span>'
                '<span class="badge">no output</span><span class="estat">—</span></summary>'
                '<div class="pending">This engine returned no text for this page (timeout or empty result). '
                "Nothing to judge.</div></details>"
            )
            continue
        listed = bool(e["flagged"] or e.get("audit") or e.get("protocol_named") or e.get("paired"))
        tag = (
            "screen flag"
            if e["flagged"]
            else (
                "audit sample"
                if e.get("audit")
                else (
                    "named in protocol"
                    if e.get("protocol_named")
                    else ("paired" if e.get("paired") else "not listed")
                )
            )
        )
        if listed:
            listed_names.append(engine)
        text = (OUT / engine / doc_id / f"p{page:03d}.md").read_text("utf-8")
        loops = (
            f'<div class="pending">Repeated lines: {html.escape("; ".join(e["repeated_lines"]))}</div>'
            if e["repeated_lines"]
            else ""
        )
        form = ""
        if listed:
            chips = "".join(
                f'<label class="chip"><input type="radio" name="{key}|{engine}" value="{v}"><span>{v}</span></label>'
                for v in VERDICT_VALUES
            )
            form = (
                f'<fieldset class="form" data-slot="{key}|{engine}"><div class="q"><div class="ql">'
                "Does the output contain text that is not on the page image?</div>"
                f'<div class="opts">{chips}</div></div>'
                '<input class="note" placeholder="note (optional)">'
                '<button type="button" class="clear">Clear</button></fieldset>'
            )
        panels.append(
            f'<details class="engine" data-engine="{engine}" data-listed="{int(listed)}">'
            f'<summary><span class="en">{engine}</span><span class="badge">{tag}</span>'
            f'<span class="badge">{e["unsupported"]} of {e["tokens"]} tokens not in reference ({e["unsupported_share"]:.0%})</span>'
            f'<span class="estat"></span></summary>{form}{loops}'
            '<div class="outwrap"><div class="viewbar"><button type="button" class="vt on" data-v="md">Rendered</button>'
            '<button type="button" class="vt" data-v="raw">Raw + highlights</button></div>'
            f'<div class="md">{render_markdown(text)}</div>'
            f'<pre class="raw" hidden>{highlight(text, set(e["unsupported_sample"]))}</pre></div></details>'
        )
    roles = "".join(f'<span class="role problem">{n}</span>' for n in listed_names)
    return f"""
<details class="page" data-key="{key}">
  <summary><span class="pt">{html.escape(key)} · {entry["run"]}</span>{roles}<span class="pstat"></span></summary>
  <div class="body">
    <div class="orig"><div class="stick">
      <button type="button" class="zoom" data-src="{image}" data-cap="{html.escape(key)}" aria-label="Open zoomable view">
        <img loading="lazy" src="{image}" alt="{html.escape(key)}">
        <span class="mag" aria-hidden="true">⌕</span>
      </button>
      <div class="hint">Click to zoom · pinch or ⌘/Ctrl-scroll inside the viewer</div>
    </div></div>
    <div class="right">{"".join(panels)}</div>
  </div>
</details>"""


_PAGE_JS = """
const STORE='exp37-noise-verdicts';
const pages=[...document.querySelectorAll('details.page')];
const slots=[...document.querySelectorAll('fieldset.form[data-slot]')];
function collect(){return slots.map(f=>{const r=f.querySelector('input:checked');return{key:f.dataset.slot,verdict:r?r.value:null,note:f.querySelector('.note').value}})}
function refresh(){let done=0,pdone=0;
 for(const f of slots){const on=!!f.querySelector('input:checked');if(on)done++;const s=f.closest('details.engine').querySelector('.estat');s.textContent=on?'✓ '+f.querySelector('input:checked').value:'needs verdict';s.className='estat'+(on?' ok':' part')}
 for(const p of pages){const fs=[...p.querySelectorAll('fieldset.form[data-slot]')];const n=fs.filter(f=>f.querySelector('input:checked')).length;const all=n===fs.length;
  const s=p.querySelector('.pstat');s.textContent=all?'✓ reviewed':n+' / '+fs.length;s.className='pstat'+(all?' ok':n?' part':'');p.dataset.done=all?'1':'';if(all)pdone++}
 const pr=document.getElementById('progress');pr.textContent='Done '+done+' / '+slots.length+' verdicts · '+pdone+' / '+pages.length+' pages';pr.className=done===slots.length?'ok':'';
 try{localStorage.setItem(STORE,JSON.stringify(collect()))}catch(e){document.getElementById('progress').textContent+=' · autosave unavailable: download often'}}
try{const by=Object.fromEntries(JSON.parse(localStorage.getItem(STORE)||'[]').map(k=>[k.key,k]));
 for(const f of slots){const v=by[f.dataset.slot];if(!v)continue;if(v.verdict){const r=f.querySelector('input[value='+v.verdict+']');if(r)r.checked=true}f.querySelector('.note').value=v.note||''}}catch(e){}
document.addEventListener('change',refresh);document.addEventListener('input',refresh);
document.addEventListener('click',e=>{const c=e.target.closest('.clear');if(c){const f=c.closest('.form');f.querySelectorAll('input').forEach(i=>{i.checked=false;if(i.classList.contains('note'))i.value=''});refresh();return}
 const v=e.target.closest('.vt');if(v){const w=v.closest('.outwrap');w.querySelectorAll('.vt').forEach(b=>b.classList.toggle('on',b===v));w.querySelector('.md').hidden=v.dataset.v!=='md';w.querySelector('.raw').hidden=v.dataset.v!=='raw'}});
for(const p of pages)p.addEventListener('toggle',()=>{if(!p.open)return;let moved=false;for(const o of pages)if(o!==p&&o.open){if(o.compareDocumentPosition(p)&Node.DOCUMENT_POSITION_FOLLOWING)moved=true;o.open=false}if(moved)p.scrollIntoView({block:'start'});
 p.querySelectorAll('details.engine[data-listed="1"]').forEach(d=>d.open=true)});
document.getElementById('next').onclick=()=>{const p=pages.find(x=>!x.dataset.done);if(!p)return alert('All pages reviewed.');p.open=true;p.scrollIntoView({behavior:'smooth',block:'start'})};
document.getElementById('collapse').onclick=()=>pages.forEach(p=>p.open=false);
document.getElementById('dl').onclick=()=>{const a=document.createElement('a');a.href=URL.createObjectURL(new Blob([JSON.stringify(collect(),null,1)],{type:'application/json'}));a.download='noise_verdicts_download.json';a.click()};
refresh();
"""


def write_page(result: dict[str, Any]) -> int:
    """Write the review page in the Experiment 34 layout for every page on either list."""
    keys = sorted(
        set(result["review_list"]["dots-mocr"]) | set(result["review_list"]["paddleocr-vl"])
    )
    cards = "\n".join(card(k, result["pages"][k]) for k in keys)
    counts = {e: len(v) for e, v in result["review_list"].items()}
    style, viewer, zoom_js = _exp34_parts()
    katex = (
        '<link rel="stylesheet" href="../katex/node_modules/katex/dist/katex.min.css">\n'
        '<script defer src="../katex/node_modules/katex/dist/katex.min.js"></script>\n'
        '<script defer src="../katex/node_modules/katex/dist/contrib/auto-render.min.js"\n'
        " onload=\"renderMathInElement(document.body,{delimiters:[{left:'$$',right:'$$',display:true},"
        "{left:'$',right:'$',display:false}],ignoredClasses:['raw'],throwOnError:false})\"></script>\n"
    )
    extra_css = (
        "<style>.form .note{font:inherit;font-size:.82rem;padding:.3rem .5rem;border:1px solid var(--line);"
        "border-radius:6px;background:var(--card);color:var(--ink)}"
        "mark{background:#ffe08a;color:inherit}@media (prefers-color-scheme:dark){mark{background:#6b5200}}"
        ".role.problem{margin-left:.2rem}#progress{font-size:.95rem;font-weight:700;color:var(--ink);background:var(--soft);border:1px solid var(--line);border-radius:999px;padding:.25rem .8rem}#progress.ok{color:#fff;background:var(--ok);border-color:var(--ok)}</style>\n"
    )
    PAGE.write_text(
        '<!doctype html><html lang="en-GB"><head><meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        "<title>Experiment 37 noise review</title>\n"
        f"{katex}{style}\n{extra_css}</head><body>\n"
        '<div class="bar"><strong>Experiment 37 — noise review (G3)</strong>'
        ' <span id="progress"></span>'
        ' <button id="next" type="button">Next unreviewed</button>'
        ' <button id="collapse" type="button">Collapse all</button>'
        ' <button id="dl" type="button">Download verdicts</button></div>\n<main>\n'
        '<p class="intro">Open a page. The original stays pinned on the left; click it to zoom. '
        "Each engine on the right has its own output. The engines named on the page header need a verdict: "
        "<b>noise</b> when the output contains text that is not on the page image (invented, garbage or bleed-through), "
        "<b>clean</b> when every piece of text is on the page. "
        "Rendered shows Markdown and maths (KaTeX 0.16.22, local) with layout tags removed and every word kept. "
        "Raw + highlights shows the exact engine text; highlighted words are not in the reference text, "
        "a hint, not a verdict. "
        f"Lists: dots-mocr {counts['dots-mocr']}, paddleocr-vl {counts['paddleocr-vl']} "
        f"(each includes {AUDIT_PER_ENGINE} audit pages). Every engine with output on a listed page gets a verdict; <i>paired</i> marks an engine the screen did not pick on that page.</p>\n"
        f"{cards}\n</main>\n{viewer}<script>{_PAGE_JS}\n{zoom_js}</script></body></html>\n",
        encoding="utf-8",
    )
    return len(keys)


def merge(download: Path) -> int:
    """Check every listed slot has a verdict, then write noise_verdicts.json."""
    result = json.loads(SCREEN.read_text("utf-8"))
    rows = {r["key"]: r for r in json.loads(download.read_text("utf-8"))}
    expected = [f"{k}|{e}" for e, keys in result["review_list"].items() for k in keys]
    missing = [k for k in expected if rows.get(k, {}).get("verdict") not in VERDICT_VALUES]
    if missing:
        print(
            f"{len(missing)} listed slots have no verdict, first: {missing[:10]}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    verdicts: dict[str, dict[str, Any]] = {e: {} for e in ENGINES}
    for slot in expected:
        key, engine = slot.split("|")
        entry = {
            "verdict": rows[slot]["verdict"],
            "source": "screen"
            if result["pages"][key]["engines"][engine]["flagged"]
            else (
                "audit"
                if result["pages"][key]["engines"][engine].get("audit")
                else (
                    "protocol"
                    if result["pages"][key]["engines"][engine].get("protocol_named")
                    else "paired"
                )
            ),
        }
        if rows[slot].get("note"):
            entry["note"] = rows[slot]["note"]
        verdicts[engine][key] = entry
    data = {
        "reviewer": "operator (Dr Muhammad Aizat Bin Md Hawari)",
        "merged_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "screen_rule": result["rule"],
        "verdicts": verdicts,
    }
    tmp = VERDICTS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(VERDICTS)
    for engine, v in verdicts.items():
        noise = sorted(k for k, x in v.items() if x["verdict"] == "noise")
        print(f"[noise] {engine}: {len(v)} verdicts, noise on {len(noise)}: {noise}", flush=True)
    return 0


def main() -> int:
    """Screen and write the page, or merge a download."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--merge", type=Path, help="verdicts JSON downloaded from the page")
    args = parser.parse_args()
    if args.merge:
        return merge(args.merge)
    result = screen()
    tmp = SCREEN.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(SCREEN)
    n = write_page(result)
    print(
        f"[noise] flagged {result['flagged_count']} · review list {{e: len(v)}} -> ".replace(
            "{e: len(v)}", str({e: len(v) for e, v in result["review_list"].items()})
        )
        + f"{n} page cards -> {PAGE}",
        flush=True,
    )
    print(f"[noise] no output: {result['no_output']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
