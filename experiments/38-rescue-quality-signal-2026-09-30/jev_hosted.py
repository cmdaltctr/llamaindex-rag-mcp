"""Score pages with hosted Jev (TypeSafe) as post-verdict arm C, amendment A3.

Page text leaves the machine: the first 2,000 characters of each page go to
api.typesafe.ai. The API key is read from TYPESAFE_API_KEY and is never saved.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

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
from score_signals import eligible_rows, verify_coverage
from signal_stats import equal_cost_threshold

ENDPOINT = "https://api.typesafe.ai/v1/systemone"
OPENJEV_ENDPOINT = "http://127.0.0.1:3000/v1/systemone"
HEAD_CHARACTERS = 2000
WORKERS = 4
ATTEMPTS = 6
RETRY_STATUS = {429, 500, 502, 503, 504, 529}


def build_body(
    question: str, text: str, model: str = "jev-latest", criteria: dict | None = None
) -> dict:
    """Build one Noul request from the head of a page."""
    noul: dict = {"type": "noul", "instructions": question}
    if criteria:
        noul["criteria"] = criteria
    return {"state": text[:HEAD_CHARACTERS], "model": model, "questions": {"readable": noul}}


def post(
    body: dict,
    key: str,
    sleep: Callable[[float], None] = time.sleep,
    endpoint: str = ENDPOINT,
) -> dict:
    """Send one request, retrying rate limits and overload with exponential backoff."""
    request = urllib.request.Request(  # noqa: S310
        endpoint,
        json.dumps(body).encode("utf-8"),
        {"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    for attempt in range(ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
                return json.load(response)
        except urllib.error.HTTPError as error:
            # Status only: the response body could echo page text or credentials.
            if error.code not in RETRY_STATUS or attempt == ATTEMPTS - 1:
                raise RuntimeError(f"Request failed with HTTP {error.code}") from None
        except urllib.error.URLError:
            if attempt == ATTEMPTS - 1:
                raise RuntimeError("Request failed: network error") from None
        sleep(2**attempt)
    raise AssertionError("unreachable")


class JevClient:
    """Probability of yes for the frozen readability question."""

    def __init__(
        self,
        question: str,
        key: str | None = None,
        send: Callable = post,
        criteria: dict | None = None,
        model: str = "jev-latest",
    ) -> None:
        self.question = question
        self.model = model
        self.criteria = criteria
        self.key = key or os.environ.get("TYPESAFE_API_KEY")
        if not self.key:
            raise RuntimeError("TYPESAFE_API_KEY is not set")
        self.send = send

    def probability(self, text: str) -> dict:
        """Return the Noul score with the exact model id and token usage."""
        start = time.perf_counter()
        reply = self.send(
            build_body(self.question, text, model=self.model, criteria=self.criteria), self.key
        )
        value = reply["answers"]["readable"]["noul"]
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            raise ValueError("Jev score outside probability bounds")
        return {
            "score": float(value),
            "model": reply["model"],
            "input_tokens": reply["usage"]["input_tokens"],
            "output_tokens": reply["usage"]["output_tokens"],
            "wall_seconds": time.perf_counter() - start,
        }


def score_many(client: JevClient, texts: list[str], workers: int = WORKERS) -> list[dict]:
    """Score pages in parallel while keeping input order."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(client.probability, texts))


def check_model(payload: dict, new_models: set[str]) -> None:
    """Stop when jev-latest resolves to more than one model version."""
    seen = {row.get("model") for row in payload["rows"]} | new_models
    seen.discard(None)
    if len(seen) > 1:
        raise ValueError(f"jev-latest changed model id mid-run: {sorted(seen)}")


def run_main(source: Path, resume: bool) -> None:
    """Score the junk and healthy rescue pages, checkpointing per document."""
    plan = approved_plan()
    if not any(a["id"] == "A3" and a["status"].startswith("APPROVED") for a in plan["amendments"]):
        raise RuntimeError("amendment A3 must be approved before sending page text")
    verify_freeze(source)
    rescue = read_json(OUTPUT / "rescue_text.json")
    rows = eligible_rows(rescue["rows"])
    question = plan["candidates"]["B"]["request"]["question"]
    client = JevClient(question)
    identity = {
        "candidate": "C",
        "population": "rescue",
        "rescue_sha256": sha256(OUTPUT / "rescue_text.json"),
        "signal_sha256": sha256(Path(__file__)),
        "candidate_definition": plan["candidates"]["C"],
        "question": question,
    }
    target = OUTPUT / "candidate_c.json"
    payload = resume_payload(target, identity, resume)
    for doc_id in rescue["completed_documents"]:
        if doc_id in payload["completed_documents"]:
            print(f"[resume C] {doc_id}", flush=True)
            continue
        doc_rows = [row for row in rows if row["doc_id"] == doc_id]
        texts = {
            tier: read_json(OUTPUT / ".rescue_text" / doc_id / f"{tier}.json")
            for tier in ("liteparse", "pypdf")
        }
        pages = [texts[row["tier"]][row["page"] - 1] for row in doc_rows]
        if any(text_sha256(t) != r["text_sha256"] for t, r in zip(pages, doc_rows, strict=True)):
            raise ValueError("saved page text hash differs from extraction")
        results = score_many(client, pages)
        check_model(payload, {r["model"] for r in results})
        payload["rows"].extend(
            {**row, **result} for row, result in zip(doc_rows, results, strict=True)
        )
        payload["completed_documents"].append(doc_id)
        atomic_json(target, payload)
        print(f"[score C] {doc_id}: {len(doc_rows)} page/tier scores", flush=True)
    verify_coverage(rows, payload["rows"])
    print(f"[score C] complete: {len(payload['rows'])} scores", flush=True)


def run_local(source: Path, resume: bool) -> None:
    """Score the 464 saved local OCR texts at C's frozen equal-cost threshold."""
    plan = approved_plan()
    verify_freeze(source)
    main = read_json(OUTPUT / "candidate_c.json")
    if len(main["completed_documents"]) != plan["source_data"]["documents"]:
        raise ValueError("main scoring for C must finish before the local follow-up")
    primary = [row for row in main["rows"] if row["tier"] == "liteparse"]
    threshold = equal_cost_threshold(primary)
    source_path = source / "output" / "local_ocr" / "pages.json"
    source_rows = read_json(source_path)["rows"]
    gated = [row for row in source_rows if row["body_label"] == "needs_ocr"]
    if len(source_rows) != 464 or len(gated) != 399:
        raise ValueError("local OCR population differs from the registered follow-up")
    root = source / "output" / ".local_ocr_text"

    def path(row: dict) -> Path:
        return root / row["doc_id"] / f"p{row['page']:03d}.md"

    question = plan["candidates"]["B"]["request"]["question"]
    identity = {
        "source_rows_sha256": sha256(source_path),
        "source_text_sha256": {
            f"{r['doc_id']}/p{r['page']:03d}": sha256(path(r)) for r in source_rows
        },
        "signal_sha256": {"C": sha256(Path(__file__))},
        "thresholds": {"C": threshold},
        "question": question,
    }
    target = OUTPUT / "jev_local_text.json"
    payload = resume_payload(target, identity, resume)
    payload["thresholds"] = {"C": threshold}
    client = JevClient(question)
    for doc_id in dict.fromkeys(row["doc_id"] for row in source_rows):
        if doc_id in payload["completed_documents"]:
            print(f"[resume local C] {doc_id}", flush=True)
            continue
        doc_rows = [row for row in source_rows if row["doc_id"] == doc_id]
        texts = [path(row).read_text(encoding="utf-8") for row in doc_rows]
        results = score_many(client, texts)
        check_model(
            payload,
            {r["model"] for r in results} | {s["scores"]["C"]["model"] for s in payload["rows"]},
        )
        payload["rows"].extend(
            {
                "doc_id": doc_id,
                "page": row["page"],
                "body_recall": row["body_recall"],
                "population": "gated" if row["body_label"] == "needs_ocr" else "figure_only",
                "text_sha256": text_sha256(text),
                "scores": {"C": result},
            }
            for row, text, result in zip(doc_rows, texts, results, strict=True)
        )
        payload["completed_documents"].append(doc_id)
        atomic_json(target, payload)
        print(f"[local C] {doc_id}: {len(doc_rows)} pages", flush=True)
    if len({(r["doc_id"], r["page"]) for r in payload["rows"]}) != 464:
        raise ValueError("local follow-up did not cover all 464 saved texts")
    print("[local C] complete: 464 saved pages", flush=True)


def main() -> None:
    """Read runtime arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-exp", required=True, type=Path)
    parser.add_argument("--part", required=True, choices=("main", "local"))
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    runner: dict[str, Any] = {"main": run_main, "local": run_local}
    runner[args.part](args.source_exp.resolve(), args.resume)


if __name__ == "__main__":
    main()
