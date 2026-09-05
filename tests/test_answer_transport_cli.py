"""CLI transport tests for ``omrg answer`` (tasks 5.1-5.3).

Exercises the Typer command through the in-process CliRunner, matching
the established ``tests/test_cli.py`` pattern: the happy path with a
cited answer, the no-evidence shape, the actionable no-provider error
with exit code 1, the ``--json`` contract, and the stream rule (human
output on stderr, keeping stdout free for the MCP protocol channel).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from omrg.transports.cli import app

runner = CliRunner()

_COLLECTION = "answer_cli_docs"


class _FakeLLM:
    """Server-model stand-in exposing the LlamaIndex completion seam."""

    def __init__(self, reply: str = "The array is calibrated at station one [1].") -> None:
        """Script the reply every completion round returns."""
        self.reply = reply
        self.calls = 0

    async def acomplete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        """Return the scripted reply as a completion object."""
        self.calls += 1
        return SimpleNamespace(text=self.reply)


def _ingest(tmp_path: Path) -> Path:
    """Ingest one document into the module's collection via the CLI.

    Ingesting through the CLI (not ``ingest_path_async`` directly)
    keeps one embedding configuration for the ingest and the answer —
    the runtime resolves settings per process, and a conftest-configured
    direct ingest can disagree with the CLI's own resolution.
    """
    source = tmp_path / "cli-answer-doc.txt"
    source.write_text(
        "The quantum lantern array is calibrated at station one every Tuesday. " * 20,
        encoding="utf-8",
    )
    result = runner.invoke(app, ["ingest", str(source), "--collection", _COLLECTION])
    assert result.exit_code == 0, result.output
    return source


def _install_llm(monkeypatch: pytest.MonkeyPatch, llm: Any) -> None:
    """Redirect the composition-root answer builder to a stand-in."""
    monkeypatch.setattr("omrg.compose.build_answer_llm", lambda settings=None: llm)


# ── Task 5.3: actionable message when no provider is configured ───────────


def test_answer_without_provider_is_actionable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Evidence present and no configured model yields an actionable error, exit 1.

    Core produces the error (with the evidence retained), so the CLI must
    surface it rather than pre-empt retrieval with its own check.
    """
    _ingest(tmp_path)
    _install_llm(monkeypatch, None)

    result = runner.invoke(app, ["answer", "lantern calibration", "--collection", _COLLECTION])

    assert result.exit_code == 1
    assert "ANSWER__PROVIDER" in result.output
    assert result.stdout.strip() == "", "human mode must not write to stdout"


def test_answer_json_provider_error_goes_to_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--json`` failure output lands on stderr in the standard result schema.

    The payload must mirror the MCP tool's dict keys (the core result
    skeleton) so a failed answer is machine-parseable on the same terms
    as a successful one, and stdout stays the MCP protocol channel.
    """
    _ingest(tmp_path)
    _install_llm(monkeypatch, None)

    result = runner.invoke(
        app, ["answer", "lantern calibration", "--collection", _COLLECTION, "--json"]
    )

    assert result.exit_code == 1
    assert result.stdout.strip() == "", "--json failure output must not write to stdout"
    data = json.loads(result.stderr)
    for key in (
        "status",
        "query",
        "answer",
        "citations",
        "evidence",
        "failure_stage",
        "error",
        "completion_source",
    ):
        assert key in data, f"JSON failure payload is missing the standard key {key!r}"
    assert data["status"] == "error"
    assert "ANSWER__PROVIDER" in data["error"]


# ── Profile-policy and no-evidence precedence (review findings) ───────────


def test_answer_hybrid_omitted_defers_to_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Omitting ``--hybrid`` passes ``None`` so the profile decides.

    A ``False`` default would silently override profiles that enable
    hybrid retrieval (the same tri-state contract ``--rerank`` already
    has, and the OpenAPI ``AnswerRequest.hybrid`` documents).
    """
    captured: dict[str, Any] = {}

    async def fake_answer(query: str, **kwargs: Any) -> dict[str, Any]:
        captured.update(kwargs)
        return {
            "status": "no_evidence",
            "query": query,
            "answer": None,
            "citations": [],
            "evidence": [],
            "failure_stage": None,
            "error": None,
            "completion_source": "none",
        }

    monkeypatch.setattr("omrg.core.answer.answer", fake_answer)
    _install_llm(monkeypatch, _FakeLLM())

    result = runner.invoke(app, ["answer", "anything", "--collection", _COLLECTION])

    assert result.exit_code == 0, result.output
    assert captured.get("hybrid") is None, (
        f"omitted --hybrid must pass None (profile decides), got {captured.get('hybrid')!r}"
    )
    assert captured.get("rerank") is None, (
        f"omitted --rerank must pass None (profile decides), got {captured.get('rerank')!r}"
    )


def test_answer_empty_collection_without_provider_is_no_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty collection outranks the missing provider.

    Core short-circuits empty retrieval to ``no_evidence`` without a
    model call, so the CLI must not exit with a provider error before
    core ran (spec scenario: empty collection short-circuits).
    """
    _install_llm(monkeypatch, None)

    result = runner.invoke(
        app, ["answer", "unmatched query", "--collection", "never_ingested_answer"]
    )

    assert result.exit_code == 0, result.output
    assert "No supporting evidence" in result.output
    assert "ANSWER__PROVIDER" not in result.output


# ── Task 5.1/5.2: output shape and streams ────────────────────────────────


def test_answer_no_evidence_message(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty retrieval reports no supporting evidence, exit code 0."""
    _install_llm(monkeypatch, _FakeLLM())

    result = runner.invoke(
        app, ["answer", "unmatched query", "--collection", "never_ingested_answer"]
    )

    assert result.exit_code == 0
    assert "No supporting evidence" in result.output


def test_answer_prints_answer_and_numbered_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Human mode prints the answer, then numbered sources with chunk ids."""
    _ingest(tmp_path)
    _install_llm(monkeypatch, _FakeLLM())

    result = runner.invoke(app, ["answer", "lantern calibration", "--collection", _COLLECTION])

    assert result.exit_code == 0, result.output
    assert "The array is calibrated" in result.output
    assert "Sources" in result.output
    assert "chunk=" in result.output


def test_answer_json_contract(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """``--json`` prints the machine result on stderr and parses.

    Gotcha #5: stdout is the MCP protocol channel, so the JSON payload
    (success AND failure) must land on stderr with stdout empty.
    """
    _ingest(tmp_path)
    _install_llm(monkeypatch, _FakeLLM())

    result = runner.invoke(
        app, ["answer", "lantern calibration", "--collection", _COLLECTION, "--json"]
    )

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "", "--json output must not write to stdout"
    data = json.loads(result.stderr)
    assert data["status"] == "ok"
    assert data["completion_source"] == "server"
    assert data["citations"], "a cited CLI answer must carry citations"
    assert data["citations"][0]["chunk_id"]


def test_answer_human_output_lands_on_stderr(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Human output stays on stderr so stdout remains protocol-clean."""
    _ingest(tmp_path)
    _install_llm(monkeypatch, _FakeLLM())

    result = runner.invoke(app, ["answer", "lantern calibration", "--collection", _COLLECTION])

    assert result.exit_code == 0
    assert result.stdout.strip() == "", "human mode must not write to stdout"
    assert "The array is calibrated" in result.stderr


# ── Review remediation: CLI-local failure paths and human rendering ────────


def _craft_result(**overrides: Any) -> dict[str, Any]:
    """Build a core-shaped result the patched ``answer()`` returns."""
    result: dict[str, Any] = {
        "status": "ok",
        "query": "lantern",
        "answer": "Station one, every Tuesday [1].",
        "citations": [
            {
                "ordinal": 1,
                "source": "doc.txt",
                "chunk_id": "c1",
                "score": 0.9123,
                "chunk_ids": ["c1", "c2"],
            }
        ],
        "evidence": [],
        "failure_stage": None,
        "error": None,
        "completion_source": "server",
        "diagnostics": {
            "retrieval_ms": 12.3,
            "generation_ms": 45.6,
            "completion_calls": 1,
        },
    }
    result.update(overrides)
    return result


def _install_core_answer(
    monkeypatch: pytest.MonkeyPatch, result: dict[str, Any] | Exception
) -> None:
    """Replace the core ``answer`` entry the CLI imports at call time.

    The fake is async because the CLI drives it through
    ``asyncio.run``; a plain function returning a dict would make
    ``asyncio.run`` raise ``TypeError`` before the result is rendered.
    """

    async def _fake_answer(*args: Any, **kwargs: Any) -> dict[str, Any]:
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("omrg.core.answer.answer", _fake_answer)


def test_answer_profile_resolution_failure_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """A profile-resolution failure emits the standard JSON error on stderr."""

    def _boom() -> Any:
        raise ValueError("profile 'bogus' is not registered")

    monkeypatch.setattr("omrg.compose.build_profile_resolver", _boom)

    result = runner.invoke(app, ["answer", "lantern", "--json"])

    assert result.exit_code == 1
    assert result.stdout.strip() == "", "--json failure output must not write to stdout"
    data = json.loads(result.stderr)
    assert data["status"] == "error"
    assert "bogus" in data["error"]
    assert data["completion_source"] == "none"


def test_answer_profile_resolution_failure_human(monkeypatch: pytest.MonkeyPatch) -> None:
    """A profile-resolution failure reports on the stderr console."""

    def _boom() -> Any:
        raise ValueError("profile 'bogus' is not registered")

    monkeypatch.setattr("omrg.compose.build_profile_resolver", _boom)

    result = runner.invoke(app, ["answer", "lantern"])

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "bogus" in result.stderr


def test_answer_provider_builder_failure_is_structured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A raising provider builder surfaces as a CLI-local JSON error."""

    def _raise(settings: Any = None) -> Any:
        raise ValueError("ANSWER__PROVIDER='bogus' is not a registered LLM provider.")

    monkeypatch.setattr("omrg.compose.build_answer_llm", _raise)

    result = runner.invoke(app, ["answer", "lantern", "--json"])

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    data = json.loads(result.stderr)
    assert "not a registered LLM provider" in data["error"]


def test_answer_connection_error_json_names_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ConnectionError becomes the friendly Ollama hint in JSON mode."""

    def _conn(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ConnectionError("dial tcp 127.0.0.1:11434: connection refused")

    monkeypatch.setattr("omrg.core.answer.answer", _conn)
    _install_llm(monkeypatch, _FakeLLM())

    result = runner.invoke(app, ["answer", "lantern", "--json"])

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    data = json.loads(result.stderr)
    assert "Ollama" in data["error"]
    assert "connection refused" in data["error"]


def test_answer_connection_error_human_names_ollama(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ConnectionError becomes the friendly Ollama hint in human mode."""

    def _conn(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise ConnectionError("dial tcp 127.0.0.1:11434: connection refused")

    monkeypatch.setattr("omrg.core.answer.answer", _conn)
    _install_llm(monkeypatch, _FakeLLM())

    result = runner.invoke(app, ["answer", "lantern"])

    assert result.exit_code == 1
    assert result.stdout.strip() == ""
    assert "Ollama" in result.stderr


def test_answer_human_output_prints_sources_and_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Human mode renders citations, merged notes and diagnostics."""
    _install_core_answer(monkeypatch, _craft_result())
    _install_llm(monkeypatch, None)

    result = runner.invoke(app, ["answer", "lantern", "--diagnostics"])

    assert result.exit_code == 0
    assert result.stdout.strip() == ""
    err = result.stderr
    assert "Sources" in err
    assert "doc.txt" in err
    assert "chunk=c1" in err
    assert "score=0.912" in err
    assert "(+1 merged)" in err
    assert "retrieval=12.3ms" in err
    assert "generation=45.6ms" in err
    assert "completions=1" in err


def test_answer_generation_unverified_warns_in_human_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A citation-less answer warns and still prints the answer text."""
    _install_core_answer(monkeypatch, _craft_result(status="generation_unverified", citations=[]))
    _install_llm(monkeypatch, None)

    result = runner.invoke(app, ["answer", "lantern"])

    assert result.exit_code == 0
    assert result.stdout.strip() == ""
    assert "no verifiable citation" in result.stderr
    assert "Station one" in result.stderr


# ── Claim verification (ADR-059): settings-only, threaded per CLI run ──────


def test_answer_verification_skipped_prints_reason_when_no_judge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No usable judge → the answer stays ok and names the skip reason."""
    _ingest(tmp_path)
    _install_llm(monkeypatch, _FakeLLM())
    monkeypatch.setattr("omrg.compose.build_verify_llm", lambda *a, **k: None)
    monkeypatch.setenv("ANSWER__VERIFY_CLAIMS", "true")

    result = runner.invoke(app, ["answer", "lantern calibration", "--collection", _COLLECTION])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "", "human mode must not write to stdout"
    assert "Verification skipped: verification provider unavailable" in result.output


def test_answer_unverified_claims_warns_in_human_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A judge-rejected claim warns without failing the run."""

    class _JudgeLLM:
        async def acomplete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            assert "\n<evidence>\n" in prompt, "the judge must see delimited evidence"
            return SimpleNamespace(text="unsupported")

    _ingest(tmp_path)
    _install_llm(monkeypatch, _FakeLLM())
    monkeypatch.setattr("omrg.compose.build_verify_llm", lambda *a, **k: _JudgeLLM())
    monkeypatch.setenv("ANSWER__VERIFY_CLAIMS", "true")

    result = runner.invoke(app, ["answer", "lantern calibration", "--collection", _COLLECTION])

    assert result.exit_code == 0, result.output
    assert result.stdout.strip() == "", "human mode must not write to stdout"
    assert "unsupported or unreadable claim(s)" in result.output
    assert "calibrated at station one" in result.output, "the answer text is retained"


def test_answer_verification_build_failure_degrades_to_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising judge build names the error; the answer still succeeds."""

    def _raise(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("no such provider")

    _ingest(tmp_path)
    _install_llm(monkeypatch, _FakeLLM())
    monkeypatch.setattr("omrg.compose.build_verify_llm", _raise)
    monkeypatch.setenv("ANSWER__VERIFY_CLAIMS", "true")

    result = runner.invoke(app, ["answer", "lantern calibration", "--collection", _COLLECTION])

    assert result.exit_code == 0, result.output
    assert "Verification skipped: verification provider unavailable: no such provider" in (
        result.output
    )
