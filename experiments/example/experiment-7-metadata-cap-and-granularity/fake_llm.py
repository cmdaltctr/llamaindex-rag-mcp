"""Deterministic fake LLM for Experiment 7 (protocol section 3).

Subclasses LlamaIndex's ``MockLLM`` so it satisfies the pydantic
``SerializeAsAny[LLM]`` validation inside TitleExtractor /
KeywordExtractor / SummaryExtractor, and overrides ``apredict`` — the one
method the locked extractors call — to return marker-derived deterministic
outputs while recording every call.

Call classification uses the locked default template fingerprints of the
three extractors (llama-index 0.14.23,
``llama_index/core/extractors/metadata_extractors.py``); the templates are
also recorded per call so a template change upstream is visible in the
artefacts instead of silently misclassifying.

Output templates (pre-registered in ``fixtures/manifest.json`` before any
treatment run): each fake output embeds the FIRST ``MARKnnnnX`` marker
found in the prompt context, so every chunk yields intentionally different
per-chunk titles/keywords/summaries (protocol section 9).
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from llama_index.core.llms import MockLLM
from pydantic import PrivateAttr

MARKER_RE = re.compile(r"MARK(\d{4})X")

TEMPLATE_FINGERPRINTS = {
    "keyword": "unique keywords for this",
    "title_node": "Give a title that summarizes all of",
    "title_combine": "candidate titles and content",
    "summary": "Summarize the key topics and entities",
}

OUTPUT_TEMPLATES = {
    "keyword": "KW{marker}A, KW{marker}B",
    "summary": "Summary for marker {marker} of the corpus section.",
    # Title candidates carry the full MARKnnnnX token so the combine call's
    # context still exposes chunk 0's marker to MARKER_RE.
    "title_node": "Title node MARK{marker}X",
    "title_combine": "Combined title {marker}",
}


def classify_call(prompt: Any, prompt_args: dict[str, Any]) -> str:
    """Classify one extractor call by its locked template fingerprint."""
    if "keywords" in prompt_args:
        return "keyword"
    try:
        template = str(prompt.get_template())
    except Exception:
        template = ""
    for kind, fingerprint in TEMPLATE_FINGERPRINTS.items():
        if fingerprint in template:
            return kind
    return "unclassified"


def context_marker(context: str) -> str:
    """Return the first ``MARKnnnnX`` marker digits in *context*, or 0000."""
    match = MARKER_RE.search(context)
    return match.group(1) if match else "0000"


def fake_output(kind: str, context: str) -> str:
    """Return the pre-registered deterministic output for one call."""
    return OUTPUT_TEMPLATES.get(kind, "UNCLASSIFIED {kind}").format(
        marker=context_marker(context), kind=kind
    )


class CountingMockLLM(MockLLM):
    """MockLLM that records every extractor call and answers deterministically."""

    _calls: list[dict[str, Any]] = PrivateAttr(default_factory=list)

    @property
    def calls(self) -> list[dict[str, Any]]:
        """Return the recorded call log (kind, marker, context hash, output)."""
        return self._calls

    async def apredict(self, prompt: Any, **prompt_args: Any) -> str:  # noqa: D102
        kind = classify_call(prompt, prompt_args)
        context = str(prompt_args.get("context_str", ""))
        output = fake_output(kind, context)
        self._calls.append(
            {
                "kind": kind,
                "marker": context_marker(context),
                "context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest(),
                "context_chars": len(context),
                "output": output,
            }
        )
        return output


def summarise_calls(calls: list[dict[str, Any]]) -> dict[str, Any]:
    """Return a deterministic (order-independent) summary of a call log.

    Call-log append order depends on the extractors' job scheduling; the
    sorted per-kind marker lists keep cell artefacts byte-stable across
    reruns regardless of interleaving.
    """
    by_kind: dict[str, list[str]] = {}
    for call in calls:
        by_kind.setdefault(call["kind"], []).append(call["marker"])
    return {
        "total_calls": len(calls),
        "kinds": {kind: sorted(markers) for kind, markers in sorted(by_kind.items())},
        "context_sha256_set": sorted({call["context_sha256"] for call in calls}),
    }
