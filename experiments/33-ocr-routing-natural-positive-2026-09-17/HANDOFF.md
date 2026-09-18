# Experiment 33 handoff — remaining work

Rewritten 2026-09-18 after task 6.7, the reader comparison, and the PR #95
merge decision. Everything below is committed; nothing depends on chat history.

## Worktrees: exactly two stay open

| Worktree (sibling of the main checkout) | Branch | Role |
| --- | --- | --- |
| `llamaindex-rag-mcp-feat-experiment-33-ocr-routing-natural-positive` | `feat/experiment-33-ocr-routing-natural-positive` | **Data and records.** The frozen corpus, page images, transcriptions, Stage A extractions and local OCR results live here and nowhere else. Every measurement runs from here |
| `llamaindex-rag-mcp-feat-page-level-ocr-routing` | `feat/page-level-ocr-routing` | **Code.** The LiteParse join-order fix and page-level-ocr-routing tasks 3 to 6 |
| `llamaindex-rag-mcp-v3` | `v3` | Integration branch. PRs target it |

Do not open a third worktree without asking the operator.

`feat/full-page-ocr-evidence` closed on 2026-09-18: merged as `1e0a4b0`,
worktree and local branch removed.

## Queue

1. ~~**Merge PR #95**~~ **Done 2026-09-18.** Squash-merged to `v3` as
   `1e0a4b0`, carrying the code fix, TDR-026 as Accepted with the Stage A
   numbers, the `pdf-reader` delta synced into the main spec, and the archived
   change. Worktree and local branch removed; see the movement log.
1a. ~~**LiteParse join-order fix**~~ **Implemented and measured 2026-09-18**,
   8 of 11 tasks. Only close-out remains: the fast suite with coverage,
   `./scripts/local_ci.sh`, and the PR. See "Session state" below.
2. **LiteParse join-order fix**, its own OpenSpec change on
   `feat/page-level-ocr-routing`. Scope and evidence gate below.
3. **`page-level-ocr-routing` tasks 3 to 6**, same branch. Already
   REWORK-approved: `OCR__LOCAL_MIN_CONFIDENCE = 0.8`, a script and typography
   pre-check before the local OCR tier, and the `io06` blind spot recorded as
   an accepted risk (confidence 0.922, recall 0.609).
4. **One PR to `v3`** covering items 2 and 3. Before opening it:
   `openspec validate --all --strict` and `./scripts/local_ci.sh`.
5. **Experiment 33 ADR, then archive the experiment.** The ADR must state
   **prominently**, at the operator's explicit request:
   1. The operator's understanding observations: equations and scientific
      notation, figures and charts needing interpretation, two- and
      three-column layout, tables, headings, footnotes and sidebars, old-book
      spelling, and non-Latin scripts (Hindi, Arabic). They are recorded as
      `understanding_label` and notes in `spot_check.json`.
   2. Task 5.3, the print-and-rescan tier, skipped by operator decision on
      2026-09-17, so real physical scan artefacts (page curl, uneven lighting,
      bleed-through, paper texture) are untested.
   3. The label validation history: the automatic rule disagreed with the
      operator on 41.5% and then 20.2% of the random sample, and the final
      labels take the operator's verdict on the 277 reviewed pages and the rule
      on the other 846.
6. **Later: a rescue-quality signal**, so a junk LiteParse rescue counts as
   OCR-required (`rf06` fast-path recall 0.236, `rf07` 0.469). `report.md`
   conclusion item 2. Its own change, after item 5.

## LiteParse join-order fix (queue item 2)

Scope:

1. The adapter in `src/omrg/integrations/pdf/liteparse.py` already labels each
   page `single`, `left` or `right` from text-item positions, then joins the
   items ignoring that label. Use the label when joining.
2. Per page, three cases: single column keeps today's order; multi-column
   re-sorts by column then position; table pages keep today's order until a
   table-aware order is measured separately.
3. Reject the naive 45% split. The measurement drops a journal front page to
   0.52 and a table page to 0.40.
4. No OCR, no worker and no routing change.

Why it matters beyond LiteParse: `rf04` is a rescued document, so the chain's
output is what retrieval sees, and it scored 0.53 reading order where plain
pypdf text scored 0.98 on the same pages. The operator's spot-check notes on
columns and tables judged pypdf text, not the pipeline, so this fix is the
first measurement of the real reading order.

Evidence gate before the PR, measured on the Experiment 33 reviewed pages:

- two-column body pages: reading-order score ≥ 0.90, up from 0.53
- no regression on `bd02` p1 (0.67) or `tl03` p5 (0.74)
- token recall unchanged, within ± 0.01
- scores reported per page class: single, multi-column, table

Measure it from **this** worktree, never the page-level one. Write the script
in `experiments/33-ocr-routing-natural-positive-2026-09-17/`, load the code
under test the way `route.py` does with `--code-root` pointing at the
page-level worktree, commit the script and its `output/*.json` here, and quote
the numbers in the proposal on the other branch.

## Results already in hand

Frozen labels: 18 documents need OCR, 22 do not (1,123 pages, 40 PDFs).

### Stage A routing (both arms)

| Arm | Recall | False negatives | False positives | Routed pages |
| --- | ---: | ---: | ---: | ---: |
| `sampled_baseline` (`5bac71e`) | 0.556 (10/18) | 8 | 1 (`mx08`) | 395 |
| `full_scan_candidate` (`7280766`, PR #95) | 0.611 (11/18) | 7 | 1 (`mx08`) | 444 |

Three miss mechanisms: 8-page detection sampling (`tl02`, fixed by PR #95);
pdf-inspector's page test missing scanned pages that carry a header line or
junk OCR text (`mx02`, `mx07`, `tl07`, `tl08`) plus the ADR-066 rescue zeroing
evidence after recovering junk (`rf06` fast-path recall 0.236, `rf07` 0.469);
and equation loss the gate never looks at (`bd04`).

### Task 6.7 local OCR tier

464 pages, 28 documents, 731 s, no error. 0.311 of body `needs_ocr` pages reach
token recall ≥ 0.8, 0.516 fall below 0.5, at 0.75 s median per page. Bimodal by
writing system: modern Latin-script print 0.977 median (0.840 ≥ 0.8), the 129
Devanagari and Arabic pages 0.000, handwriting 0.310, the early-modern Latin
book `io06` 0.609. Confidence separates (AUC 0.949); a 0.8 cut escalates 46.9%
and keeps 11.3% below 0.5 recall. `pages_recommending_hosted` fired on 6 of the
206 bad pages.

### Reader comparison (`output/reader_comparison.json`)

On the 41 reviewed pages labelled `usable`: `pdf_inspector` median recall 0.683
and order 0.683 with no text at all on 19 of 41; `liteparse` 0.991 and 0.982;
`pypdf` 0.990 and 0.964. Where pdf-inspector produces text it ties pypdf on
recall and equals or beats it on order. LiteParse keeps the words and loses the
order on multi-column pages, which is queue item 2.

## Session state, 2026-09-18

### Branch `feat/page-level-ocr-routing`, rebased on `v3` at `1e0a4b0`

Committed:

| SHA | What |
| --- | --- |
| `378e26b` | propose page-level OCR routing (planning only) |
| `c4a6d20` | record the evidence gate 1 REWORK verdict |
| `12025fd` | propose the liteparse reading-order fix |
| `38d6bad` | **implement** the liteparse layout classifier and join |
| `d8d7025` | **implement** the OCR routing unit and local tier settings, and the index identity |

`04b2df6` **committed all of it** — tasks 4.1, 4.5a and 4.5b, the three file
splits, the inventory registration and the tripwire re-baseline. The tree is
clean. New modules: `integrations/pdf/page_routing.py`,
`core/ingestion/embed_exclusions.py`, `compose_settings.py`, plus
`tests/unit/test_page_evidence.py` and `tests/unit/test_page_merge.py`.

Verified green at `04b2df6`: full fast suite **2984 passed, 135 skipped, 0
failed**; `openspec validate --all --strict` 57 passed; ruff clean.

**The full fast suite found four failures first, all of them new modules that
were not registered where the project requires.** Targeted suites do not catch
these; `./scripts/local_ci.sh` does. Run it before believing a change is done:

| Failure | Cause | Fix applied |
| --- | --- | --- |
| `test_no_global_settings_reads` | `compose_settings.py` calls `get_settings`, and the allowlist named only the three older composition-root files | added to `_PERMITTED_PATHS` |
| `test_strategy_registration_inventory` (×2) | `integrations/pdf/page_routing.py` absent from the `docs/guides/architecture.md` integration inventory | row added, marker count 19 → 20 |
| `test_clean_base_tripwire` | the pinned executed count moved again with the new tests | re-baselined 2948 → 2983 (effective 2979) from the reported count |

A new integration module needs an inventory row and a marker bump. A new
composition-root file needs an allowlist entry. Neither is optional.

### Task 6.7 and the reader comparison are committed here

This worktree is at `6b70b4f`. `output/local_ocr/`, `output/reader_comparison.json`
and `output/reading_order.json` are committed; the corpus, page images,
transcripts and extractions remain gitignored and exist nowhere else.

### Decisions taken this session, with their reasons

1. **Flat env names.** `OCR_ROUTING_UNIT`, `OCR_LOCAL_MIN_CONFIDENCE`,
   `OCR_LOCAL_OFFLINE`, `OCR_LOCAL_MODEL_DIRECTORY`. `pydantic-settings`
   resolves its `__` delimiter only into nested blocks, and the OCR settings
   are flat top-level fields, so the nested spellings the planning documents
   used first would have been discarded in silence. Those four nested
   spellings are listed in `config/legacy.py` under a new
   `_NEVER_SHIPPED_ALIASES` group with its own message and lifetime rule.
2. **An unknown routing unit raises**, unlike `PDF_READER` and `RAG_PROFILE`,
   which warn and fall back because `auto` resolution is a capability policy.
   The unit feeds the index identity, so a fallback would index a corpus under
   a unit nobody chose.
3. **No script or typography pre-check.** Dropped on the operator's decision.
   The failures announce themselves after the attempt — all 129 Devanagari and
   Arabic pages returned recall 0.000, which empty output catches — and a
   pre-check would need a signal nobody has measured. Task 4.2a is a
   post-check: empty or whitespace output, confidence below 0.8, or
   `hosted_recommended`.
4. **Unit-scoped exclusion keys.** The four page-source counts stay in the one
   central `EXCLUDED_EMBED_METADATA_KEYS`, and `build_index_identity`
   subtracts them when the routing payload says `document`. A document-unit
   install therefore keeps digest
   `3b04467b572e122e25ad04fe7e5175c97e4c055ee0c9eba31c22ad4faaba4550` and does
   not reindex; a page-unit install gets `c51d08f1…` and does.
   `_INDEX_IDENTITY_SCHEMA` stays at 5.
5. **Merge shape.** One document per file, pages joined in page order with a
   blank line, four scalar counts summing to `page_count`, unresolved pages
   keeping native text with no marker, and `ocr_backend` taking a new value
   `mixed` when more than one backend produced text.

### Traps found, do not rediscover them

1. `pdf_inspector.extract_pages_markdown` numbers pages from **0**;
   `process_pdf_with_ocr` numbers them from **1**, and so do the labels.
   `page_routing.page_evidence` normalises to 1-based. Task 6.7 was verified
   unaffected against `mx02` pages 15 to 17.
2. `build_index_identity` hashes the **ambient** embedding model, which
   conftest replaces with a mock. A recorded digest in a test would pin the
   mock, not the configuration. Compare against a payload passed through
   `ocr_routing=` instead.
3. The 500-line ceiling is strict and three files sat on it. `source_state.py`,
   `compose.py` and `config/__init__.py` were split or trimmed to fit; see the
   new modules above. Run `tests/test_file_size_ceiling.py` **before**
   committing, not after — this session committed a violation in `d8d7025`
   and had to repair it.
3a. Read the **pytest summary line**, not the ruff line, before calling a suite
   green. A combined `ruff && pytest` command ends with ruff's
   `All checks passed!` on screen while pytest's own result sits above it. This
   session reported a green suite that had four failures.
4. Splitting `settings_to_effective` into `compose_settings.py` moved the
   patch target: four test files now patch
   `omrg.compose_settings.get_settings` (CLAUDE.md gotcha 8b).
5. `tests/test_clean_base_tripwire.py` pins the base suite's executed count.
   It was re-baselined 2941 → 2948 for the 7 new liteparse reader tests. Adding
   tests moves it again; read the real count from the failure message rather
   than guessing.

## Map: where things live and where they go

```
                         ┌──────────────────────────────┐
                         │            main              │  releases only
                         └──────────────▲───────────────┘
                                        │
                         ┌──────────────┴───────────────┐
                         │             v3               │  everything lands here
                         │   (integration branch)       │
                         └───▲───────────────────▲──────┘
                             │  PR              │  PR
        ┌────────────────────┴──────┐   ┌───────┴───────────────────────┐
        │ feat/page-level-ocr-      │   │ feat/experiment-33-ocr-       │
        │ routing          [CODE]   │   │ routing-natural-positive      │
        │                           │   │                    [DATA]     │
        │ 1. liteparse column fix   │   │ frozen corpus, page images,   │
        │    (done, 38d6bad)        │   │ transcriptions, labels,       │
        │ 2. page-level routing     │   │ Stage A results, report, ADR  │
        │    3.1 settings    done   │   │                               │
        │    3.2 fingerprint done   │   │ runs every measurement, using │
        │    4.1 page evidence      │   │ --code-root to borrow the     │
        │    4.5 merge  <-- HERE    │   │ code from the other worktree  │
        │    4.6 fallbacks          │   │                               │
        │    5.x tests, 6.2 docs    │   │                               │
        └───────────┬───────────────┘   └───────────▲───────────────────┘
                    │                               │
                    └───── numbers only ────────────┘
                     (measured there, quoted here)

closed: feat/full-page-ocr-evidence, merged to v3 as 1e0a4b0
```

Two pull requests, both into `v3`, never into each other:

1. `feat/page-level-ocr-routing` -> `v3`: the LiteParse fix plus page-level
   routing, once tasks 4.5 to 6.2 are done.
2. `feat/experiment-33-...` -> `v3`: protocol, labels, report and ADR, last.

Order of work, with the reason each step waits:

```
 [1] finish page-level tasks 4.5, 4.6, 5.x, 6.2      (code worktree)
      |
 [2] measure the liteparse evidence gate             (data worktree,
      |   two-column order >= 0.90, no regression     --code-root at [1])
      |
 [3] one PR to v3 for both changes                   (code worktree)
      |
 [4] add the results to report.md, write the ADR     (data worktree)
      |
 [5] PR to v3, archive the change, carry the
      gitignored data to v3, remove the worktree     (data worktree)
      |
 [6] later, own branch: rescue-quality signal so a junk
     liteparse rescue counts as OCR-required (rf06, rf07)
```

Why it looks like ping-pong: the code lives in one worktree and the only copy
of the measurement data lives in the other. Code work happens in the code
worktree; anything that produces a number happens in the data worktree. Nothing
else crosses between them.

## Data carry-over (CLAUDE.md Critical Gotcha #15)

Gitignored data moves forward by hand, before any worktree is removed:

```
feat/full-page-ocr-evidence -> feat/page-level-ocr-routing
feat/page-level-ocr-routing -> feat/experiment-33-ocr-routing-natural-positive
feat/experiment-33-...      -> llamaindex-rag-mcp-v3   (final home)
```

Carry the preserve class: `experiments/**/output/`, `experiments/**/corpus/`,
`eval_results.json`, `ground-truth.json` and any `*.json` a report links to;
`graphify-out/`; `.pi/hindsight*`; `.ua/`.

Never copy `.env`. Do not copy regenerable caches: `.venv`, `.coverage`,
`__pycache__`, `.ruff_cache`, `.pytest_cache`, `output/.pdfi_models`.

Procedure at every removal:

1. Copy with `rsync -a`, source first, destination second.
2. Verify before removing: same file count, same total bytes, and one sha256
   spot check per directory. Show the operator the check output.
3. Only then `git worktree remove <path>`.
4. Record here what moved where, and on what date.

This worktree holds the largest and most valuable set: 40 PDFs, 1,123 page
images, 1,614 transcriptions (about $5.30 of OpenRouter spend), the Stage A
extractions and the local OCR results. It cannot be regenerated for free.
Heavy artefacts should go to a GitHub Release before the final removal, per the
`.gitignore` note.

### Movement log

| Date | From | To | What |
| --- | --- | --- | --- |
| 2026-09-18 | `feat/full-page-ocr-evidence` | — | Nothing carried. Its only preserve-class artefact was `graphify-out/` (40 files, 2,448,366 bytes), which is derived from the working tree and regenerates with `graphify update .`. The destination held its own graph of its own branch (21 files, 1,281,171 bytes, `graph.json` sha `d60cd498…` against the source's `52cd415c…`), so copying would have overwritten a live graph with a stale one. Operator decided not to copy. No `.pi`, `.ua`, experiment `output/` or `corpus/`, `eval_results.json`, `ground-truth.json` or `.env` existed there. Worktree removed after PR #95 merged as `1e0a4b0` |

## Guardrails

1. `labels.json` and the corpus are frozen. Never edit a label. Run
   `uv run python $E/freeze.py --check` before any measurement. Report drift;
   do not patch digests without telling the operator.
2. Thresholds `0.5` and `0.10` do not change in Experiment 33. Recalibration
   needs its own proposal.
3. Stage B with PaddleOCR-VL (tasks 6.1 to 6.6) stays **unauthorised**. It
   needs a separate operator decision naming the document subset, timeout and
   runtime budget.
4. Keep `pdf_inspector` → `liteparse` → `pypdf` (ADR-066) as the reader chain.
   The poppler and pypdf text layers exist only as the experiment's answer key.
5. OpenRouter is used only for labelling, and labelling is finished.
6. Experiment PDFs, page images, transcripts and extractions are gitignored.
   Keep it that way.

## Known trap

`pdf_inspector.extract_pages_markdown` numbers pages from **0**;
`process_pdf_with_ocr` numbers them from **1**, and so do the labels.
`compare_readers.py` normalises to 1-based. Task 6.7 was unaffected (verified
against `mx02` pages 15 to 17) and PR #95 only counts those lists.
