# Remote backup evidence

## Scope and approval

The operator explicitly approved the existing ten-commit remote backup with these safeguards: inspect committed secrets and private data, preserve all uncommitted work locally, push only the inspected HEAD, and create no pull request. The controlling approval is recorded verbatim in `design.md` under “Operator approval received on 2026-09-09”.

- Worktree: `/Users/aizat/Development/PROJECTS/llamaindex-rag-mcp-v3-feat-improve-rag-input-quality-5`
- Branch: `feat/improve-rag-input-quality-5`
- Approved local HEAD: `afe151e93dd9b79e18618811dc15e35c6a96b16d`
- Inspected range: `2c58b45..afe151e`
- Commit count: 10

## Inspected commits

1. `afe151e93dd9b79e18618811dc15e35c6a96b16d` `docs(adr): record the input-quality promotion decisions as ADR-064`
2. `65703bae3eae25f5f8026c53b88809924986ce27` `feat(experiments): run experiment 28 — OCR routing on a real library`
3. `f569931aa311c50ec790b7e288e672286611da2a` `docs(experiments): preregister experiment 28 and freeze its gates`
4. `c1833f72f9a21a243730873869352a11760bcf09` `test(validation): record the stage 6 validation results (tasks 6.5-6.8)`
5. `84115694c4c10c3d32cc4350d354d9a1859a7123` `docs(openspec): tick tasks 4.7, 5.3 and 5.4 with their evidence pointers`
6. `59d77ae8ec16870829c52048f43a19e3ebb8da86` `feat(experiments): run experiment 27, the combined candidate path (task 5.4)`
7. `6e01839711912887b1d552fe7450d5437de7ce6c` `feat(experiments): run experiment 26, the query-instruction ablation (task 5.3)`
8. `e79599dd7ffaa7366575d20a85b607384273fc7e` `docs(experiments): freeze experiment 27 gates before any measurement`
9. `5b6fb66eb4aeba7e09f2b56591bcb4527cffdaad` `docs(guides): document OCR routing, the query instruction and index identity`
10. `d3bb602a9427c29dad944ac8d9a03f69967b5acf` `docs(experiments): close out task 5.1 with the unmeasured wording items`

## Pre-push security inspection

The pre-push security delegate audited the complete range directly with git and gitleaks. The audit covered 38 paths and 47 intermediate blobs.

- Direct git-range gitleaks result: zero leaks.
- Public revision strings were false positives.
- Existing public username paths were recorded as public paths.
- No unresolved secret or private-data finding prevented the approved push.

## Local preservation before push

The archive was created before the push outside the worktree:

- Archive: `/Users/aizat/Development/PROJECTS/input-quality-repair-uncommitted-20260909-afe151e.tar.gz`
- SHA-256: `4ab16079e1ac894ca753fb0c607643edb5ca9a2899a77c4e204f402ee08b893e`
- Contents: 20 modified or untracked files at archive time.
- Readability check: passed.
- Byte comparison: 20 of 20 source files compared with no mismatches.

No `.env` file was intentionally edited. `.env.example` was intentionally edited. The ignored `.env` file was never touched. The staging area was empty.

The existing ignored preservation patch remains in place:

- Patch: `.pi/recovery/input-quality-start.patch`
- SHA-256: `397ee7b626c3dc0ed28e1a62a16f1db799756ef7214f29999caccd3487d4a2af`
- State: retained and previously verified.

After the push, a separate external archive preserved that ignored patch:

- Archive: `/Users/aizat/Development/PROJECTS/input-quality-repair-preserved-patch-20260909-afe151e.tar.gz`
- SHA-256: `92aefb2c1ff637cda50842ba36b66d40998f5e7479fc428440c4c5ca0855de3e`
- Readability check: passed.

This second archive was made after the push. It is distinct from the pre-push archive.

## Remote verification

`git fetch`, then `git pull --ff-only origin feat/improve-rag-input-quality-5`, reported the branch up to date. `git push origin HEAD:refs/heads/feat/improve-rag-input-quality-5` succeeded with `2c58b45..afe151e`.

The local and remote feature ref both resolved to `afe151e93dd9b79e18618811dc15e35c6a96b16d`. Uncommitted work was preserved. No pull request was created.

## Boundary of this archive

The pre-push archive covers only the 20 files present when it was created. Current changes made after that archive are not backed up by it. This evidence update does not create another backup.
