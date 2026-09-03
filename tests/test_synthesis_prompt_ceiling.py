"""Synthesis prompt-budget ceiling tests (security finding F7).

``_widen_for_round_bound`` previously widened the per-round character
budget without limit so every evidence character could reach a prompt.
A large ``top_k`` or expansion window could therefore allocate an
arbitrarily large prompt (model cost, memory).  The fix imposes a hard
per-round character ceiling independent of the configured context
window, drops or trims the lowest-ranked evidence that does not fit,
and marks the truncation in the prompt itself.
"""

from __future__ import annotations

from llama_index.core.schema import NodeWithScore, TextNode

from rag_mcp.core.answer import synthesis

_CEILING = synthesis._PROMPT_CHAR_CEILING
_MARKER = "[evidence truncated]"


def _node(label: int, size: int) -> NodeWithScore:
    """One evidence node of roughly *size* characters, labelled [n]."""
    return NodeWithScore(node=TextNode(text=f"[{label}] " + "x" * size), score=1.0)


class _PromptCapture:
    """Seam that records every prompt and replies with a grounded stub."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return "Grounded answer [1]."


async def test_oversized_evidence_prompt_stays_under_ceiling() -> None:
    """2.4M characters of evidence cannot produce an unbounded prompt."""
    capture = _PromptCapture()
    nodes = [_node(i, 60_000) for i in range(1, 41)]  # ~2.4M chars total

    _answer, calls = await synthesis.run_synthesis(
        "query",
        nodes,
        seam=capture,
        context_window=8_192,
        max_output_tokens=512,
        max_rounds=4,
    )

    assert calls >= 1
    assert capture.prompts, "the seam must have received at least one prompt"
    # Template + query overhead on top of the per-round budget; still
    # bounded by the ceiling plus fixed slack, never by evidence size.
    bound = _CEILING + 512 + synthesis._TEMPLATE_SLACK + len("query") + 8_192
    for prompt in capture.prompts:
        assert len(prompt) <= bound, f"prompt of {len(prompt)} chars exceeds the ceiling budget"
    assert any(_MARKER in prompt for prompt in capture.prompts)


async def test_normal_evidence_untruncated() -> None:
    """Evidence that fits the configured window keeps every source."""
    capture = _PromptCapture()
    nodes = [_node(i, 500) for i in range(1, 6)]

    await synthesis.run_synthesis(
        "query",
        nodes,
        seam=capture,
        context_window=8_192,
        max_output_tokens=512,
        max_rounds=4,
    )

    assert capture.prompts
    assert all(_MARKER not in prompt for prompt in capture.prompts)
    # Every label reached the prompt — nothing was dropped or trimmed.
    assert all(f"[{i}]" in capture.prompts[0] for i in range(1, 6))


async def test_truncation_drops_the_lowest_ranked_first() -> None:
    """The earliest (highest-ranked) labels survive; the tail is cut."""
    capture = _PromptCapture()
    nodes = [_node(i, 60_000) for i in range(1, 41)]

    await synthesis.run_synthesis(
        "query",
        nodes,
        seam=capture,
        context_window=8_192,
        max_output_tokens=512,
        max_rounds=4,
    )

    joined = "\n".join(capture.prompts)
    assert "[1]" in joined, "the highest-ranked source must survive truncation"
    assert "[40]" not in joined, "the lowest-ranked source must be dropped"


async def test_plan_next_prompt_agrees_with_pipeline_after_truncation() -> None:
    """MRTR planning returns exactly the prompt the pipeline consumes.

    The truncation is deterministic and shared by both paths, so the
    replay agreement (design D6) still holds when evidence is cut.
    """
    nodes = [_node(i, 60_000) for i in range(1, 41)]

    planned = await synthesis.plan_next_prompt(
        "query",
        nodes,
        previous_replies=[],
        context_window=8_192,
        max_output_tokens=512,
        max_rounds=4,
    )

    capture = _PromptCapture()
    await synthesis.run_synthesis(
        "query",
        nodes,
        seam=capture,
        context_window=8_192,
        max_output_tokens=512,
        max_rounds=4,
    )
    assert planned is not None
    assert planned == capture.prompts[0]


def test_widen_budget_is_capped_at_the_ceiling() -> None:
    """The widened per-round budget never exceeds the hard ceiling."""
    budget = synthesis._widen_for_round_bound(
        total_context_chars=500_000_000,
        context_window=8_192,
        max_output_tokens=512,
        max_rounds=4,
    )
    assert budget <= _CEILING
