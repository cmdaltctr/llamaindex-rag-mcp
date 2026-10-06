# Design

## Context

See proposal.md (Why). Current state that shapes the approach:

- **Baseline exists.** Experiment 37 holds per-page Markdown, per-page state and `summary.json` for dots.mocr (PyTorch MPS) and PaddleOCR-VL (CPU) on 257 pages. The gitignored per-page files were copied into the v3 worktree on 2026-10-06 (Gotcha #15) and match the source byte for byte.
- **Two baseline limits.** The engines ran at the same time in Experiment 37, so baseline timings carry shared load. MLX conversions are not byte copies of the PyTorch weights.
- **No MLX engine folder.** The `OcrEngine` contract and `OcrRoutes` do not know MLX. The experiment cannot use the host path for the MLX arms.
- **PaddleOCR-VL shape.** The shipped engine builds `PaddleOCRVL(device="cpu")` and handles page subsets (TDR-027, TDR-029). PaddleOCR documents `vl_rec_backend="mlx-vlm-server"`, which sends only the recognition step to a local server. The layout model `PP-DocLayoutV3` still runs on CPU.
- **dots.mocr shape.** The shipped engine renders at 200 DPI, uses the upstream layout prompt, caps output at 8192 tokens, decodes greedily and post-processes with `layout.py`.
- **Licence.** The dots.mocr agreement covers derivative works. An MLX conversion is a derivative.

## Goals / Non-Goals

**Goals:**

- Give a fair, complete comparison of two MLX arms against their baselines on the Experiment 37 pages.
- Keep the operator in control of gates, installs, downloads and runs.
- Reuse Experiment 37 tools so the new numbers use the same rules.

**Non-Goals:**

- Adding an MLX engine folder, route, setting or dependency.
- Testing quantised models, other hardware or other models.
- Changing the maths detector or the routing gates.

## Decisions

### D1. Standalone probe, not the host path

Run the MLX arms from standalone scripts, as Experiment 34 did for its probe. Each script runs in the environment it needs and writes to the Experiment 37 output layout under new arm names. The comparison is about the backend, so the scripts reuse the engine constants and post-processing.

- Alternative: build an MLX engine folder first. Rejected. It would change shipped code before the evidence exists.
- Alternative: run through `OcrRoutes` with a fake engine. Rejected. It tests plumbing, not the backend.

### D2. Hold everything except the backend

Keep the prompt, render size, token cap, decoding rule and `layout.py` post-processing identical to the shipped dots.mocr engine. For PaddleOCR-VL keep the engine's page-subset handling. Differences in output then trace to the backend, the conversion and the numerics, which the experiment cannot separate and says so.

### D3. Two environments for MLX

`mlx-vlm` lives in a gitignored `mlx-env/` in the experiment folder. `A4` calls it over HTTP from the already provisioned PaddleOCR-VL environment. `A2` calls `mlx-vlm` directly from `mlx-env/`. No MLX or PyTorch package enters the OMRG environment.

### D4. Memory is two processes

Sample `proc_pid_rusage` lifetime maximum for the client and for the `mlx_vlm.server` process, and report the sum. This extends the Experiment 37 sampler, which watched one worker.

### D5. Similarity is a defined metric

Use the Dice coefficient over token multisets with the Experiment 33 tokeniser. The scratch test reported "token match" with no recorded method, so its numbers are context only.

### D6. Gates belong to the operator

The protocol lists candidates. `plan.json` holds `gates: NOT SET` until the operator fills it. Amendments after a run starts are dated and keep the original rule.

### D7. Review only where it matters

The operator reviews the screened noise pages, the lowest-similarity pages and a small random sample, using the Experiment 34 review layout. This keeps the review short and aims it at the pages most likely to differ.

## Risks / Trade-offs

- [Baseline timings include shared load, so a speed gain could be partly an artefact] → State the limit beside every speed result. Offer the `T-control` re-timing of the baselines alone (open decision DR-1).
- [The conversion differs from the pinned PyTorch weights] → Record each repository revision. Report differences as findings. Do not claim the backend alone caused them.
- [`mlx-vlm` handles dots.mocr or PaddleOCR-VL differently from the reference code] → The two-page smoke run compares against scratch figures before the full run. Stop if the output is empty.
- [Memory is summed over two processes and may double count shared pages] → Report the method. Treat the sum as an upper bound.
- [The licence tag on a conversion hides clauses] → The operator decides before any download (approval gate 3, DR-2).
- [Page time includes CPU layout for `A4`] → Report layout and recognition time apart where the log allows. Say that `A4` speed is bounded by the CPU layout step.
- [A long GPU run blocks the machine] → Run detached, checkpoint per page and resume after a stop.

## Open Questions

- DR-1: re-time the baselines alone? Candidate: yes, 30 pages, seed 41.
- DR-2: does the 2026-10-04 licence acceptance cover the MLX conversion?
- DR-3: how many lowest-similarity pages go on the review page?
- OI-1 to OI-4 (see `protocol.md`): `layout.py` imports, pinned-revision loading in `mlx-vlm`, page-subset reuse for `A4`, review size.

The operator resolves DR-1 to DR-3 before the first run.
