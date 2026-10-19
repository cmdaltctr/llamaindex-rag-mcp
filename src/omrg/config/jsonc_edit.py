"""Edit one value in JSON-with-comments text and keep every other byte (D4).

``set_value`` replaces the value of an existing member, or inserts a new
member before the closing brace of its object (and creates the nested object
when it is missing). ``remove_value`` removes a member with its comma. Both
return new text and never touch the input. Comments, key order and the layout
of the other members stay as they were.

The scanner reads the text once and records where each member sits. It
accepts what ``parse_jsonc`` accepts: ``//`` and ``/* */`` comments and
trailing commas. A target key that appears twice, a path through a value that
is not an object, or text that is not an object raise :class:`JsoncEditError`.

This module is a leaf: it imports nothing from OMRG.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

_SPACE = " \t\r\n"
_UNIT = "  "  # indent for a layout that offers no hint


class JsoncEditError(ValueError):
    """The text cannot be edited safely. The message names no value."""


@dataclass
class _Member:
    key: str
    start: int  # the opening quote of the key
    value_start: int
    value_end: int  # exclusive
    comma: int | None  # index of the comma after the value, if any


@dataclass
class _Object:
    start: int  # the "{"
    end: int  # the "}"
    members: list[_Member]


class _Scanner:
    """One pass over the text. Raises :class:`JsoncEditError` on anything odd."""

    def __init__(self, text: str) -> None:
        self.text = text

    def fail(self, why: str) -> JsoncEditError:
        return JsoncEditError(f"omrg.jsonc cannot be edited: {why}.")

    def skip(self, i: int) -> int:
        """Return the index of the next character that is not space or comment."""
        text, n = self.text, len(self.text)
        while i < n:
            if text[i] in _SPACE:
                i += 1
            elif text.startswith("//", i):
                end = text.find("\n", i)
                i = n if end < 0 else end
            elif text.startswith("/*", i):
                end = text.find("*/", i + 2)
                if end < 0:
                    raise self.fail("a comment is not closed")
                i = end + 2
            else:
                break
        return i

    def string_end(self, i: int) -> int:
        """Return the index after the string that starts at *i*."""
        text, n = self.text, len(self.text)
        j = i + 1
        while j < n and text[j] != '"':
            j += 2 if text[j] == "\\" else 1
        if j >= n:
            raise self.fail("a string is not closed")
        return j + 1

    def value_end(self, i: int) -> int:
        """Return the index after the value that starts at *i*."""
        text, n = self.text, len(self.text)
        if i >= n:
            raise self.fail("a value is missing")
        ch = text[i]
        if ch == '"':
            return self.string_end(i)
        if ch == "{":
            return self.object_at(i).end + 1
        if ch == "[":
            j = self.skip(i + 1)
            while j < n and text[j] != "]":
                j = self.skip(self.value_end(j))
                if j < n and text[j] == ",":
                    j = self.skip(j + 1)
            if j >= n:
                raise self.fail("an array is not closed")
            return j + 1
        j = i
        while j < n and text[j] not in _SPACE + ",}]" and not text.startswith(("//", "/*"), j):
            j += 1
        if j == i:
            raise self.fail("a value is missing")
        return j

    def object_at(self, i: int) -> _Object:
        """Parse the object whose ``{`` is at *i*."""
        text, n = self.text, len(self.text)
        members: list[_Member] = []
        j = self.skip(i + 1)
        while True:
            if j >= n:
                raise self.fail("an object is not closed")
            if text[j] == "}":
                return _Object(i, j, members)
            if text[j] != '"':
                raise self.fail("a key must be a string")
            key_end = self.string_end(j)
            try:
                key = json.loads(text[j:key_end])
            except ValueError as exc:
                raise self.fail("a key is not valid") from exc
            colon = self.skip(key_end)
            if colon >= n or text[colon] != ":":
                raise self.fail("a colon is missing")
            value_start = self.skip(colon + 1)
            value_end = self.value_end(value_start)
            after = self.skip(value_end)
            comma = after if after < n and text[after] == "," else None
            members.append(_Member(key, j, value_start, value_end, comma))
            if comma is not None:
                j = self.skip(comma + 1)
            elif after < n and text[after] == "}":
                j = after
            else:
                raise self.fail("a comma is missing")

    def root(self) -> _Object:
        """Parse the top-level object. Only space and comments may follow it."""
        start = self.skip(0)
        if start >= len(self.text) or self.text[start] != "{":
            raise self.fail("the top level must be an object")
        obj = self.object_at(start)
        if self.skip(obj.end + 1) != len(self.text):
            raise self.fail("there is text after the object")
        return obj

    def find(self, obj: _Object, key: str) -> _Member | None:
        """Return the member named *key*; raise when the key appears twice."""
        found = [m for m in obj.members if m.key == key]
        if len(found) > 1:
            raise JsoncEditError(f"omrg.jsonc has the key {key!r} twice. Fix it, then save again.")
        return found[0] if found else None

    def child(self, member: _Member) -> _Object:
        if self.text[member.value_start] != "{":
            raise JsoncEditError(f"omrg.jsonc: {member.key!r} is not an object.")
        return self.object_at(member.value_start)


# ── Layout helpers ───────────────────────────────────────────────────────


def _line_start(text: str, i: int) -> int:
    return text.rfind("\n", 0, i) + 1


def _indent_of_line(text: str, i: int) -> str:
    """Return the leading space of the line that holds index *i*."""
    start = _line_start(text, i)
    j = start
    while j < len(text) and text[j] in " \t":
        j += 1
    return text[start:j]


def _newline(text: str) -> str:
    return "\r\n" if "\r\n" in text else "\n"


def _render(
    chain: Sequence[str], value: Any, indent: str, unit: str, multiline: bool, nl: str
) -> str:
    """Return the text of ``"k1": {"k2": ... value}`` for the keys in *chain*."""
    head = f"{json.dumps(chain[0])}: "
    if len(chain) == 1:
        return head + json.dumps(value, ensure_ascii=False)
    inner = _render(chain[1:], value, indent + unit, unit, multiline, nl)
    if multiline:
        return f"{head}{{{nl}{indent + unit}{inner}{nl}{indent}}}"
    return f"{head}{{ {inner} }}"


def _after_note(text: str, i: int) -> int:
    """Return *i*, moved past a comment that sits on the same line after it."""
    j = i
    while j < len(text) and text[j] in " \t":
        j += 1
    if text.startswith("//", j):
        end = text.find("\n", j)
        return len(text) if end < 0 else end
    if text.startswith("/*", j):
        end = text.find("*/", j + 2)
        if end >= 0 and "\n" not in text[j:end]:
            return end + 2
    return i


def _insert(text: str, obj: _Object, chain: Sequence[str], value: Any) -> str:
    """Insert ``chain`` (one new member, nested as needed) into *obj*."""
    nl = _newline(text)
    outer = _indent_of_line(text, obj.start)
    multiline = "\n" in text[obj.start : obj.end + 1]
    if obj.members and multiline:
        first = obj.members[0]
        pad = text[_line_start(text, first.start) : first.start]
        inner = pad if pad.strip() == "" and len(pad) > len(outer) else outer + _UNIT
    else:
        inner = outer + _UNIT
    unit = inner[len(outer) :] if inner.startswith(outer) and len(inner) > len(outer) else _UNIT
    member = _render(chain, value, inner, unit, multiline, nl)

    if not obj.members:
        inside = text[obj.start + 1 : obj.end]
        if inside.strip() == "":
            body = f"{nl}{inner}{member}{nl}{outer}" if multiline else f" {member} "
            return text[: obj.start + 1] + body + text[obj.end :]
        stop = obj.end
        while text[stop - 1] in _SPACE:
            stop -= 1
        glue = f"{nl}{inner}" if multiline else " "
        return text[:stop] + glue + member + text[stop:]

    last = obj.members[-1]
    after = last.value_end if last.comma is None else last.comma + 1
    stop = _after_note(text, after)
    glue = f"{nl}{inner}" if multiline else " "
    tail = "," if last.comma is not None else ""
    comma = "," if last.comma is None else ""
    return (
        text[: last.value_end]
        + comma
        + text[last.value_end : stop]
        + glue
        + member
        + tail
        + text[stop:]
    )


# ── Public edits ─────────────────────────────────────────────────────────


def set_value(text: str, path: Sequence[str], value: Any) -> str:
    """Return *text* with the member at *path* set to *value*.

    Args:
        text: JSONC text whose top level is an object.
        path: Keys from the top level, such as ``("retrieval", "top_k")``.
        value: A JSON-serialisable value.

    Raises:
        JsoncEditError: *path* is empty, the text is not an editable object,
            a key on the path appears twice, or a parent is not an object.
    """
    if not path:
        raise JsoncEditError("omrg.jsonc: a key path is needed.")
    scanner = _Scanner(text)
    obj = scanner.root()
    for depth, key in enumerate(path[:-1]):
        member = scanner.find(obj, key)
        if member is None:
            return _insert(text, obj, path[depth:], value)
        obj = scanner.child(member)
    member = scanner.find(obj, path[-1])
    if member is None:
        return _insert(text, obj, path[-1:], value)
    rendered = json.dumps(value, ensure_ascii=False)
    return text[: member.value_start] + rendered + text[member.value_end :]


def remove_value(text: str, path: Sequence[str]) -> str:
    """Return *text* without the member at *path*. A missing member changes nothing.

    The member's comma goes with it. Comments stay. A nested object that the
    removal leaves empty, with no comment inside, goes too.

    Raises:
        JsoncEditError: As :func:`set_value`.
    """
    if not path:
        raise JsoncEditError("omrg.jsonc: a key path is needed.")
    scanner = _Scanner(text)
    obj = scanner.root()
    for key in path[:-1]:
        member = scanner.find(obj, key)
        if member is None or text[member.value_start] != "{":
            return text
        obj = scanner.object_at(member.value_start)
    member = scanner.find(obj, path[-1])
    if member is None:
        return text
    new = _cut(text, obj, member)
    if len(path) > 1:
        parent = _Scanner(new)
        holder = parent.root()
        for key in path[:-2]:
            found = parent.find(holder, key)
            if found is None:
                return new
            holder = parent.object_at(found.value_start)
        found = parent.find(holder, path[-2])
        if found is not None:
            emptied = parent.object_at(found.value_start)
            if not emptied.members and new[emptied.start + 1 : emptied.end].strip() == "":
                return remove_value(new, path[:-1])
    return new


def _cut(text: str, obj: _Object, member: _Member) -> str:
    """Cut *member* (and one comma) out of *obj*."""
    index = obj.members.index(member)
    end = member.value_end if member.comma is None else member.comma + 1
    start = member.start
    ranges: list[tuple[int, int]] = []
    previous = obj.members[index - 1] if index > 0 else None
    if member.comma is None and previous is not None and previous.comma is not None:
        between = text[previous.comma + 1 : start]
        if between.strip() == "":
            start = previous.comma  # one cut: the comma, the gap and the member
        else:
            ranges.append((previous.comma, previous.comma + 1))
    before = text[_line_start(text, start) : start]
    rest_end = text.find("\n", end)
    rest = text[end : len(text) if rest_end < 0 else rest_end]
    if before.strip() == "" and rest.strip() == "" and start == member.start:
        stop = len(text) if rest_end < 0 else rest_end + 1
        ranges.append((_line_start(text, start), stop))
    else:
        if member.comma is not None:
            while end < len(text) and text[end] in " \t":
                end += 1
        ranges.append((start, end))
    for lo, hi in sorted(ranges, reverse=True):
        text = text[:lo] + text[hi:]
    return text
