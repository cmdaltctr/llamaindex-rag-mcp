"""Score the pre-registered wordings with Julia, hosted Jev or local OpenJev (amendment A3).

Julia W1 is candidate B2 and Jev W1 is candidate C. OpenJev scores W1 to W3 here,
on a local server bound to 127.0.0.1, so page text stays on the machine.
Both models read the first 2,000 characters of each page.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from experiment_io import (
    OUTPUT,
    approved_plan,
    atomic_json,
    read_json,
    resume_payload,
    sha256,
    text_sha256,
    verify_freeze,
)
from jev_hosted import (
    HEAD_CHARACTERS,
    OPENJEV_ENDPOINT,
    WORKERS,
    JevClient,
    check_model,
    post,
    score_many,
)
from score_signals import eligible_rows, verify_coverage

PLAIN = ("no", "yes")
CLOUD = {"clef": ("G", "clef"), "clefflash": ("H", "clef-flash")}


def julia_request(wording: dict) -> dict:
    """Send the false and true descriptions as Julia's ordered noul options."""
    return {
        "type": wording.get("type", "noul"),
        "question": wording["question"],
        "options": [wording["false"], wording["true"]],
    }


def jev_criteria(wording: dict) -> dict | None:
    """Send criteria only when the wording defines more than plain yes and no."""
    if (wording["false"], wording["true"]) == PLAIN:
        return None
    return {"true": wording["true"], "false": wording["false"]}


def scorer(model: str, wording: dict, plan: dict):
    """Return a function that maps a list of page heads to score dictionaries."""
    if model == "jev":
        client = JevClient(wording["question"], criteria=jev_criteria(wording))
        return lambda texts: score_many(client, texts)
    if model in CLOUD:
        token, account = (
            os.environ.get("CLOUDFLARE_API_TOKEN"),
            os.environ.get("CLOUDFLARE_ACCOUNT_ID"),
        )
        if not (token and account):
            raise RuntimeError("CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID must be set")
        api_name = CLOUD[model][1]
        endpoint = f"https://api.cloudflare.com/client/v4/accounts/{account}/ai/run/@cf/cloudflare/{api_name}"
        client = JevClient(
            wording["question"],
            key=token,
            criteria=jev_criteria(wording),
            model=api_name,
            send=lambda body, key: post(body, key, endpoint=endpoint)["result"],
        )
        return lambda texts: score_many(client, texts)
    if model in ("openjev", "flash9b", "clefmlx", "clefmlx8", "clefgguf"):
        client = JevClient(
            wording["question"],
            key="local",
            criteria=jev_criteria(wording),
            send=lambda body, key: post(body, key, endpoint=OPENJEV_ENDPOINT),
        )
        # llama-server stalled when four decision requests overlapped (60 s timeouts), so
        # it gets one request at a time. The other local servers already queue requests.
        workers = 1 if model == "clefgguf" else WORKERS
        return lambda texts: score_many(client, texts, workers=workers)
    from julia_onnx import JuliaRuntime, yes_probability

    runtime = JuliaRuntime(plan, require_parity=True)
    request = julia_request(wording)
    return lambda texts: [
        {"score": yes_probability(runtime.logits({**request, "state": t}))} for t in texts
    ]


def run(source: Path, model: str, name: str, resume: bool) -> None:
    """Score one model and wording over every junk and healthy page/tier pair."""
    plan = approved_plan()
    if model in CLOUD and CLOUD[model][0] not in plan["candidates"]:
        raise RuntimeError(
            "register the Cloudflare candidate in plan.json before sending page text"
        )
    wording = plan["wordings"][name]
    verify_freeze(source)
    rescue = read_json(OUTPUT / "rescue_text.json")
    rows = eligible_rows(rescue["rows"])
    identity = {
        "model": model,
        "wording": name,
        "definition": wording,
        "head_characters": HEAD_CHARACTERS,
        "rescue_sha256": sha256(OUTPUT / "rescue_text.json"),
        "runner_sha256": sha256(Path(__file__)),
    }
    target = OUTPUT / f"wording_{model}_{name.lower()}.json"
    payload = resume_payload(target, identity, resume)
    score = scorer(model, wording, plan)
    for doc_id in rescue["completed_documents"]:
        if doc_id in payload["completed_documents"]:
            continue
        doc_rows = [r for r in rows if r["doc_id"] == doc_id]
        texts = {
            tier: read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
            for tier in ("liteparse", "pypdf")
        }
        pages = [texts[r["tier"]][r["page"] - 1] for r in doc_rows]
        if any(text_sha256(t) != r["text_sha256"] for t, r in zip(pages, doc_rows, strict=True)):
            raise ValueError("saved page text hash differs from extraction")
        results = score([t[:HEAD_CHARACTERS] for t in pages])
        if model in ("jev", "openjev", "flash9b", "clefmlx", "clefmlx8", "clefgguf", *CLOUD):
            check_model(payload, {r["model"] for r in results})
        payload["rows"].extend({**r, **s} for r, s in zip(doc_rows, results, strict=True))
        payload["completed_documents"].append(doc_id)
        atomic_json(target, payload)
        print(f"[{model} {name}] {doc_id}", flush=True)
    verify_coverage(rows, payload["rows"])
    print(f"[{model} {name}] complete: {len(payload['rows'])} scores", flush=True)


def main() -> None:
    """Read runtime arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument(
        "--model",
        required=True,
        choices=(
            "julia",
            "jev",
            "openjev",
            "flash9b",
            "clef",
            "clefflash",
            "clefmlx",
            "clefmlx8",
            "clefgguf",
        ),
    )
    parser.add_argument("--wording", required=True, choices=("W1", "W2", "W3", "C1"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    run(args.source_exp.resolve(), args.model, args.wording, args.resume)


if __name__ == "__main__":
    main()
