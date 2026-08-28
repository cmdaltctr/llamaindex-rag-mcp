"""CLI transport — command-line interface split by command group.

This package contains the Typer application and one module per command
group: ``ingest.py``, ``search.py``, ``list.py``, ``watch.py``,
``delete.py``, ``benchmark.py``, ``profile.py``, and
``install_login_watcher.py``.

All output goes to stderr (gotcha #5 — stdout is the MCP protocol channel
when the server starts with no subcommand).

Public API: ``run_cli()`` is the entry point declared in ``pyproject.toml``.
"""

from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys

import typer
from rich.console import Console
from rich.logging import RichHandler

# The composition root is initialised from ``callback`` after Click has
# handled help and version flags.
from ... import compose

_JSON_HELP = "Output results as JSON."
_runtime_details_enabled = False

app = typer.Typer(
    name="rag-mcp",
    help=(
        "LlamaIndex RAG MCP server — document ingestion and semantic "
        "retrieval. Run with no arguments to start the MCP stdio server."
    ),
    no_args_is_help=False,
    add_completion=True,
)

console = Console(stderr=True)

# ── Ollama base URL for error messages ────────────────────────────────────
_OLLAMA_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


def _print_ollama_error(detail: str, json_output: bool = False) -> None:
    """Print a friendly Ollama connection error message."""
    msg = (
        f"Cannot connect to Ollama at {_OLLAMA_URL}. Is Ollama running? Start it with: ollama serve"
    )
    if detail:
        msg += f"\n  Detail: {detail}"
    if json_output:
        typer.echo(json.dumps({"status": "error", "message": msg}))
    else:
        console.print(f"[red]Error:[/red] {msg}")


def _detect_gpu_acceleration(embed_model: str | None = None) -> None:
    """Check Ollama runner type and log GPU acceleration status.

    Only runs when ``LOG_LEVEL=DEBUG``.  Never raises — logs a warning
    on any failure.
    """
    logger = logging.getLogger(__name__)
    if embed_model is None:
        embed_model = compose.runtime_summary()[0]
    try:
        result = subprocess.run(
            ["ollama", "ps", "--format", "json"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            logger.debug(
                "Could not determine Ollama runner — ollama ps exited %d",
                result.returncode,
            )
            return

        data = json.loads(result.stdout)
        models = data.get("models", [])
        for model_info in models:
            name = model_info.get("name", "")
            if embed_model in name:
                runner = model_info.get("details", {}).get("format", "") or model_info.get(
                    "details", {}
                ).get("runner", "")
                vram = model_info.get("size", "")
                if "metal" in runner.lower() or "gpu" in runner.lower():
                    logger.debug(
                        "Ollama running %s on Metal GPU — VRAM: %s",
                        name,
                        vram,
                    )
                else:
                    logger.warning(
                        "Ollama running %s on CPU — consider enabling Metal for faster embeddings",
                        name,
                    )
                return

        logger.debug(
            "Could not determine Ollama runner — %s not found in running models",
            embed_model,
        )
    except FileNotFoundError:
        logger.debug("Could not determine Ollama runner — ollama CLI not found")
    except subprocess.TimeoutExpired:
        logger.debug("Could not determine Ollama runner — ollama ps timed out")
    except Exception as exc:
        logger.debug("Could not determine Ollama runner — %s", exc)


def _setup_logging() -> None:
    """Configure Python logging for rag_mcp modules.

    All output goes to stderr to keep stdout clean for the MCP protocol.
    Controlled by LOG_LEVEL env var (default: INFO).
    """
    global _runtime_details_enabled

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, level, logging.INFO)

    handler = RichHandler(
        level=log_level,
        console=Console(stderr=True),
        show_time=True,
        show_path=False,
        markup=False,
    )
    logging.basicConfig(
        level=log_level,
        format="%(name)s: %(message)s",
        datefmt="[%X]",
        handlers=[handler],
        force=True,
    )
    _runtime_details_enabled = True


def _sanitise_display_name(name: str) -> str:
    """Remove ANSI escape sequences from display strings."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", name)


def _version(value: bool) -> None:
    """Print version and exit."""
    if value:
        from ... import __version__

        typer.echo(f"rag-mcp {__version__}")
        raise typer.Exit()


def _initialise_runtime() -> None:
    """Initialise runtime dependencies for a command that will execute."""
    try:
        compose.ensure_runtime_setup()
    except (ImportError, ValueError, RuntimeError) as exc:
        # RuntimeError carries the redacted Chroma Cloud connection
        # failure — an explicit cloud selection never falls back to a
        # local index, so the command must stop here.
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from None
    if not _runtime_details_enabled:
        return
    embed_model, batch_size, concurrency = compose.runtime_summary()
    logger = logging.getLogger(__name__)
    logger.info(
        "Embedding model: %s | batch_size: %d | concurrency: %d",
        embed_model,
        batch_size,
        concurrency,
    )
    # Storage summary: selected backend plus location — never the API key.
    logger.info("%s", compose.storage_summary())
    if logger.isEnabledFor(logging.DEBUG):
        _detect_gpu_acceleration(embed_model)


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        help="Show version and exit.",
        callback=_version,
        is_eager=True,
    ),
) -> None:
    """Run with no arguments to start the MCP stdio server."""
    _initialise_runtime()
    if ctx.invoked_subcommand is None:
        from ..mcp import main as mcp_main

        mcp_main()


def run_cli() -> None:
    """Entry point for CLI mode — delegates to the Typer app."""
    global _runtime_details_enabled

    if not {"--help", "-h", "--version"}.intersection(sys.argv[1:]):
        _setup_logging()
    try:
        app()
    finally:
        _runtime_details_enabled = False


# ── Register all command groups ───────────────────────────────────────────
# Importing these modules registers their ``@app.command()`` decorators.
from . import (  # noqa: E402,F401
    benchmark,
    delete,
    ingest,
    install_login_watcher,
    list,
    profile,
    search,
    watch,
)
