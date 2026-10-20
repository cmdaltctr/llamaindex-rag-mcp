"""Grounded-answer prompt templates.

Adapted from llama-index's ``CITATION_QA_TEMPLATE`` (upstream prose is
better-tested than a fresh attempt): the instruction block tells the
model to answer only from the supplied sources, to cite the bracketed
source numbers, and to state plainly when the sources do not support an
answer — citing the sources it examined when it says so.

The pipeline labels every supplied chunk with its 1-based ordinal in
square brackets (``[1]``, ``[2]`` ...) inside the node text, so the
context joined below carries the citation numbers by construction and
citation ordinals parsed back out of the answer text refer to rows the
system supplied — never to identifiers the model invented.
"""

from __future__ import annotations

from llama_index.core.prompts import PromptTemplate

#: Layout rules for the reply. Chat renders the answer as Markdown, and a
#: model that gets no layout rules tends to write one dense block. The
#: citation rule keeps a marker on the line of the claim it supports.
_LAYOUT_RULES = (
    "Write the answer in Markdown that is easy to scan.\n"
    "Use short paragraphs of one to three sentences, with a blank line "
    "between paragraphs.\n"
    "Use a numbered list for steps that happen in order. Use a bulleted "
    "list for items that have no order.\n"
    "Add a short heading only when the answer has more than one part.\n"
    "Put commands, file names and option names in backticks. Put a "
    "command that needs more than one line in a fenced code block.\n"
    "Put each citation at the end of the sentence or list item it "
    "supports, on the same line, never on its own line.\n"
)

#: QA template for the first completion round: receives every source
#: label carried by the joined context and the query.
GROUND_TEXT_QA_TEMPLATE = PromptTemplate(
    "You are a retrieval-grounded answering assistant.\n"
    "Context information from retrieved sources is below.\n"
    "Each source starts with its citation number in square brackets, "
    "for example [1].\n"
    "---------------------\n"
    "{context_str}\n"
    "---------------------\n"
    "Given the context information and not prior knowledge, answer the "
    "query.\n"
    "Cite every claim with the bracketed number of the source that "
    "supports it, for example [1] or [2, 3].\n"
    "Use only the provided sources; do not add facts from outside them.\n"
    "If the sources together do not support an answer, say so plainly "
    'and cite the sources you examined, for example: "The provided '
    'sources do not cover this; see [1], [2]."\n'
    f"{_LAYOUT_RULES}"
    "Query: {query_str}\n"
    "Answer: "
)

#: Refine template for COMPACT refinement rounds (variable names follow
#: llama-index's default refine template: ``existing_answer`` and
#: ``context_msg``).
GROUND_REFINE_TEMPLATE = PromptTemplate(
    "The original query is below.\n"
    "---------------------\n"
    "{query_str}\n"
    "---------------------\n"
    "We have provided an existing answer: {existing_answer}\n"
    "We have the opportunity to refine the existing answer (only if "
    "needed) with some more context below.\n"
    "---------------------\n"
    "{context_msg}\n"
    "---------------------\n"
    "Given the new context, refine the original answer to better answer "
    "the query.\n"
    "Keep every bracketed citation number already present, and cite any "
    "newly used source with its bracketed number, for example [1] or "
    "[2, 3].\n"
    "Keep the layout of the answer: short paragraphs, a numbered list for "
    "ordered steps, a bulleted list for unordered items, and each "
    "citation on the line of the claim it supports.\n"
    "If the context is not useful, return the original answer unchanged.\n"
    "Refined Answer: "
)
