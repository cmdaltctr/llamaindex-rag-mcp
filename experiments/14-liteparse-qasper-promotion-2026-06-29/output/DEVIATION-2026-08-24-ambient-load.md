# Deviation record: ambient machine load during Experiment 14 campaign

Date: 2026-08-24, 09:20 local.
Ratified by: Dr Muhammad Aizat Bin Md Hawari (rectified for non-quiet run)

## Condition

Load averages at launch: 7.72 / 6.91 / 8.11 (1/5/15 min) on 8 physical
cores, 32 GB RAM. Earlier same morning: 5.32 / 5.54 / 8.60.

Active consumers that could not be stopped:

1. Two opencode sessions (one is the campaign operator).
2. Orca app + helper renderers.
3. Microsoft Edge helpers.
4. WindowServer (desktop compositing).

## Effect on evidence

- Quality metrics (coverage@k, hit@k, MRR@k, H1 corpus validity, H3
  reranker lift, non-regression): VALID. Rankings are deterministic —
  frozen PDF corpus, fixed 112-query set, fixed indexes, ONNX reranker.
  CPU contention changes wall-clock, not ordering.
- H2 speed evidence (parse_time_s_total, embed_write_time_s,
  ingestion_time_s, P95 latency): FLAGGED. Ambient contention inflates
  all timing. The three builds run sequentially, so unequal background
  load between them can bias the parser comparison in either direction.

## Disposition

1. H2 comparative verdict is PROVISIONAL under this note: direction is
   credible only where the margin between parsers is large relative to
   load variance observed here (1-min load ranged 5.3-7.7 pre-launch).
2. A marginal H2 result (parsers within ~20% of each other) requires a
   quiet-machine re-run of the build stage before any promotion claim.
   Parse timing is re-derivable without re-embedding if needed
   (per-doc parse_time_s is recorded in the parse-event logs).
3. Gate 6C H2 adjudication and results.md must reference this note.
