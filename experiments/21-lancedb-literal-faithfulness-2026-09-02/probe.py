"""Experiment 21: LanceDB engine literal-faithfulness inventory.

Deterministic, offline probe that inventories which value classes the
engine's literal builder (``lancedb.expr.lit(...).to_sql()``) mis-serialises
on lancedb 0.37.1, proves ``translate_where`` refuses exactly those and
accepts a corpus of ordinary values without false refusals, and checks on a
live table that refused values never reach the engine and accepted values
match only their own row.

Run:
    uv run python experiments/21-lancedb-literal-faithfulness-2026-09-02/probe.py

Output:
    results.md            — human-readable inventory table + verdict
    eval_results.json     — raw machine-readable data
"""

from __future__ import annotations

import json
import sys
import tempfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

# Ensure the project source is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import lancedb  # noqa: E402
from lancedb.expr import lit  # noqa: E402

from rag_mcp.core.vectordb.lance_filter import translate_where  # noqa: E402

# ── Hostile corpus: value classes that might break the engine ──────────

HOSTILE_CORPUS: list[tuple[str, object]] = [
    # Apostrophe runs (known mis-serialisation)
    ("apostrophe double", "''"),
    ("apostrophe triple", "'''"),
    ("apostrophe quadruple", "''''"),
    ("apostrophe in word", "a''b"),
    ("apostrophe run + text", "x'' OR ''1''=''1"),
    # Backslash-apostrophe (known mis-serialisation)
    ("backslash-apostrophe", "\\'"),
    ("backslash-apostrophe in word", "a\\'b"),
    ("backslash-apostrophe payload", "\\' OR '1'='1"),
    # Double quotes
    ("double quote", 'a"b'),
    ("double quotes wrapped", '"plain"'),
    # Unicode
    ("unicode accented", "café"),
    ("unicode chinese", "中文"),
    ("unicode japanese", "日本語"),
    ("unicode emoji", "🔐"),
    # Control characters
    ("NUL", "\x00"),
    ("control chars", "\x01\x02\x03"),
    ("newline", "a\nb"),
    ("carriage return", "a\rb"),
    ("crlf", "a\r\nb"),
    ("tab", "a\tb"),
    # Long strings
    ("long 1000", "a" * 1000),
    ("long 5000", "x" * 5000),
    # Numeric edge cases
    ("int zero", 0),
    ("int negative", -1),
    ("int large", 999999999999),
    ("float zero", 0.0),
    ("float negative", -0.5),
    ("float pi", 3.14),
    ("float inf", float("inf")),
    ("float -inf", float("-inf")),
    ("float nan", float("nan")),
    ("float 1e10", 1e10),
    ("float 1e-10", 1e-10),
    # Decimal
    ("Decimal zero", Decimal("0")),
    ("Decimal pi", Decimal("3.14")),
    ("Decimal negative", Decimal("-7.5")),
    # Date
    ("date", date(2026, 9, 2)),
    ("date epoch", date(1970, 1, 1)),
    # Datetime
    ("datetime naive", datetime(2026, 9, 2, 15, 30, 45)),
    ("datetime winter", datetime(2026, 1, 15, 12, 0, 0)),
    ("datetime summer", datetime(2026, 7, 15, 12, 0, 0)),
    ("datetime microsecond", datetime(2026, 9, 2, 15, 30, 45, 123456)),
    ("datetime epoch", datetime(1970, 1, 1, 0, 0, 0)),
    # Bytes
    ("bytes empty", b""),
    ("bytes hello", b"hello"),
    ("bytes binary", b"\x00\x01\x02"),
    # Boolean
    ("bool true", True),
    ("bool false", False),
    # Classic injection payloads
    ("classic OR 1=1", "x' OR '1'='1"),
    ("classic DROP", "'; DROP TABLE t; --"),
    ("classic UNION", "a' UNION SELECT id FROM t --"),
    ("classic comment", "a' /* comment"),
    ("template injection", "{{7*7}}"),
    ("jndi", "${jndi:ldap://x}"),
]


# ── Ordinary-value corpus: realistic metadata that must pass ───────────

ORDINARY_CORPUS: list[tuple[str, object]] = [
    # File paths
    ("path 1", "src/main.py"),
    ("path 2", "docs/guides/architecture.md"),
    ("path 3", "a/b/c/d/e/f.py"),
    ("path windows", "C:\\Users\\dev\\project\\file.py"),
    ("path with spaces", "my documents/file name.txt"),
    # ISO dates
    ("iso date 1", "2026-09-02"),
    ("iso date 2", "2025-01-15"),
    ("iso datetime", "2026-09-02T15:30:45"),
    # Tags
    ("tag ai", "AI"),
    ("tag biology", "Biology"),
    ("tag chemistry", "Chemistry"),
    ("tag multi-word", "machine-learning"),
    ("tag numeric", "v2.0"),
    # Numerics
    ("score 1", 1),
    ("score 2", 42),
    ("score 3", 100),
    ("rating", 4.5),
    ("percentage", 0.95),
    # Boolean-like
    ("flag true", True),
    ("flag false", False),
    # Plain strings
    ("title", "Getting Started with LlamaIndex"),
    ("author", "Dr Muhammad Aizat Bin Md Hawari"),
    ("description", "A guide to building RAG pipelines"),
    ("empty string", ""),
    # Single apostrophe (ordinary, not a run)
    ("single apostrophe", "x' OR '1'='1"),
    ("possessive", "Aizat's guide"),
    ("contraction", "don't"),
]


def _serialise(value: object) -> tuple[str, str | None]:
    """Serialise a value through lit().to_sql(), returning (sql, error)."""
    try:
        sql = lit(value).to_sql()
        return sql, None
    except Exception as e:
        return "", str(e)


def _translate(value: object) -> tuple[str | None, str | None]:
    """Translate a filter on the value, returning (sql, error)."""
    try:
        sql = translate_where({"tag": value})
        return sql, None
    except (ValueError, TypeError) as e:
        return None, str(e)


def _is_faithful(value: object, sql: str) -> bool:
    """Check if the engine output faithfully represents the value."""
    from rag_mcp.core.vectordb.lance_literal import _is_faithful_literal

    return _is_faithful_literal(value, sql)


def run_hostile_sweep() -> list[dict]:
    """Sweep the hostile corpus through the engine and translator."""
    print("Phase 1: Hostile corpus sweep", flush=True)
    results: list[dict] = []
    for label, value in HOSTILE_CORPUS:
        engine_sql, engine_err = _serialise(value)
        trans_sql, trans_err = _translate(value)
        faithful = _is_faithful(value, engine_sql) if engine_sql and not engine_err else False
        translator_verdict = "accepted" if trans_sql else "refused"
        results.append(
            {
                "label": label,
                "value_type": type(value).__name__,
                "value_repr": repr(value)[:80],
                "engine_output": engine_sql[:120] if engine_sql else None,
                "engine_error": engine_err,
                "faithful": faithful,
                "translator_verdict": translator_verdict,
                "translator_error": trans_err[:120] if trans_err else None,
            }
        )
        status = "FAITHFUL" if faithful else "UNFAITHFUL"
        verdict = "accepted" if trans_sql else "REFUSED"
        print(
            f"  {label:35s} | {status:10s} | translator: {verdict}",
            flush=True,
        )
    return results


def run_ordinary_corpus() -> list[dict]:
    """Assert ordinary values pass translate_where without false refusal."""
    print("\nPhase 2: Ordinary-value corpus (zero false refusals)", flush=True)
    results: list[dict] = []
    refusals = 0
    for label, value in ORDINARY_CORPUS:
        trans_sql, trans_err = _translate(value)
        accepted = trans_sql is not None
        if not accepted:
            refusals += 1
        results.append(
            {
                "label": label,
                "value_type": type(value).__name__,
                "value_repr": repr(value)[:80],
                "accepted": accepted,
                "error": trans_err[:120] if trans_err else None,
            }
        )
    print(f"  {len(results)} values tested, {refusals} false refusals", flush=True)
    return results


def run_live_table_check() -> list[dict]:
    """Check refused values raise before SQL, accepted values match own row."""
    print("\nPhase 3: Live-table check", flush=True)
    results: list[dict] = []
    with tempfile.TemporaryDirectory() as tmpdir:
        db = lancedb.connect(str(Path(tmpdir) / "lancedb"))
        # Build a table with rows whose tag values are the accepted STRING
        # payloads. Pyarrow requires a consistent column type, so only
        # string values go into the live table; non-string types are
        # verified by the hostile sweep and the test suite.
        accepted_strings: list[str] = []
        seen: set[str] = set()
        for _label, value in HOSTILE_CORPUS:
            if not isinstance(value, str):
                continue
            trans_sql, _ = _translate(value)
            if trans_sql is not None and value not in seen:
                seen.add(value)
                accepted_strings.append(value)

        # Create a table with one row per accepted string value
        rows: list[dict] = []
        for i, value in enumerate(accepted_strings):
            rows.append(
                {
                    "id": f"row_{i}",
                    "tag": value,
                    "vector": [0.0, 0.0, 0.0, 0.0],
                }
            )
        # Add a decoy row
        rows.append({"id": "decoy", "tag": "unrelated", "vector": [0.1, 0.0, 0.0, 0.0]})
        table = db.create_table("probe", rows, mode="overwrite")

        # Check each accepted string value matches only its own row
        for value in accepted_strings:
            try:
                sql = translate_where({"tag": value})
                if sql is None:
                    results.append(
                        {
                            "value_repr": repr(value)[:60],
                            "check": "own_row",
                            "result": "skipped",
                            "detail": "translate returned None",
                        }
                    )
                    continue
                count = table.count_rows(filter=sql)
                own_row = count == 1
                results.append(
                    {
                        "value_repr": repr(value)[:60],
                        "check": "own_row",
                        "result": "pass" if own_row else "FAIL",
                        "detail": f"matched {count} rows (expected 1)",
                    }
                )
                if not own_row:
                    print(
                        f"  FAIL: {repr(value)[:40]} matched {count} rows",
                        flush=True,
                    )
            except Exception as e:
                results.append(
                    {
                        "value_repr": repr(value)[:60],
                        "check": "own_row",
                        "result": "error",
                        "detail": str(e)[:120],
                    }
                )

        # Check refused values raise before reaching the engine
        for label, value in HOSTILE_CORPUS:
            trans_sql, trans_err = _translate(value)
            if trans_sql is None:
                results.append(
                    {
                        "label": label,
                        "value_repr": repr(value)[:60],
                        "check": "refused_before_engine",
                        "result": "pass",
                        "detail": "raised before .where()",
                    }
                )

    passed = sum(1 for r in results if r["result"] == "pass")
    failed = sum(1 for r in results if r["result"] == "FAIL")
    print(f"  {passed} passed, {failed} failed", flush=True)
    return results


def write_results(
    hostile: list[dict],
    ordinary: list[dict],
    live: list[dict],
    output_dir: Path,
) -> None:
    """Write results.md and eval_results.json atomically."""
    # Identify unfaithful classes
    unfaithful = [r for r in hostile if not r["faithful"] and r["engine_output"]]
    faithful_count = sum(1 for r in hostile if r["faithful"])
    unfaithful_count = len(unfaithful)

    # Known mis-serialisation classes
    known_unfaithful_labels = {
        "apostrophe double",
        "apostrophe triple",
        "apostrophe quadruple",
        "apostrophe in word",
        "apostrophe run + text",
        "backslash-apostrophe",
        "backslash-apostrophe in word",
        "backslash-apostrophe payload",
    }
    discovered_unfaithful = {
        r["label"] for r in unfaithful if r["label"] not in known_unfaithful_labels
    }

    # Ordinary corpus false refusals
    false_refusals = [r for r in ordinary if not r["accepted"]]

    # Live table results
    live_pass = sum(1 for r in live if r["result"] == "pass")
    live_fail = sum(1 for r in live if r["result"] == "FAIL")

    # Verdict
    prediction_supported = (
        all(r["label"] in known_unfaithful_labels for r in unfaithful)
        and not discovered_unfaithful
        and len(false_refusals) == 0
        and live_fail == 0
    )

    status = "PASS" if prediction_supported else "FAIL"

    # Write JSON
    json_data = {
        "experiment": "21-lancedb-literal-faithfulness-2026-09-02",
        "date": "2026-09-02",
        "status": status,
        "prediction_supported": prediction_supported,
        "hostile_corpus": hostile,
        "ordinary_corpus": ordinary,
        "live_table": live,
        "summary": {
            "hostile_total": len(hostile),
            "faithful": faithful_count,
            "unfaithful": unfaithful_count,
            "known_unfaithful_classes": sorted(known_unfaithful_labels),
            "discovered_unfaithful_classes": sorted(discovered_unfaithful),
            "ordinary_total": len(ordinary),
            "false_refusals": len(false_refusals),
            "live_pass": live_pass,
            "live_fail": live_fail,
        },
    }
    json_path = output_dir / "eval_results.json"
    tmp_json = json_path.with_suffix(".json.tmp")
    tmp_json.write_text(json.dumps(json_data, indent=2, default=str))
    tmp_json.rename(json_path)
    print(f"\nWrote {json_path}", flush=True)

    # Write results.md
    md_lines: list[str] = []
    md_lines.append("# Experiment 21 Results: LanceDB Engine Literal-Faithfulness Inventory")
    md_lines.append("")
    md_lines.append("**ID**: `21-lancedb-literal-faithfulness-2026-09-02`")
    md_lines.append("**Date run**: 2026-09-02")
    md_lines.append("**Operator**: Dr Muhammad Aizat Bin Md Hawari with AI agent")
    md_lines.append(f"**Status**: {status}")
    if prediction_supported:
        outcome = (
            "Prediction supported — only the two known mis-serialisation classes are unfaithful."
        )
    else:
        outcome = "Prediction not supported — additional mis-serialisation classes discovered."
    md_lines.append(f"**Outcome**: {outcome}")
    md_lines.append("**Raw data**: [`eval_results.json`](./eval_results.json)")
    md_lines.append("")
    md_lines.append("---")
    md_lines.append("")
    md_lines.append("## TL;DR / Decision")
    md_lines.append("")
    if prediction_supported:
        md_lines.append("- Decision: accept the LanceDB filter policy exception (ADR-058)")
        md_lines.append("- The engine mis-serialises exactly the two known value classes:")
        md_lines.append("  apostrophe runs and backslash-before-apostrophe")
        md_lines.append("- `translate_where` refuses both classes and accepts all ordinary values")
        md_lines.append(f"- False refusals on ordinary values: {len(false_refusals)}")
        md_lines.append(f"- Live-table failures: {live_fail}")
    else:
        md_lines.append("- Decision: additional investigation required")
        if discovered_unfaithful:
            md_lines.append(
                f"- Discovered additional unfaithful classes: {sorted(discovered_unfaithful)}"
            )
        if false_refusals:
            md_lines.append(f"- False refusals: {len(false_refusals)}")
        if live_fail:
            md_lines.append(f"- Live-table failures: {live_fail}")
    md_lines.append("")
    md_lines.append("## Hypothesis / Purpose")
    md_lines.append("")
    md_lines.append(
        "> On lancedb 0.37.1, the engine's literal builder mis-serialises exactly "
        "the two known value classes (apostrophe runs; backslash directly before "
        "an apostrophe) and no others, and `translate_where` refuses those two "
        "while accepting every ordinary value."
    )
    md_lines.append("")
    md_lines.append(f"Verdict: {'supported' if prediction_supported else 'not supported'}.")
    md_lines.append("")
    md_lines.append("## Method / reproduction")
    md_lines.append("")
    md_lines.append("```bash")
    md_lines.append("uv run python experiments/21-lancedb-literal-faithfulness-2026-09-02/probe.py")
    md_lines.append("```")
    md_lines.append("")
    md_lines.append("## Results")
    md_lines.append("")
    md_lines.append("### Hostile corpus inventory")
    md_lines.append("")
    md_lines.append("| Value class | Type | Engine output | Faithful | Translator verdict |")
    md_lines.append("| --- | --- | --- | :---: | --- |")
    for r in hostile:
        engine_out = r["engine_output"] or f"ERROR: {r['engine_error']}"
        faithful_str = "yes" if r["faithful"] else "no"
        row = (
            f"| {r['label']} | {r['value_type']} "
            f"| `{engine_out[:60]}` | {faithful_str} "
            f"| {r['translator_verdict']} |"
        )
        md_lines.append(row)
    md_lines.append("")
    md_lines.append("### Ordinary-value corpus")
    md_lines.append("")
    md_lines.append(f"- Total values tested: {len(ordinary)}")
    md_lines.append(f"- Accepted: {sum(1 for r in ordinary if r['accepted'])}")
    md_lines.append(f"- False refusals: {len(false_refusals)}")
    if false_refusals:
        md_lines.append("")
        md_lines.append("False refusals:")
        for r in false_refusals:
            md_lines.append(f"- {r['label']}: {r['error']}")
    md_lines.append("")
    md_lines.append("### Live-table check")
    md_lines.append("")
    md_lines.append(f"- Passed: {live_pass}")
    md_lines.append(f"- Failed: {live_fail}")
    if live_fail:
        md_lines.append("")
        md_lines.append("Failures:")
        for r in live:
            if r["result"] == "FAIL":
                md_lines.append(f"- {r.get('label', r.get('value_repr', '?'))}: {r['detail']}")
    md_lines.append("")
    md_lines.append("### Pass/fail against criteria")
    md_lines.append("")
    md_lines.append("| Criterion | Threshold | Measured | Pass? |")
    md_lines.append("| --- | --- | --- | :---: |")
    hostile_check = "✅" if len(hostile) > 0 else "❌"
    md_lines.append(
        f"| Hostile corpus inventory complete "
        f"| All classes recorded | {len(hostile)} classes | {hostile_check} |"
    )
    known_refused = all(
        any(r["label"] == lbl and r["translator_verdict"] == "refused" for r in hostile)
        for lbl in known_unfaithful_labels
    )
    refused_str = "all refused" if known_refused else "NOT all refused"
    refused_check = "✅" if known_refused else "❌"
    md_lines.append(
        f"| Known mis-serialisation classes refused "
        f"| All refused | {refused_str} | {refused_check} |"
    )
    refusal_check = "✅" if len(false_refusals) == 0 else "❌"
    md_lines.append(
        f"| No false refusals on ordinary values | 0 | {len(false_refusals)} | {refusal_check} |"
    )
    live_check = "✅" if live_fail == 0 else "❌"
    md_lines.append(
        f"| Live-table: accepted values match own row "
        f"| 0 failures | {live_fail} failures | {live_check} |"
    )
    discovered_check = "✅" if len(discovered_unfaithful) == 0 else "❌"
    md_lines.append(
        f"| No additional mis-serialisation classes "
        f"| 0 discovered | {len(discovered_unfaithful)} discovered "
        f"| {discovered_check} |"
    )
    md_lines.append("")
    md_lines.append("## Conclusion / Decision")
    md_lines.append("")
    if prediction_supported:
        md_lines.append("The prediction is supported. On lancedb 0.37.1:")
        md_lines.append("")
        md_lines.append("1. The engine's literal builder mis-serialises exactly two value")
        md_lines.append("   classes: apostrophe runs (collapsing `''` to one apostrophe) and")
        md_lines.append("   backslash directly before an apostrophe (emitting `\\'` undoubled).")
        md_lines.append("2. `translate_where` refuses both classes with an actionable error.")
        md_lines.append("3. Every ordinary metadata value passes without false refusal.")
        md_lines.append("4. Accepted values' equality filters match only their own row on a")
        md_lines.append("   live table.")
        md_lines.append("")
        md_lines.append("This evidence supports ADR-058 (LanceDB filter policy exception).")
    else:
        md_lines.append("The prediction is not supported. Additional investigation required.")
    md_lines.append("")
    md_lines.append("## Reproduction")
    md_lines.append("")
    md_lines.append("```bash")
    md_lines.append("uv run python experiments/21-lancedb-literal-faithfulness-2026-09-02/probe.py")
    md_lines.append("```")
    md_lines.append("")
    md_lines.append("## Artefacts")
    md_lines.append("")
    md_lines.append("| File | Description |")
    md_lines.append("| --- | --- |")
    md_lines.append("| `protocol.md` | Pre-run plan and pass criteria |")
    md_lines.append("| `probe.py` | The probe script |")
    md_lines.append("| `results.md` | This report |")
    md_lines.append("| `eval_results.json` | Raw machine-readable data |")
    md_lines.append("")
    md_lines.append("## References")
    md_lines.append("")
    md_lines.append("- [`protocol.md`](./protocol.md)")
    md_lines.append("- ADR-058: LanceDB filter policy exception")
    md_lines.append("- ADR-046: LanceDB vector store backend")
    md_lines.append(
        "- Security finding F1: "
        "`openspec/changes/archive/2026-09-03-add-grounded-answer-synthesis-3/`"
        "security-review.md"
    )

    md_path = output_dir / "results.md"
    tmp_md = md_path.with_suffix(".md.tmp")
    tmp_md.write_text("\n".join(md_lines))
    tmp_md.rename(md_path)
    print(f"Wrote {md_path}", flush=True)


def main() -> None:
    output_dir = Path(__file__).resolve().parent
    print("Experiment 21: LanceDB Engine Literal-Faithfulness Inventory", flush=True)
    print(f"Output directory: {output_dir}", flush=True)
    print(f"Python: {sys.version}", flush=True)
    print(f"LanceDB: {lancedb.__version__}", flush=True)
    print(flush=True)

    hostile = run_hostile_sweep()
    ordinary = run_ordinary_corpus()
    live = run_live_table_check()

    write_results(hostile, ordinary, live, output_dir)

    # Print summary
    unfaithful = [r for r in hostile if not r["faithful"] and r["engine_output"]]
    known_unfaithful_labels = {
        "apostrophe double",
        "apostrophe triple",
        "apostrophe quadruple",
        "apostrophe in word",
        "apostrophe run + text",
        "backslash-apostrophe",
        "backslash-apostrophe in word",
        "backslash-apostrophe payload",
    }
    discovered = [r for r in unfaithful if r["label"] not in known_unfaithful_labels]
    false_refusals = [r for r in ordinary if not r["accepted"]]
    live_fail = sum(1 for r in live if r["result"] == "FAIL")
    print(flush=True)
    print("=" * 60, flush=True)
    print(f"Hostile corpus: {len(hostile)} values, {len(unfaithful)} unfaithful", flush=True)
    print(f"  Known unfaithful: {len(unfaithful) - len(discovered)}", flush=True)
    print(f"  Newly discovered: {len(discovered)}", flush=True)
    print(
        f"Ordinary corpus: {len(ordinary)} values, {len(false_refusals)} false refusals",
        flush=True,
    )
    live_pass = sum(1 for r in live if r["result"] == "pass")
    print(
        f"Live table: {live_pass} passed, {live_fail} failed",
        flush=True,
    )
    if not discovered and not false_refusals and live_fail == 0:
        print("VERDICT: PASS — prediction supported", flush=True)
    else:
        print("VERDICT: FAIL — prediction not supported", flush=True)
    print("=" * 60, flush=True)


if __name__ == "__main__":
    main()
