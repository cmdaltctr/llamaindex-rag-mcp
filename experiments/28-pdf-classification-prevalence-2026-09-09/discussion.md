## Discussion

### H1 fails, and the failure is a 991-page document

One document routed that should not have: `doc_077`, classified `mixed`
at confidence 0.76, **991 pages**, **1,127 characters per page**. That is
a healthy text layer — a third of the median density in this library, but
three orders of magnitude above the "no usable text" line at any
threshold tested.

Only **10 of its 991 pages** are flagged as needing OCR. Barely 1%. The
gate sends all 991 anyway, because `mixed` is in
`OCR_UNCONDITIONAL_TYPES` and task 2.4 dispatches whole files with no
page-level stitching.

At the committed warm worst case of 106.4 s/page that is **29.3 hours of
OCR for one document that already extracts fine**. The whole 79-document
library takes 80 seconds on the fast path. Enabling this default would
have made it **1,375× slower**, and 96% of that cost buys nothing.

### The operator's instinct was right and my retraction was wrong

Earlier in this session I claimed a mostly-text document containing a few
image-only pages would classify `mixed` and drag the entire file into
OCR. I then withdrew the claim, because the one fixture that tests it —
`eval_mixed.pdf`, a text page plus an image-only page — classified
`text_based` at confidence 0.5 and stayed on the fast path.

The real library vindicates the original claim. `eval_mixed.pdf` is a
two-page synthetic file; `doc_077` is a 991-page real document, and the
classifier treats them differently.

The lesson is not that the first instinct was lucky. It is that a single
synthetic two-page fixture was never adequate evidence in either
direction, and I treated it as decisive twice — once to raise an alarm,
once to withdraw it. The fixture set could not answer this question. That
is exactly why this experiment exists.

### The calibrated thresholds are the good part

The routing breaks down cleanly, and the split is the opposite of what
the promotion debate assumed:

| Document | `pdf_type` | Pages | Flagged | Chars/page | Needed OCR? | Routed by |
| --- | --- | ---: | ---: | ---: | --- | --- |
| `doc_045` | scanned | 23 | 23 | 0 | **yes** | unconditional type rule |
| `doc_067` | text_based | 17 | 17 | 0 | **yes** | **calibrated page-fraction threshold only** |
| `doc_077` | mixed | 991 | 10 | 1,127 | no | unconditional type rule |

`doc_067` is the interesting one. `pdf-inspector` classified it
`text_based` at **confidence 1.0** while it extracts **zero characters
across all 17 pages**. Classification alone would have missed it
completely. The 0.5 page-fraction threshold — 17 of 17 pages flagged —
is the only thing that caught it.

So experiment 23's calibration earns its keep: it caught a document the
classifier was confidently wrong about, and it produced no false routes.
Every false route came from the unconditional `pdf_type` rule instead.

### H2 fails too, but read it correctly

needs-OCR prevalence is 2 of 79 (2.5%), Wilson 95% CI [0.7%, 8.8%]. The
lower bound does not clear the 1% bar the power analysis set, so H2
fails as preregistered.

**This does not mean scanned documents are rare in academic libraries.**
The interval runs up to 8.8% — as many as one document in eleven could
need OCR and this study could not tell. n = 79 cannot resolve it. The
honest statement is that the prevalence is unresolved at this sample
size, not that the need is absent. A larger corpus would settle it; the
operator scoped this one to the Zotero library.

### Robustness

The ground-truth threshold does not drive the verdict. At 50, 100 and 200
characters per page the counts are identical: 2 documents need OCR, 1
false route. `doc_077` sits at 1,127 characters per page, five times
above the loosest threshold tested, so no plausible definition of "has a
text layer" excludes it.

No document sits within 0.05 of either 0.5 threshold, so the calibration
is not balanced on a knife edge for this population.

Zero parse failures across 79 documents and 2,744 pages.

### Decision, per the rule fixed before the data

The preregistered decision rule says: *safety gate fails → promote
nothing.* That is the outcome.

1. `OCR_FALLBACK_ENABLED` keeps its packaged default of `false`.
2. `OCR_FALLBACK_MIN_CONFIDENCE` and `OCR_FALLBACK_PAGE_FRACTION` keep
   their `0.0` never-trigger sentinels.
3. The calibrated 0.5 / 0.5 values stay documented in `.env.example` and
   the ADR as the values an operator should use when enabling OCR.

Following the frozen rule matters here precisely because the analysis
below suggests a *better* configuration exists. Rewriting the decision
rule after seeing which component failed is how a gate becomes
decoration.

### Exploratory finding — a design defect, not a calibration problem

**Labelled exploratory. Observed after the data, on the same data, and
therefore not confirmatory evidence for anything.**

The defect is locatable to one line. `OCR_UNCONDITIONAL_TYPES` in
`core/../integrations/pdf/ocr_routing.py` contains `mixed`, so a `mixed`
classification bypasses the calibrated thresholds entirely — and whole-
file dispatch then multiplies the mistake by the page count.

On this population, removing `mixed` from the unconditional set would
have produced:

- `doc_045` (scanned, unconditional) — still routed. Correct.
- `doc_067` (17/17 pages flagged ≥ 0.5) — still routed. Correct.
- `doc_077` (10/991 = 1% flagged, below 0.5) — **not routed**. Correct.

Zero false routes, both true positives kept. But this is one library, and
the observation was made after seeing the numbers. It is a hypothesis for
a new preregistered experiment on a fresh corpus, not a change to make on
the strength of this run.

### Scope limit, binding on the change record

This experiment sampled **one operator's curated academic library**:
79 documents, 2,744 pages, overwhelmingly born-digital journal PDFs
(median 3,907 characters per page, 72 of 79 classified at confidence 1.0).

It cannot license a default for corpora it never saw — scanned archives,
historical collections, OCR-hostile institutional repositories. What it
does establish is that on a normal modern paper library the OCR fallback
default would have been a serious mistake, and that the mistake is
structural rather than a matter of tuning.
