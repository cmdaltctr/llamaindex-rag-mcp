# Task 2.3 prose reconciliation (2026-09-09)

## Summary

The shared OCR comments now describe the committed unconditional `mixed`
routing policy and the preserved, unapproved local threshold variant.
They contain no claim that the routing concern is fixed.

## Evidence

Verified in this worktree on `feat/improve-rag-input-quality-5` at
`afe151e93dd9b79e18618811dc15e35c6a96b16d`:

- Documentation paths reviewed: `.env.example` and `docs/guides/ingestion.md`.
- A wording check found no `is fixed`, `now fixed`, or `no longer routes
  unconditionally` claim in either file.
- `git diff --check -- .env.example docs/guides/ingestion.md` passed.
- The protected routing source matched apply-start:
  `2c80585c0bd294880c6926532a49cdb4a9d0adc432732a3f921849b9a2be6f5b`.
- The protected routing test matched apply-start:
  `e890bdb08344a39f37d173b4c64f38981d5338eb78e1b9740044a8f611a9ab49`.
- The preserved patch matched its recorded digest and size:
  `397ee7b626c3dc0ed28e1a62a16f1db799756ef7214f29999caccd3487d4a2af`,
  9,356 bytes.

## Discussion

The existing dirty production source and test were not edited. Their hashes
prove that this task did not alter the preserved mixed-policy patch. No
packaged setting changed. OCR remains disabled with the recorded sentinel
thresholds until the operator approves a policy.