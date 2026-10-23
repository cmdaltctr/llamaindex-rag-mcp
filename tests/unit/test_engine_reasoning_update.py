"""A reasoning level saved while ``omrs web`` runs reaches the Engine (task 4.1).

``Engine.use_provider_settings`` refuses any change outside the editable
provider values. ``answer.reasoning`` and ``answer.verify_reasoning`` are
editable (add-chat-reasoning-and-usage D4), so a Settings page save takes
effect from the next answer with no restart.
"""

from __future__ import annotations

import pytest
from tests.unit.test_engine_pipelines_support import build_engine

from omrs.core.settings import AnswerBlock


@pytest.mark.parametrize("field", ["reasoning", "verify_reasoning"])
def test_a_saved_level_applies_to_a_running_engine(effective_settings, field: str) -> None:
    engine = build_engine(effective_settings())
    engine.use_provider_settings(effective_settings(answer=AnswerBlock(**{field: "low"})))
    assert getattr(engine._effective_settings.answer, field) == "low"


def test_the_refusal_message_names_the_levels(effective_settings) -> None:
    engine = build_engine(effective_settings())
    with pytest.raises(ValueError, match="reasoning level"):
        engine.use_provider_settings(effective_settings(answer=AnswerBlock(max_rounds=2)))
