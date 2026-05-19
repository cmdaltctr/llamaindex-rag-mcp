# ADR-001: Use uv as Package Manager

**Date:** 2026-05-11
**Status:** Accepted
**Deciders:** Dr Muhammad Aizat Bin Md Hawari
**Git Commits:** `5594176`

## Context

The project needs a Python package manager that handles dependency resolution,
virtual environment creation, and script entry points. The chosen tool must
work well for a project that is both a library and a CLI application with a
`[project.scripts]` entry point (`rag-mcp = "rag_mcp.cli:run_cli"`).

Traditional tools like `pip` + `requirements.txt` lack lockfiles and fast
resolution. `poetry` is mature but slow. `pipenv` has fallen out of favour.
The Python ecosystem has recently seen the emergence of extremely fast
Rust-based tools.

## Decision

Use **uv** (by Astral, the makers of Ruff) as the sole package manager.

- Dependencies declared in `pyproject.toml` (PEP 621 format)
- Lockfile managed by `uv.lock`
- Virtual environments created via `uv sync`
- Scripts executed via `uv run rag-mcp`
- Build backend: `hatchling` (configured in `pyproject.toml`)

## Consequences

### Positive
- Blazing fast dependency resolution (Rust-based)
- Single tool handles venv, dependency management, and script running
- Deterministic builds via `uv.lock`
- PEP 621 compliant — no vendor lock-in, interchangeable with other tools

### Negative
- uv is newer than pip/poetry; some CI environments need explicit installation
- Team members unfamiliar with uv need a brief onboarding step

### Neutral
- All developer documentation references `uv` commands (`uv sync`, `uv run`)

## Alternatives Considered

| Tool | Rejected Because |
|------|-----------------|
| **pip + requirements.txt** | No lockfile, slow resolution, no workspace support |
| **poetry** | Slower dependency resolution, heavier toolchain |
| **pipenv** | Largely superseded by newer tools, slower performance |
| **pdm** | Less community momentum than uv |

## References

- `pyproject.toml` — project metadata, dependencies, and build configuration
- `uv.lock` — deterministic dependency lockfile
