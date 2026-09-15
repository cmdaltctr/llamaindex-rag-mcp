# Design: Pin Magika and correct content-detection parsing

## Context

`integrations/magika.py` uses one subprocess CLI selected by injected
`MAGIKA_BINARY`. It has an existing timeout and a warned suffix fallback.
This remains the transport contract.

User-verified `magika==1.0.3`, and prior `0.6.3`, emit nested JSONL results.
The output belongs at `result.value.output`. The current parser reads
`obj.output` and fabricates `unknown/unknown` with `is_text=true`.

The current uncommitted state has `magika>=1.0.3` in `pyproject.toml`, a 1.0.3
lock entry, and three red tests. Leave it untouched in this planning session.

Verification found 24 of 24 real PDFs and real Python files equivalent. Raw
Markdown and TXT labels differ. The observed taxonomy has no literal
`binary` group. TDR-025 remains authoritative for settings injection and
identity. Its `google-magika` and unverified-taxonomy wording is historical
and superseded by the provided evidence until a later TDR update.

A successful classification controls early binary skipping, AST code routing,
and explicit `content_type` identity. Markdown parsing uses its existing
suffix-or-reader-format rule. It remains unchanged.

## Goals

- Pin the official package as `magika==1.0.3` in a later implementation.
- Parse valid JSONL and fail the whole production scan safely for invalid rows.
- Preserve readable documents and code when `is_text` is false.
- Compare existing scanner path sets without a new traversal.
- Block acceptance when a real corpus has a residual label difference.

## Non-Goals

- No Python API migration, second transport, compatibility layer, or taxonomy framework.
- No extension-admission, graph, threshold, cache, retry, confidence, or pipeline change.
- No copied suffix table, second directory walker, label backfill, or re-ingest.
- No benchmark framework, plugin, configuration, or dependency beyond the exact pin.

## Decisions

### D1 — Keep one injected subprocess CLI transport (Q1)

Keep the existing `MAGIKA_BINARY` subprocess transport, timeout, entry points,
and settings injection. Parse `result.value.output` only where
`result.status == "ok"`. Require non-empty string `group` and `label` fields
and boolean `is_text`. Ignore blank JSONL lines. A non-`ok` status, non-JSON
row, malformed successful envelope, or bad required field fails the whole
scan. Raise `ValueError` for invalid rows and add it to the existing
`detect_file_types` fallback catch. This retains the warned suffix fallback
without a new exception class. No error-status allowlist exists. Do not
silently drop an error row or report partial success. Missing
binary, non-zero exit, and timeout use the same fallback. Reject Python API
migration: `identify_path`, `result.ok`, and `result.output` avoid JSON, but
break the selectable executable contract and add object lifecycle. Reject a
schema-version abstraction because this pin supports the observed shape only.

### D2 — Apply one narrow binary boundary rule (Q2)

At the integration boundary, set `group="binary"` only when `is_text is False`
and `group not in {"document", "code", "text"}`. Preserve `label` and
`is_text`. The existing `content_type.startswith("binary")` pipeline check
remains the only skip mechanism. PDF, DOC, DOCX, PPTX, and XLSX remain
readable when `group=document` and `is_text=false`, subject to the existing
extension gate. The versioned taxonomy marks Ada, Django, and Scheme as code,
and BRF as text, while `is_text=false`. A bare false-text rule or document-only
exemption would skip readable input. Reject a taxonomy framework, configuration,
dataclass, or transport abstraction.

### D3 — Normalise only two confirmed text aliases (Q3)

Map detected `text/markdown` to `document/markdown` and `text/txt` to
`document/text`. This avoids the known Markdown and TXT identity churn while
leaving `.md` parsing unchanged. Raw-label acceptance has no value here because
it would cause a taxonomy-only rebuild. Do not use suffixes to correct content,
edit `_SUFFIX_MAP`, add broad aliases, relabel stored rows, or backfill
identity. PDF and Python labels stay unchanged. Identity remains stable only
when its prior explicit label and all other inputs match; old `None` or
`unknown` values can rebuild on a later explicit ingest.

### D4 — Report diagnostic limits separately (Q4)

Use Magika's final `output`, never `dl`. Short or low-confidence Python can
return `text/txt`, normalised to `document/text`. A deliberately misnamed
fixture and a tiny-source probe use the same detector and smoke tool. Designate them before execution. Record their expected non-zero outcome
and any tiny-source limitation separately. Do not pad, retry, change
thresholds, or force a suffix language label. Freeze the real acceptance
corpus before execution with representative common PDF, Python, Markdown, and
TXT paths. It remains a hard all-match, no-error gate. A short-file mismatch
inside that frozen corpus executes option 2. Do not move or exclude a file
after its output is known.

### D5 — Use existing scanners in a fail-closed smoke gate

A later `scripts/magika_label_smoke.py` accepts explicit operator paths and
`--json`. It SHALL reuse `scan_with_suffix` from `core.codebase.codebase_map`
and the corrected Magika scanner, passing injected settings to both.
It MAY reuse `FileEntry` or settings data when needed. It does not copy the suffix table or add a directory walker.
Existing suffix traversal exclusions and limits remain. It compares the path
sets from those existing scanners, then compares their effective
OMRG-normalised labels.

The script may import the `codebase_map` module for `scan_with_suffix`. It
must not import or call `build_codebase_map`, `Engine`, or ingestion,
embedding, store, or composition-root APIs. Static checks catch
`build_codebase_map` and `Engine` symbols. The isolated-process blocker bans
only forbidden ingestion, store, embedder, and composition-root modules. It
does not ban `codebase_map` itself. Both checks must be mutation-sensitive.

The JSON contract retains `groups[].files` records with `path`,
`suffix_label`, `magika_label`, and `would_change`; `total_files`; and
`would_change_count`. Match by path, never zip or JSON order. Fail clearly for
empty input, invalid records, unavailable or timed-out detection, or missing,
extra, or duplicate paths. Each invocation exits non-zero for any mismatch.
It exits zero only for a complete, non-empty all-match result. Run the
pre-designated misnamed and tiny-source diagnostics separately. Record their
expected non-zero outcomes and limitations. Run the frozen acceptance corpus
separately. Its non-zero result executes option 2.

## Evidence

Official sources checked 2026-09-15:

- [CLI JSON and JSONL documentation](https://github.com/google/magika/blob/main/rust/cli/README.md)
  shows the nested `result.value.output` shape.
- [Python binding documentation](https://github.com/google/magika/blob/main/website-ng/src/content/docs/cli-and-bindings/python.md)
  requires `result.ok` before `result.output` access.
- [Magika Python v1.0.3 content definitions](https://github.com/google/magika/blob/python-v1.0.3/python/src/magika/config/content_types_kb.min.json)
  is the authoritative versioned taxonomy for this pin.
- [CLI v1.0.2 status serialisation](https://github.com/google/magika/blob/cli/v1.0.2/rust/cli/src/main.rs#L496-L511)
  corroborates status handling. It does not equate this CLI tag with Python 1.0.3.

The user verified 1.0.3 and 0.6.3. This plan does not claim every release was
tested.

## Risks and implementation gate

Parser defects can create a false successful scan. A permissive binary rule
can skip readable code or documents. Label differences can change identity on
a later explicit ingest. The smoke gate exposes these risks before acceptance.

Before execution, freeze a real acceptance corpus with representative common
PDF, Python, Markdown, and TXT paths. Predesignate deliberately misnamed and
tiny-source probes as separate diagnostics. Run every invocation through the
same smoke and detector. Record commands, executable, exact package and pin,
path coverage, mismatches, counts, elapsed detection, and diagnostic limits
without file contents or secrets. Each diagnostic mismatch remains non-zero
and is recorded separately. A frozen acceptance-corpus mismatch, fallback,
error, empty input, or path-set difference executes option 2. Do not move or
exclude an acceptance file after seeing output. No corpus or persistent-store
ingest occurs. Do not merge until the acceptance gate passes.

After a pass, ask for authorisation before the fast suite and local CI. These
checks may use existing isolated test fixtures and doubles. They must not use
an operator corpus, re-ingest, external model, or production store. Measure
existing CI tripwire counts. Do not guess counts or lower a gate to hide a
failure.

## Undo plan

This planning change remains safe. Before later implementation, record a
path-scoped baseline and diff. `adad033` is the pre-pin dependency reference.
`3dd89f7` contains the settings-injection fix and must remain preserved. Do
not blindly restore either whole ancestor. Do not treat dirty `pyproject.toml`
or `uv.lock` as a safe baseline.

If the implemented acceptance-corpus smoke fails, STOP AND REPORT, then
execute option 2. Remove only the exact
pin-created dependency and lock changes, including the original worker's
dependency delta, plus pin-created parser, tool, and test hunks. Preserve
documentation, pre-existing settings work, unrelated worker changes, and red
regression evidence. Ask approval only before destructive file deletion or
package resynchronisation. Never use `git reset --hard`, a blind whole-file
checkout, automatic retry, re-ingest, or merge.

Create a rejected ADR disposition even though the success ADR is pass-gated.
Update TDR-025, Experiment 31 limitations, and these artifacts with the
rejected pin, smoke evidence, fallback reality, and no reruns. Keep success
tasks incomplete and cancel them with an explanation. No stores are touched,
so no data rollback exists.

## Cut scope

This plan excludes a Python migration, all-taxonomy mapping, benchmark
infrastructure, unconditional dependency-floor exemption, and separate
refactor or research architecture work. Each future task supports a
specification scenario or required decision, tripwire, or undo evidence.
