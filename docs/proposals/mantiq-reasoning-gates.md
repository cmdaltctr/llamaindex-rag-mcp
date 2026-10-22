# Manṭiq Reasoning Gates for Retrieval-Augmented Generation

**Paper 2 of the fellowship programme.** Companion to
[authority-aware-retrieval.md](./authority-aware-retrieval.md).
OpenSpec change: `openspec/changes/mantiq-reasoning-gates/`.

## Summary

A retrieval-augmented generation (RAG) system can hold correct evidence and
still give a wrong answer. It can misread a term, treat "may" as "always", or
draw a conclusion the premises do not licence. This proposal adds two opt-in
checks around the answering step of OMRG, our modular RAG framework. The first
check fixes what the question means before we search. The second check tests
whether each conclusion in the answer follows validly from the claims the
evidence supports. Between them sits the claim-verification stage we already
have. The structure follows the classical Islamic logic tradition (Manṭiq),
which separates forming a concept from judging a proposition from drawing an
inference. We use that separation as an engineering pattern. We do not claim
the classical texts describe software.

The headline contribution is the inference gate. Nothing in the current RAG
literature names the inference form, rejects the two classic conditional
fallacies, or refuses a disjunctive conclusion when the alternatives are not
shown to be exhaustive. The concept-formation gate is supporting machinery
and will be judged by a strict ablation.

## The problem

Errors in a RAG answer come from four places.

1. **Concept error.** The system retrieves the wrong sense of a term. "Node"
   in a LlamaIndex repository is not Node.js. "Appeal" in a legal corpus is
   not visual appeal.
2. **Retrieval error.** The right evidence exists and is not found.
3. **Judgement error.** The evidence is found and the answer claims more than
   it supports. "Some" becomes "all". "May" becomes "must".
4. **Reasoning error.** Every premise is correct and the conclusion still does
   not follow. "If backend X is selected, file Y is created. File Y exists.
   So X was selected." That is affirming the consequent.

Retrieval error is well studied. Judgement error at the single-claim level is
what our Experiment 20 measured and ADR-059 addressed. Concept error and
reasoning error have no gate in OMRG today, and we found no RAG system that
gates them explicitly.

## What exists already in OMRG

- **Claim verification (ADR-059).** After the model writes an answer, a judge
  reads each cited sentence with its cited evidence and returns `supported`
  or `unsupported`. Experiment 20 showed a cloud judge reached recall 1.0 and
  false rejection 0.0 on 120 labelled claim-evidence triples. A local 4-billion
  parameter judge was not feasible. This stage is, in classical terms, the
  judgement step (Taṣdīq). Paper 2 leaves it unchanged and adds its own
  four-verdict judge beside it, so people who never turn manṭiq on see no
  difference.
- **Injected answering (ADR-057).** The answer model and the judge are passed
  in from the composition root as async callables. Nothing in the core imports
  a provider. The new gates use the same seam.
- **Authority-aware retrieval (Paper 1).** When Paper 1 lands, each evidence
  row carries a label: controlling, qualified, superseded, historical, not yet
  in force, or in unresolved conflict.
  Paper 2 reads that label to decide which claims may serve as premises. Paper
  2 also works without the label, over plain evidence.

## The idea

The pipeline becomes:

```
query
  → Taṣawwur   (what exactly is being asked?)
  → retrieval  (what evidence exists?)
  → Taṣdīq     (which claims does the evidence support?)
  → Qiyās      (which conclusions follow from the supported claims?)
  → answer     (only validated claims and inferences, with the rest reported)
```

Terms, explained once:

- **Taṣawwur** means forming a concept before judging anything about it. We
  build a small structured *concept frame*: the key terms, the sense of each
  term in this corpus, the canonical concept, what is broader, narrower and
  excluded, whether the question asks for a general rule or one particular
  case, how the question divides into search branches, and an operational
  definition. The frame is checked for three things: it includes what belongs,
  excludes what does not, and does not define a term by itself.
- **Taṣdīq** means assent to a proposition. The manṭiq judge returns four
  verdicts: `supported`, `contradicted`, `unsupported`, `uncertain`. It also
  records the conditions the evidence attached to the claim, such as "may",
  "if", "unless", "only when". `Unsupported` means the evidence does not say
  it. It does not mean the claim is false.
- **Qiyās** (also *istidlāl*) means structured inference. We label each
  multi-premise sentence in the answer with one of five forms: categorical
  chaining, conditional chaining, affirming the antecedent, denying the
  consequent, and disjunctive elimination. Deterministic code then runs the
  checks: every premise is supported; the form is well formed; the conclusion
  does not affirm a consequent or deny an antecedent; a disjunctive conclusion
  is allowed only if the alternatives are shown to be exhaustive; the
  conclusion's modal strength is no stronger than the weakest premise; the
  conclusion names nothing the premises did not.

The model does two closed-choice jobs: label the inference form and extract
the premise structure. It does not grade validity. That keeps the gate
auditable, and it lets us measure labelling accuracy and check correctness
separately.

## Architecture

**Data model.** Four frozen records, all serialisable without a model:

| Record | Produced by | Holds |
|---|---|---|
| `ConceptFrame` | Taṣawwur | terms, senses, canonical concept, broader / narrower / excluded, scope, divisions, definition, validation flags |
| `EvidenceRecord` | retrieval (existing) | chunk text, lineage, scores, optional `authority_status` |
| `ClaimRecord` | Taṣdīq | proposition, cited evidence ids, verdict, conditions, uncertainty reason |
| `InferenceRecord` | Qiyās | premise claim ids, inference type, conclusion, validity, per-check results |

**Five gates.**

1. Concept gate: a frame exists, or the reason it does not.
2. Retrieval gate: the frame rewrites the query text that goes to search.
   For now its include terms, exclude terms and scope reach search only
   through that query text.
3. Judgement gate: every cited claim has a four-way verdict and its
   conditions.
4. Inference gate: every multi-premise sentence has a typed, checked record.
5. Answer gate: only `supported` claims and `valid` inferences reach the
   returned text. Rejected sentences are listed with their failing checks. If
   nothing survives, the answer text stays as written and the manṭiq result
   block says that nothing passed. The base answer statuses never change.

**Where it lives.** Manṭiq is an opt-in plugin. It ships as three pipeline
steps (concept frame, Taṣdīq and Qiyās) and one `answer-mantiq` pipeline
template, in a new package `core/mantiq/`. A user profile turns it on by using
that template. Built-in profiles and every other pipeline stay exactly as they
are, and a test proves today's answers do not change. Gate options are
settings on the pipeline steps, so no global setting is added. The
engineering design is in `openspec/changes/mantiq-reasoning-gates/design.md`.

## Evaluation plan

Three experiments. Numbers up to 43 are taken, so these are 44A to 44C.

**44A. Which judge?** The 120 Experiment 20 triples carry two labels today,
so they are first relabelled into four verdicts, with a blind second-annotator
check. Then rerun them, plus 60 new triples with modal qualifiers. Cells: the
four-verdict manṭiq judge (primary), the existing ADR-059 two-way judge on the
same triples, and the lexical baseline. Whether to add rows for an NLI
cross-encoder or a small local decision model is decided later. Our
Experiment 38 found Julia 1 weaker than Clef-flash on OCR junk detection.
Metrics: four-way macro-F1, unsupported recall, false rejection, exact match
on conditions, P95 latency, cost per claim. A judge is recommended only if it
reaches unsupported recall ≥ 0.90 with false rejection ≤ 0.10 on the original
120. If a local row is added and passes, it removes the cloud dependency that
ADR-059 accepted.

**44B. Does the inference gate catch bad reasoning?** Build 150 to 200 items
from retrieved premises. For each of the five forms: valid instances, the
matching fallacy, a non-exhaustive disjunction, a strengthened qualifier, and
a conclusion with surplus content. Metrics: labelling accuracy per form,
precision and recall per check, invalid-inference rejection rate, and
valid-inference false-rejection rate. Gate: reject ≥ 85 percent of invalid
inferences while wrongly rejecting ≤ 15 percent of valid ones.

**44C. Is the concept frame more than query rewriting?** This is the objection
a reviewer will raise, so we answer it directly. It starts only after
Experiment 35A has run. Cells: raw query,
multi-query rewrite, HyDE-style hypothetical passage, concept frame. Corpus:
the Experiment 35A document subset plus 40 questions built around terms with
two senses in the corpus. Metrics: recall@10 and nDCG@10. The frame keeps its
place as a first-class stage only if it beats the best rewrite baseline by at
least 5 points recall@10 on the ambiguity set without losing on the general
set. If it does not, it becomes an optional diagnostic and the paper reports
the null result.

## Related work and how this differs

- **Abductive missing-premise RAG** (arXiv 2511.04020) generates premises the
  evidence lacks. We do the opposite. We refuse conclusions the supported
  premises do not licence.
- **Syllogistic reasoning evaluations on FOLIO** (arXiv 2608.12374) measure
  whether language models can solve syllogisms. We do not ask the model to
  solve them. We ask it to label the form, and code checks validity.
- **FAIR-RAG** (arXiv 2510.22344) audits evidence for gaps and re-queries.
  Its gate is about coverage. Ours is about inference validity over what was
  found.
- **Context-driven decomposition under knowledge conflict** (arXiv
  2605.14473) isolates a conflicting premise and records a resolution trace.
  It works at the level of one fact against the model's prior. Our inference
  record works across several supported claims and names the form.
- **Claim verification** (our ADR-059, and the broader faithfulness
  literature) checks one claim against its evidence. It cannot see that two
  supported claims were combined invalidly. That is the gap Qiyās fills.

## Timeline

Paper 2 starts when Paper 1 reaches its experiment phase, roughly week 10 of
Paper 1, and runs about 14 weeks.

| Weeks | Work |
|---|---|
| 1 | Record today's answers as the golden output. Package, import boundary, data model. |
| 2 to 3 | Four-way judge, condition capture, premise eligibility. Concept frame builder. |
| 4 to 6 | Inference labeller, deterministic checks, answer gate, pipeline steps and template. |
| 6 | Web: template action in Studio and the manṭiq block in chat. Decide any extra 44A model rows. |
| 7 to 8 | Relabel the Experiment 20 triples. Experiment 44A. |
| 8 to 10 | Build the 44B item set. Run 44B. |
| 10 to 11 | Experiment 44C. |
| 12 to 14 | ADR, profile decision, paper draft, preprint. |

## Target venues

- ACL or EMNLP findings, for the inference-validation framing.
- SIGIR or ECIR, if the concept-frame ablation is strong.
- JURIX or ICAIL, if the 44B item set leans on the legal corpus from Paper 1.
- The Muslims in ML workshop at NeurIPS as an early airing of the
  methodological framing.

## Risks and mitigations

- **The labeller mislabels forms.** Mislabelled and unclassified items map to
  `unverifiable`, never `valid`. 44B reports labelling accuracy on its own.
- **The checks are too strict.** Rejected sentences are reported with their
  failing checks. 44B caps valid false rejection at 15 percent. The
  surplus-content check uses normalised token match with a stop-list tuned on
  a development split only.
- **The four-way prompt is worse than the two-way one.** 44A reruns the
  original two-way metrics under both prompts. Below 0.90 unsupported recall,
  the prompt is revised before any profile turns the gate on.
- **The concept frame adds nothing.** 44C is built to find that out. A null
  result is publishable and keeps the paper honest.
- **Latency.** One frame call plus one judge call per claim and per inference.
  Only people who bind a profile to the manṭiq template pay it. Built-in
  profiles never run manṭiq.
- **An extra local model may not run.** If 44A adds one, a smoke test comes
  first. If it fails, 44A keeps the other cells and records the gap.

## Out of scope

- Formal syllogistic figures and moods, or any theorem prover.
- A new MCP tool. The existing answer result carries a `mantiq` block only
  for profiles that use the template.
- Changes to retrieval strategies or to the existing claim judge. The frame
  only rewrites the query text.
- Training or fine-tuning any model.
- Digitising Manṭiq or uṣūl al-fiqh. The classical terms name the stages and
  motivate the checks; they do not become executable doctrine.
