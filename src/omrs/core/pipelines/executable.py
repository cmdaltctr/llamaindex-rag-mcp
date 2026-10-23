"""Detect executable text in graph parameters.

Graph documents carry data for registered operations. They never carry
Python expressions, shell commands or dynamic imports. Parameter schemas
already reject unknown keys; this check rejects string values that look
like code. Operations mark prompt-like parameters as free text, and those
values are data, so this check skips them.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern, re.IGNORECASE), reason)
    for pattern, reason in (
        (r"__\w+__", "Python dunder access"),
        (r"\b(?:eval|exec|compile|getattr|setattr|open)\s*\(", "Python built-in call"),
        (r"\bimportlib\b|\bimport\s+[A-Za-z_]", "dynamic import"),
        (r"\blambda\b[^:]*:", "Python lambda"),
        (r"\b(?:os|sys|subprocess|shutil|builtins)\s*\.\s*\w+", "Python module access"),
        (r"\$\(|`", "shell command substitution"),
        (r"(?:^|[;&|]\s*)(?:rm|curl|wget|sh|bash|zsh|python\d?|uv|uvx|pip)\b", "shell command"),
        (r"&&|\|\||\|\s*(?:sh|bash|zsh|python\d?)\b", "shell command chaining"),
        (r"^\s*#!", "script interpreter line"),
    )
)


def executable_reason(value: str) -> str | None:
    """Return why ``value`` looks executable, or ``None`` when it is data."""
    for pattern, reason in _PATTERNS:
        if pattern.search(value):
            return reason
    return None


def iter_strings(value: Any, path: str = "") -> Iterator[tuple[str, str]]:
    """Yield ``(path, text)`` for every string inside a JSON value."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from iter_strings(item, f"{path}.{key}" if path else str(key))
    elif isinstance(value, list | tuple):
        for index, item in enumerate(value):
            yield from iter_strings(item, f"{path}[{index}]")
