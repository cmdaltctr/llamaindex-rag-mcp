"""The grounded-answer prompts ask for a readable, structured reply.

Chat renders the answer as Markdown. A model that is not told how to lay
out its reply tends to write one dense block. These tests pin the layout
instructions and check that they leave the citation rules and the prompt
budget intact.
"""

from __future__ import annotations

from omrs.core.answer import synthesis
from omrs.core.answer.prompt import GROUND_REFINE_TEMPLATE, GROUND_TEXT_QA_TEMPLATE


def _text_qa() -> str:
    return GROUND_TEXT_QA_TEMPLATE.format(context_str="[1] A source.", query_str="A question?")


def _refine() -> str:
    return GROUND_REFINE_TEMPLATE.format(
        query_str="A question?", existing_answer="An answer [1].", context_msg="[2] More."
    )


def test_text_qa_prompt_asks_for_short_paragraphs_and_lists() -> None:
    prompt = _text_qa()
    assert "short paragraphs" in prompt
    assert "numbered list" in prompt
    assert "bulleted list" in prompt


def test_text_qa_prompt_asks_for_code_in_backticks_and_fences() -> None:
    prompt = _text_qa()
    assert "backticks" in prompt
    assert "fenced code block" in prompt


def test_text_qa_prompt_keeps_a_citation_on_its_own_sentence_line() -> None:
    assert "never on its own line" in _text_qa()


def test_text_qa_prompt_keeps_the_citation_and_grounding_rules() -> None:
    prompt = _text_qa()
    assert "Cite every claim" in prompt
    assert "Use only the provided sources" in prompt
    assert "do not cover this" in prompt


def test_refine_prompt_keeps_the_layout_and_the_citations() -> None:
    prompt = _refine()
    assert "short paragraphs" in prompt
    assert "Keep every bracketed citation number" in prompt


def test_template_text_fits_the_prompt_slack() -> None:
    """The fixed prompt text must stay inside the per-round slack."""
    fixed = GROUND_TEXT_QA_TEMPLATE.format(context_str="", query_str="")
    assert len(fixed) < synthesis._TEMPLATE_SLACK
    refine_fixed = GROUND_REFINE_TEMPLATE.format(query_str="", existing_answer="", context_msg="")
    assert len(refine_fixed) < synthesis._TEMPLATE_SLACK
