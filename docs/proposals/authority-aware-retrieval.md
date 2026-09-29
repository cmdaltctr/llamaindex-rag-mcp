# Authority-Aware Retrieval: Separating Relevance from Authority in RAG

**Paper 1 of the fellowship programme.** Companion to
[mantiq-reasoning-gates.md](./mantiq-reasoning-gates.md).
OpenSpec change: `openspec/changes/authority-aware-retrieval/`.

## Summary

A retrieval-augmented generation (RAG) system ranks passages by how well they
match the question. It does not ask whether a passage still applies. When a
corpus holds a 2024 handbook, a 2025 addendum for regulated staff, and a 2026
handbook that replaces the 2024 one, all three are real documents, all three
stay indexed, and all three can score highly on the same query. The system
hands the language model an obsolete rule and its replacement side by side and
leaves the model to guess.

This proposal adds an opt-in authority layer to OMRG, our modular RAG
framework. At ingestion it extracts typed, evidence-bearing relations between
documents: one corroborates, explains, specialises, restricts, amends or
supersedes another, or conflicts with it. At query time a deterministic
resolver reads those relations and tags each candidate as controlling,
qualified, superseded, historical or in unresolved conflict. It never drops a
passage. The reranker then orders the tagged passages as before.

The resolution ordering comes from uṣūl al-fiqh, the Islamic science of legal
method, and its treatment of apparently conflicting evidences. Reconcile
before you declare supersession. The specific qualifies the general. The
restricted qualifies the unrestricted. Supersession needs evidence. When
nothing resolves the conflict, say so. We use this as an engineering
abstraction. We do not digitise jurisprudence.

## The problem in one page

Vector similarity measures how close two texts are in meaning. Two versions of
the same policy are very close in meaning. That is the whole difficulty. The
old rule and the new rule land next to each other in the result list, and the
model receives both.

Three tempting fixes fail.

1. **Newest file wins.** File dates are weak evidence. A parser change can
   give a document a new index version without any change in the world. An
   addendum that narrows a rule is newer than the rule but does not replace it.
2. **Let the reranker sort it out.** The reranker answers "which passage best
   matches the question". That is relevance. Whether a passage is still in
   force is a different question. One model cannot answer both with one score.
3. **Delete superseded documents.** "What was the policy in March 2023?" then
   has no answer. Superseded does not mean false. It means not controlling for
   the present date.

The failure is not rare. It appears in employment policy, contracts and
amendments, regulations, technical standards, API documentation across
versions, clinical guidance and organisational procedures. Any domain where
"which text applies" matters as much as "which text is similar" has it.

## What exists already in OMRG

The framework already has the foundations this layer needs.

- **Stable source and chunk lineage** (ADR-052). Every chunk carries a
  `source_id`, `source_version` and `chunk_id`. Replacing a document in place
  is failure-safe. We know where every passage came from.
- **Hybrid retrieval.** Dense and sparse retrieval fused with reciprocal rank
  fusion, then an optional cross-encoder reranker. The stage boundaries are
  explicit in `core/retrieval/pipeline.py`.
- **A strategy registry.** A new retrieval stage is one file plus one
  `register()` line. Dispatch never branches on strategy names.
- **A document graph** in `core/documents/`. It already builds typed edges
  between chunks, but the types are similarity, category, keyword and heading.
  It can propose candidate pairs. It cannot say how they relate.
- **Claim verification** (ADR-059). The answer pipeline can already judge a
  claim as supported, contradicted or unsupported by its cited evidence. It
  needs the evidence set to be sound first.

Provenance is solved. Authority is not. The gap is one layer: the relations
between sources.

## The idea

### A relation vocabulary

Seven directed relations, each stored with the evidence that produced it.

| Relation | Meaning | Classical analogue |
|---|---|---|
| corroborates | B states a compatible rule to A | jamʿ, reconciliation |
| explains | B clarifies or elaborates A | bayān |
| specialises | B applies to a subset of A's scope | takhṣīṣ, the specific qualifies the general |
| restricts | B adds a condition to A | taqyīd, the restricted qualifies the unrestricted |
| amends | B replaces part of A | partial naskh |
| supersedes | B replaces A in full | naskh, abrogation |
| conflicts_with | both apply and nothing resolves them | taʿāruḍ with tawaqquf, suspend judgement |

Each edge records the source and target `source_id`, a scope (whole document,
section or clause), effective dates, the chunk that supplied the evidence, the
evidence text, its origin (explicit text, metadata or model) and a confidence.
A user can ask "why did you ignore the 2024 policy?" and get "because the 2026
policy states that it supersedes it" with the sentence quoted.

### A resolution ordering

The resolver applies the uṣūl ordering, not a similarity score and not a date.

1. Do both texts apply to this question at all?
2. Can they both be true? If so, keep both, mark corroborates or explains.
3. Is one more specific? Keep both, apply the specific within its scope.
4. Does one add a condition? Keep both, apply the condition.
5. Is there explicit evidence of amendment or supersession? Mark it, keep
   the older text as historical.
6. If none of the above, mark an unresolved conflict and surface it.

### Two principles that shape everything

**Relevance and authority stay separate.** The resolver runs after fusion and
before the reranker. It annotates. The reranker orders. Neither does the
other's job.

**Deterministic first, model second.** Explicit supersession language,
effective-date clauses and clause references are found by rules and marked
`explicit_text`. A local decision model may type harder pairs, marked `model`
with a probability, and only when the operator turns it on. Model-typed edges
never enter the document graph, so the invariant that graph construction is
deterministic holds.

## Architecture

```
ingest ──► chunk ──► embed ──► store
              │
              └──► [authority extractor]  ──► relation sidecar
                   (opt-in, per profile)      authority/relations.jsonl
                                              one record per edge

search ──► dense + sparse ──► RRF ──► [authority resolver] ──► reranker ──► results
                                       (opt-in, per profile)
                                       loads the sidecar,
                                       tags each row,
                                       drops nothing
```

- New package `core/authority/` with settings, relations, extract, resolve and
  storage modules. It shares only settings with ingestion and retrieval.
- Settings block `AuthorityBlock`, `enabled: false` by default, env prefix
  `AUTHORITY__`. The `documents` profile may enable it. The `codebase` profile
  keeps it off.
- Registered as the `"authority"` retrieval strategy. When disabled the search
  path is byte-identical to today.
- Relations live in a per-collection sidecar, not in vector rows, so they
  survive source replacement and work the same on LanceDB and Chroma.
- `search_documents` gains an optional `as_of` date. With it, a superseded
  passage becomes controlling for that date when the edge's effective window
  covers it.
- Each result row gains `authority_status` and `authority_reason`. The result
  envelope gains a `conflicts` list when the resolver cannot decide.
- The model tier is built in `compose.py` and injected as a callable, the same
  pattern as the reranker and the verify judge. No PyTorch on the default path.

## Evaluation plan

### Experiment 38: five cases, five metrics

A synthetic corpus of fifteen documents, three per case type, with about sixty
questions labelled with controlling, qualifying and superseded sources, an
`as_of` date where relevant, and an unresolved-conflict flag.

| Case | Expected behaviour |
|---|---|
| Full supersession | Current query returns the new text. Historical query returns the old. |
| General plus specific | Both kept. The exception applies only inside its scope. |
| Partial amendment | The original stays controlling except for the amended clause. |
| Corroboration | Both kept. No conflict manufactured. |
| Unresolved conflict | The conflict is reported, not silently resolved. |

Ordinary recall at k does not capture these. Five pre-registered metrics do.

1. **Stale authority rate.** How often an obsolete rule is returned as
   controlling. Lower is better.
2. **Incorrect supersession rate.** How often a valid general or historical
   rule is wrongly suppressed.
3. **Scope resolution accuracy.** How often a specific exception is applied
   only to its correct subset.
4. **Conflict detection recall.** When two applicable sources conflict, how
   often the system flags it.
5. **Historical authority accuracy.** For dated questions, how often the rule
   in force on that date is returned.

The second half of the experiment repeats the protocol on a real corpus: one
UK Act with several amending instruments from legislation.gov.uk, which gives
genuine partial amendment and point-in-time ground truth.

### Ablations

- Baseline hybrid retrieval with no authority stage.
- Newest-document-wins heuristic.
- Deterministic tier only.
- Deterministic plus model tier.
- Resolver with the reconciliation step removed, to show that "reconcile
  before supersede" earns its place.

### Relation typing models

Relation typing is a closed-choice task, so it suits small decision models. A
separate set of about 200 labelled passage pairs will compare three options
before any is adopted: Julia 1, a 144M-parameter open-weight decision model
that runs on CPU through ONNX; an NLI cross-encoder mapped onto the vocabulary;
and a small local language model. The comparison is a paper artefact in its
own right. The published Julia 1 benchmarks are hundred-item pilots in other
domains, so nothing is assumed until measured.

## Related work and how this differs

The knowledge-conflict literature is active in 2026. ConflictRAG (arXiv
2605.17301) detects and classifies conflicts and scores source credibility.
ArbGraph (2604.18362) builds a claim graph with support and contradiction
edges and arbitrates before generation. EvoTrustRAG (2608.07933) asks whether a
conflict reflects knowledge evolution, an intervention, or remains unresolved.
All three reduce the question to "which claim wins". None distinguishes a text
that narrows another from one that replaces it, and none keeps a superseded
text as controlling for a past date.

SAT-Graph RAG (de Martim, 2505.00039, with the API paper 2510.06002) is the
nearest structural rival. It models versioned legal norms as a temporal graph
and supports point-in-time retrieval. It needs a hand-built ontology of one
legal corpus, its relations are structural rather than normative, and it has
no notion of the specific qualifying the general.

The difference here is a typed normative vocabulary, a resolution ordering with
a documented methodological origin, evidence stored on every edge, an explicit
refusal state, and a design that runs over an ordinary chunk store with the
whole layer switchable off.

## Timeline

Sixteen weeks from October 2026 to the end of January 2027.

| Weeks | Deliverable |
|---|---|
| 1 to 2 | OpenSpec change reviewed, synthetic corpus and questions built, metrics frozen |
| 3 to 6 | `core/authority/` extractor, sidecar, resolver, registry wiring, tests at the 95 percent tier |
| 7 to 9 | Experiment 38 on the synthetic corpus, then the UK statute corpus |
| 10 to 12 | Ablations, relation-typing model comparison, ADR, write-up |
| 13 to 16 | Paper draft, reproducibility package, arXiv preprint, venue submission |

Paper 2 starts its own proposal in parallel from about week 10, since it
consumes this layer's labelled evidence set.

## Target venues

SIGIR or ECIR for the retrieval framing. JURIX or ICAIL if the legal corpus
becomes the centre of the paper. ACL Findings if the framing leans towards
language processing. The Muslims in ML workshop at NeurIPS is a low-cost first
airing for the methodological origin.

## Risks and mitigations

- **Reviewers dismiss the uṣūl framing as decoration.** Present it as the
  source of a concrete, testable ordering. Cite primary sources (al-Shāfiʿī's
  Risāla, al-Ghazālī's Mustaṣfā, Ibn Qutayba's Taʾwīl Mukhtalif al-Ḥadīth) and
  Kamali's English treatment. Keep the mapping table tight and mark every
  loose point as an analogy.
- **Rule-based extraction misses relations that lack explicit language.**
  Report the miss rate honestly. The model tier exists for this case and is
  measured separately.
- **Pairwise typing is quadratic.** The document graph's similarity edges and
  shared clause references act as the pair proposer. Only proposed pairs are
  typed.
- **The synthetic corpus is too easy.** The UK statute half of the experiment
  exists to answer this. Report both.
- **The field moves before publication.** Preprint by week 16. The
  benchmark and metrics are released regardless of venue outcome.
- **The Julia 1 ONNX path may not run in Python.** A smoke test comes first.
  If it fails, the model stays behind the optional `torch` extra and the
  NLI cross-encoder becomes the default model tier candidate.

## Out of scope

- Concept formation before retrieval and inference validation after
  verification. Both belong to Paper 2, `mantiq-reasoning-gates`.
- Two-pass answer generation. The MCP client owns final synthesis.
- Any change to reranker behaviour or defaults.
- Automatic deletion of superseded documents.
- A general knowledge graph. The relation sidecar carries normative
  relations only.
