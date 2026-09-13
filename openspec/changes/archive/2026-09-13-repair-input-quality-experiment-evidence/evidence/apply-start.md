# Recovery apply: starting point

## Summary

The operator approved applying the recovery proposal. Task 1.1 is verified: the existing four-file patch has an exact local backup. No production file, experiment result, index or default was changed during preservation.

## Operator instructions

The apply request explicitly requires:

- Work slowly and ask for clarification when a decision is needed.
- Use plain English in protocols, with enough technical detail to reproduce the work. Explain technical terms where used.
- Use plain English in results.
- Include substantive `## Summary` and `## Discussion` sections inside each new or amended `results.md`. A separate discussion file alone does not satisfy this request.

For each report, the summary should state the question, observed outcome and decision status. The discussion should explain what the evidence supports, its limits and the remaining questions. Report generation must preserve both sections.

Approval to apply the recovery plan does not approve a replacement OCR rule, corpus scan, paid run or default promotion.

## Preservation evidence

- Worktree: `/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3-feat-improve-rag-input-quality-5`
- Branch: `feat/improve-rag-input-quality-5`
- HEAD: `afe151e93dd9b79e18618811dc15e35c6a96b16d`
- Remote-tracking feature ref: `2c58b4530fe4ea432f39c1e7bfd2a63a2f5fed97`
- Backup: `.pi/recovery/input-quality-start.patch`, relative to this worktree; gitignored and local only.
- Backup size: 9,356 bytes.
- Backup SHA-256: `397ee7b626c3dc0ed28e1a62a16f1db799756ef7214f29999caccd3487d4a2af`
- Verification: compared backup bytes with `/usr/bin/git diff --no-ext-diff --binary --` over the four paths below. Exact equality passed.

| File | SHA-256 before further work |
| --- | --- |
| `.env.example` | `890c739ea4016491bce99b5b8ca0a813f36677c1b2ee9e833d66fa1bb9f003d3` |
| `docs/guides/ingestion.md` | `2b13f2fd24174b2d92bbe9de7d5d3bbecd2e6599305584d5a42885e231c656c6` |
| `src/omrg/integrations/pdf/ocr_routing.py` | `2c80585c0bd294880c6926532a49cdb4a9d0adc432732a3f921849b9a2be6f5b` |
| `tests/test_ocr_routing_gate.py` | `e890bdb08344a39f37d173b4c64f38981d5338eb78e1b9740044a8f611a9ab49` |

## Discussion

The backup preserves an unapproved patch; it does not approve its contents. Future edits to shared documentation must be reviewed against this starting point so the routing change is not adopted accidentally.

Task 1.2 requires a command tool with an explicit working-directory parameter before tests or other writing commands. That capability must be checked before implementation requiring runtime verification proceeds. Historical test counts do not verify new work.
