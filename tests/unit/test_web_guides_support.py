"""Helpers for the web workspace and notebook guide tests (tasks 6.9, 8.7).

Each helper reads a guide and checks one kind of citation against the
repository: file paths, ``/v1`` routes in the OpenAPI contract, and
relative Markdown links with their anchors. No tests live here.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
GUIDES = REPO / "docs" / "guides"
OPENAPI = REPO / "src" / "omrg" / "transports" / "api" / "openapi.yaml"

_CODE = re.compile(r"`([^`\n]+)`")
_ROUTE = re.compile(r"^(?:(GET|POST|PUT|PATCH|DELETE) )?(/v1(?:/[^\s?]*)?)")
_LINK = re.compile(r"\]\(((?:\.\./)*[\w./-]+\.md)(?:#([\w-]+))?\)")
_HEADING = re.compile(r"^#{1,6} (.+)$", re.M)
_REPO_PREFIXES = ("src/", "docs/", "tests/", "plugins/", "scripts/", "web/")


def code_spans(text: str) -> list[str]:
    """Return every inline code span in *text*."""
    return _CODE.findall(text)


def missing_repository_paths(text: str) -> list[str]:
    """Return cited repository paths (in code spans) that do not exist."""
    cited = [span for span in code_spans(text) if span.startswith(_REPO_PREFIXES)]
    return [path for path in cited if not (REPO / path).exists()]


def cited_routes(text: str) -> list[tuple[str | None, str]]:
    """Return ``(method or None, contract path)`` for each cited ``/v1`` route."""
    routes = []
    for span in code_spans(text):
        match = _ROUTE.match(span)
        if match is None:
            continue
        path = match.group(2)[len("/v1") :] or "/"
        routes.append((match.group(1), path))
    return routes


def undeclared_routes(text: str) -> list[str]:
    """Return cited routes that ``openapi.yaml`` does not declare."""
    paths = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))["paths"]
    problems = []
    for method, path in cited_routes(text):
        if path not in paths and not (path == "/" and method is None):
            problems.append(f"{method or 'ANY'} {path}")
        elif method is not None and method.lower() not in paths[path]:
            problems.append(f"{method} {path}")
    return problems


def anchor(heading: str) -> str:
    """Return the GitHub-style anchor of a Markdown heading."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def broken_links(guide: Path) -> list[str]:
    """Return relative ``.md`` links of *guide* whose file or anchor is missing."""
    problems = []
    for target, fragment in _LINK.findall(guide.read_text(encoding="utf-8")):
        path = (guide.parent / target).resolve()
        if not path.is_file():
            problems.append(target)
            continue
        if fragment:
            anchors = {anchor(h) for h in _HEADING.findall(path.read_text(encoding="utf-8"))}
            if fragment not in anchors:
                problems.append(f"{target}#{fragment}")
    return problems


def links_to(document: Path, guide_name: str) -> bool:
    """Return whether *document* has a Markdown link to the guide file."""
    return (
        re.search(
            rf"\]\((?:[\w./-]*/)?{re.escape(guide_name)}(?:#[\w-]+)?\)",
            document.read_text(encoding="utf-8"),
        )
        is not None
    )
