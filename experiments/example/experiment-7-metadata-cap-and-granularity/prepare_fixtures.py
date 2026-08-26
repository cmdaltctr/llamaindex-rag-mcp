"""Generate the Experiment 7 fixture documents (protocol section 3).

Writes two deterministic synthetic documents under ``fixtures/``:

- ``synthetic_token_char_divergence.txt`` — blocks that alternate
  short-token, long-token, and CJK/punctuation content so token count and
  character count diverge strongly per chunk; every block carries a unique
  ``MARKnnnnX`` marker.
- ``realistic_long_document.md`` — a realistic long Markdown article
  (headings, paragraphs, bullet lists, one fenced code block, one table)
  with a marker sentence every second section.

No randomness, no timestamps: identical bytes on every regeneration.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES_DIR = SCRIPT_DIR / "fixtures"

LONG_WORDS = [
    "internationalisation",
    "characterisation",
    "responsibilities",
    "comprehensiveness",
    "interoperability",
    "disproportionately",
    "unconstitutional",
    "misinterpretations",
]
SHORT_LETTERS = "abcdefghij"
CJK_WORDS = ["図書館", "検索", "要約", "量子", "文献", "分析", "要約", "検索"]

MARKER_A = "MARK{index:04d}X"
MARKER_B = "MARK{index:04d}X"


def synthetic_block(index: int) -> list[str]:
    """Build one divergence block (~110 tokens) with a unique marker."""
    kind = index % 3
    lines = [f"Block {index:03d} reference {MARKER_A.format(index=index)}."]
    if kind == 0:
        # Short tokens: one-letter words, roughly 2 chars per token.
        for row in range(4):
            letters = " ".join(SHORT_LETTERS[(row + offset) % 10] for offset in range(28))
            lines.append(f"letters {row:02d}: {letters}.")
    elif kind == 1:
        # Long tokens: multi-syllable words, 10+ chars per token.
        for row in range(4):
            words = " ".join(LONG_WORDS[(row + offset) % len(LONG_WORDS)] for offset in range(6))
            lines.append(f"lexemes {row:02d}: {words}.")
    else:
        # CJK/punctuation-dense lines: characters the default tokenizer
        # encodes near one token per character.
        for row in range(4):
            words = " ".join(CJK_WORDS[(row + offset) % len(CJK_WORDS)] for offset in range(7))
            lines.append(f"corpus {row:02d}: {words}.")
    lines.append("")
    return lines


def build_synthetic_document() -> str:
    """Build the token/char divergence document (~70 blocks)."""
    lines = ["Synthetic token-character divergence corpus.", ""]
    for index in range(70):
        lines.extend(synthetic_block(index))
    return "\n".join(lines).rstrip("\n") + "\n"


SECTION_TOPICS = [
    ("retrieval", "Retrieval quality depends on the corpus, the embedder, and the ranking policy."),
    ("chunking", "Chunk boundaries decide whether a retrieved passage answers the question alone."),
    ("metadata", "File-level metadata gives every stored chunk the same provenance labels."),
    ("evaluation", "Paired designs remove corpus variance when comparing two retrieval arms."),
    ("thresholds", "A similarity threshold trades coverage for precision on every query."),
    ("storage", "Vector stores differ in distance metrics, filters, and generation semantics."),
    (
        "reranking",
        "A cross encoder reorders candidates but inherits the candidate pool's blind spots.",
    ),
    (
        "observability",
        "Runtime manifests make a reported number attributable to what actually ran.",
    ),
]
PARA_SENTENCES = [
    "The pipeline reads the document once and splits it with the declared splitter.",
    "Every chunk inherits the file-level metadata dictionary after aggregation.",
    "The extractor budget bounds how many chunks reach the expensive stage.",
    "Deterministic fixtures keep the comparison reproducible across reruns.",
    "The cap is expressed in chunk units rather than character units.",
    "Section markers let the harness attribute each call to its source chunk.",
]


def build_realistic_document() -> str:
    """Build the realistic Markdown article (~36 sections, 2 markers per 3)."""
    lines = [
        "# Long Document Evaluation Corpus",
        "",
        "A realistic Markdown article for metadata-extraction budget tests. "
        "Reference marker MARK1000X opens the corpus.",
        "",
    ]
    marker = 1001
    for section in range(24):
        topic, lead = SECTION_TOPICS[section % len(SECTION_TOPICS)]
        lines.append(f"## {topic.capitalize()} notes {section:02d}")
        lines.append("")
        lines.append(lead)
        lines.append("")
        for paragraph in range(3):
            sentences = [
                PARA_SENTENCES[(section + paragraph + offset) % len(PARA_SENTENCES)]
                for offset in range(5)
            ]
            lines.append(" ".join(sentences))
            # One marker per paragraph keeps every chunk's first marker
            # unique: marker spacing (~100 tokens) is far below the chunk
            # advance (chunk_size - overlap = 412 tokens).
            lines.append(f"Reference marker {MARKER_B.format(index=marker)}.")
            lines.append("")
            marker += 1
        if section == 7:
            lines.append("### Worked example")
            lines.append("")
            lines.append("```python")
            lines.append("def budget(chunks, cap):")
            lines.append("    return chunks[:cap]")
            lines.append("```")
            lines.append("")
        if section == 13:
            lines.append("| stage | unit | bounded by |")
            lines.append("|---|---|---|")
            lines.append("| split | chunk | splitter settings |")
            lines.append("| extract | chunk | configured cap |")
            lines.append("| store | file | aggregated metadata |")
            lines.append("")
        lines.append("- First bullet restates the section topic.")
        lines.append("- Second bullet notes the paired comparison.")
        lines.append("- Third bullet records the marker attribution.")
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    synthetic = build_synthetic_document()
    realistic = build_realistic_document()
    (FIXTURES_DIR / "synthetic_token_char_divergence.txt").write_text(synthetic, encoding="utf-8")
    (FIXTURES_DIR / "realistic_long_document.md").write_text(realistic, encoding="utf-8")
    print(
        f"wrote synthetic ({len(synthetic)} chars) and realistic ({len(realistic)} chars)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
