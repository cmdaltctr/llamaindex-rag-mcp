"""Clean reader-produced Markdown without changing protected code or maths."""

from __future__ import annotations

import html
import re

#: 1: image blocks removed with their text (Experiment 36 first measurement).
#: 2: every block unwrapped; text inside image blocks kept, no placeholder.
NORMALISER_VERSION = 2

_FENCE = re.compile(r"(?m)^ {0,3}(`{3,}|~{3,})[^\n]*\n.*?^ {0,3}\1[ \t]*(?:\n|$)", re.S)
_INLINE_CODE = re.compile(r"(?<!`)(`+)(?!`)[^\n]*?\1(?!`)")
_TABLE = re.compile(r"<table\b[^>]*>.*?</table\s*>", re.I | re.S)
_DISPLAY_MATH = re.compile(r"\$\$.*?\$\$", re.S)
_ENV_MATH = re.compile(r"\\begin\{([A-Za-z*]+)\}.*?\\end\{\1\}", re.S)
_INLINE_MATH = re.compile(r"(?<!\$)\$(?!\$)[^\n$]+?\$(?!\$)")
_DIV = re.compile(r"<div\b[^>]*>(?:(?!</?div\b).)*?</div\s*>", re.I | re.S)
_DIV_TAG = re.compile(r"<(/?)div\b[^>]*>", re.I | re.S)
_IMAGE = re.compile(r"<img\b[^>]*>", re.I | re.S)
_TAG = re.compile(r"<(/?)(u|span|font|center|b|strong|i|em)\b[^>]*>", re.I)
_BR = re.compile(r"<br\b[^>]*>", re.I)
_HTML_TAG = re.compile(r"<(/?)([A-Za-z][\w-]*)\b([^>]*)>")
_SPAN = re.compile(r"\b(colspan|rowspan)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s>]+))", re.I)
_STRUCTURAL = frozenset({"table", "thead", "tbody", "tr", "td", "th"})
_KNOWN_TAGS = _STRUCTURAL | {
    "div",
    "img",
    "u",
    "span",
    "font",
    "center",
    "b",
    "strong",
    "i",
    "em",
    "br",
}


def _clean_table(table: str) -> str:
    """Keep table structure and cell spans without presentation attributes."""

    def clean_tag(match: re.Match[str]) -> str:
        closing, name, attributes = match.groups()
        name = name.lower()
        if name not in _STRUCTURAL:
            return ""
        if closing:
            return f"</{name}>"
        spans = "".join(
            f' {item.group(1).lower()}="{item.group(2) or item.group(3) or item.group(4)}"'
            for item in _SPAN.finditer(attributes)
        )
        return f"<{name}{spans}>"

    return _HTML_TAG.sub(clean_tag, table)


def normalise_reader_text(text: str) -> str:
    """Remove known PDF reader noise while keeping visible document text.

    Args:
        text: Markdown or plain text emitted by a PDF reader.

    Returns:
        Normalised text with code, tables and LaTeX maths preserved.
    """
    marker = "\x00omrg-protected-"
    while marker in text:
        marker += "-"
    protected: list[str] = []

    def protect(segment: str) -> str:
        protected.append(segment)
        return f"{marker}{len(protected) - 1}\x00"

    def save(match: re.Match[str]) -> str:
        return protect(match.group(0))

    for pattern in (_FENCE, _INLINE_CODE, _TABLE, _DISPLAY_MATH, _ENV_MATH, _INLINE_MATH):
        text = pattern.sub(save, text)

    # Keep unknown HTML tags byte-for-byte, including entities in attributes.
    text = _HTML_TAG.sub(
        lambda match: match.group(0) if match.group(2).lower() in _KNOWN_TAGS else save(match),
        text,
    )

    # Leave malformed trailing div content untouched instead of guessing a boundary.
    open_divs: list[int] = []
    for tag in _DIV_TAG.finditer(text):
        if tag.group(1):
            if open_divs:
                open_divs.pop()
        else:
            open_divs.append(tag.start())
    if open_divs:
        start = open_divs[0]
        text = text[:start] + protect(text[start:])

    # Every block is unwrapped, image-bearing or not: text a reader recognised
    # inside a picture (a badge, an advertisement) is document text, and the
    # <img> tags go with the bare-image rule below. No placeholder is left
    # (Experiment 36, operator decisions 2026-09-25).
    def clean_div(match: re.Match[str]) -> str:
        block = match.group(0)
        return block[block.find(">") + 1 : block.lower().rfind("</div")]

    while True:
        updated = _DIV.sub(clean_div, text)
        if updated == text:
            break
        text = updated

    text = _IMAGE.sub("", text)

    def format_tag(match: re.Match[str]) -> str:
        name = match.group(2).lower()
        if name in {"b", "strong"}:
            return "**"
        if name in {"i", "em"}:
            return "*"
        return ""

    text = _TAG.sub(format_tag, text)
    text = _BR.sub("\n", text)
    text = html.unescape(text)
    text = re.sub(r"(?:[ \t]*\n){3,}", "\n\n", text)
    for index in range(len(protected) - 1, -1, -1):
        segment = protected[index]
        restored = _clean_table(segment) if _TABLE.fullmatch(segment) else segment
        text = text.replace(f"{marker}{index}\x00", restored)
    return text
