"""CLI transport — command-line interface split by command group.

This package contains the Typer application and one module per command
group: ``ingest.py``, ``search.py``, ``list.py``, ``watch.py``,
``delete.py``, ``benchmark.py``, and ``profile.py``.

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
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler

from ...config import get_settings
from ...core.ingestion.loader import SUPPORTED_EXTENSIONS

# Import the composition root early so the LlamaIndex global
# ``Settings.embed_model`` is assigned before any ingest/search call
# (previously done at import time in ``config.py``; see ADR-031).
from ... import compose  # noqa: F401

_JSON_HELP = "Output results as JSON."

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
        f"Cannot connect to Ollama at {_OLLAMA_URL}. "
        "Is Ollama running? Start it with: ollama serve"
    )
    if detail:
        msg += f"\n  Detail: {detail}"
    if json_output:
        typer.echo(json.dumps({"status": "error", "message": msg}))
    else:
        console.print(f"[red]Error:[/red] {msg}")



def _detect_gpu_acceleration() -> None:
    """Check Ollama runner type and log GPU acceleration status.

    Only runs when ``LOG_LEVEL=DEBUG``.  Never raises — logs a warning
    on any failure.
    """
    logger = logging.getLogger(__name__)
    try:
        result = subprocess.run(
            ["ollama", "ps", "--format", "json"],
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
            if get_settings().embed_model in name:
                runner = model_info.get("details", {}).get(
                    "format", ""
                ) or model_info.get("details", {}).get("runner", "")
                vram = model_info.get("size", "")
                if "metal" in runner.lower() or "gpu" in runner.lower():
                    logger.debug(
                        "Ollama running %s on Metal GPU — VRAM: %s",
                        name, vram,
                    )
                else:
                    logger.warning(
                        "Ollama running %s on CPU — consider enabling "
                        "Metal for faster embeddings",
                        name,
                    )
                return

        logger.debug(
            "Could not determine Ollama runner — %s not found in "
            "running models",
            get_settings().embed_model,
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

    logger = logging.getLogger(__name__)
    logger.info(
        "Embedding model: %s | batch_size: %d | concurrency: %d",
        get_settings().embed_model,
        get_settings().ingestion.embed_batch_size,
        get_settings().ingestion.embed_concurrency,
    )

    if log_level <= logging.DEBUG:
        _detect_gpu_acceleration()


def _sanitise_display_name(name: str) -> str:
    """Remove ANSI escape sequences from display strings."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", name)


def _version(value: bool) -> None:
    """Print version and exit."""
    if value:
        from ... import __version__

        typer.echo(f"rag-mcp {__version__}")
        raise typer.Exit()


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
    if ctx.invoked_subcommand is None:
        from ..mcp import main as mcp_main

        mcp_main()


def run_cli() -> None:
    """Entry point for CLI mode — delegates to the Typer app."""
    _setup_logging()
    app()



# ── Register all command groups ───────────────────────────────────────────
# Importing these modules registers their ``@app.command()`` decorators.
from . import ingest, search, list, watch, delete, benchmark, profile  # noqa: E402,F401
