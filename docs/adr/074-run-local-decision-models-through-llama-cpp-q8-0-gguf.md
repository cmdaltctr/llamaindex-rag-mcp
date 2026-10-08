# ADR-074: Run Local Decision Models Through llama.cpp Q8_0 GGUF

**Date:** 2026-10-08
**Status:** Proposed
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Related:** [ADR-024](024-dual-deployment-modes.md) (local-first, cloud opt-in), [ADR-073](073-make-the-torch-extra-a-normal-choice.md) (optional `torch` extra)
**Evidence:** `experiments/38-rescue-quality-signal-2026-09-30/report.md` (section "Clef-flash (Cloudflare): every run, hosted and local")

## Context

A decision model answers a typed question about some text, for example "is this page readable writing?". It takes a TypeSafe `/v1/systemone` request and returns a probability. Experiment 38 used decision models to score rescue text for junk.

Clef-flash is Cloudflare's 9B decision model. It uses the same request format as Jev, and its licence is Apache 2.0. Experiment 38 scored it in four ways, each on three wordings and all 1,322 page/tier pairs:

| Run | Bits | Download | Seconds per page |
| --- | ---: | ---: | ---: |
| Hosted, Cloudflare Workers AI (H) | not published | none | not compared |
| MLX 4-bit (I) | 4 | 6.2 GB | 0.70 |
| MLX 8-bit (K) | 8 | 10.7 GB | 1.13 |
| llama.cpp Q8_0, `ggml-org/Clef-Flash-GGUF` (J) | 8 | 9.7 GB | 0.84 |

Speed was measured one request at a time on 40 fixed pages, with nothing else on the GPU.

Agreement with hosted Clef-flash:

- **Both 8-bit builds match hosted.** Correlation with hosted is above 0.999 on every wording. Both builds catch the same number of junk pages, send the same usable documents to OCR, and give the same gate outcome on every wording.
- **llama.cpp Q8_0 is the closer 8-bit build.** Its average difference from hosted is 0.0034, 0.0019 and 0.0026 on W1, W2 and W3. MLX 8-bit gives 0.0058, 0.0031 and 0.0038. Q8_0 is closer to hosted on 816, 885 and 760 of 1,322 pages.
- **4-bit is not safe without a full check.** MLX 4-bit differs from hosted by more than 0.10 on 177, 168 and 96 pages on W1, W2 and W3. Its worst gap is a junk page scored 0.86 against 0.20 hosted. On W1 it sends the usable document `tl06` to OCR, and it fails gate G2 on every wording.
- **The 4-bit GGUF was checked on 94 pages only.** llama.cpp Q4_K_M missed the "no page off by more than 0.10" mark by 0.008. That check used a set that is 87% junk, so it is too weak to compare with the full-set rows. Its scores were not saved.

Runtime facts from the run:

- llama.cpp build b11510 includes the Metal fix from PR #30100. The installed `~/.llama-app` build 11429 lacks the fix and was not used.
- `llama-server` stalled when four decision requests overlapped (60 s timeouts). The scorer sends it one request at a time.
- The MLX server queues requests. Per-request times saved in the scoring files therefore include waiting and are not used for speed.

The project rule is local-first (ADR-024). Cloud features must be opt-in and fall back to local. PyTorch must stay out of the base install and the default retrieval path.

The experiment verdict is FAIL. No candidate passed gates G1, G2 and G3. This ADR does not depend on that verdict. It records how to run a local decision model. It does not record whether to use one.

## Decision

1. Run local decision models through `llama-server` (llama.cpp) with an 8-bit GGUF. For Clef-flash, use `ggml-org/Clef-Flash-GGUF` Q8_0.
2. Use llama.cpp build b11510 or later. It must include the Metal fix from PR #30100. Check the build number, because `llama update` can lag behind the main release.
3. MLX 8-bit is an accepted fallback. Use it where llama.cpp is not available.
4. Do not use a 4-bit build (MLX 4-bit, GGUF Q4_K_M or similar) until its scores match a reference on the full page set. A check on a few documents is not sufficient.
5. Send one request at a time to a local server. Measure speed one request at a time, with nothing else on the GPU.
6. Bind the local server to `127.0.0.1`. Page text stays on the machine.
7. Treat `llama-server` as an external process. The project calls it over HTTP with the same `/v1/systemone` request as hosted Jev. It is not a Python dependency of OMRG, and this ADR adds no package to `pyproject.toml`.

This ADR does **not** adopt Clef-flash as the rescue-quality gate in production. That decision waits on Experiment 42, a confirmatory run on new documents (OpenSpec change `experiment-42-clef-flash-confirmation`).

## Consequences

### Positive

- Page text stays on the machine. Hosted Clef-flash and hosted Jev send the first 2,000 characters of every page to a third party.
- Clef-flash is Apache 2.0, so the local build allows production use. OpenJev (CC BY-NC 4.0) does not.
- Q8_0 is the closest local match to hosted, and it is faster (0.84 s against 1.13 s a page) and smaller (9.7 GB against 10.7 GB) than MLX 8-bit.
- The local model file has a fixed version. Hosted Clef-flash returns only the name `clef-flash`, so a silent model update cannot be detected.
- No PyTorch and no new Python dependency. The default install and the hard boundaries stay unchanged.

### Negative

- The operator must install and run `llama-server` and download a 9.7 GB model file.
- One request at a time limits throughput. Q8_0 takes 0.84 s a page, and hosted Clef-flash took 0.40 s with four requests at a time.
- Older llama.cpp builds lack the Metal fix. A build check is a manual step.
- The 8-bit file is larger than a 4-bit file (9.7 GB against 6.5 GB for Q4_K_M).

### Neutral

- The evidence covers Clef-flash on 40 documents on one Mac. Other decision models and other hardware are untested. A new model needs its own check against a reference before this rule applies to it.
- The two 8-bit builds do not use identical quantisation schemes. The comparison between runtimes is close, not exact.
- AGENTS.md Critical Gotcha 16 states the same rule in short form.

## Alternatives Considered

| Option | Rejected Because |
|--------|-----------------|
| **Hosted Clef-flash (Cloudflare Workers AI)** | Page text leaves the machine. The API returns no model version. The free daily limit stopped hosted Clef 27B at 13 of 40 documents. Allowed only as an opt-in reference, not as the default. |
| **Hosted Jev (TypeSafe)** | Page text, including personal records, leaves the machine. Closed weights, and `jev-latest` is an alias that can change model. Kept as a reference arm only. |
| **OpenJev 27B, local MLX 4-bit** | Licence is CC BY-NC 4.0, so no production use. 6.2 to 7.5 s a page. Kept as a reference arm only. |
| **MLX 8-bit as the primary runtime** | Gives the same gate outcome, but is further from hosted on all three wordings, slower (1.13 s a page) and larger (10.7 GB). Kept as the fallback. |
| **MLX 4-bit** | Differs from hosted on 96 to 177 pages per wording and sends a usable document to OCR. Fails G2 on every wording. |
| **llama.cpp Q4_K_M** | Checked on 94 mostly-junk pages only, and missed the 0.10 mark there. Not allowed until a full-set check passes. |

## References

- `experiments/38-rescue-quality-signal-2026-09-30/report.md` (Clef-flash build comparison, held-out gates, Conclusion, Limits and next actions)
- `experiments/38-rescue-quality-signal-2026-09-30/plan.json` (candidates H, I, J and K: runtime, build and privacy terms)
- `experiments/38-rescue-quality-signal-2026-09-30/output/clef_flash_variants.json` and `output/clef_flash_speed.json`
- `experiments/38-rescue-quality-signal-2026-09-30/measure_speed.py` and `score_wordings.py`
- `AGENTS.md` Critical Gotcha 16
- `openspec/changes/experiment-42-clef-flash-confirmation/` (adoption decision, pending)
