"""Answer command — ``omrg answer "<question>"``.

Retrieves through the same profile-resolved path as ``search``, then
synthesises a grounded answer through the composition root's answer
model, printing the answer followed by numbered sources.  All output
(human and ``--json``) goes to stderr per gotcha #5 — stdout stays the
MCP protocol channel.
"""

from __future__ import annotations

import asyncio
import json
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from io import StringIO
from typing import Any

import typer

from ... import compose
from . import _OLLAMA_URL, _print_ollama_error, app, console


def _server_seam(llm: Any) -> Any:
    """Adapt the composition-root LLM to the core async completion seam."""

    async def seam(prompt: str) -> str:
        completion = await llm.acomplete(prompt)
        return completion.text

    return seam


def _failure_result(query: str, error: str) -> dict[str, Any]:
    """Build the standard error result for CLI-local failures.

    Mirrors the core/MCP result skeleton so every ``--json`` emission
    (success and failure) parses on the same terms.
    """
    return {
        "status": "error",
        "query": query,
        "answer": None,
        "citations": [],
        "evidence": [],
        "failure_stage": None,
        "error": error,
        "completion_source": "none",
    }


def _emit_failure(query: str, error: str, json_output: bool) -> None:
    """Print a CLI-local failure on stderr in the requested mode."""
    if json_output:
        typer.echo(json.dumps(_failure_result(query, error), indent=2), err=True)
    else:
        console.print(f"[red]Error:[/red] {error}")


def _ollama_message(detail: str) -> str:
    """Build the friendly Ollama connection message for JSON mode.

    Duplicated from ``_print_ollama_error`` because that helper's JSON
    branch writes to stdout (pre-existing behaviour in a shared module
    this change does not touch); the JSON payload here must go to
    stderr per gotcha #5.
    """
    msg = (
        f"Cannot connect to Ollama at {_OLLAMA_URL}. Is Ollama running? Start it with: ollama serve"
    )
    if detail:
        msg += f"\n  Detail: {detail}"
    return msg


@app.command()
def answer(
    query: str = typer.Argument(..., help="Natural language question to answer."),
    top_k: int | None = typer.Option(None, "--top-k", "-k", help="Max evidence chunks."),
    rerank: bool | None = typer.Option(
        None,
        "--rerank/--no-rerank",
        help="Re-score evidence with the cross-encoder reranker (omit for policy default).",
    ),
    hybrid: bool | None = typer.Option(
        None,
        "--hybrid/--no-hybrid",
        help="Fuse dense vector retrieval with sparse BM25 via RRF (omit for policy default).",
    ),
    collection: str = typer.Option(
        "documents",
        "--collection",
        "-c",
        help="Collection to answer over.",
    ),
    diagnostics: bool = typer.Option(
        False,
        "--diagnostics",
        help="Include retrieval/generation timings and completion counts.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output the result as JSON."),
) -> None:
    """Answer a question from indexed documents with verifiable citations."""
    from ...core.answer import answer as do_answer

    try:
        effective = compose.build_profile_resolver().resolve(collection)
    except ValueError as exc:
        _emit_failure(query, str(exc), json_output)
        raise typer.Exit(code=1) from None

    if top_k is None:
        top_k = effective.top_k

    # Resolve the model once, then hand core the seam or ``None``.  Core
    # owns the outcome: an empty collection still short-circuits to
    # ``no_evidence`` without a model call (spec: empty collection
    # short-circuits), and only evidence-present runs surface core's
    # actionable provider-missing error (task 5.3).
    try:
        llm = compose.build_answer_llm()
    except (ValueError, ImportError) as exc:
        _emit_failure(query, str(exc), json_output)
        raise typer.Exit(code=1) from None
    complete = _server_seam(llm) if llm is not None else None
    source = "server" if llm is not None else "none"

    # Claim verification (ADR-059) is settings-only — no ``--verify``
    # flag by design.  The judge is the server-side model resolved from
    # the profile/env-precedenced answer block; a build failure
    # degrades to verification_skipped, never a CLI failure.
    verify_complete: Any = None
    verify_unavailable_reason: str | None = None
    if getattr(effective.answer, "verify_claims", False):
        try:
            verify_llm = compose.build_verify_llm(answer_block=effective.answer)
        except (ValueError, ImportError) as exc:
            verify_unavailable_reason = f"verification provider unavailable: {exc}"
        else:
            if verify_llm is not None:
                verify_complete = _server_seam(verify_llm)
            else:
                verify_unavailable_reason = (
                    "verification provider unavailable (no judge configured)"
                )

    try:
        output_guard = redirect_stdout(StringIO()) if json_output else nullcontext()
        error_guard = redirect_stderr(StringIO()) if json_output else nullcontext()
        with output_guard, error_guard:
            result = asyncio.run(
                do_answer(
                    query,
                    top_k=top_k,
                    rerank=rerank,
                    hybrid=hybrid,
                    collection_name=collection,
                    include_diagnostics=diagnostics,
                    complete=complete,
                    verify_complete=verify_complete,
                    verify_unavailable_reason=verify_unavailable_reason,
                    completion_source=source,
                    effective_settings=effective,
                )
            )
    except ConnectionError as exc:
        if json_output:
            _emit_failure(query, _ollama_message(str(exc)), json_output)
        else:
            _print_ollama_error(str(exc))
        raise typer.Exit(code=1) from None
    except Exception as exc:  # noqa: BLE001 — CLI boundary reports, never raises.
        _emit_failure(query, str(exc), json_output)
        raise typer.Exit(code=1) from None

    if json_output:
        # Gotcha #5: stdout is the MCP protocol channel — the machine
        # payload goes to stderr for success and failure alike.
        typer.echo(json.dumps(result, indent=2), err=True)
        if result["status"] == "error":
            raise typer.Exit(code=1)
        return

    _print_human(result)


def _print_human(result: dict[str, Any]) -> None:
    """Print the answer, then numbered sources with score and chunk id."""
    status = result.get("status")
    if status == "no_evidence":
        console.print("[yellow]No supporting evidence was found.[/yellow]")
        return
    if status == "error":
        console.print(f"[red]Error:[/red] {result.get('error')}")
        raise typer.Exit(code=1) from None

    if status == "generation_unverified":
        console.print(
            "[yellow]Warning:[/yellow] the answer carried no verifiable "
            "citation; treat it as unverified.\n"
        )
    if status == "unverified_claims":
        failing = result.get("unverified_claims") or []
        console.print(
            "[yellow]Warning:[/yellow] claim verification found "
            f"{len(failing)} unsupported or unreadable claim(s); the "
            "citations resolve, but the cited evidence does not fully "
            "support the answer.\n"
        )
    skipped = result.get("verification_skipped")
    if skipped:
        console.print(f"[dim]Verification skipped: {skipped}[/dim]\n")
    console.print(result.get("answer") or "")

    citations = result.get("citations") or []
    if citations:
        console.print("\n[bold]Sources[/bold]")
        for citation in citations:
            ordinal = citation.get("ordinal")
            source = citation.get("source") or "?"
            chunk_id = citation.get("chunk_id") or "?"
            score = citation.get("score")
            merged = len(citation.get("chunk_ids") or []) > 1
            merged_note = f" (+{len(citation['chunk_ids']) - 1} merged)" if merged else ""
            score_text = f"{score:.3f}" if isinstance(score, (int, float)) else "-"
            console.print(f"  {ordinal}. {source} chunk={chunk_id} score={score_text}{merged_note}")

    diagnostics = result.get("diagnostics")
    if diagnostics:
        console.print(
            f"\n[dim]retrieval={diagnostics['retrieval_ms']:.1f}ms "
            f"generation={diagnostics['generation_ms']:.1f}ms "
            f"completions={diagnostics['completion_calls']}[/dim]"
        )
