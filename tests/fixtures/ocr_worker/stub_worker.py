"""Stub OCR worker for stream-discipline tests (stdlib only).

Speaks the same JSON Lines protocol as the real worker so the client
tests can exercise framing without the Paddle environment. The mode
argument selects a failure or noise behaviour:

- ``echo``: answer every request with a valid success envelope;
- ``error``: answer with a structured ``stub_failure`` envelope;
- ``wrong-id``: answer with a mismatched request identifier;
- ``bad-json``: emit one non-JSON line on standard output;
- ``nonterminal``: emit a request-type object on standard output;
- ``wrong-version``: answer with protocol version ``0.9``;
- ``close-stdout``: close standard output without responding;
- ``crash``: exit with status 3 without responding;
- ``hang``: never respond.

``--stderr-lines N`` writes N noise lines to standard error before
each response, so tests can prove independent drainage.

``--capabilities MODE`` answers the metadata-only capability probe
(design D2.4) instead of entering the request loop: print one JSON
fingerprint line and exit. Modes: ``json`` (a wire-valid fingerprint),
``bad-json`` (garbage on standard output), ``wrong-protocol`` /
``wrong-schema`` (incompatible identities), ``fail`` (exit status 1
without output), ``hang`` (never answer).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

PROTOCOL_VERSION = "1.0"
OUTPUT_SCHEMA = {"id": "omrg.ocr.parse_output", "version": "1"}

CAPABILITY_MODES = ("json", "bad-json", "wrong-protocol", "wrong-schema", "fail", "hang")


def stub_fingerprint_payload() -> dict:
    """Build the stub worker's wire-valid capability fingerprint."""
    return {
        "protocol_version": PROTOCOL_VERSION,
        "packages": {"stub-worker": "1.0"},
        "pipeline": {"identity": "stub-pipeline", "revision": "1"},
        "model": {"identity": "stub-model", "revision": "1"},
        "output_schema": dict(OUTPUT_SCHEMA),
    }


MODES = (
    "echo",
    "error",
    "wrong-id",
    "bad-json",
    "nonterminal",
    "wrong-version",
    "close-stdout",
    "crash",
    "hang",
)


def _emit(payload: dict) -> None:
    """Write one JSON line to standard output and flush it."""
    sys.stdout.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    sys.stdout.write("\n")
    sys.stdout.flush()


def _stderr_noise(count: int) -> None:
    """Write bounded-size noise lines to standard error and flush."""
    for index in range(count):
        sys.stderr.write(f"stub-worker noise {index:06d} {'x' * 64}\n")
    sys.stderr.flush()


def _success(request_id: str, pdf_path: str) -> dict:
    """Build a wire-valid success envelope for the given request."""
    return {
        "id": request_id,
        "protocol_version": PROTOCOL_VERSION,
        "type": "parse_result",
        "ok": True,
        "markdown": f"# Stub extraction\n\nPath: {pdf_path}",
        "metadata": {
            "ocr_backend": "stub-worker",
            "page_count": 1,
            "output_schema": OUTPUT_SCHEMA,
        },
    }


def _failure(request_id: str) -> dict:
    """Build a wire-valid error envelope for the given request."""
    return {
        "id": request_id,
        "protocol_version": PROTOCOL_VERSION,
        "type": "parse_error",
        "ok": False,
        "error": {"code": "stub_failure", "message": "stub failure"},
    }


def _run_capabilities(mode: str) -> int:
    """Answer the metadata-only capability probe, then exit.

    The ``json`` mode prints a wire-valid fingerprint; every other mode
    simulates one unavailability class the OMRG probe must collapse to
    the stable unavailable fingerprint.
    """
    if mode == "json":
        _emit(stub_fingerprint_payload())
        return 0
    if mode == "bad-json":
        sys.stdout.write("this is not json {{{\n")
        sys.stdout.flush()
        return 0
    if mode == "wrong-protocol":
        payload = stub_fingerprint_payload()
        payload["protocol_version"] = "0.9"
        _emit(payload)
        return 0
    if mode == "wrong-schema":
        payload = stub_fingerprint_payload()
        payload["output_schema"] = {"id": "somebody.elses.schema", "version": "9"}
        _emit(payload)
        return 0
    if mode == "fail":
        sys.stderr.write("stub-worker capabilities failing on purpose\n")
        sys.stderr.flush()
        return 1
    # hang: never answer; the probe's own timeout is under test.
    sys.stderr.write("stub-worker capabilities hanging on purpose\n")
    sys.stderr.flush()
    time.sleep(30)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the stub loop selected by the mode argument."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=MODES, default="echo")
    parser.add_argument("--stderr-lines", type=int, default=0)
    parser.add_argument(
        "--capabilities",
        choices=CAPABILITY_MODES,
        default=None,
        nargs="?",
        const="json",
        help="answer the capability probe and exit (default mode: json)",
    )
    args = parser.parse_args(argv)

    if args.capabilities is not None:
        return _run_capabilities(args.capabilities)

    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            sys.stderr.write("stub-worker received a non-JSON line; stopping\n")
            return 2
        request_id = request["id"]
        pdf_path = request["pdf_path"]

        if args.mode == "echo":
            _stderr_noise(args.stderr_lines)
            _emit(_success(request_id, pdf_path))
        elif args.mode == "error":
            _stderr_noise(args.stderr_lines)
            _emit(_failure(request_id))
        elif args.mode == "wrong-id":
            _emit(_success(request_id + "-wrong", pdf_path))
        elif args.mode == "bad-json":
            sys.stdout.write("this is not json {{{\n")
            sys.stdout.flush()
        elif args.mode == "nonterminal":
            payload = dict(request)
            payload["type"] = "parse"
            _emit(payload)
        elif args.mode == "wrong-version":
            payload = _success(request_id, pdf_path)
            payload["protocol_version"] = "0.9"
            _emit(payload)
        elif args.mode == "close-stdout":
            # Close the descriptor itself: closing the sys.stdout
            # wrapper does not reliably signal EOF to the parent on
            # every platform, and this mode exists to test exactly
            # that early-EOF path.
            sys.stdout.flush()
            os.close(1)
            time.sleep(30)
        elif args.mode == "crash":
            sys.stderr.write("stub-worker crashing on purpose\n")
            sys.stderr.flush()
            sys.exit(3)
        elif args.mode == "hang":
            sys.stderr.write("stub-worker hanging on purpose\n")
            sys.stderr.flush()
            time.sleep(30)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
