"""Generate Experiment 1 fixtures and the pre-registered label manifest.

Writes 18 synthetic source fixtures (12 Python, 4 JavaScript, 2 TypeScript)
under ``fixtures/src/`` and derives ``fixtures/manifest.json`` from the
source text alone — never from treatment output (protocol §9: labels are
written before any chunker runs).

Label protocol:
- Python: ``ast.parse`` top-level ``FunctionDef`` / ``AsyncFunctionDef`` /
  ``ClassDef`` nodes, 1-based inclusive line spans.
- JS/TS: fixtures use only column-0 ``function name(...) {`` and
  ``class Name ... {`` declarations; the span ends at the matching
  column-0 ``}`` line.

Deterministic: no randomness, no timestamps in the manifest (it is the
corpus identity anchor hashed into every cell runtime manifest).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SCRIPT_DIR / "fixtures"
SRC_DIR = FIXTURES_DIR / "src"

CODE_MAX_CHARS = 1500


def py_function(name: str, doc: str, body: list[str]) -> list[str]:
    """Build a top-level Python function as source lines."""
    lines = [f"def {name}(value):", f'    """{doc}"""']
    lines.extend(f"    {statement}" for statement in body)
    lines.extend(["", ""])
    return lines


def py_class(name: str, methods: list[tuple[str, str, list[str]]]) -> list[str]:
    """Build a top-level Python class with indented methods."""
    lines = [f"class {name}:"]
    for method_name, doc, body in methods:
        lines.append(f"    def {method_name}(self, value):")
        lines.append(f'        """{doc}"""')
        lines.extend(f"        {statement}" for statement in body)
        lines.append("")
    lines.extend(["", ""])
    return lines


def js_function(name: str, body: list[str], *, typed: bool = False) -> list[str]:
    """Build a top-level JS/TS function closed by a column-0 brace."""
    signature = (
        f"function {name}(input: number): number {{" if typed else f"function {name}(input) {{"
    )
    lines = [signature]
    lines.extend(f"    {statement}" for statement in body)
    lines.extend(["}", "", ""])
    return lines


def py_statements(var: str, count: int) -> list[str]:
    """Deterministic Python statements, roughly 44 characters per line."""
    lines = []
    for i in range(count):
        if i % 3 == 0:
            lines.append(f"{var} = {var} * 2 + {i}  # transform step {i:03d}")
        elif i % 3 == 1:
            lines.append(f"{var} = {var} + {i * 7}  # additive step {i:03d}")
        else:
            lines.append(f"{var} = max({var} - {i}, 0)  # clamp step {i:03d}")
    lines.append(f"return {var}")
    return lines


def js_statements(var: str, count: int) -> list[str]:
    """Deterministic JS/TS statements, roughly 46 characters per line."""
    lines = [f"let {var} = input;"]
    for i in range(count):
        if i % 3 == 0:
            lines.append(f"{var} = {var} * 2 + {i};  // transform {i:03d}")
        elif i % 3 == 1:
            lines.append(f"{var} = {var} + {i * 7};  // additive {i:03d}")
        else:
            lines.append(f"{var} = Math.max({var} - {i}, 0);  // clamp {i:03d}")
    lines.append(f"return {var};")
    return lines


# ── Fixture assembly ────────────────────────────────────────────────────


def build_py_simple(index: int) -> list[str]:
    """Simple fixtures: a handful of small definitions, one chunk either way."""
    lines = [f"# py_simple_{index:02d}: small definitions, no nesting.", ""]
    for i in range(4 + index % 3):
        lines.extend(
            py_function(f"simple_{i}", f"Simple transform number {i}.", py_statements("value", 4))
        )
    lines.extend(py_class("simple_box", [("wrap", "Wrap the value.", py_statements("value", 3))]))
    return lines


def build_py_nested(index: int) -> list[str]:
    """Nested fixtures: definitions inside definitions, several chunks."""
    lines = [f"# py_nested_{index:02d}: nested functions and classes.", ""]

    def nested_function(order: int) -> list[str]:
        inner_count = 4 + order + index
        outer_count = 10 + 2 * order + index
        return [
            f"def nested_function_{order}(value):",
            f'    """Nested function number {order}."""',
            "    def inner_helper(seed):",
            f'        """Inner helper number {order}."""',
            *(f"        {statement}" for statement in py_statements("seed", inner_count)),
            *(f"    {statement}" for statement in py_statements("value", outer_count)),
            "",
            "",
        ]

    for order in range(3):
        lines.extend(nested_function(order))

    methods = [
        (f"method_{m}", f"Class method number {m}.", py_statements("value", 8)) for m in range(3)
    ]
    lines.extend(py_class("nested_engine", methods))
    return lines


def build_py_longbody(index: int) -> list[str]:
    """Long-body fixtures: functions sized around half the character ceiling."""
    lines = [f"# py_longbody_{index:02d}: long function bodies.", ""]
    counts = [[26, 30, 12], [24, 24, 24], [32, 18, 14]][index % 3]
    for i, count in enumerate(counts):
        lines.extend(
            py_function(f"long_body_{i}", f"Long body function {i}.", py_statements("value", count))
        )
    return lines


def build_py_boundary(index: int) -> list[str]:
    """Boundary fixtures: definitions sized at and beyond code_max_chars."""
    lines = [f"# py_boundary_{index:02d}: definitions near the 1500 char ceiling.", ""]
    if index == 0:
        lines.extend(
            py_function("fits_below", "Sized just under the ceiling.", py_statements("value", 28))
        )
        lines.extend(
            py_function("at_ceiling", "Sized right at the ceiling.", py_statements("value", 31))
        )
        lines.extend(
            py_function("tail_small", "Small trailer definition.", py_statements("value", 5))
        )
    elif index == 1:
        lines.extend(
            py_function("oversized", "Deliberately beyond the ceiling.", py_statements("value", 48))
        )
        lines.extend(
            py_function(
                "before_big", "Small definition before the big one.", py_statements("value", 8)
            )
        )
        lines.extend(
            py_function(
                "after_big", "Small definition after the big one.", py_statements("value", 8)
            )
        )
    else:
        methods = [
            (f"engine_method_{m}", f"Engine method {m}.", py_statements("value", 20))
            for m in range(2)
        ]
        lines.extend(py_class("boundary_engine", methods))
        lines.extend(
            py_function(
                "sized_just_over", "Just over the class ceiling.", py_statements("value", 6)
            )
        )
    return lines


def build_js_simple(index: int, *, typed: bool) -> list[str]:
    suffix = "ts" if typed else "js"
    lines = [f"// js_simple_{index:02d}.{suffix}: small top-level functions.", ""]
    for i in range(4 + index % 2):
        lines.extend(js_function(f"simpleStep{i}", js_statements("value", 5), typed=typed))
    return lines


def build_js_nested(index: int, *, typed: bool) -> list[str]:
    suffix = "ts" if typed else "js"
    lines = [f"// js_nested_{index:02d}.{suffix}: functions with inner functions.", ""]
    for i in range(3):
        inner = [
            "    function innerHelper(seed) {",
            *(f"        {statement}" for statement in js_statements("seed", 4)[:-1]),
            "        return seed;",
            "    }",
        ]
        body = (
            ["    let value = input;"]
            + inner
            + [
                *(f"    {statement}" for statement in js_statements("value", 10)[1:-1]),
                "    value = value + innerHelper(value);",
                "    return value;",
            ]
        )
        signature = (
            f"function nestedStep{i}(input: number): number {{"
            if typed
            else f"function nestedStep{i}(input) {{"
        )
        lines.extend([signature, *body, "}", "", ""])
    return lines


def build_js_longbody(index: int) -> list[str]:
    lines = ["// js_longbody_01.js: long function bodies.", ""]
    for i, count in enumerate([26, 24, 10]):
        lines.extend(js_function(f"longBody{i}", js_statements("value", count)))
    return lines


def build_js_boundary(index: int) -> list[str]:
    lines = ["// js_boundary_01.js: definitions near the 1500 char ceiling.", ""]
    lines.extend(js_function("fitsBelow", js_statements("value", 28)))
    lines.extend(js_function("oversizedJs", js_statements("value", 46)))
    lines.extend(js_function("tailSmall", js_statements("value", 5)))
    return lines


def build_fixture_set() -> dict[str, list[str]]:
    """Return fixture id -> source lines for the full 18-file matrix."""
    fixtures: dict[str, list[str]] = {}
    for index in range(3):
        fixtures[f"py_simple_{index + 1:02d}"] = build_py_simple(index)
        fixtures[f"py_nested_{index + 1:02d}"] = build_py_nested(index)
        fixtures[f"py_longbody_{index + 1:02d}"] = build_py_longbody(index)
        fixtures[f"py_boundary_{index + 1:02d}"] = build_py_boundary(index)
    fixtures["js_simple_01"] = build_js_simple(1, typed=False)
    fixtures["js_nested_01"] = build_js_nested(1, typed=False)
    fixtures["js_longbody_01"] = build_js_longbody(1)
    fixtures["js_boundary_01"] = build_js_boundary(1)
    fixtures["js_simple_02"] = build_js_simple(2, typed=True)
    fixtures["js_nested_02"] = build_js_nested(2, typed=True)
    return fixtures


# ── Labelling ───────────────────────────────────────────────────────────


def label_python(source: str) -> list[dict]:
    """Label top-level Python definitions via ``ast.parse``."""
    tree = ast.parse(source)
    labels = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            labels.append(
                {"name": node.name, "start_line": node.lineno, "end_line": node.end_lineno}
            )
    return labels


def label_js(source: str) -> list[dict]:
    """Label column-0 JS/TS functions by matching the column-0 closing brace."""
    lines = source.splitlines()
    labels = []
    open_index = None
    name = ""
    for index, line in enumerate(lines):
        stripped = line.strip()
        if open_index is None:
            if line.startswith("function ") and stripped.endswith("{"):
                name = stripped.split("(")[0].removeprefix("function ").strip()
                open_index = index
        elif line == "}":
            labels.append({"name": name, "start_line": open_index + 1, "end_line": index + 1})
            open_index = None
    return labels


def line_char_offsets(source: str) -> list[int]:
    """Char offset of every line start plus one past-the-end sentinel."""
    offsets = [0]
    for line in source.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    return offsets


def format_python_fixtures() -> None:
    """Format the emitted .py fixtures with the locked ruff.

    The committed fixture bytes must be ruff-clean AND identical to the
    bytes the labels were derived from, so formatting happens between
    writing the sources and labelling them.  Deterministic: same ruff
    version, same input, same output.
    """
    import subprocess

    subprocess.run(  # noqa: S603 — ruff is the intended formatter binary
        [sys.executable, "-m", "ruff", "format", str(SRC_DIR)],
        check=True,
        capture_output=True,
        text=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    SRC_DIR.mkdir(parents=True, exist_ok=True)
    fixtures = build_fixture_set()

    language_by_ext = {".py": "python", ".js": "javascript", ".ts": "typescript"}
    complexity_by_prefix = {
        "py_simple": "simple",
        "py_nested": "nested",
        "py_longbody": "long-body",
        "py_boundary": "boundary",
        "js_simple": "simple",
        "js_nested": "nested",
        "js_longbody": "long-body",
        "js_boundary": "boundary",
    }

    for fixture_id, lines in sorted(fixtures.items()):
        source = "\n".join(lines).rstrip("\n") + "\n"
        if fixture_id.startswith("py_"):
            ext = ".py"
        elif fixture_id.endswith("02"):
            ext = ".ts"
        else:
            ext = ".js"
        (SRC_DIR / f"{fixture_id}{ext}").write_text(source, encoding="utf-8")
    format_python_fixtures()

    entries = []
    for fixture_id in sorted(fixtures):
        if fixture_id.startswith("py_"):
            ext = ".py"
        elif fixture_id.endswith("02"):
            ext = ".ts"
        else:
            ext = ".js"
        path = SRC_DIR / f"{fixture_id}{ext}"
        source = path.read_text(encoding="utf-8")

        language = language_by_ext[ext]
        labels = label_python(source) if language == "python" else label_js(source)
        offsets = line_char_offsets(source)
        for label in labels:
            span = offsets[label["end_line"]] - offsets[label["start_line"] - 1]
            label["span_chars"] = span
            label["fits_under_ceiling"] = span <= CODE_MAX_CHARS

        complexity = next(
            complexity_by_prefix[prefix]
            for prefix in sorted(complexity_by_prefix, key=len, reverse=True)
            if fixture_id.startswith(prefix)
        )
        if not labels:
            raise SystemExit(f"fixture {fixture_id} produced no labelled definitions")
        entries.append(
            {
                "id": fixture_id,
                "path": f"fixtures/src/{path.name}",
                "sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "language": language,
                "complexity": complexity,
                "source_chars": len(source),
                "source_lines": source.count("\n"),
                "definitions": labels,
            }
        )

    python_count = sum(1 for entry in entries if entry["language"] == "python")
    brace_count = len(entries) - python_count
    if python_count < 10 or brace_count < 5:
        raise SystemExit(
            f"fixture counts below protocol minimums: py={python_count} other={brace_count}"
        )

    manifest = {
        "label_protocol": (
            "python: ast.parse top-level def/class line spans (1-based inclusive); "
            "js/ts: column-0 function declarations matched to column-0 closing brace. "
            "Labels derived from source text only, written before any treatment run "
            "(protocol section 9)."
        ),
        "code_max_chars": CODE_MAX_CHARS,
        "fixture_count": len(entries),
        "languages": sorted({entry["language"] for entry in entries}),
        "fixtures": entries,
    }
    manifest_path = FIXTURES_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(entries)} fixtures and labels to {manifest_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
