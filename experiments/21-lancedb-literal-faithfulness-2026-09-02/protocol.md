# Experiment 21: LanceDB Engine Literal-Faithfulness Inventory

**ID**: `21-lancedb-literal-faithfulness-2026-09-02`
**Date**: 2026-09-02
**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent (for automation)
**Status**: PLANNED

---

## Hypothesis / Purpose

On lancedb 0.37.1, the engine's literal builder (`lancedb.expr.lit(...).to_sql()`)
mis-serialises exactly the two known value classes — apostrophe runs (collapsing
`''` to one apostrophe) and backslash directly before an apostrophe (emitting `\'`
undoubled) — and no others. The translator `translate_where` refuses those two
classes while accepting every ordinary value without false refusal.

## Background

Security finding F1 of `add-grounded-answer-synthesis-3` classified the LanceDB
filter adapter as CRITICAL because the filter sink is SQL text assembled from
client input. The adapter serialises every value through the engine's own
literal builder and verifies each fragment fail-closed against the original
value. This experiment provides the reproducible engine-behaviour inventory the
decision record (ADR-058) cites.

- Related ADR: ADR-058 (LanceDB filter policy exception)
- Related ADR: ADR-046 (LanceDB vector store backend)
- Security finding: `openspec/changes/archive/2026-09-03-add-grounded-answer-synthesis-3/security-review.md` F1

## Variables

| Type                         | Variable                          | Values                                      |
| ---------------------------- | --------------------------------- | ------------------------------------------- |
| Independent (what we change) | Value class handed to `lit()`     | strings, numerics, dates, datetimes, bytes  |
| Dependent (what we measure)  | Engine output faithfulness        | faithful / unfaithful / refused             |
| Controlled (held constant)   | lancedb version                   | 0.37.1 (locked)                             |

## Environment & Prerequisites

| Requirement   | Version / Value                        |
| ------------- | -------------------------------------- |
| Python        | 3.12                                   |
| lancedb       | 0.37.1 (locked in `pyproject.toml`)    |
| Hardware      | Apple Silicon Mac                      |
| Key config    | None — deterministic, offline          |

```bash
# Verify prerequisites
uv sync
uv run python -c "import lancedb; print(lancedb.__version__)"
```

## Corpus

No external corpus. The probe generates value classes programmatically:

| Value class          | Examples                                    |
| -------------------- | ------------------------------------------- |
| Apostrophe runs      | `''`, `'''`, `a''b`, `''''`                 |
| Backslash-apostrophe | `\\'`, `a\\'b`                              |
| Double quotes        | `a"b`, `"plain"`                            |
| Unicode              | `café`, `中文`, `日本語`                    |
| Control characters   | `\x00`, `\x01\x02`, `\n`, `\t`             |
| NUL                  | `\x00`                                      |
| Newlines             | `a\nb`, `a\r\nb`                            |
| Long strings         | 1000-char, 5000-char                        |
| Numeric edge cases   | 0, -1, 3.14, float('inf'), float('nan')     |
| Datetime edge cases  | epoch, winter, summer, microsecond precision|
| Bytes                | empty, hello, binary                        |
| Ordinary values      | file paths, ISO dates, tags, numerics       |

## Method (How to Reproduce)

```bash
# Step 1: Run the probe (deterministic, offline, no model calls)
uv run python experiments/21-lancedb-literal-faithfulness-2026-09-02/probe.py

# Step 2: Review results
cat experiments/21-lancedb-literal-faithfulness-2026-09-02/results.md
cat experiments/21-lancedb-literal-faithfulness-2026-09-02/eval_results.json
```

The probe performs three checks:

1. **Hostile corpus sweep**: serialises every value class through
   `lancedb.expr.lit(...).to_sql()` and records the raw output.
2. **Ordinary-value corpus**: asserts that a few hundred realistic metadata
   values pass `translate_where` with zero false refusals.
3. **Live-table check**: creates a real LanceDB table and verifies that
   refused values raise before any SQL reaches the engine, and accepted
   values' equality filters match only their own row.

## Success Criteria

| Check                                                        | Pass condition                                      |
| ----------------------------------------------------------- | --------------------------------------------------- |
| Hostile corpus inventory complete                           | Every value class has a recorded engine output       |
| Known mis-serialisation classes refused                    | Apostrophe runs and backslash-apostrophe are refused |
| No false refusals on ordinary values                       | Zero refusals across the ordinary-value corpus       |
| Live-table: refused values never reach the engine          | Every refused value raises before `.where()`         |
| Live-table: accepted values match only their own row      | Each accepted value's equality filter returns 1 row  |
| No additional mis-serialisation classes discovered         | Only the two known classes are unfaithful            |

## Results

See `results.md`.

## Conclusion / Decision

Recorded in ADR-058.

## Artefacts

| File                | Description                                       |
| ------------------- | ------------------------------------------------- |
| `protocol.md`       | This file                                          |
| `probe.py`          | The probe script                                   |
| `results.md`        | Full results with the inventory table              |
| `eval_results.json` | Raw machine-readable data                          |
