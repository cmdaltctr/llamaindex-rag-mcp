"""Clean-base install tripwire (task 5.4, make-lancedb-default-and-isolate-chromadb).

Proves the base environment contains neither Chroma distribution, that the
installed project metadata keeps both packages behind the ``chroma`` extra
marker, and that the default runtime path (settings → compose → retrieval)
never loads a Chroma module. The whole module skips when the ``chroma``
extra IS installed — the chroma-extra CI job runs the complement suite.
"""

from __future__ import annotations

import re
import subprocess
import sys
from importlib import import_module, metadata
from importlib.util import find_spec
from pathlib import Path

import pytest

_CHROMA_INSTALLED = find_spec("chromadb") is not None

pytestmark = pytest.mark.skipif(
    _CHROMA_INSTALLED,
    reason="chroma extra installed; this tripwire asserts the clean base install",
)

_CHROMA_DISTS = ("chromadb", "llama-index-vector-stores-chroma")

# ── Base-skip manifest (task 5.2) ─────────────────────────────────────
# The only sanctioned base skips are the named Chroma-gated files. These
# pinned counts come from a clean base install at
# make-lancedb-default-and-isolate-chromadb (commits 869105b..c73f9b4),
# measured via `uv sync --frozen` (the CI-equivalent base state); bump
# them only when the suite legitimately changes. The executed and
# skipped counts come from the self-ignored ``-rs`` run summary line.
# capability added the red-first core (15), compose (4), MCP transport
# (16), LM-free search guard (2), OpenAPI conformance (3) and the
# seven-tool discovery rename, plus five CLI transport cases for
# `omrg answer` (net +46; 2178 -> 2224). The slow golden-answer case
# is deselected by the not-slow marker, not skipped.
# Re-baselined at add-grounded-answer-synthesis-3 review remediation:
# the second review round added the MRTR split suite, filter-security
# fuzz corpus, citations/synthesis bounds, compose degradation, CLI
# stream/hybrid/no-evidence cases, conformance null-and-limits pins,
# and CLI failure-path coverage (2224 -> 2363), plus the similarity
# threshold finiteness case (2364).
# Re-baselined at add-claim-verification-stage: the injected judge,
# graceful-degradation, prompt-injection, profile/env precedence, compose,
# diagnostics, MRTR-prefetch, and transport-level judge-threading suites,
# plus the review round (trailing citations, delimiter escaping, CLI
# degradation) added 39 counted cases (2398 -> 2437).
# Re-baselined at make-omrg-a-standalone-framework-4 review remediation:
# the PR-85 review fixes added the engine-isolation suites — builder
# validation and resolver wiring (legacy-env, fail-closed Chroma,
# explicit-settings strategies, store/env snapshot), engine answer
# threading and LLM-failure propagation, verify degradation, close
# release/reject, profile-resolver store and env-snapshot cases,
# injected-model cache cases, the write-contract global-forbidden and
# adapter-close cases, the SearchRetriever forwarding case, and the
# rewritten settings-guard fixtures, and the decisive two-engine
# isolation suite (tasks 4.8/4.9) with engine-level profile-isolation
# cases (2468 -> 2508 executed, and the two new chroma-gated
# write-contract cases add 2 base skips: 127 -> 129).
# Reference counts assume historical ground truth and the Qwen tokenizer cache
# are present, and the optional OpenAI-like adapter is absent.
# Re-baselined at add-vector-store-label-to-knowledge-base: two registry label
# cases and three collection-list store cases add 5 executed tests (5142 -> 5147).
# Re-baselined at add-collection-display-name: the display name round-trip case,
# 16 route cases and one OpenAPI case add 18 executed tests (5147 -> 5165).
# Re-baselined at organise-backend-folders (2026-10-16): the folder-layout (11)
# and folder-guide (41) suites, 9 registry-string and import-detector cases, 3
# wheel-guide cases, 1 route-scan case and 3 contract-coverage cases for the new
# packages add 68 executed tests (5165 -> 5233). No test was removed.
# Re-baselined at unify-profiles-and-pipelines (2026-10-17): the profile store,
# service, upgrade, resolver, contract, Engine dispatch, route, MCP, CLI and
# watcher suites add 349 executed tests (5233 -> 5582). One test was removed:
# the old "runs on one Engine are serialised" case, replaced by the locking suite.
# Re-baselined at add-chat-history-and-canvas-view-controls (2026-10-18): migration 5 (4),
# chat repository (16) and chat route (14) cases add 34 executed tests (5741 -> 5775);
# the 14 route cases need the web extra.
# Two layout direction cases (GraphLayout model) add 2 more (5775 -> 5777 with the web extra).
# Five chat route error-branch cases (codecov patch gap) add 5 more (5784 -> 5789).
# Re-baselined at add-llm-provider-settings (2026-10-18): descriptor, value-source, keychain,
# engine-provider, redaction, connection and Chat settings route cases add 261 (5789 -> 6050).
# Re-baselined at the openai_compatible and anthropic providers (2026-10-18): 43 descriptor,
# value-source, redaction and Engine cases, 31 route cases (they need the web extra) and 62
# extra role-by-provider parameter cases add 136 (6050 -> 6186). The Anthropic build case uses
# a stub module, so it runs with or without the anthropic extra.
# 6197 = 6190 measured here + 3 tokenizer + 4 ground-truth cases that skip on a clean runner.
# The last four cases are the shared-prefix redaction and no-environment-key tests.
# +5 (2026-10-18, TDR-036): empty-reply and refine-swallow cases in test_answer_empty_reply.py.
# +52 (2026-10-18, user config folder): test_user_config.py and the key-route log test.
# +206 (2026-10-18, context windows and the managed llama.cpp server): settings, launch rules,
# lifecycle with a fake server, routes, Ollama call payloads.
# 6460 = 6453 measured with the web extra + 3 tokenizer + 4 ground-truth cases.
# +2 (2026-10-18): the own-group signal guard tests in test_llamacpp_server_lifecycle.py.
# +15 (2026-10-18, task 17.9): llama.cpp idle sleep rule, route, settings and lock cases.
# +1 (2026-10-18): status read during a timed-out start never says exited.
# +1 (2026-10-19): the fake llama-server answers without a reverse DNS lookup.
# -2 (2026-10-19): the two real-Uvicorn signal tests in test_launch_link.py are marked slow.
# +54 (2026-10-19, add-web-power-menu): admission count (4), power control argv and runner
# (15), power routes (26), launch wiring (2) and the `omrg web start` command (7).
# +499 (2026-10-19, move-settings-to-config-file): the settings-file source, JSONC editor and
# writer, key references, handover, restart snapshot, configuration route, `omrg config`
# commands and the file-backed settings routes. Measured with the web extra: 7162 executed
# against 6663 before (6670 less the 7 optional cases above).
_BASE_EXECUTED = 7169
# Re-baselined check-embedding-stamp-before-dimension (2026-10-18): 10 new cases
# (store stamp-first tests and graph embed-step tests). Measured in two clean
# venvs: 5741 with the web extra, 5091 without; the web extra still adds 650.
# Re-baselined at ci-integration-core-web: the sse-starlette shutdown-flag isolation
# module adds 2 executed tests that need no fastapi (5582 -> 5584).
# Re-baselined at add-pdf-reader-step-setting (2026-10-17): the step reader, option
# availability, fingerprint, identity and Engine probe suites add 36 executed tests
# (5584 -> 5620).
# Re-baselined at add-profile-embedding-model (2026-10-18): the provider model
# override, store and retrieval identity, Engine embedder, workspace v4, lock,
# check-model, route and review-fix suites add 118 executed tests (5620 -> 5738).
# Re-baselined at add-web-allow-origin-option: the origin parser suite adds 23
# executed tests that need no fastapi, and the policy, MCP and launch cases add
# 10 that do (5109 -> 5142; see _WEB_EXTRA_CASES below).
# The working-directory .env check adds 2 executed tests (5107 -> 5109).
# Re-baselined at add-run-output-inspection-and-upload-limit: the run artefact
# route, node summary artefacts, the upload-limit setting, routes and launch
# option, and their contract checks add 49 executed tests (5058 -> 5107). 37 of
# them need fastapi, 36 in two new modules (see _WEB_EXTRA_CASES below).
# Re-baselined at redesign-web-workspace (backend tasks 5 to 7): the integration
# catalogue, experiment folders, provider connections and server log routes
# add 165 executed tests (4893 -> 5058). 70 of them are in four new
# fastapi-dependent modules (see _WEB_EXTRA_CASES below).
# Re-baselined at add-mcp-http-transport (2026-10-14): Engine client
# completion and redaction, the MCP factory and context, workspace settings
# and token storage, port selection, and the MCP-over-HTTP gate, end-to-end
# and contract tests add 117 executed tests (4776 -> 4893). Five of them are
# the Chroma Cloud redaction cases of test_mcp_tools.py, which now build an
# Engine with cloud credentials and no longer need the chroma extra: they ran
# as skips before (133 -> 128 skipped).
# Re-baselined after the add-local-web-pipeline-workspace verification gap
# fixes (2026-10-13): provenance, job events, experiment outputs, OCR
# ownership, import-contract, wheel-check and verification-gap tests add 87
# executed tests (4689 -> 4776); skips and deselections are unchanged.
# Re-baselined at add-local-web-pipeline-workspace (2026-10-13): graph
# contracts, runner, domain graph adapters and parity fixtures, workspace
# records and run service, web transport and OpenAPI conformance, plugin
# host, experiment contexts, starter notebook and guide tests add 1274
# executed tests (3415 -> 4689); skips are unchanged and one slow wheel
# test adds a deselection (19 -> 20).
# Re-baselined at repair-modular-core-boundaries (2026-10-13): registry
# dispatch, owning-store metadata, codebase cache-context and accessor-guard
# regressions add 102 executed tests (3313 -> 3415); skips and deselections
# are unchanged.
# Re-baselined at raise-local-ocr-min-confidence-to-0-9 (2026-10-07):
# below-cut, default-agreement and page/document identity cases add 4
# executed tests (3309 -> 3313); skips and deselections are unchanged.
# Re-baselined at modular-ocr-workers-dots-mocr (2026-09-30): the worker
# core, dots-mocr engine, route, maths-page and route-identity suites,
# plus the ported worker-loop and provisioning cases — +166 (3143 -> 3309).
# Re-baselined at the PR #101 review fix (2026-09-28): whitespace-only
# local OCR on an unresolved page keeps native text — +1 (3142 -> 3143).
# Re-baselined at the PR #100 review fix (2026-09-28): an entity-encoded
# query separator in a Markdown link destination — +1 (3141 -> 3142).
# Re-baselined at normaliser version 2 (2026-09-25, Experiment 36): an
# image-only block leaves no placeholder — +1 (3140 -> 3141).
# Re-baselined at the OCR worker per-page fix (2026-09-25, Experiment 34
# A9): page 1 keeps only its own text — +1 (3139 -> 3140).
# Re-baselined at reader-output normalisation (2026-09-25): fixture,
# rule, setting, chunker and index-identity regressions add 44 cases.
# Re-baselined at the LiteParse line join fix (2026-09-24, Experiment 34):
# words on one visual line, a superscript, a column gap, a right-to-left
# step and a kerning split — net +5 (3090 -> 3095).
# Re-baselined at page-level-ocr-routing review fixes (2026-09-18): the
# CodeRabbit pass hardened both protocol twins' ``make_success`` builder
# (8 parametrised cases), the worker failure envelopes' version echo (2),
# the protocol-1.0 page-request gate (1) and the local model identity
# cache scoping (2) — net +13 (3077 -> 3090).
# Re-baselined at page-level-ocr-routing tasks 4.4/4.5c/4.6 (2026-09-18):
# the page unit wired into the reader seam adds 11 cases — only flagged
# pages OCRed, the all-local backend, one-request escalation, the
# per-page attribution degradations, missing worker and missing local
# runtime, post-dispatch failure, the ADR-066 rescue fallback, and the
# document-unit regression (3066 -> 3077).
# Re-baselined at page-level-ocr-routing task 4.3 (2026-09-18): worker
# protocol 1.1 adds 61 cases — the twinned validation module, the pages
# request and pages_markdown response round trips and validation matrix
# on both copies, the minimum-version rule, the fingerprint supported-set
# acceptance, the client pages wire test, and the worker loop's version
# echo and per-page answer (3005 -> 3066).
# Re-baselined at page-level-ocr-routing task 4.2 (2026-09-18): the local OCR
# tier and its post-check escalation add 22 cases — the force-mode tier call
# and its settings mapping, the escalation matrix (empty, whitespace,
# below-cut, missing-confidence, missing-page, hosted, accumulating
# reasons, the injected cut), the resolved model identity probe and its
# cache, and the identity-payload scoping (2983 -> 3005).
# Re-baselined at page-level-ocr-routing (2026-09-18): the routing unit and its
# index-identity scoping add 35 cases — per-page evidence (5), the page merge
# (12), the never-shipped-alias tripwire (6), the unit-scoped exclusion keys and
# their emitted-document guard (9), and the routing-unit settings (3)
# (2948 -> 2983).
# Re-baselined at liteparse-reading-order (2026-09-18): the layout classifier
# adds 7 cases — two-column join order and its multi_column label, a full-width
# running head over two columns, single-column and table pages keeping library
# order, a sidebar failing the balance condition, and content preservation
# (2941 -> 2948).
# Re-baselined at fix-stale-cleanup-batching (2026-09-16): the batched
# stale-deletion regression adds 1 case (2927 -> 2928).
# Re-baselined for the PR-94 CodeRabbit remediation (2026-09-16): four
# new cases — computed-dynamic-import guard, duplicate-path-spelling and
# file-inside-directory smoke validation, and the binary-transition row
# removal regression (2928 -> 2932); the codecov patch follow-up adds the
# binary-cleanup failure-path case (2932 -> 2933).
# Re-baselined at full-page-ocr-evidence (2026-09-17): eight pdf-inspector
# full-scan evidence cases (2933 -> 2941).
# Re-baselined at pin-magika-detection (2026-09-16): the pinned detector
# added 28 regressions (3 base-install/smoke subprocess, 13 parser and
# boundary, 12 smoke-guard and comparison cases), measured 2923 executed
# in this environment (historical ground truth absent: -4; cached Qwen
# tokenizer present: -0). No skips were added or removed.
# Re-baselined 2026-09-15 from 2897 (thread-settings-through-magika-detection):
# the content-type detection fix adds 2 cases — the ingest-level regression
# (injected settings, no process-global default, no extension-routing
# fallback) and the _magika_binary unit pin.
# Re-baselined 2026-09-13 from 2891 (tiered-reader-fallback-chain): the
# liteparse-first fallback chain adds 6 cases — contradiction rescue,
# unavailable/failed-tier hand-over, extraction-only settings, bare
# adapter use without global settings, and the preserved configured
# LiteParse path.
# Re-baselined 2026-09-13 from 2888 (promote-ocr-fallback-defaults):
# two gate-level pins for the promoted packaged defaults
# (test_packaged_defaults_carry_the_promoted_gate,
# test_fully_flagged_text_based_routes_at_packaged_defaults) plus one
# seam-composition pin (test_packaged_default_composes_the_seam).
# Re-baselined 2026-09-13 from 2879 (pdf-reader-extraction-fallback):
# the Sloman guard adds 9 cases — 7 adapter-level contradiction, retry,
# evidence-correction and no-retry cases plus 2 seam-level routing cases
# at the promoted 0.5/0.10 thresholds.
# Re-baselined 2026-09-13 from 2858 (repeat-pdf-routing-study): the
# experiment 29 tooling suite adds 21 cases — collection discovery,
# private-leak refusal, pinned-baseline verification, synthetic routing
# replay, resume safety and the routing-code-clean guard.
# Re-baselined 2026-09-10 from 2774 (repair-fast-suite-regressions): the
# committed exp 26/27 verdict-validity suites add 38 cases (e5240d1) and
# the mixed-PDF threshold-routing regression tests add 4 (9bf4810). Both
# suites are committed and reviewed; the earlier objection to counting
# the routing tests applied only while the patch was unapproved.
# Re-baselined 2026-09-10 from 2816: the consolidation change added 20
# new tests — 6 mixed-PDF routing gate tests, 4 reader dispatch boundary
# tests, 4 unconditional-types identity tests, 3 exp26 verdict validity
# tests (missing file, negative latency, full-precision thresholds) plus
# 1 parametrize case, and 2 exp27 verdict validity tests (missing file,
# negative latency).
# Review amendment adds 22 synthetic cases: 21 summary safety cases and
# one combined-gate precision case. This expected delta requires a local
# tripwire run; it is not a newly measured CI result.
# The improve-rag-input-quality-5 branch added 259 base cases after
# the prior 2515 pin. Nine cases use the optional OpenAI-like adapter
# packages. The conditional adjustment below keeps the tripwire valid
# in either supported dependency set.
# Includes the 31 engine and public API cases added by PR 85,
# the login-watcher installer suite with security-audit, contention-warning,
# ANSI-stripping, different-label replacement (deferred removal + bootout
# probe), exact-path detection, and ExpatError-skip pins; the
# embedding-write-contract validator suite plus the Experiment 14
# harness regressions (validate-embedding-write-contract, ebc934b); the
# stable source/chunk lineage suites (add-stable-source-chunk-lineage);
# the CLI invalid-path regression (fix/cli-delete-invalid-path); the
# embedding norm-guard suite (guard-embedding-normalisation); the
# LanceDB path-component validation, layout-pin, registry honesty, and
# watcher write-lock suites (add-per-collection-persist-dirs); and the
# native sparse capability, FTS adapter lifecycle, locked-version
# contract, sparse-backend registry/composition validation, and hybrid
# native pipeline suites (implement-native-sparse-backend-strategy);
# the seven search-diagnostics MCP/CLI passthrough cases; the seven core and
# four transport orphaned-source visibility cases; plus 13 fast
# retrieval-quality metric, fixture, and baseline-schema cases;
# plus the force-basicConfig sheltering and closed-FileHandler detection
# regressions (fix-test-isolation-mcp-cli-order); plus the
# embedding-text composition, reader text-format, page-provenance, and
# profile-scoped-extension suites
# (fix-embedding-and-structure-fidelity-1).
# Re-baselined at fix-retrieval-freshness-and-context-assembly-2 stage 5:
# the count had drifted behind stages 1-4 (masked by the stage-1 red
# tests failing the subprocess returncode gate first) and now also
# includes the stage-1 red suites, stages 2-4 (durable data version,
# BM25 invalidation, lineage navigation) and the stage-5 context-assembly
# suite (38 cases) plus MCP/CLI expand-window passthrough (3 cases).
# Re-baselined at fix-retrieval-freshness-and-context-assembly-2 stage 7:
# stage 6 (watcher move handling + source-scoped stale selection) added
# four watcher-move cases after the stage-5 baseline was cut.
# Re-baselined for the CI ChromaDB fix: the $and-wrapping fix added
# four duck-typed where-translation cases to the vectordb contract
# suite (2174 -> 2178).
# Re-baselined at add-grounded-answer-synthesis-3: the answering
# capability added the red-first core (15), compose (4), MCP transport
# (16), LM-free search guard (2), OpenAPI conformance (3) and the
# seven-tool discovery rename, plus five CLI transport cases for
# `omrg answer` (net +46; 2178 -> 2224). The slow golden-answer case
# is deselected by the not-slow marker, not skipped.
# The exact skipped count is no longer pinned (see ``_base_suite_counts``): the
# inner suite runs in parallel, and a parallel run reports one fewer skip than a
# serial run. A test that stops running still moves the exact executed count, and
# the Chroma skip sources are asserted statically below.
# +2 at modular-ocr-workers-dots-mocr: the real-eq01 detector case and the
# real dots.mocr patch case run only when OMRG_EQ01_PDF or
# OMRG_DOTS_MOCR_MODEL_DIR names a local copy (131 -> 133).
# Four historical-prefix cases need ignored ground truth. New safety
# regressions are synthetic and always run. Preserve both exact counts
# when that optional historical input is absent (as in a fresh checkout).
_HISTORICAL_GT = (
    Path(__file__).resolve().parents[1]
    / "experiments/22-raw-query-qwen4b-baseline-2026-09-07/output/ground-truth.json"
)
if not _HISTORICAL_GT.exists():
    _BASE_EXECUTED -= 4
# The nine Exp25 installed-adapter cases always run now:
# the OpenAI-like packages moved into the base dependencies (ADR-083), so the
# pin below includes them and there is no conditional adjustment.
# Three model-token chunking cases use a cached Qwen3-Embedding-4B tokenizer
# when it is present in the HuggingFace hub cache. They skip on a clean CI
# runner, so both supported environments keep an exact, documented manifest.
# Measured 2026-09-11 by running the base suite with $HOME pointed at an empty
# dir (tokenizer absent, historical ground truth still present): executed
# dropped 2858 -> 2855, skipped rose 131 -> 134. The prior value of 2 was
# latent — the count assertion was unreachable until the docs-reference gate
# stopped failing the subprocess returncode check first.
_CACHED_TOKENIZER_CASES = 3
_HF_CACHE = Path.home() / ".cache" / "huggingface" / "hub"
_has_qwen_tokenizer = bool(
    list(_HF_CACHE.glob("models--Qwen--Qwen3-Embedding-4B/snapshots/*/tokenizer.json"))
)
if not _has_qwen_tokenizer:
    _BASE_EXECUTED -= _CACHED_TOKENIZER_CASES
# The reference counts assume the optional ``web`` extra (FastAPI) is
# installed, as in the CI ``test`` job. Without it, each web test module
# skips at import through ``pytest.importorskip("fastapi")``: its cases do
# not run, and pytest reports one skip per module, not one per case. The
# floors matrix and the extras jobs install no ``web`` extra.
# Measured 2026-10-13 by hiding fastapi behind an import shim and running
# the 28 fastapi-dependent files with and without it: 344 cases run with
# the extra; without it each of the 28 modules reports one skip.
# Re-measured at add-mcp-http-transport: six new fastapi-dependent modules add 58
# cases (402 with the extra; 34 module skips without it).
# Re-measured at redesign-web-workspace: four new fastapi-dependent modules
# (integrations, experiment folders, connections, logs) add 70 cases (472
# with the extra; 38 module skips without it).
# Re-measured at add-run-output-inspection-and-upload-limit: two new
# fastapi-dependent modules (run artefacts, upload limit) add 36 cases and the
# MCP conformance module adds 1 (509 with the extra; 40 module skips without it).
# Re-measured at add-web-allow-origin-option: new cases in three existing
# fastapi-dependent modules add 10 (519 with the extra; still 40 module skips).
# Re-measured at ci-integration-core-web: CI had not run on integration/core-web,
# so the count drifted unseen while the profiles, pipelines and Studio changes
# landed. The floors job (no web extra) ran 4951 executed tests against 5056
# pinned, so the fastapi-dependent cases are 105 more (624 with the extra).
# Re-measured at add-profile-embedding-model (2026-10-18) in two clean venvs:
# 5731 executed with the web extra, 5081 without, so 26 more (650).
# add-chat-history-and-canvas-view-controls: the 14 chat route cases need fastapi (664).
# Re-measured at the openai_compatible and anthropic providers: 31 route cases (700).
# Re-measured 2026-10-18 on a base install with no web extra (floors, Python 3.12): the provider
# settings routes, Chat settings, llama.cpp server, config folder and key-route cases all need
# fastapi, so 5771 expected vs 5488 run gave 283 more (983).
# Re-measured at add-web-login-item (2026-10-19) from the CI logs of PR #119: the
# test job ran 6590 executed with the web extra and the floors job ran 5587
# without it, so 20 of the 118 new cases need fastapi (1003).
# +7 executed after the PR #119 review (2026-10-19): install and restart race cases and the
# link-renewal retry; 2 of them need fastapi (1005).
# +14 executed after the restart and link-file fixes (2026-10-19): 8 restart cases and 6
# link-file cases; the 6 link-file cases need fastapi (1011).
# -2 (2026-10-19): the two signal tests moved to the slow suite (1009).
# +47 (2026-10-19, add-web-power-menu): every new case except the 7 `omrg web start`
# cases needs fastapi (1056).
# +75 (2026-10-19, move-settings-to-config-file): measured by hiding fastapi behind an
# import shim, 6031 executed without it against 7162 with it (1131).
_WEB_EXTRA_CASES = 1131
if find_spec("fastapi") is None:
    _BASE_EXECUTED -= _WEB_EXTRA_CASES
# -m "not slow": existing 14, four quality gates and the profile latency check (2026-10-17)
_BASE_DESELECTED = 21
# +2 (2026-10-19): the two signal tests in test_launch_link.py are slow. That module
# needs fastapi (module-level importorskip), so a run without it never collects them.
if find_spec("fastapi") is not None:
    _BASE_DESELECTED += 2
# plus the golden-answer gate (add-grounded-answer-synthesis-3 task 7.1)
# plus the marimo-manifest wheel check (add-local-web-pipeline-workspace).
_CHROMA_GATED_FILES = frozenset(
    {
        "test_chroma_cloud.py",
        "test_chunk_lineage_navigation.py",
        "test_compose.py",
        "test_embedding_write_contract.py",
        "test_experiment_storage.py",
        "test_hybrid_retrieval.py",
        "test_lancedb_store.py",
        "test_metadata_extractor.py",
        "test_native_sparse_backend.py",
        "test_vectordb_contract.py",
    }
)


def _scrub_chroma_modules() -> list[str]:
    """Remove chromadb and its submodules from sys.modules; return names."""
    import sys

    names = [name for name in sys.modules if name == "chromadb" or name.startswith("chromadb.")]
    for name in names:
        del sys.modules[name]
    return names


def test_installed_distributions_exclude_chroma() -> None:
    """A base install must contain neither Chroma distribution."""
    installed = {dist.metadata["Name"].lower() for dist in metadata.distributions()}
    for dist in _CHROMA_DISTS:
        assert dist not in installed, f"{dist} is installed in the base environment"


def test_project_requires_keep_chroma_behind_extra_marker() -> None:
    """Built-package metadata must not declare Chroma as unconditional Requires-Dist.

    The wheel-level check (task 1.3) inspects the built artefact directly;
    this tripwire inspects the *installed* distribution metadata, which is
    what a fresh ``pip install omrg`` environment resolves against.
    """
    requires = metadata.requires("omrg") or []
    for req in requires:
        normalised = req.lower().replace("_", "-")
        assert not normalised.startswith("chromadb(") or "extra ==" in req, (
            f"unconditional chromadb requirement: {req}"
        )
        assert not normalised.startswith("llama-index-vector-stores-chroma") or (
            "extra ==" in req
        ), f"unconditional chroma-vector-store requirement: {req}"
    # And the extra-marked entries must exist.
    marked = [r for r in requires if "chromadb" in r.lower() and "extra ==" in r]
    assert marked, "expected a chromadb requirement behind the chroma extra marker"


def test_default_runtime_loads_no_chroma_modules() -> None:
    """Importing the default runtime path must not load any Chroma module."""
    _scrub_chroma_modules()
    import_module("omrg.compose")
    import_module("omrg.core.retrieval")
    import_module("omrg.core.ingestion")

    import sys

    leaked = [name for name in sys.modules if name == "chromadb" or name.startswith("chromadb.")]
    assert not leaked, f"default runtime imported chroma modules: {leaked}"


def test_base_default_search_runs_without_chroma() -> None:
    """A search against an empty default collection returns [] with Chroma absent.

    Exercises the settings → store resolution → dense query path end to
    end (no results expected — the store is empty), proving the base
    install's default path is functional without the chroma extra.
    """
    _scrub_chroma_modules()
    from omrg.core.retrieval import search

    results = search("tripwire query", top_k=3, hybrid=False)
    assert results == []

    import sys

    leaked = [name for name in sys.modules if name == "chromadb" or name.startswith("chromadb.")]
    assert not leaked, f"search imported chroma modules: {leaked}"


def _pytest_args(*extra: str) -> list[str]:
    """Return the inner pytest command, ignoring this module to avoid recursion."""
    return [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        "not slow",
        "-q",
        "--ignore=tests/test_clean_base_tripwire.py",
        *extra,
    ]


def _base_suite_counts() -> tuple[int, int]:
    """Run the fast base suite in this environment; return ``(passed, deselected)``.

    The subprocess reuses the running interpreter so the assertion holds for the
    exact environment under test. It runs in parallel when pytest-xdist is
    installed (``--dist loadfile`` comes from ``pyproject.toml``), about three
    times faster than a serial run. A parallel summary line has no deselected
    count, so that number comes from a separate collection-only run, which takes
    seconds and gives the same answer in serial and parallel.
    """
    root = Path(__file__).resolve().parent.parent
    parallel = ("-n", "auto", "--maxprocesses=8") if find_spec("xdist") is not None else ()
    run = subprocess.run(
        _pytest_args(*parallel),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=1800,
    )
    assert run.returncode == 0, f"base suite failed:\n{run.stdout}\n{run.stderr}"
    summary = re.search(r"(\d+) passed", run.stdout)
    assert summary, f"unparseable base suite summary:\n{run.stdout[-500:]}"

    collect = subprocess.run(
        _pytest_args("--collect-only"),
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert collect.returncode == 0, f"collection failed:\n{collect.stdout}\n{collect.stderr}"
    collected = re.search(r"tests? collected(?: \((\d+) deselected\))?", collect.stdout)
    assert collected, f"unparseable collection summary:\n{collect.stdout[-500:]}"
    return int(summary.group(1)), int(collected.group(1) or 0)


def test_base_skip_manifest_is_exact() -> None:
    """The clean-base suite pins its executed and deselected counts and Chroma guards.

    Task 5.2: the only sanctioned base skips are the named Chroma-gated
    files, and every one of those cases must run in the chroma-extra CI
    job (which fails if anything skips with the ``chroma extra not
    installed`` reason). The exact executed count catches a test that stops
    running, and the deselected count catches a test that gains or loses the
    ``slow`` mark. The exact skipped count is not pinned: a parallel run
    reports one fewer skip than a serial run, and a skip adds nothing the
    other checks miss. The Chroma-skip sources are asserted statically,
    because module-level ``importorskip`` output differs across invocation
    contexts and is not reliably parseable.
    """
    passed, deselected = _base_suite_counts()

    assert passed == _BASE_EXECUTED, f"base executed count drifted: {passed}"
    assert deselected == _BASE_DESELECTED, f"base deselected count drifted: {deselected}"

    # Static guard check: every declared chroma-gated file must carry its
    # Chroma guard, and no other test file may name the chroma-extra skip
    # reason (a mis-scoped guard would leak that string elsewhere).
    tests_dir = Path(__file__).parent
    guarded: set[str] = set()
    for path in tests_dir.glob("test_*.py"):
        if path.name == Path(__file__).name:
            continue  # this manifest file mentions the reason in prose
        text = path.read_text(encoding="utf-8")
        if "chroma extra not installed" in text:
            guarded.add(path.name)
    missing = _CHROMA_GATED_FILES - guarded
    assert not missing, (
        f"declared chroma-gated files no longer carry their guard: {sorted(missing)}"
    )
    unexpected = guarded - _CHROMA_GATED_FILES
    assert not unexpected, (
        f"chroma-gated skip reason found outside the allowed files: {sorted(unexpected)}"
    )
