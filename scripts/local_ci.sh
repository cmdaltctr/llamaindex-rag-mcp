#!/usr/bin/env bash
# Local equivalent of the PR-blocking CI jobs. Run before pushing to
# catch failures without spending workflow minutes.
#
# Covers: ruff, ruff format, import-linter, OpenSpec strict validation,
# the OpenAPI contract, the torch-free default-install check, and the
# full fast suite under the same env vars CI sets, the frontend gates,
# and the web wheel asset check (skipped when npm is absent).
#
# Deliberately excluded (not replicable without mutating the venv):
#   - floors matrix (uv sync --resolution lowest-direct per extra)
#   - extras matrices (community-leiden, torch, chroma installs)
#   - retrieval-quality tiers and the macOS-only slow suite
# If a change touches dependency floors or an optional extra, let CI
# carry those jobs — or replicate with a throwaway venv.

set -euo pipefail
cd "$(dirname "$0")/.."

step() { printf '\n== %s ==\n' "$1" >&2; }

step "ruff check (whole repo)"
uv run --no-sync ruff check .

step "ruff format --check (whole repo)"
uv run --no-sync ruff format --check .

step "import-linter contracts"
uv run --no-sync lint-imports

step "OpenSpec validate --all --strict"
openspec validate --all --strict

step "OpenAPI contract"
uv run --no-sync python -c "import yaml; from openapi_spec_validator import validate; validate(yaml.safe_load(open('src/omrg/transports/api/openapi.yaml')))"
echo "OpenAPI contract valid"

step "default install is torch-free"
packages="$(uv pip list)"
if printf '%s\n' "$packages" | grep -qiE '^(torch|transformers)([[:space:]]|$)'; then
  echo "FAIL: torch or transformers found in default install" >&2
  exit 1
fi
echo "OK: default install is torch-free"

step "fast suite (CI env)"
PDF_READER=pypdf \
EMBED_PROVIDER=local \
LOCAL_BACKEND=ollama \
EMBED_MODEL=nomic-embed-text \
OLLAMA_BASE_URL=http://localhost:11434 \
METADATA_LLM_PROVIDER=local \
  uv run --no-sync pytest -m "not slow" --tb=short -q

step "frontend gates and web wheel assets"
# CI runs the frontend job; the release workflow runs the wheel check.
# The wheel goes to a temporary directory, so dist/ stays untouched.
if command -v npm >/dev/null 2>&1; then
  (cd web && npm ci && npm run lint && npm run typecheck && npm test && npm run build)
  wheel_dir="$(mktemp -d)"
  trap 'rm -rf "$wheel_dir"' EXIT
  uv build --wheel --out-dir "$wheel_dir"
  uv run --no-sync python scripts/check_web_wheel.py "$wheel_dir"/*.whl
  echo "OK: wheel contains the web workspace assets"
else
  echo "SKIPPED: npm not found. Install Node 22 or later to run the frontend gates and the web wheel check." >&2
fi

step "pyright (advisory — CI runs it non-blocking)"
if command -v npx >/dev/null 2>&1; then
  npx --yes pyright@1.1.412 src || echo "pyright findings (advisory, same as CI)"
else
  echo "npx not available — skipped"
fi

printf '\n== local CI passed ==\n' >&2
