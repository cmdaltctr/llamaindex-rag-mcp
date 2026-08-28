"""Fast tests for Experiment 5b campaign-context evidence capture.

These tests pin the platform-independent evidence contract only. They do not
exercise or claim Apple Silicon MPS behaviour.
"""

from __future__ import annotations

import platform
from types import SimpleNamespace

import harness
import run_eval


def test_campaign_context_records_registered_block_evidence(monkeypatch) -> None:
    """Protocol section 15 evidence is retained verbatim at block boundaries."""
    calls: list[list[str]] = []

    def fake_run(argv, **_kwargs):
        calls.append(list(argv))
        stdout = {
            "ps": "Now drawing from 'AC Power'",
            "therm": "Note: No thermal warning level has been recorded",
        }[argv[-1]]
        return SimpleNamespace(returncode=0, stdout=stdout)

    monkeypatch.setattr(run_eval.subprocess, "run", fake_run)
    monkeypatch.setattr(run_eval.time, "monotonic", lambda: 123.5)
    monkeypatch.setattr(platform, "mac_ver", lambda: ("26.5.1", ("", "", ""), "arm64"))

    declaration = "No foreground interference during this block"
    context = run_eval.campaign_context(
        1,
        phase="start",
        operator_declaration=declaration,
    )

    assert context["block"] == 1
    assert context["phase"] == "start"
    assert context["t_monotonic"] == 123.5
    assert context["power_source"] == "Now drawing from 'AC Power'"
    assert context["thermal_state"] == "Note: No thermal warning level has been recorded"
    assert context["operator_interference_declaration"] == declaration
    assert context["cell_order"] == list(harness.COUNTERBALANCE_TABLE[1])
    assert context["macos_version"] == "26.5.1"
    assert calls == [["pmset", "-g", "ps"], ["pmset", "-g", "therm"]]


def test_campaign_context_records_explicit_null_when_pmset_is_unavailable(monkeypatch) -> None:
    """Non-macOS hosts keep the evidence schema without inventing readings."""

    def missing_pmset(*_args, **_kwargs):
        raise FileNotFoundError("pmset is unavailable")

    monkeypatch.setattr(run_eval.subprocess, "run", missing_pmset)

    context = run_eval.campaign_context(
        2,
        phase="end",
        operator_declaration="test declaration",
    )

    assert context["power_source"] is None
    assert context["thermal_state"] is None
    assert context["cell_order"] == list(harness.COUNTERBALANCE_TABLE[2])
