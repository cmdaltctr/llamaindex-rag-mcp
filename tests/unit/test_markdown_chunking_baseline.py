"""Stage 1 baseline for Markdown chunking (tasks 1.3 and 1.4).

Records the CURRENT Markdown pipeline behaviour — MarkdownNodeParser →
SentenceSplitter → heading/prepend/drop hooks — on the committed fixture
``tests/fixtures/markdown_baseline.md`` at a small budget (128 tokens,
overlap 25), so the stage 3 model-token-aware splitter lands as a visible
diff. Pins are observed, not idealised:

- SentenceSplitter counts tokens with tiktoken ``cl100k_base`` (the
  llama-index default on this lock) and honours the configured budget.
- Heading-bounded sections that fit stay single chunks; the table unit
  stays intact; the oversized Delta section sub-splits into exactly 3
  continuation chunks under its parent's ``header_path``.
- Task 1.4: the small-chunk filter estimates tokens as
  ``len(text) // 4`` (four characters per token, per the 6b/6c reports);
  the committed CJK fixture demonstrates why that disagrees with a real
  Qwen tokenizer on multibyte text. The real-Qwen leg is skipped unless a
  Qwen tokenizer is already in the local Hugging Face cache — this suite
  never downloads models.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
BASELINE_MD = FIXTURES_DIR / "markdown_baseline.md"
CJK_MD = FIXTURES_DIR / "markdown_cjk_estimate.md"

BUDGET = 128
OVERLAP = 25


def _cl100k():
    """The tokenizer SentenceSplitter uses by default on this lock."""
    import tiktoken

    return tiktoken.get_encoding("cl100k_base")


def _chunk_markdown(text: str, settings) -> list:
    """Run the exact production markdown route (sentence.py + hooks)."""
    from llama_index.core import Document

    from omrg.core.chunking.markdown import (
        apply_heading_prepend,
        drop_small_markdown_chunks,
        ensure_heading_metadata,
    )
    from omrg.core.chunking.sentence import _split_documents_sync
    from omrg.core.settings import resolve_effective_settings

    resolved = resolve_effective_settings(settings)
    nodes = _split_documents_sync([Document(text=text)], True, BUDGET, OVERLAP)
    ensure_heading_metadata(nodes)
    apply_heading_prepend(nodes, resolved.chunking.markdown_heading_prepend)
    return drop_small_markdown_chunks(nodes, BUDGET, resolved.chunking.markdown_min_chunk_fraction)


# ---------------------------------------------------------------------------
# Task 1.3 — chunk boundaries and token-size behaviour
# ---------------------------------------------------------------------------


def test_markdown_chunk_boundaries_baseline(effective_settings) -> None:
    """Record the current chunk map for the baseline fixture at 128/25.

    Observed and pinned on 2026-09-06 (llama-index-core 0.14.23,
    tiktoken cl100k_base):

    - 7 chunks total; every chunk within the 128-token budget;
    - H1 + intro merge into one chunk; Alpha, Beta (list), and Gamma
      (table) each stay one intact chunk;
    - the oversized Delta section sub-splits into exactly 3 continuation
      chunks carrying the Gamma Table header path.
    """
    settings = effective_settings()  # defaults: prepend False, drop filter disabled
    nodes = _chunk_markdown(BASELINE_MD.read_text(encoding="utf-8"), settings)
    tokenizer = _cl100k()

    # Recorded chunk count and budget contract.
    assert len(nodes) == 7
    token_counts = [len(tokenizer.encode(n.text)) for n in nodes]
    assert max(token_counts) <= BUDGET
    # Heading boundaries: Alpha and Beta never share a chunk.
    alpha = [n for n in nodes if "OMRG-ALPHA-77" in n.text]
    beta = [n for n in nodes if "- beta item" in n.text]
    assert len(alpha) == 1 and len(beta) == 1
    assert "beta item" not in alpha[0].text
    assert "OMRG-ALPHA-77" not in beta[0].text

    # The bullet list stays together when it fits.
    bullet_markers = ("- beta item one", "- beta item two", "- beta item three")
    assert all(marker in beta[0].text for marker in bullet_markers)

    # The table unit stays intact: header and both data rows in one chunk.
    gamma = [n for n in nodes if "| name | qty | price |" in n.text]
    assert len(gamma) == 1
    assert "| bolt |" in gamma[0].text and "| nut  |" in gamma[0].text
    assert len(tokenizer.encode(gamma[0].text)) <= BUDGET

    # H1 and its intro paragraph merge into the first chunk.
    assert nodes[0].text.startswith("# Baseline Markdown Fixture")
    assert "Intro paragraph" in nodes[0].text

    # header_path comes from the markdown itself (baseline format pin).
    assert alpha[0].metadata["header_path"] == "/Baseline Markdown Fixture/"
    delta_chunks = [
        (i, n)
        for i, n in enumerate(nodes)
        if n.metadata["header_path"] == "/Baseline Markdown Fixture/Gamma Table/"
    ]
    assert len(delta_chunks) == 3, "Delta section sub-splits into exactly 3 chunks at this budget"
    assert all(token_counts[i] <= BUDGET for i, _ in delta_chunks)


def test_budget_forces_oversized_section_to_split(effective_settings) -> None:
    """Only the oversized Delta section produces multiple chunks.

    Header paths are shared by sibling sections, so the oversized section
    is identified by its text: every Delta continuation chunk keeps the
    enclosing Gamma Table ancestry from the markdown itself.
    """
    settings = effective_settings()
    nodes = _chunk_markdown(BASELINE_MD.read_text(encoding="utf-8"), settings)

    delta = [n for n in nodes if "delta section repeats" in n.text]
    assert len(delta) >= 2, "the oversized section must sub-split at this budget"
    assert all(
        n.metadata["header_path"] == "/Baseline Markdown Fixture/Gamma Table/" for n in delta
    ), "every continuation chunk keeps the enclosing heading ancestry"

    # Sibling sections stay single chunks (identified by unique markers).
    singles = {
        "OMRG-ALPHA-77": "/Baseline Markdown Fixture/",
        "- beta item one": "/Baseline Markdown Fixture/",
        "| name | qty | price |": "/Baseline Markdown Fixture/",
    }
    for marker, expected_path in singles.items():
        carriers = [n for n in nodes if marker in n.text]
        assert len(carriers) == 1, marker
        assert carriers[0].metadata["header_path"] == expected_path


# ---------------------------------------------------------------------------
# Task 1.4 — four-characters-per-token estimate vs a real Qwen tokenizer
# ---------------------------------------------------------------------------


def _markdown_nodes(text: str) -> list:
    from llama_index.core import Document
    from llama_index.core.node_parser import MarkdownNodeParser

    return MarkdownNodeParser().get_nodes_from_documents([Document(text=text)])


def test_four_char_estimate_drops_small_cjk_section() -> None:
    """The small-chunk filter estimates tokens as ``len(text) // 4``.

    Task 1.4 regression fixture: on the committed CJK fixture the whole
    section is well under 128 characters, so ``int(128 * 4 * 0.25) == 128``
    estimate chars drop it — although a real Qwen tokenizer counts CJK at
    close to one token per character and would keep it (asserted by the
    cached-tokenizer leg below when a local Qwen tokenizer exists).
    """
    from omrg.core.chunking.markdown import drop_small_markdown_chunks

    nodes = _markdown_nodes(CJK_MD.read_text(encoding="utf-8"))
    cjk_node = next(n for n in nodes if "汉字" in n.text)

    # Precondition: the node is small in characters but far above 32 real
    # CJK tokens (CJK tokenizes at roughly one token per character).
    node_len = len(cjk_node.text)
    assert 32 <= node_len < 128, f"fixture precondition broken: node is {node_len} chars"

    # ASCII control sits between the *4 and *5 keep thresholds so the
    # assertion can tell the four-char estimate apart from a five-char one.
    control = SimpleNamespace(text="x" * 155)
    kept = drop_small_markdown_chunks([cjk_node, control], chunk_size=128, min_chunk_fraction=0.25)

    assert int(128 * 4 * 0.25) == 128  # the estimate threshold in chars
    assert cjk_node not in kept, "the estimate must drop the small CJK section"
    assert control in kept, "the estimate keeps ASCII nodes at/above the char floor"


def _find_local_qwen_tokenizer() -> Path | None:
    """Locate a Qwen tokenizer.json already in the local HF cache."""
    cache = Path.home() / ".cache" / "huggingface" / "hub"
    candidates = sorted(cache.glob("models--Qwen*/snapshots/*/tokenizer.json"))
    return candidates[0] if candidates else None


def test_qwen_tokenizer_disagrees_with_char_estimate() -> None:
    """With a locally cached Qwen tokenizer: real count ≫ len(text) // 4.

    Skipped unless a Qwen tokenizer.json is already on disk — this suite
    must not download models. The committed fixture plus the arithmetic
    pin above carry the regression when it skips.
    """
    tokenizer_path = _find_local_qwen_tokenizer()
    if tokenizer_path is None:
        pytest.skip("no Qwen tokenizer.json in the local Hugging Face cache; not downloading")

    from tokenizers import Tokenizer

    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    nodes = _markdown_nodes(CJK_MD.read_text(encoding="utf-8"))
    cjk_node = next(n for n in nodes if "汉字" in n.text)

    real_tokens = len(tokenizer.encode(cjk_node.text).ids)
    estimate = len(cjk_node.text) // 4
    # The filter floor is 0.25 * 128 == 32 tokens; CJK text clears it in
    # real tokens while the four-char estimate lands far below it.
    assert estimate < 32 <= real_tokens
    assert real_tokens > estimate, "the recorded disagreement is gone"
