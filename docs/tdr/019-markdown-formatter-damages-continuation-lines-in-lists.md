# TDR-019: Markdown formatter damages continuation lines in list items

**Date:** 2026-09-01
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Tags:** documentation | markdown | formatter | review

## Context

The `split-mcp-transport-by-tool` change ran `ruff format` across the
documentation tree (793 files formatted). The formatter aligned tables,
normalised emphasis markers (`*text*` → `_text_`), and rewrapped list
continuation lines. Two of those rewraps silently changed the meaning of a
hash formula in `docs/guides/architecture.md`:

1. The `chunk_id` continuation line lost its two-space indentation, making
   `decimal index + NUL + text hash)` read as a top-level paragraph
   fragment instead of a continuation of the `SHA-256(...)` call.
2. The vector-row formula's `+ chunk_id` was rewritten as a nested
   `- chunk_id` list item. The `+` became a `-`, and the indentation
   increased from two spaces to four, turning an arithmetic operand into
   a new bullet point.

A separate review pass also found that ADR-036 §4 claimed "every MCP tool
handler returns an error dict" when list handlers return `list[dict]` and
`get_codebase_map` returns `str`. That was a prose drift, not formatter
damage, but it shared the same root cause: documentation was updated by
automated tooling without a semantic review of the diff.

### Root Cause Analysis

The formatter treats markdown list items as structural elements and
rewraps continuation lines according to its own indentation rules. It does
not understand that a `+` at the start of a continuation line is an
arithmetic operator in a formula, not a bullet marker. When the
continuation line's leading content begins with `+ <backtick>chunk_id`,
the formatter interprets it as a nested list item and converts it to
`- <backtick>chunk_id` with deeper indentation.

The damage is silent because:

1. The file still renders as valid markdown.
2. The diff looks like a cosmetic reformat (indentation change, `+` → `-`).
3. No test validates the semantic content of documentation prose.

## Decision

Two rules for documentation changes that run a formatter:

1. **Review every formatter diff for list-item continuation lines.** A
   continuation line that begins with `+`, `-`, or `*` followed by a
   space is at risk: the formatter may reinterpret it as a bullet. Pay
   attention to indentation changes — a lost or gained two-space indent
   changes whether a line is a continuation or a new item.

2. **Prefer code blocks for multi-line formulas.** Wrap hash formulas,
   arithmetic expressions, and any line where a leading `+` or `-` is an
   operator (not a bullet) in a fenced code block. The formatter does not
   rewrap code block contents.

```markdown
<!-- Before: at risk -->
- the vector row ID = SHA-256 over `source_id` + NUL + `source_attempt` + NUL
  + `chunk_id`. It stays attempt-specific ...

<!-- After: safe -->
- the vector row ID =
  `SHA-256(source_id + NUL + source_attempt + NUL + chunk_id)`.
  It stays attempt-specific ...
```

For the immediate fix, the two damaged lines in
`docs/guides/architecture.md` were restored by hand to their pre-formatter
content. The formula was not moved into a code block because the
surrounding list structure is part of the document's navigability.

## Consequences

### Positive

- The hash formula is correct again. A future implementer reading the
  architecture guide will not mistake `chunk_id` for a separate bullet.
- The rule is general: it applies to any documentation file that mixes
  prose lists with inline formulas.

### Negative

- Hand-restoration is not durable. A future `ruff format` run will
  re-damage the same lines unless they are protected (code block) or the
  formatter is configured to skip them.

### Neutral

- The ADR-036 prose drift (error dict claim) was corrected in the same
  pass but is a separate class of issue — it was human error, not
  formatter damage.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| Move the formula into a fenced code block | The surrounding list structure is part of the document's navigability; a code block breaks the reading flow. |
| Configure the formatter to skip `docs/guides/` | The formatter's table alignment and emphasis normalisation are valuable across the whole tree. |
| Add a test that validates documentation prose | Prose content is not machine-checkable without an LLM; a regex check would be brittle. |

## How to Recognise / Handle This Again

1. **Symptom.** A documentation diff after a formatter run shows a
   continuation line losing indentation, or a `+` at the start of a line
   becoming a `-`. The rendered markdown still looks valid.
2. **Diagnose.** After any `ruff format` or `prettier` run on
   documentation, grep the diff for lines starting with `+  -` or
   `-  +` inside list contexts. Check that no continuation line lost its
   leading whitespace.
3. **Recover.** Restore the indentation and operator by hand. If the
   formula is likely to be re-damaged, wrap it in a fenced code block.

## Revisit Triggers

- The formatter is upgraded or its markdown rules change.
- A new documentation file mixes prose lists with inline formulas.
- A pre-commit hook is added that runs the formatter on documentation.

## References

- Change: `openspec/changes/split-mcp-transport-by-tool/`
- Affected file: `docs/guides/architecture.md:180-185`
- Related ADR: `docs/adr/036-phase-5-refactor-transport-separation.md` §4
  (prose drift corrected in the same review pass)
- Review findings: 2 Medium (ADR-036 prose drift, architecture.md formula
  damage), 2 Low (TDR-017 stale path, codebase.py import scope)
