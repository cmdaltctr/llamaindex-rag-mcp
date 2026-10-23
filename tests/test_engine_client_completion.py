"""Engine.answer accepts client completion and pre-resolved rows.

Covers the ``engine-scoped-composition`` delta of ``add-mcp-http-transport``
(design D8): a client completion replaces only the answer model, the
verifier stays server-side, ``max_rounds`` caps the answer block, and
``rows`` reach core unchanged so no second retrieval runs.
"""

from __future__ import annotations

import asyncio
import types
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from omrs.core.answer.pipeline import ResolvedRetrieval
from omrs.core.settings import AnswerBlock, EffectiveSettings, MetadataBlock


def _settings(tmp_path: Any, **answer: Any) -> EffectiveSettings:
    return EffectiveSettings(
        metadata=MetadataBlock(extraction_mode="disabled"),
        lancedb_uri=str(tmp_path / "lancedb"),
        answer=AnswerBlock(**answer),
    )


def _engine(settings: EffectiveSettings, **kwargs: Any) -> Any:
    from omrs.engine import Engine

    store = MagicMock(cache_identity="test-identity")
    return Engine(settings, store=store, embed_model=MagicMock(model_name="m"), **kwargs)


def _capture() -> tuple[dict[str, Any], Any]:
    captured: dict[str, Any] = {}

    async def fake_answer(_query: str, **kwargs: Any) -> dict:
        captured.update(kwargs)
        return {"status": "ok", "completion_source": kwargs["completion_source"]}

    return captured, patch("omrs.core.answer.pipeline.answer", side_effect=fake_answer)


def test_client_completion_is_exported_from_engine_module() -> None:
    from omrs.engine import ClientCompletion

    completion = ClientCompletion(complete=AsyncMock(), source="client_mrtr", max_rounds=2)
    assert completion.source == "client_mrtr"
    assert completion.max_rounds == 2


def test_client_completion_replaces_server_model_and_reports_source(tmp_path: Any) -> None:
    from omrs.engine import ClientCompletion

    server_llm = MagicMock()
    server_llm.acomplete = AsyncMock(return_value=types.SimpleNamespace(text="server"))
    engine = _engine(_settings(tmp_path), answer_llm_factory=lambda: server_llm)
    client = AsyncMock(return_value="client")
    captured, patcher = _capture()

    with patcher:
        result = asyncio.run(
            engine.answer(
                "q",
                client_completion=ClientCompletion(
                    complete=client, source="client_legacy", max_rounds=3
                ),
            )
        )

    assert captured["complete"] is client
    assert captured["completion_source"] == "client_legacy"
    assert result["completion_source"] == "client_legacy"
    server_llm.acomplete.assert_not_called()


def test_client_completion_never_replaces_the_verifier(tmp_path: Any) -> None:
    from omrs.engine import ClientCompletion

    verify_llm = MagicMock()
    verify_llm.acomplete = AsyncMock(return_value=types.SimpleNamespace(text="judged"))
    engine = _engine(
        _settings(tmp_path, verify_claims=True), verify_llm_factory=lambda _b: verify_llm
    )
    client = AsyncMock(return_value="client")
    captured, patcher = _capture()

    with patcher:
        asyncio.run(
            engine.answer(
                "q",
                client_completion=ClientCompletion(
                    complete=client, source="client_mrtr", max_rounds=2
                ),
            )
        )

    assert captured["verify_complete"] is not client
    assert asyncio.run(captured["verify_complete"]("p")) == "judged"
    client.assert_not_called()


def test_client_completion_caps_answer_rounds(tmp_path: Any) -> None:
    from omrs.engine import ClientCompletion

    engine = _engine(_settings(tmp_path, max_rounds=8))
    captured, patcher = _capture()

    with patcher:
        asyncio.run(
            engine.answer(
                "q",
                client_completion=ClientCompletion(
                    complete=AsyncMock(), source="client_mrtr", max_rounds=3
                ),
            )
        )

    assert captured["effective_settings"].answer.max_rounds == 3


def test_rows_reach_core_unchanged(tmp_path: Any) -> None:
    engine = _engine(_settings(tmp_path))
    preflight = ResolvedRetrieval(rows=[{"text": "t"}], sampling_calls=2)
    captured, patcher = _capture()

    with patcher:
        asyncio.run(engine.answer("q", rows=preflight))

    assert captured["rows"] is preflight


def test_without_client_completion_behaviour_is_unchanged(tmp_path: Any) -> None:
    server_llm = MagicMock()
    server_llm.acomplete = AsyncMock(return_value=types.SimpleNamespace(text="server"))
    settings = _settings(tmp_path, max_rounds=8)
    engine = _engine(settings, answer_llm_factory=lambda: server_llm)
    captured, patcher = _capture()

    with patcher:
        asyncio.run(engine.answer("q"))

    assert captured["completion_source"] == "server"
    assert captured["rows"] is None
    assert captured["effective_settings"] is settings
    assert asyncio.run(captured["complete"]("p")) == "server"
