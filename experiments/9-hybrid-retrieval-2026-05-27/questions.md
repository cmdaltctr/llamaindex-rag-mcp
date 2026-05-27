# Exp 9 — Ground-Truth Queries (Human-Readable)

19 queries total. The companion machine-readable file is `ground-truth.json`.

| Partition          | Count | Goal                                                  |
| ------------------ | ----- | ----------------------------------------------------- |
| Rare-term          | 8     | Hybrid should beat dense-only by ≥ 10 pp on Hit@1     |
| Semantic           | 6     | Hybrid should match dense-only within −2 pp           |
| Mixed (general)    | 5     | Sanity — no regression                                |
| **Named cases**    | 2     | Colosseum (must hit) and BM25-only MCP-1138 case      |
| **Total**          | **19**|                                                       |

## Rare-term (8) — exact-token overlap with the gold chunk

These queries contain at least one identifier that the gold document
repeats verbatim. BM25 should rank the gold chunk in the top 5; dense
retrieval frequently does not.

1. **NAMED CASE — Colosseum (regression target).** Where was the Colosseum
   built? → `sample.md` → "Rome".
   This is the documented dense-only failure case from
   `experiments/1-reranker-threshold-calibration-2026-05-12/results.md`.
   Pure dense retrieval scored this at 0.015. Hybrid must hit it at top-1.

2. **NAMED CASE — BM25-only.** What is the resolution for the MCP-1138
   build error? → `mcp-1138-error-codes.md` → "git submodule".
   `MCP-1138` is a coined product code with no semantic content. Dense
   retrieval has nothing to grip onto; BM25 should land it at rank 1.

3. How does `numpy.fft.rfft2` differ from `fft2`? → `numpy-fft-readme.md`
   → "real".

4. What is the BRCA1 protein's role in homologous recombination repair?
   → `brca1-research-note.md` → "RAD51".

5. What does 42 U.S.C. § 1983 allow plaintiffs to sue state actors for?
   → `42-usc-1983-summary.md` → "deprivation".

6. What does the `ECONNREFUSED` error code mean in Node.js?
   → `econnrefused-troubleshooting.md` → "actively rejected".

7. What is the I²C address of the SCD41 element on the XK-2034b sensor
   module? → `xk-2034b-product-spec.md` → "0x62".

8. Under EU Reg. 2016/679, what is the maximum administrative fine for
   the most serious infringements? → `eu-2016-679-gdpr-summary.md`
   → "€20 million".

## Semantic (6) — minimal content-token overlap with the gold chunk

These queries are written so that, after lowercasing and stop-word
removal, the content-token intersection with the gold document is
**at most three weak tokens** (e.g. "fuel", "framework", "european").
The discriminative vocabulary of the gold document — the terms a BM25
ranker would weight most by IDF — does not appear in the query.

The point is to favour dense retrieval. BM25 should rank the gold
chunk poorly here; if it does not, the corpus or the query needs
tightening. The test is whether RRF fusion preserves the dense win
or whether BM25 pulls in unrelated high-keyword-overlap chunks.

Per-query overlap (computed against the actual document text):

9. What innovation lets GPT-class systems handle long-range word ties
   efficiently? → `transformers.md` → "self-attention".
   Overlap: `lets` only. The discriminative document vocabulary
   ("self-attention", "softmax", "query/key/value", "RoPE",
   "FlashAttention") is absent from the query.

10. What scientific framework explains earthquakes, mountain building,
    and the slow movement of continents? → `plate-tectonics.md`
    → "Plate tectonics".
    Overlap: `explains`, `framework`, `slow`. The document's
    discriminative vocabulary ("plate tectonics", "lithosphere",
    "subduction", "mid-ocean ridge", "Wegener") is absent from the
    query.

11. How do statisticians measure the total economic output of a country?
    → `gdp-economics.md` → "gross domestic product".
    Overlap: empty. The document calls it "GDP", "gross domestic
    product", "value added", "national accounts" — none of which the
    query uses.

12. What kind of car uses a rechargeable cell stack instead of liquid
    fuel? → `electric-vehicles.md` → "battery pack".
    Overlap: `fuel`, `uses`. The document's discriminative vocabulary
    ("electric vehicle", "EV", "battery pack", "lithium-ion",
    "petrol or diesel powertrain") is absent from the query.

13. How do green plants manufacture sugar from atmospheric gases using
    sunlight? → `photosynthesis.md` → "photosynthesis".
    Overlap: `plants`, `using`. The document's discriminative
    vocabulary ("photosynthesis", "chloroplast", "chlorophyll",
    "thylakoid", "ATP", "NADPH", "Calvin cycle") is absent from the
    query.

14. Which city is celebrated for a wrought-iron landmark? → `sample.md`
    → "Paris".
    Overlap: empty. Single-hop semantic — the gold chunk says "Paris.
    It is known for the Eiffel Tower"; the query paraphrases the Eiffel
    Tower as "wrought-iron landmark" without using "Eiffel", "tower",
    or any other discriminative token from the document.

## Mixed (5) — partial overlap, sanity check

These queries blend exact tokens with paraphrase. Hybrid should at
least match dense-only.

15. Tell me about Python data science libraries → `python.txt` →
    "scikit-learn".

16. What is JavaScript used for on the server? → `javascript.txt` →
    "Node.js".

17. How does qualified immunity affect Section 1983 lawsuits against
    police officers? → `42-usc-1983-summary.md` → "qualified immunity".

18. What is the relationship between BRCA1 deficiency and PARP
    inhibitors? → `brca1-research-note.md` → "synthetic lethality".

19. What troubleshooting steps fix a partial git submodule checkout?
    → `mcp-1138-error-codes.md` → "git submodule update --init
    --recursive".

## Notes on the corpus

- The 5 Exp 1 fixtures (`exp1-fixtures/`) keep the Colosseum query alive
  as a regression target and supply the Python/JavaScript content for the
  mixed partition.
- The 8 rare-term docs each centre on one identifier that is repeated
  enough times to dominate BM25's ranking. The identifiers cover the
  five categories called out in the protocol: product code (XK-2034b,
  MCP-1138), library identifier (numpy.fft.rfft2, torch.nn.LayerNorm),
  legal citation (42 U.S.C. § 1983, EU Reg. 2016/679), gene name
  (BRCA1), and error/version code (ECONNREFUSED). torch.nn.LayerNorm is
  in the corpus as a "BM25 trap" — no query targets it, but a poorly
  tokenised BM25 may surface it on rare-term queries that mention
  attention or numerics.
- The 6 semantic-pack queries were each test-tokenised against the gold
  document with `re.findall(r"\\w+", lower(text))`, lowercased, and
  filtered by a small stop-word list. The content-token intersection is
  at most three weak tokens per query (worst case: query 10 with
  `explains`, `framework`, `slow`). The discriminative vocabulary of
  each gold document — the high-IDF terms BM25 weights most — is absent
  from the query. BM25 should rank the gold chunk poorly on these.
- Mixed-partition queries 17 and 18 deliberately target the rare-term
  documents but use paraphrase that still preserves at least one
  identifier ("Section 1983", "BRCA1"). Hybrid should match dense-only
  on these because both retrievers can ground onto the identifier.
