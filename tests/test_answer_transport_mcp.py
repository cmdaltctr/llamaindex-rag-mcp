"""Protocol-era and transport tests for the ``answer_documents`` MCP tool.

Covers task 1.5: the ``select_completion_source`` matrix, modern MRTR usage
that never touches deprecated ``create_message``, the negotiated legacy seam,
the lazy server-model fallback, the neither-available actionable error, the
never-raise guarantee, and the configured refinement-round bound.

Every test must FAIL today (``transports/mcp/answer.py`` does not exist).
"""

from __future__ import annotations

import contextlib
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import mcp.server.session as server_session
import pytest
from mcp.client import Client
from mcp.shared.exceptions import MCPDeprecationWarning
from mcp.types import CreateMessageResult, SamplingCapability, TextContent

from conftest import connected_client
from rag_mcp.core.ingestion import ingest_path_async
from rag_mcp.transports.mcp import answer_documents
from rag_mcp.transports.mcp.answer import (
    MODERN_PROTOCOL_VERSION,
    _legacy_complete,
    select_completion_source,
)

_COLLECTION = "answer_mcp_docs"
_DOC_TEXT = "The quantum lantern array is calibrated at station one every Tuesday. " * 40
_QUERY = "quantum lantern calibration"
_CAPABILITY = SamplingCapability()
_MODERN = "2026-07-28"
_LEGACY = "2025-06-18"


def _extract_result(result: Any) -> dict[str, Any]:
    """Extract the data payload from a CallToolResult (mirrors test_mcp_tools)."""
    if hasattr(result, "structured_content") and result.structured_content:
        return result.structured_content.get("result", result.structured_content)
    from mcp.types import TextContent as _TextContent

    if result.content and isinstance(result.content[0], _TextContent):
        import json

        return json.loads(result.content[0].text)
    return result


async def _ingest_collection(tmp_path: Path) -> Path:
    """Ingest one multi-lineage document into the module's collection."""
    source = tmp_path / "mcp-answer-doc.txt"
    source.write_text(_DOC_TEXT, encoding="utf-8")
    result = await ingest_path_async(str(source), collection_name=_COLLECTION)
    assert result["status"] == "ok", result
    return source


# ── select_completion_source matrix ───────────────────────────────────────


def test_modern_constant_is_exported() -> None:
    """The modern protocol boundary constant matches the pinned SDK era."""
    assert MODERN_PROTOCOL_VERSION == "2026-07-28"


def test_modern_with_capability_and_preference_uses_mrtr() -> None:
    """Scenario: modern client sampling uses MRTR."""
    assert (
        select_completion_source(
            protocol_version=_MODERN,
            sampling_capability=_CAPABILITY,
            prefer_client=True,
            allow_legacy=False,
        )
        == "client_mrtr"
    )


def test_modern_never_yields_legacy_even_when_allowed() -> None:
    """The legacy path is never selected on a modern session."""
    assert (
        select_completion_source(
            protocol_version=_MODERN,
            sampling_capability=_CAPABILITY,
            prefer_client=True,
            allow_legacy=True,
        )
        == "client_mrtr"
    )


def test_legacy_session_with_permission_uses_legacy() -> None:
    """Scenario: legacy sampling is explicitly negotiated."""
    assert (
        select_completion_source(
            protocol_version=_LEGACY,
            sampling_capability=_CAPABILITY,
            prefer_client=True,
            allow_legacy=True,
        )
        == "client_legacy"
    )


def test_legacy_session_without_permission_falls_back_to_server() -> None:
    """Without the allow_legacy opt-in an old session uses the server model."""
    assert (
        select_completion_source(
            protocol_version=_LEGACY,
            sampling_capability=_CAPABILITY,
            prefer_client=True,
            allow_legacy=False,
        )
        == "server"
    )


def test_no_capability_uses_server_model() -> None:
    """Without an advertised model-request capability the server model runs."""
    for version in (_MODERN, _LEGACY):
        assert (
            select_completion_source(
                protocol_version=version,
                sampling_capability=None,
                prefer_client=True,
                allow_legacy=True,
            )
            == "server"
        )


def test_no_client_preference_uses_server_model() -> None:
    """``prefer_client=False`` disables both client paths."""
    assert (
        select_completion_source(
            protocol_version=_MODERN,
            sampling_capability=_CAPABILITY,
            prefer_client=False,
            allow_legacy=True,
        )
        == "server"
    )


def test_no_protocol_version_uses_server_model() -> None:
    """A direct (no session) call has no client path, so the server model runs."""
    assert (
        select_completion_source(
            protocol_version=None,
            sampling_capability=_CAPABILITY,
            prefer_client=True,
            allow_legacy=True,
        )
        == "server"
    )


# ── Tool advertisement ────────────────────────────────────────────────────


async def test_tool_is_read_only_and_describes_the_cost(mcp_server) -> None:
    """Scenario: the tool description states the cost and names the alternative."""
    async with connected_client(mcp_server) as client:
        listing = await client.list_tools()

    tool = next(item for item in listing.tools if item.name == "answer_documents")
    assert tool.annotations is not None
    dumped = tool.annotations.model_dump(by_alias=True)
    assert dumped["readOnlyHint"] is True
    assert dumped["destructiveHint"] is False
    description = (tool.description or "").lower()
    assert "search_documents" in description
    assert "completion" in description or "language model" in description


# ── Modern MRTR over an in-memory session ────────────────────────────────


async def test_modern_session_uses_mrtr_and_never_create_message(
    mcp_server, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: modern client sampling uses MRTR, never ``create_message``."""
    await _ingest_collection(tmp_path)
    seen_prompts: list[str] = []

    async def _sampling_callback(context: Any, params: Any) -> CreateMessageResult:
        block = params.messages[-1].content
        seen_prompts.append(getattr(block, "text", ""))
        return CreateMessageResult(
            role="assistant",
            model="client-model",
            content=TextContent(type="text", text="The array is calibrated at station one [1]."),
        )

    async def _forbidden(self: Any, *args: Any, **kwargs: Any) -> None:
        raise AssertionError("deprecated create_message was called on a modern session")

    monkeypatch.setattr(server_session.ServerSession, "create_message", _forbidden)

    async with Client(
        mcp_server,
        sampling_callback=_sampling_callback,
        sampling_capabilities=SamplingCapability(),
    ) as client:
        result = await client.call_tool(
            "answer_documents",
            {
                "query": _QUERY,
                "collection": _COLLECTION,
                "similarity_threshold": 0.0,
            },
        )

    data = _extract_result(result)
    assert data["status"] == "ok", data
    assert data["completion_source"] == "client_mrtr"
    assert len(seen_prompts) >= 1, "the client sampling callback must see the prompt"


# ── Server-model fallback (direct handler invocation) ────────────────────


class _FakeLLM:
    """Server-model stand-in exposing the LlamaIndex async completion seam."""

    def __init__(self) -> None:
        self.calls = 0

    async def acomplete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        """Return a completion object carrying a grounded reply."""
        self.calls += 1
        return SimpleNamespace(text="The array is calibrated at station one [1].")


async def test_server_fallback_reports_server_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: falls back to the configured server model."""
    await _ingest_collection(tmp_path)
    fake = _FakeLLM()
    monkeypatch.setattr("rag_mcp.compose.build_answer_llm", lambda settings=None: fake)

    result = await answer_documents(
        query=_QUERY,
        collection=_COLLECTION,
        similarity_threshold=0.0,
        ctx=None,
    )

    assert result["status"] == "ok", result
    assert result["completion_source"] == "server"
    assert fake.calls >= 1


async def test_neither_path_returns_actionable_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: neither available names both options and never raises."""
    await _ingest_collection(tmp_path)
    monkeypatch.setattr("rag_mcp.compose.build_answer_llm", lambda settings=None: None)

    result = await answer_documents(
        query=_QUERY,
        collection=_COLLECTION,
        similarity_threshold=0.0,
        ctx=None,
    )

    assert result["status"] == "error"
    message = result.get("error") or ""
    assert "ANSWER__PROVIDER" in message
    assert "sampling" in message.lower() or "client" in message.lower()


async def test_internal_failure_is_returned_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Scenario: the tool never raises, even when core explodes."""

    async def _explode(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("core exploded")

    await _ingest_collection(tmp_path)
    monkeypatch.setattr("rag_mcp.transports.mcp.answer.answer", _explode)

    result = await answer_documents(query=_QUERY, collection=_COLLECTION, ctx=None)

    assert result["status"] == "error"
    standard_keys = (
        "query",
        "answer",
        "citations",
        "evidence",
        "failure_stage",
        "error",
        "completion_source",
    )
    for key in standard_keys:
        assert key in result, f"error result is missing the standard key {key!r}"


# ── Legacy sampling seam ──────────────────────────────────────────────────


class _RecordingSession:
    """Fake ``ctx.session`` recording create_message calls."""

    def __init__(self, reply: str) -> None:
        self.reply = reply
        self.prompts: list[list[Any]] = []

    async def create_message(self, messages: list[Any], **kwargs: Any) -> CreateMessageResult:
        """Record the messages and return the scripted client text."""
        self.prompts.append(list(messages))
        return CreateMessageResult(
            role="assistant",
            model="stub",
            content=TextContent(type="text", text=self.reply),
        )


class _FakeContext:
    """Minimal context carrying only the session the legacy seam needs."""

    def __init__(self, session: Any) -> None:
        self.session = session


async def test_legacy_seam_returns_client_text() -> None:
    """The legacy seam awaits ``create_message`` and returns the client text."""
    session = _RecordingSession("legacy reply body")

    text = await _legacy_complete(_FakeContext(session), "answer this")

    assert text == "legacy reply body"
    assert len(session.prompts) == 1
    assert session.prompts[0], "the prompt messages must reach the session"


async def test_real_create_message_emits_deprecation_warning() -> None:
    """The SDK's real ``create_message`` is deprecated as of 2026-07-28."""
    with pytest.warns(MCPDeprecationWarning):
        with contextlib.suppress(Exception):
            await server_session.ServerSession.create_message(
                object.__new__(server_session.ServerSession), [], max_tokens=8
            )


# ── Refinement-round bound ────────────────────────────────────────────────


async def test_completion_calls_respect_the_configured_round_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """COMPACT refinement is bounded by ``answer.max_rounds`` on the server path."""
    from rag_mcp.core.settings import (
        AnswerBlock,
        get_default_effective_settings,
        set_default_effective_settings,
    )

    await _ingest_collection(tmp_path)
    current = get_default_effective_settings()
    bounded = current.model_copy(update={"answer": AnswerBlock(context_window=64, max_rounds=2)})
    set_default_effective_settings(bounded)

    fake = _FakeLLM()

    async def _counting(prompt: str, **kwargs: Any) -> SimpleNamespace:
        fake.calls += 1
        return SimpleNamespace(
            text=f"Grounded finding number {fake.calls} [1]. With added substantive detail."
        )

    fake.acomplete = _counting  # type: ignore[method-assign]
    monkeypatch.setattr("rag_mcp.compose.build_answer_llm", lambda settings=None: fake)

    result = await answer_documents(
        query=_QUERY,
        collection=_COLLECTION,
        similarity_threshold=0.0,
        diagnostics=True,
        ctx=None,
    )

    assert result["status"] == "ok", result
    reported = result["diagnostics"]["completion_calls"]
    assert reported <= 2, f"the pipeline must bound refinement rounds, saw {reported}"
    assert fake.calls <= 2


# ── Claim verification (ADR-059): transport-level threading ───────────────


async def test_verification_skipped_when_judge_build_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A raising judge build degrades to verification_skipped, never an error."""
    await _ingest_collection(tmp_path)
    fake = _FakeLLM()
    monkeypatch.setattr("rag_mcp.compose.build_answer_llm", lambda settings=None: fake)

    def _no_judge(*args: Any, **kwargs: Any) -> Any:
        raise ImportError("OPENROUTER_API_KEY is not set")

    monkeypatch.setattr("rag_mcp.compose.build_verify_llm", _no_judge)
    monkeypatch.setenv("ANSWER__VERIFY_CLAIMS", "true")
    # Force the process-wide resolver to rebuild so the env change
    # reaches the profile-resolved answer block (its bundles cache per
    # instance; a stale cache would keep verify_claims=false).
    from rag_mcp.transports import mcp as mcp_transport

    monkeypatch.setattr(mcp_transport, "_profile_resolver", None)
    try:
        result = await answer_documents(
            query=_QUERY,
            collection=_COLLECTION,
            similarity_threshold=0.0,
            ctx=None,
        )
    finally:
        monkeypatch.setattr(mcp_transport, "_profile_resolver", None)

    assert result["status"] == "ok", result
    assert "verification provider unavailable" in result["verification_skipped"]
    assert "verified" not in result


async def test_verification_judges_through_the_injected_seam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An adversarial answer over real evidence surfaces unverified_claims."""
    await _ingest_collection(tmp_path)
    adversarial = _FakeLLM()

    async def _lie(prompt: str, **kwargs: Any) -> SimpleNamespace:
        return SimpleNamespace(
            text="Quantum lanterns were invented in 1204 AD by Genghis Khan [1]."
        )

    adversarial.acomplete = _lie  # type: ignore[method-assign]
    monkeypatch.setattr("rag_mcp.compose.build_answer_llm", lambda settings=None: adversarial)

    class _JudgeLLM:
        calls = 0

        async def acomplete(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
            _JudgeLLM.calls += 1
            assert "\n<evidence>\n" in prompt, "the judge must see delimited evidence"
            return SimpleNamespace(text="unsupported")

    monkeypatch.setattr("rag_mcp.compose.build_verify_llm", lambda *a, **k: _JudgeLLM())
    monkeypatch.setenv("ANSWER__VERIFY_CLAIMS", "true")
    from rag_mcp.transports import mcp as mcp_transport

    monkeypatch.setattr(mcp_transport, "_profile_resolver", None)
    try:
        result = await answer_documents(
            query=_QUERY,
            collection=_COLLECTION,
            similarity_threshold=0.0,
            diagnostics=True,
            ctx=None,
        )
    finally:
        monkeypatch.setattr(mcp_transport, "_profile_resolver", None)

    assert result["status"] == "unverified_claims", result
    assert result["unverified_claims"], "the failing claim must be listed"
    assert result["evidence"], "evidence is retained"
    assert result["diagnostics"]["verification_calls"] >= 1
    assert _JudgeLLM.calls >= 1
