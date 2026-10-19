"""Remove credentials from values before they are stored or shown.

Two checks apply. A mapping key that names a credential (for example
``api_key``, ``token`` or ``Authorization``) has its whole value replaced.
Every string is also scanned for credential shapes: bearer values, URLs
with a user name or password, credential query parameters, ``key=value``
assignments and well-known provider key prefixes.

The rules prefer redaction of a harmless value over a leak. For example a
key named ``cache_key`` is redacted too.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[redacted]"

_SECRET_KEY = re.compile(
    r"(?:^|_)(?:api_?key|apikey|key|secret|secrets|password|passwd|pwd|token|"
    r"access_token|refresh_token|id_token|auth|authorization|bearer|credential|"
    r"credentials|cookie|session|private_key|signature)$"
)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

_CREDENTIAL_NAMES = (
    r"api[_-]?key|apikey|access[_-]?token|refresh[_-]?token|token|secret|"
    r"client[_-]?secret|password|passwd|pwd|sig|signature|auth"
)
_TEXT_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    # scheme://user:password@host -> scheme://[redacted]@host
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s@:]*(?::[^/\s@]*)?@"), rf"\1{REDACTED}@"),
    # ?api_key=value or &token=value
    (re.compile(rf"(?i)([?&](?:{_CREDENTIAL_NAMES})=)[^&#\s]+"), rf"\1{REDACTED}"),
    # Authorization header values. A short word after "bearer" is prose.
    (re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{8,}"), rf"\1 {REDACTED}"),
    (
        re.compile(r"\b(Basic)\s+(?=[A-Za-z0-9+/]*[0-9+/])[A-Za-z0-9+/]{8,}={0,2}"),
        rf"\1 {REDACTED}",
    ),
    # api_key=value, password: value
    (
        re.compile(rf"(?i)(?<![\w-])((?:{_CREDENTIAL_NAMES})\s*[:=]\s*)[^\s,;&]+"),
        rf"\1{REDACTED}",
    ),
    # Provider key shapes.
    (
        re.compile(
            r"\b(?:sk-[A-Za-z0-9_-]{16,}|sk_(?:live|test)_[A-Za-z0-9]{16,}|"
            r"hf_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|"
            r"xox[abprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{35})"
        ),
        REDACTED,
    ),
)


def is_secret_key(key: str) -> bool:
    """Return whether a mapping key names a credential.

    The key is compared in snake case, so ``apiKey`` and ``api-key`` match
    ``api_key``.
    """
    normalised = _CAMEL.sub("_", key).lower().replace("-", "_")
    return bool(_SECRET_KEY.search(normalised))


def redact_text(text: str) -> str:
    """Return ``text`` with every credential shape replaced."""
    for pattern, replacement in _TEXT_RULES:
        text = pattern.sub(replacement, text)
    return text


def redact(value: Any) -> Any:
    """Return a copy of a JSON-like value with credentials replaced.

    Mappings become dictionaries with string keys, and tuples become lists.
    Other scalar types are returned unchanged.
    """
    if isinstance(value, Mapping):
        return {
            str(key): REDACTED if is_secret_key(str(key)) else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def contains_secret(value: Any) -> bool:
    """Return whether :func:`redact` would change ``value``."""
    if isinstance(value, Mapping):
        return any(is_secret_key(str(key)) or contains_secret(item) for key, item in value.items())
    if isinstance(value, list | tuple):
        return any(contains_secret(item) for item in value)
    if isinstance(value, str):
        return redact_text(value) != value
    return False
