"""Synthesis engine for grounded answering.

Drives llama-index's COMPACT response mode over an injected async
completion seam: :class:`SeamLLM` adapts ``async complete(prompt) -> str``
to a LlamaIndex ``CustomLLM``, and :func:`run_synthesis` wires it into
``get_response_synthesizer(response_mode=COMPACT, use_async=True)``.

Round bounding (design D4/D6): COMPACT packs context into as many
rounds as the prompt helper's window allows.  The helper here counts
CHARACTERS with a deterministic fake tokenizer, so the per-round budget
is exact.  When the evidence needs more rounds than ``max_rounds``
allows, the budget is widened so the final rounds absorb the overflow —
rounds never exceed the bound.

Prompt ceiling (security finding F7): the widened budget is capped at
``_PROMPT_CHAR_CEILING`` regardless of the configured context window,
so a huge ``top_k`` or expansion cannot allocate an arbitrarily large
prompt.  Evidence that does not fit inside ``max_rounds`` rounds at the
capped budget is dropped lowest-ranked-first and the final retained
node is trimmed, with an inline ``[evidence truncated]`` marker so the
truncation is observable in the prompt itself (diagnostics plumbing is
owned elsewhere).  Both ``run_synthesis`` and ``plan_next_prompt`` fit
evidence through the same deterministic helper, so the MRTR replay
agreement (design D6) holds under truncation too.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from llama_index.core.indices.prompt_helper import PromptHelper
from llama_index.core.llms import CompletionResponse, CustomLLM, LLMMetadata
from llama_index.core.llms.callbacks import llm_completion_callback
from llama_index.core.prompts import PromptTemplate
from llama_index.core.response_synthesizers import get_response_synthesizer
from llama_index.core.response_synthesizers.type import ResponseMode
from llama_index.core.schema import NodeWithScore, TextNode

from .prompt import GROUND_REFINE_TEMPLATE, GROUND_TEXT_QA_TEMPLATE

#: Async completion seam: takes the prompt text, returns the reply text.
CompletionSeam = Callable[[str], Awaitable[str]]

#: Reserved head-room (characters) for template boilerplate when
#: widening the per-round budget for the round bound.
_TEMPLATE_SLACK = 1024

#: Hard ceiling (characters) on one synthesis prompt round, independent
#: of the configured context window (security finding F7).  A huge
#: ``top_k`` or a misconfigured ``ANSWER__CONTEXT_WINDOW`` must not be
#: able to allocate an arbitrarily large prompt (model cost, memory).
#: ~256 KiB of characters sits above every practical local model's
#: window, so legitimate workloads are never clipped; evidence beyond
#: the ceiling is dropped lowest-ranked-first and marked in the prompt.
_PROMPT_CHAR_CEILING = 262_144

#: Inline observability marker appended to the prompt when evidence was
#: dropped or trimmed to respect ``_PROMPT_CHAR_CEILING``.  Diagnostics
#: plumbing is owned elsewhere, so the marker lives in the prompt text.
_EVIDENCE_TRUNCATED_MARKER = "\n[evidence truncated]\n"

#: Packing head-room (characters) reserved from every round so the
#: truncation marker always fits inside the final allowed round.  The
#: prompt helper packs whole nodes per round, so without this reserve a
#: completely full final round would push the marker into a round the
#: bound then suppresses.
_MARKER_RESERVE = len(_EVIDENCE_TRUNCATED_MARKER) + 64


def _char_tokenizer(text: str) -> list[int]:
    """Deterministic character-count stand-in for a real tokenizer.

    Every character is one token, so the prompt helper's window is an
    exact character budget — no tokenizer download, no estimate drift
    between environments.
    """
    return [0] * len(text)


class SeamLLM(CustomLLM):
    """LlamaIndex LLM adapter over an injected async completion seam.

    Counts seam invocations on :attr:`seam_calls` (reported as the
    completion-call diagnostic) and enforces the round bound: once
    ``max_rounds`` seam calls have been made, a further completion
    request reuses the last reply instead of touching the seam.  The
    pre-widened budget makes that path rare; the adapter rule is the
    belt-and-braces guarantee the reported call count never exceeds the
    configured bound.
    """

    context_window: int = 8192
    num_output: int = 2048
    model_name: str = "answer-seam"
    max_rounds: int = 4

    seam: Any = None
    seam_calls: int = 0
    last_reply: str = ""

    @property
    def metadata(self) -> LLMMetadata:
        """Expose the declared window/output budget to the framework."""
        return LLMMetadata(
            context_window=self.context_window,
            num_output=self.num_output,
            model_name=self.model_name,
        )

    @llm_completion_callback()
    def complete(self, prompt: str, formatted: bool = False, **kwargs: Any) -> CompletionResponse:
        """Refuse synchronous completion — the seam is async-only."""
        raise NotImplementedError("The grounded-answer seam is asynchronous; call acomplete().")

    @llm_completion_callback()
    async def acomplete(
        self, prompt: str, formatted: bool = False, **kwargs: Any
    ) -> CompletionResponse:
        """Serve one completion round through the injected seam."""
        if self.seam_calls >= self.max_rounds:
            # Round bound reached (the widened budget should have
            # prevented this): reuse the last reply rather than
            # exceeding the advertised bound.
            return CompletionResponse(text=self.last_reply)
        reply = await self.seam(prompt)
        self.last_reply = reply
        self.seam_calls += 1
        return CompletionResponse(text=reply)

    @llm_completion_callback()
    def stream_complete(self, prompt: str, formatted: bool = False, **kwargs: Any):
        """Refuse streaming — the seam is whole-reply only."""
        raise NotImplementedError("The grounded-answer seam does not stream.")


def _widen_for_round_bound(
    total_context_chars: int,
    context_window: int,
    max_output_tokens: int,
    max_rounds: int,
) -> int:
    """Return the per-round context budget honouring the round bound.

    The natural budget is ``context_window`` characters per round.  When
    the total context needs more than ``max_rounds`` rounds at that
    budget, the budget grows to ``ceil(total / max_rounds)`` so the last
    rounds absorb the overflow.  The result is capped at
    :data:`_PROMPT_CHAR_CEILING` in both branches — the ceiling is
    independent of the configured context window, so a misconfigured
    window cannot bypass it (finding F7).  Evidence that still does not
    fit is dropped by :func:`_fit_evidence`, never by widening further.
    """
    natural_budget = max(1, context_window - max_output_tokens - _TEMPLATE_SLACK)
    if max_rounds * natural_budget >= total_context_chars:
        return min(natural_budget, _PROMPT_CHAR_CEILING)
    # Ceil division: the smallest per-round budget that fits the whole
    # context inside the round bound.
    widened = -(-total_context_chars // max_rounds)
    return min(max(natural_budget, widened), _PROMPT_CHAR_CEILING)


def _trimmed_node(node: NodeWithScore, room: int) -> NodeWithScore:
    """Copy *node* with its text cut to *room* characters plus the marker.

    The node's metadata (lineage) is preserved so downstream consumers
    of the node keep their identifiers; only the prompt text shrinks.
    """
    trimmed = (node.get_content() or "")[:room] + _EVIDENCE_TRUNCATED_MARKER
    return NodeWithScore(
        node=TextNode(text=trimmed, metadata=dict(node.node.metadata or {})),
        score=node.score if node.score is not None else 0.0,
    )


def _notified_node(node: NodeWithScore) -> NodeWithScore:
    """Copy *node* with the truncation notice prepended to its text.

    The first evidence node always lands in the first synthesis round,
    and the first round is always delivered — so prepending the notice
    there is the one observability channel the prompt packer cannot
    defeat (large or tail-position markers can be left unmerged by the
    packer's sentence phase even when nominal room exists).
    """
    notified = _EVIDENCE_TRUNCATED_MARKER + (node.get_content() or "")
    return NodeWithScore(
        node=TextNode(text=notified, metadata=dict(node.node.metadata or {})),
        score=node.score if node.score is not None else 0.0,
    )


def _fit_evidence(
    nodes: list[NodeWithScore], per_round_budget: int, max_rounds: int
) -> list[NodeWithScore]:
    """Fit evidence under the hard prompt ceiling, lowest-ranked first out.

    Nodes are assumed ranked best-first (retrieval order).  The prompt
    helper packs WHOLE nodes per round, so affordability is simulated
    with the same greedy packing: a node that does not fit the current
    round starts the next one.  The first node that would start a round
    beyond ``max_rounds`` is trimmed into the final allowed round's
    remaining space plus the truncation marker, and every node after it
    (lower-ranked) is dropped.  The marker therefore appears whenever
    anything was cut, and always inside a round that reaches the model.

    Each node costs its text length plus one separator character — the
    separator the prompt helper inserts between packed nodes.  A node
    larger than one round's capacity spans several rounds in the real
    packer, so the walk advances the round counter accordingly.
    """
    capacity = max(per_round_budget - _MARKER_RESERVE, 1)
    kept: list[NodeWithScore] = []
    round_index = 1
    used_in_round = 0
    for node in nodes:
        text = node.get_content() or ""
        cost = len(text) + 1
        spans = max(1, -(-cost // capacity))
        if used_in_round + cost > capacity:
            round_index += 1
            used_in_round = 0
        round_index += spans - 1
        if round_index > max_rounds:
            room = max(0, capacity - used_in_round - len(_EVIDENCE_TRUNCATED_MARKER) - 1)
            kept.append(_trimmed_node(node, min(len(text), room)))
            # Observability the packer cannot defeat: the first node
            # always reaches the first (guaranteed) round, so the
            # truncation notice is prepended there.
            kept[0] = _notified_node(kept[0])
            return kept
        kept.append(node)
        # After a roll-over the node either fits whole (accumulate its
        # cost), or it is oversized and leaves its remainder in the
        # last round it spans.
        if used_in_round + cost <= capacity:
            used_in_round += cost
        else:
            used_in_round = cost - (spans - 1) * capacity
    return nodes  # everything fit; nothing was cut


def _fit_and_measure(
    nodes: list[NodeWithScore],
    context_window: int,
    max_output_tokens: int,
    max_rounds: int,
) -> tuple[list[NodeWithScore], int]:
    """Fit *nodes* under the ceiling and return ``(fitted, total_chars)``.

    Shared by :func:`run_synthesis` and :func:`plan_next_prompt` so both
    paths truncate identically — the MRTR replay agreement (design D6)
    holds under truncation by construction.
    """
    rough = sum(len(node.get_content() or "") + 1 for node in nodes)
    per_round = _widen_for_round_bound(rough, context_window, max_output_tokens, max_rounds)
    fitted = _fit_evidence(nodes, per_round, max_rounds)
    total = sum(len(node.get_content() or "") + 1 for node in fitted)
    return fitted, total


def build_synthesiser(
    *,
    seam: CompletionSeam,
    context_window: int,
    max_output_tokens: int,
    max_rounds: int,
    total_context_chars: int,
    text_qa_template: PromptTemplate | None = None,
    refine_template: PromptTemplate | None = None,
) -> tuple[Any, SeamLLM]:
    """Construct the COMPACT synthesiser and its counting seam adapter.

    Args:
        seam: Async completion seam (``prompt -> reply``).
        context_window: Per-round context budget in characters.
        max_output_tokens: Reply head-room reserved inside the budget.
        max_rounds: Maximum completion rounds.
        total_context_chars: Total character size of the evidence the
            synthesiser will receive (drives the round-bound widening).
        text_qa_template: QA template (defaults to the grounded prompt).
        refine_template: Refine template (defaults to the grounded
            refine prompt).

    Returns:
        ``(synthesiser, adapter)`` — call ``await synthesiser.asynthesize``
        and read ``adapter.seam_calls`` for the completion count.
    """
    per_round_budget = _widen_for_round_bound(
        total_context_chars, context_window, max_output_tokens, max_rounds
    )
    adapter = SeamLLM(
        context_window=per_round_budget + max_output_tokens + _TEMPLATE_SLACK,
        num_output=max_output_tokens,
        model_name="answer-seam",
        max_rounds=max_rounds,
        seam=seam,
        seam_calls=0,
        last_reply="",
    )
    helper = PromptHelper(
        context_window=per_round_budget + max_output_tokens + _TEMPLATE_SLACK,
        num_output=max_output_tokens,
        chunk_size_limit=per_round_budget,
        tokenizer=_char_tokenizer,
        separator=" ",
    )
    synthesiser = get_response_synthesizer(
        llm=adapter,
        prompt_helper=helper,
        response_mode=ResponseMode.COMPACT,
        use_async=True,
        text_qa_template=text_qa_template or GROUND_TEXT_QA_TEMPLATE,
        refine_template=refine_template or GROUND_REFINE_TEMPLATE,
    )
    return synthesiser, adapter


async def run_synthesis(
    query: str,
    nodes: list[NodeWithScore],
    *,
    seam: CompletionSeam,
    context_window: int,
    max_output_tokens: int,
    max_rounds: int,
) -> tuple[str, int]:
    """Synthesise an answer over ``nodes`` through the seam.

    Args:
        query: The user query.
        nodes: Scored nodes whose texts carry the ``[n]`` source labels.
        seam: Async completion seam.
        context_window: Per-round character budget.
        max_output_tokens: Reply head-room.
        max_rounds: Maximum completion rounds.

    Returns:
        ``(answer_text, completion_calls)``.
    """
    nodes, total = _fit_and_measure(nodes, context_window, max_output_tokens, max_rounds)
    synthesiser, adapter = build_synthesiser(
        seam=seam,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        max_rounds=max_rounds,
        total_context_chars=total,
    )
    response = await synthesiser.asynthesize(query, nodes)
    return str(response), adapter.seam_calls


#: Unique sentinel reply that stops a planning replay: never produced by
#: a real completion, so it can stand for "the pipeline asked for another
#: round" without ambiguity.
_STOP_REPLY = "__OMRG_PLAN_STOP__"


async def plan_next_prompt(
    query: str,
    nodes: list[NodeWithScore],
    *,
    previous_replies: list[str],
    context_window: int,
    max_output_tokens: int,
    max_rounds: int,
) -> str | None:
    """Return the prompt the next completion round would receive, or None.

    Runs the same deterministic synthesis the pipeline runs, replaying
    ``previous_replies`` as the seam's answers; when the synthesiser
    asks for a further round the captured prompt is returned.  When the
    previous replies already complete the synthesis, ``None`` is
    returned — no further round is needed.

    The MCP transport's MRTR resolvers use this to ask the client for
    exactly the prompt the pipeline will consume (design D6: core owns
    prompt construction; the replay guarantees agreement by construction).
    Evidence is fitted under the hard prompt ceiling exactly as
    :func:`run_synthesis` fits it, so the planned prompt and the
    consumed prompt agree even when truncation occurred.
    """
    nodes, total = _fit_and_measure(nodes, context_window, max_output_tokens, max_rounds)
    prompts: list[str] = []
    state: dict[str, Any] = {"served": 0}

    async def _replay_seam(prompt: str) -> str:
        prompts.append(prompt)
        index = state["served"]
        state["served"] += 1
        if index < len(previous_replies):
            return previous_replies[index]
        return _STOP_REPLY

    synthesiser, _adapter = build_synthesiser(
        seam=_replay_seam,
        context_window=context_window,
        max_output_tokens=max_output_tokens,
        max_rounds=max_rounds,
        total_context_chars=total,
    )
    response = str(await synthesiser.asynthesize(query, nodes))
    if response.strip() == _STOP_REPLY:
        # The synthesiser asked for round len(previous_replies)+1 and was
        # handed the sentinel: the captured prompt is the next round's.
        return prompts[len(previous_replies)]
    return None
