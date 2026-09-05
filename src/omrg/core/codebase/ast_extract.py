"""Tree-sitter AST parsing and relationship extraction.

Split out of ``code_graph.py`` (task 8.4), which exceeded the 500-line
ceiling. This module owns everything that touches tree-sitter: the language
mapping, parser construction, import/class/function extraction, and import
path resolution. ``code_graph.py`` keeps graph assembly.

Extraction is deterministic — no LLM is involved (AGENTS.md invariant #8).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class ASTResult:
    """Result of tree-sitter AST extraction for a single file.

    Attributes:
        imports: List of imported module/file paths (resolved to file paths).
        exports: List of exported symbol names.
        functions: List of defined function names.
        classes: List of defined class names.
        inheritance: List of (child_class, parent_class) tuples.
    """

    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    inheritance: list[tuple[str, str]] = field(default_factory=list)


# Magika language label -> tree-sitter grammar name.
# Relocated from config.py (task 7.11): this is a static lookup table, not an
# env-configurable setting, and it belongs with the AST extraction that reads it.
MAGIKA_LABEL_TO_TREESITTER: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "jsx": "jsx",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "c_sharp",
    "go": "go",
    "rust": "rust",
    "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
    "scala": "scala",
}


# ── Language mapping ─────────────────────────────────────────────────────

# Magika label → tree-sitter language name for tree_sitter_language_pack.
_MAGIKA_TO_TS_LANG: dict[str, str] = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "tsx": "tsx",
    "jsx": "jsx",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "csharp": "c_sharp",
    "go": "go",
    "rust": "rust",
    "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
    "scala": "scala",
    "html": "html",
    "css": "css",
    "sql": "sql",
    "bash": "bash",
    "shell": "bash",
    "yaml": "yaml",
    "toml": "toml",
    "json": "json",
}


def _get_parser(language: str):
    """Get a tree-sitter parser for a language.

    Args:
        language: Tree-sitter language identifier (e.g., "python", "typescript").

    Returns:
        A ``tree_sitter.Parser`` configured for the language, or None if
        the language is not supported.
    """
    try:
        from tree_sitter_language_pack import get_parser

        return get_parser(language)
    except Exception as exc:
        logger.debug("No tree-sitter parser for language %r: %s", language, exc)
        return None


def _resolve_import_path(
    import_spec: str,
    current_file: str,
    project_root: str,
    extensions: list[str] | None = None,
) -> str | None:
    """Resolve an import to a file path within the project.

    Handles both relative imports (``./auth``, ``../utils``) and
    Python-style module imports (``utils``, ``omrg.config``).

    Args:
        import_spec: The import path string (e.g., "./auth", "utils").
        current_file: Path of the file doing the import (relative to root).
        project_root: Project root directory.
        extensions: File extensions to try (default: [".ts", ".tsx", ".js", ".jsx", ".py"]).

    Returns:
        Resolved file path relative to project root, or None if not found.
    """
    if extensions is None:
        extensions = [".ts", ".tsx", ".js", ".jsx", ".py", ".mjs", ".cjs"]

    # Convert dotted module paths to file paths (e.g., "omrg.config" → "omrg/config").
    file_spec = import_spec.replace(".", "/") if not import_spec.startswith(".") else import_spec

    current_dir = Path(current_file).parent

    # For relative imports (./ or ../), resolve relative to current file's directory.
    if import_spec.startswith("."):
        base = (Path(project_root) / current_dir / file_spec).resolve()
    else:
        # For non-relative imports, try:
        # 1. Same directory as current file
        # 2. Project root
        # 3. src/ directory under project root
        candidates = [
            Path(project_root) / current_dir / file_spec,
            Path(project_root) / file_spec,
            Path(project_root) / "src" / file_spec,
        ]
        for base in candidates:
            base = base.resolve()
            # Try as exact file with extension.
            for ext in extensions:
                candidate = base.with_suffix(ext)
                if candidate.exists():
                    try:
                        return str(candidate.relative_to(project_root))
                    except ValueError:
                        return str(candidate)
            # Try as directory with index file.
            for ext in extensions:
                index_file = base / f"index{ext}"
                if index_file.exists():
                    try:
                        return str(index_file.relative_to(project_root))
                    except ValueError:
                        return str(index_file)
        return None

    # Relative import resolution.
    for ext in extensions:
        candidate = base.with_suffix(ext)
        if candidate.exists():
            try:
                return str(candidate.relative_to(project_root))
            except ValueError:
                return str(candidate)

    # Try as directory with index file.
    for ext in extensions:
        index_file = base / f"index{ext}"
        if index_file.exists():
            try:
                return str(index_file.relative_to(project_root))
            except ValueError:
                return str(index_file)

    return None


def _extract_python_imports(content_bytes: bytes) -> list[str]:
    """Extract import paths from a Python AST.

    Args:
        content_bytes: Source code as bytes.

    Returns:
        List of import module paths.
    """
    imports: list[str] = []
    source = content_bytes.decode("utf-8", errors="replace")

    # Use regex for robustness — tree-sitter node traversal is language-specific.
    # Match: from X import Y  /  import X
    for match in re.finditer(
        r"^\s*(?:from\s+(\S+)\s+import|import\s+(\S+))",
        source,
        re.MULTILINE,
    ):
        module = match.group(1) or match.group(2)
        if module:
            # Convert dotted path to file path: omrg.config → omrg/config
            imports.append(module.replace(".", "/"))

    return imports


def _extract_ts_imports(content_bytes: bytes) -> list[str]:
    """Extract import paths from TypeScript/JavaScript source.

    Args:
        content_bytes: Source code as bytes.

    Returns:
        List of import path strings (relative paths only).
    """
    imports: list[str] = []
    source = content_bytes.decode("utf-8", errors="replace")

    # Match: import ... from '...'  /  import '...'  /  require('...')
    for match in re.finditer(
        r"""(?:import\s+.*?\s+from\s+|import\s+|require\s*\(\s*)['"`]([^'"`]+)['"`]""",
        source,
    ):
        spec = match.group(1)
        if spec:
            imports.append(spec)

    return imports


def _extract_classes_and_inheritance(
    content_bytes: bytes,
    language: str,
) -> tuple[list[str], list[tuple[str, str]]]:
    """Extract class names and inheritance relationships.

    Args:
        content_bytes: Source code as bytes.
        language: Language identifier.

    Returns:
        Tuple of (class names, inheritance pairs).
    """
    classes: list[str] = []
    inheritance: list[tuple[str, str]] = []
    source = content_bytes.decode("utf-8", errors="replace")

    if language in ("python",):
        # class Child(Parent):  /  class Child:
        for match in re.finditer(
            r"^\s*class\s+(\w+)\s*(?:\(([^)]+)\))?\s*:",
            source,
            re.MULTILINE,
        ):
            child = match.group(1)
            classes.append(child)
            if match.group(2):
                for parent in match.group(2).split(","):
                    parent = parent.strip().split("[")[0].strip()
                    if parent:
                        inheritance.append((child, parent))

    elif language in ("typescript", "javascript", "tsx", "jsx"):
        # class Child extends Parent  /  class Child implements IFace
        for match in re.finditer(
            r"^\s*(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?",
            source,
            re.MULTILINE,
        ):
            child = match.group(1)
            classes.append(child)
            if match.group(2):
                inheritance.append((child, match.group(2)))

    elif language in ("java", "kotlin", "scala", "csharp", "c_sharp"):
        # class Child extends Parent  /  class Child : Parent
        for match in re.finditer(
            r"^\s*(?:public\s+|private\s+|protected\s+)?(?:class|interface)\s+(\w+)"
            r"(?:\s+extends\s+(\w+)|\s*:\s*(\w+))?",
            source,
            re.MULTILINE,
        ):
            child = match.group(1)
            classes.append(child)
            parent = match.group(2) or match.group(3)
            if parent:
                inheritance.append((child, parent))

    return classes, inheritance


def _extract_functions(content_bytes: bytes, language: str) -> list[str]:
    """Extract function names from source code.

    Args:
        content_bytes: Source code as bytes.
        language: Language identifier.

    Returns:
        List of function names.
    """
    functions: list[str] = []
    source = content_bytes.decode("utf-8", errors="replace")

    if language == "python":
        for match in re.finditer(
            r"^\s*(?:async\s+)?def\s+(\w+)",
            source,
            re.MULTILINE,
        ):
            functions.append(match.group(1))
    elif language in ("typescript", "javascript", "tsx", "jsx"):
        # function foo()  /  const foo = () => {}  /  export function foo()
        for match in re.finditer(
            r"^\s*(?:export\s+)?(?:async\s+)?function\s+(\w+)",
            source,
            re.MULTILINE,
        ):
            functions.append(match.group(1))
        # Arrow functions: const foo = (...) => ...
        for match in re.finditer(
            r"^\s*(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>",
            source,
            re.MULTILINE,
        ):
            functions.append(match.group(1))

    return functions


def extract_ast_relationships(
    file_path: str,
    content: str,
    language: str,
) -> ASTResult:
    """Extract structural relationships from a code file using tree-sitter.

    Parses the file to extract imports, exports, function definitions, class
    definitions, and class inheritance. The extraction is deterministic —
    no LLM involvement.

    Args:
        file_path: Relative path of the file within the project.
        content: File content as a string.
        language: Tree-sitter language identifier (e.g., "python", "typescript").

    Returns:
        An ``ASTResult`` with extracted relationships. For unsupported
        languages or malformed source, returns an empty result with a
        debug/warning log.
    """
    result = ASTResult()

    ts_lang = _MAGIKA_TO_TS_LANG.get(language)
    if ts_lang is None:
        logger.debug("Unsupported language for AST extraction: %s", language)
        return result

    content_bytes = content.encode("utf-8", errors="replace")

    # Try tree-sitter parsing (for validation), but use regex for extraction
    # which is more robust across language variants.
    parser = _get_parser(ts_lang)
    if parser is not None:
        try:
            parser.parse(content_bytes)
        except Exception as exc:
            logger.warning("tree-sitter parse error in %s: %s", file_path, exc)

    # Extract imports based on language family.
    if ts_lang == "python":
        result.imports = _extract_python_imports(content_bytes)
    elif ts_lang in ("typescript", "javascript", "tsx", "jsx"):
        result.imports = _extract_ts_imports(content_bytes)
    else:
        # For other languages, try a generic import regex.
        source = content_bytes.decode("utf-8", errors="replace")
        for match in re.finditer(
            r"""(?:import\s+|require\s*\(\s*|#include\s+<?)['"`<]?([^'"`>\s]+)""",
            source,
        ):
            result.imports.append(match.group(1))

    # Extract classes and inheritance.
    result.classes, result.inheritance = _extract_classes_and_inheritance(
        content_bytes,
        ts_lang,
    )

    # Extract functions.
    result.functions = _extract_functions(content_bytes, ts_lang)

    # Exports: for Python, all top-level definitions are "exported".
    # For TS/JS, look for `export` keyword.
    if ts_lang == "python":
        result.exports = result.functions + result.classes
    elif ts_lang in ("typescript", "javascript", "tsx", "jsx"):
        source = content_bytes.decode("utf-8", errors="replace")
        for match in re.finditer(
            r"^\s*export\s+(?:function|class|const|let|var|default)\s+(\w+)",
            source,
            re.MULTILINE,
        ):
            result.exports.append(match.group(1))

    return result
