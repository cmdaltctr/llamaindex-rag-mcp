# Design: Experiment 31 Reader Rescue Retrieval Impact

## Context

The current PDF path uses `pdf-inspector` first. When a text-based PDF reports an empty extraction, OMRG can retry with LiteParse with OCR disabled and then pypdf. Experiment 30 validated text recovery and cost on known failures. It did not test retrieval impact.

## Goals

- Measure whether reader rescue restores gold evidence that the control path loses.
- Measure whether restored evidence improves downstream retrieval.
- Keep all non-reader variables fixed.
- Preserve full experiment provenance and negative results.

## Non-Goals

- Do not recalibrate OCR routing.
- Do not compare embedding models.
- Do not change the reader fallback order.
- Do not promote or remove a production default from this experiment alone.

## Experimental Cells

### Cell A: control

Use `pdf-inspector` extraction only. Do not invoke LiteParse or pypdf rescue when extraction is empty.

### Cell B: candidate

Use the current production chain:

`pdf-inspector -> LiteParse with OCR disabled -> pypdf`

Both cells continue through the same current chunking, embedding, vector-store, retrieval, and reranking path.

## Corpus

Use two groups:

1. Development/regression group: the known pathological documents from Experiment 30 and related documented failures.
2. Held-out group: independently selected natural PDFs with a usable text layer where `pdf-inspector` produces empty or materially incomplete evidence.

The held-out group must be frozen before measured scoring. Documents inspected while designing or debugging the candidate do not count as held-out evidence.

## Gold Evidence

Each measured query must identify answer-supporting evidence in the source PDF independently of the reader output. Gold evidence must not be created from either experiment cell's extracted text.

## Metrics

Primary measurements:

- gold-evidence recoverability before embedding;
- Evidence Recall@1, @3, @5, and @10;
- MRR@10;
- no-hit rate.

Secondary measurements:

- extraction latency;
- chunk count;
- embedding request tokens;
- index size when available.

The report must present paired per-query results and confidence intervals where the sample supports them. Small samples must be reported as small samples rather than converted into strong general claims.

## Validity Controls

- Freeze corpus, queries, qrels, and query order before measured runs.
- Use the same embedding provider/model identity in both cells.
- Use the same tokenizer, chunker, retrieval settings, vector store, and reranker settings in both cells.
- Record source commit, lockfile hash, effective settings, and index identity.
- Abort a measured cell when a controlled variable differs unexpectedly.

## Decision Rule

This experiment produces evidence about the existing fallback chain. It does not directly change production behaviour.

If the candidate recovers more gold evidence but retrieval does not improve, retain the result and investigate retrieval separately. If the candidate causes a material retrieval regression, open a separate change before altering production behaviour.
