"""Observer bootstrap and file hashing for the watch daemon.

Split out of ``watcher.py`` (task 8.6), which exceeded the 500-line ceiling.

design.md D8 proposed a ``debounce.py``, but the debounce timers are per-file
state owned by :class:`DocumentIngestHandler` and cannot be lifted out without
inventing an artificial seam. The natural boundary is event *handling* (which
stays in ``watcher.py``) versus daemon *lifecycle* — observer setup, signal
handling — which lives here.

The content-hash helper (``_sha256_file``) and ``MAX_FILE_SIZE`` moved to
``_shared.py`` to break the watcher↔runner import cycle.
"""

from __future__ import annotations

import logging
import signal
from pathlib import Path

from watchdog.observers import Observer

from .watcher import (
    DEFAULT_DEBOUNCE_SECONDS,
    MIN_DEBOUNCE_SECONDS,
    DocumentIngestHandler,
    resolve_watch_extensions,
)

logger = logging.getLogger(__name__)


# ── CLI entry point ──────────────────────────────────────────────────────────


def watch_directory(
    path: str,
    debounce: float = DEFAULT_DEBOUNCE_SECONDS,
    verbose: bool = False,
    collection_name: str = "documents",
) -> None:
    """Start watching a directory for document changes.

    This is the core function called by the CLI ``watch`` subcommand.
    It creates the handler, starts the watchdog observer, and blocks
    until SIGINT is received.

    Args:
        path: Directory to watch recursively.
        debounce: Debounce interval in seconds (minimum 0.5).
        verbose: Enable DEBUG-level logging if True.
        collection_name: ChromaDB collection to route auto-ingested
            files into (default ``"documents"``).
    """
    from rich.console import Console

    console = Console(stderr=True)

    # Validate debounce
    if debounce < MIN_DEBOUNCE_SECONDS:
        console.print(
            f"[red]Error:[/red] --debounce must be >= {MIN_DEBOUNCE_SECONDS}s (got {debounce}s)"
        )
        raise SystemExit(1)

    # Validate path
    watch_path = Path(path).expanduser().resolve()
    if not watch_path.exists():
        console.print(f"[red]Error:[/red] Path not found: {path}")
        raise SystemExit(1)
    if not watch_path.is_dir():
        console.print(f"[red]Error:[/red] Not a directory: {path}")
        raise SystemExit(1)

    # Adjust log level if verbose. Set it on the daemon PACKAGE, not this
    # module: after the task 8.6 split the event-handling logs come from
    # rag_mcp.daemon.watcher, so scoping to __name__ would silence exactly
    # the output --verbose is meant to reveal.
    if verbose:
        # Set the package logger and the event-handling module explicitly.
        # A child logger with its own level set does not inherit the
        # parent's, so relying on the package alone would leave a
        # pre-configured rag_mcp.daemon.watcher silent.
        logging.getLogger("rag_mcp.daemon").setLevel(logging.DEBUG)
        logging.getLogger("rag_mcp.daemon.watcher").setLevel(logging.DEBUG)

    # Create handler and observer. The watch patterns come from the
    # collection's resolved profile extension set (design D4) so watch and
    # manual ingest cannot diverge: a codebase-profile collection watches
    # source extensions too.
    extensions = resolve_watch_extensions(collection_name)
    handler = DocumentIngestHandler(
        debounce_seconds=debounce,
        watch_root=watch_path,
        collection_name=collection_name,
        extensions=extensions,
    )
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=True)

    # ── SIGINT handler for graceful shutdown ────────────────────────────
    _original_handler = signal.getsignal(signal.SIGINT)
    _sigint_count = 0

    def _on_sigint(signum: int, frame: object) -> None:
        nonlocal _sigint_count
        _sigint_count += 1
        if _sigint_count == 1:
            console.print(
                "\n[yellow]Interrupt received — stopping watcher…[/yellow] "
                "(Ctrl+C again to force quit)"
            )
            handler.stop()
            observer.stop()
        else:
            # Second interrupt: restore default and re-raise
            signal.signal(signal.SIGINT, _original_handler)
            raise KeyboardInterrupt

    signal.signal(signal.SIGINT, _on_sigint)

    # Start watching
    observer.start()
    console.print(f"Watching [bold]{watch_path}[/bold] for document changes…")
    console.print(
        f"  [dim]Collection: {collection_name} | "
        f"Debounce: {debounce}s | "
        f"Extensions: {', '.join(sorted(extensions))}[/dim]"
    )

    try:
        # Block until the observer is stopped (by SIGINT or error)
        observer.join()
    except KeyboardInterrupt:
        # Second Ctrl+C — force stop
        handler.stop()
        observer.stop()
        observer.join(timeout=2)
    finally:
        signal.signal(signal.SIGINT, _original_handler)

    console.print("[green]Watcher stopped cleanly.[/green]")
