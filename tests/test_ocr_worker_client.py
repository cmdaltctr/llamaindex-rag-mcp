"""Stream-discipline and lifecycle tests for the OCR worker client.

Covers task 2.2 and 2.2b: round trips against the stub worker, heavy
standard-error drainage that never blocks or contaminates standard
output, structured errors for every post-dispatch failure mode, and
the real worker loop's framing (one terminal line per request, logs on
standard error only).
"""

from __future__ import annotations

import io
import subprocess
import sys
from pathlib import Path

import pytest

from omrg.integrations.ocr_worker import OcrWorkerClient, OcrWorkerError
from omrg.integrations.ocr_worker import protocol as omrg_protocol

REPO_ROOT = Path(__file__).resolve().parent.parent
STUB_WORKER = REPO_ROOT / "tests" / "fixtures" / "ocr_worker" / "stub_worker.py"
WORKER_SRC = REPO_ROOT / "ocr-worker" / "src"

STDERR_FLOOD_LINES = 20000


def _stub_command(mode: str, *extra: str) -> list[str]:
    """Build the launch command for the stub worker."""
    return [sys.executable, str(STUB_WORKER), "--mode", mode, *extra]


@pytest.fixture
def small_pdf(tmp_path: Path) -> Path:
    """A minimal valid-enough PDF file for request payloads."""
    pdf = tmp_path / "small.pdf"
    pdf.write_bytes(b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< >>\n%%EOF\n")
    return pdf


# ── Happy path ─────────────────────────────────────────────────────────────


def test_round_trip_returns_correlated_success(small_pdf: Path) -> None:
    """One request in, one correlated terminal success line out."""
    with OcrWorkerClient(_stub_command("echo")) as client:
        result = client.parse(str(small_pdf))
    assert isinstance(result, omrg_protocol.ParseSuccess)
    assert str(small_pdf) in result.markdown
    assert result.metadata["ocr_backend"] == "stub-worker"
    assert result.metadata["page_count"] == 1
    assert result.protocol_version == omrg_protocol.PROTOCOL_VERSION


def test_client_starts_lazily_and_is_reusable(small_pdf: Path) -> None:
    """Construction starts nothing; the first parse starts one worker."""
    client = OcrWorkerClient(_stub_command("echo"))
    assert client.is_started is False
    try:
        client.parse(str(small_pdf))
        assert client.is_started is True
        pid_first = client._process.pid if client._process else None
        client.parse(str(small_pdf))
        assert client._process.pid == pid_first
    finally:
        client.close()


def test_multiple_requests_share_one_process(small_pdf: Path) -> None:
    """Sequential requests reuse the subprocess (long-lived worker)."""
    with OcrWorkerClient(_stub_command("echo")) as client:
        for _ in range(5):
            result = client.parse(str(small_pdf))
            assert isinstance(result, omrg_protocol.ParseSuccess)
        assert client.is_started is True


def test_stderr_callback_receives_every_line(small_pdf: Path) -> None:
    """Drained diagnostics reach the logging callback intact."""
    seen: list[str] = []
    command = _stub_command("echo", "--stderr-lines", "5")
    with OcrWorkerClient(command, on_stderr_line=seen.append) as client:
        client.parse(str(small_pdf))
    assert len([line for line in seen if "noise" in line]) == 5


# ── Stream discipline (task 2.2b) ─────────────────────────────────────────


def test_heavy_stderr_never_blocks_or_contaminates_stdout(small_pdf: Path) -> None:
    """A stderr flood bigger than any pipe buffer must not block the worker.

    Without independent drainage the stub would fill its 64 KiB
    standard-error pipe and block before answering; the client would
    then time out instead of completing.
    """
    seen: list[str] = []
    command = _stub_command("echo", "--stderr-lines", str(STDERR_FLOOD_LINES))
    with OcrWorkerClient(command, request_timeout=60.0, on_stderr_line=seen.append) as client:
        result = client.parse(str(small_pdf))
    assert isinstance(result, omrg_protocol.ParseSuccess)
    assert result.metadata["ocr_backend"] == "stub-worker"
    noise = [line for line in seen if "noise" in line]
    assert len(noise) == STDERR_FLOOD_LINES
    # The stderr text never reached the protocol stream.
    assert "noise" not in result.markdown


def test_drained_stderr_buffer_is_bounded(small_pdf: Path) -> None:
    """The internal stderr buffer keeps only the most recent lines."""
    command = _stub_command("echo", "--stderr-lines", "1500")
    with OcrWorkerClient(command) as client:
        client.parse(str(small_pdf))
    drained = client.drained_stderr()
    assert len(drained) <= 1000
    assert any("noise 001499" in line for line in drained[-5:])


# ── Structured failures (task 2.2) ────────────────────────────────────────


def test_unexpected_stdout_closure_is_structured(small_pdf: Path) -> None:
    """Output closing before a response yields a structured error."""
    with OcrWorkerClient(_stub_command("close-stdout")) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf), timeout=30.0)
    assert excinfo.value.code == "worker_closed_output"
    assert client.is_started is False


def test_worker_crash_is_structured(small_pdf: Path) -> None:
    """A non-zero exit before responding yields a structured error."""
    with OcrWorkerClient(_stub_command("crash")) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf), timeout=30.0)
    assert excinfo.value.code == "worker_crashed"
    assert "3" in excinfo.value.message
    assert client.is_started is False


def test_wrong_id_is_a_protocol_violation(small_pdf: Path) -> None:
    """A response with a mismatched identifier cannot be correlated."""
    with OcrWorkerClient(_stub_command("wrong-id")) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf))
    assert excinfo.value.code == "protocol_violation"
    assert "mismatched_id" in excinfo.value.message


def test_bad_json_line_is_a_protocol_violation(small_pdf: Path) -> None:
    """A non-JSON line on standard output is a protocol failure."""
    with OcrWorkerClient(_stub_command("bad-json")) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf))
    assert excinfo.value.code == "protocol_violation"
    assert "invalid_json" in excinfo.value.message


def test_nonterminal_line_is_a_protocol_violation(small_pdf: Path) -> None:
    """A request-type envelope on standard output is not a response."""
    with OcrWorkerClient(_stub_command("nonterminal")) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf))
    assert excinfo.value.code == "protocol_violation"
    assert "non_terminal_type" in excinfo.value.message


def test_wrong_version_is_a_protocol_violation(small_pdf: Path) -> None:
    """A response speaking another protocol version is rejected."""
    with OcrWorkerClient(_stub_command("wrong-version")) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf))
    assert excinfo.value.code == "protocol_violation"
    assert "unsupported_protocol_version" in excinfo.value.message


def test_worker_error_envelope_surfaces_its_code(small_pdf: Path) -> None:
    """A structured worker error keeps its code and message."""
    with OcrWorkerClient(_stub_command("error")) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf))
    assert excinfo.value.code == "stub_failure"
    assert excinfo.value.message == "stub failure"


def test_timeout_is_structured(small_pdf: Path) -> None:
    """A worker that never responds produces a timeout error."""
    with OcrWorkerClient(_stub_command("hang"), request_timeout=1.0) as client:
        with pytest.raises(OcrWorkerError) as excinfo:
            client.parse(str(small_pdf))
    assert excinfo.value.code == "timeout"
    assert client.is_started is False


def test_spawn_failure_is_structured(small_pdf: Path) -> None:
    """A command that cannot spawn produces a structured error."""
    client = OcrWorkerClient(["/definitely/not/an/executable-omrg-test"])
    with pytest.raises(OcrWorkerError) as excinfo:
        client.parse(str(small_pdf))
    assert excinfo.value.code == "spawn_failed"


def test_close_is_idempotent(small_pdf: Path) -> None:
    """Closing twice is safe and leaves no process held."""
    client = OcrWorkerClient(_stub_command("echo"))
    try:
        client.parse(str(small_pdf))
    finally:
        client.close()
        client.close()
    assert client.is_started is False


# ── Real worker loop framing (task 2.2 / 2.2b) ────────────────────────────


def _load_worker_module(monkeypatch: pytest.MonkeyPatch):
    """Import the worker loop module straight from ocr-worker/src."""
    monkeypatch.syspath_prepend(str(WORKER_SRC))
    import omrg_ocr_worker.worker as worker_module

    return worker_module


def test_worker_loop_success_framing_in_process(
    monkeypatch: pytest.MonkeyPatch, small_pdf: Path
) -> None:
    """A stubbed seam yields exactly one terminal line on stdout.

    The stubbed seam builds its envelope with the worker's own
    protocol factories: each side of the wire encodes its own envelope
    types, and the strict encoder rejects foreign objects.
    """
    worker = _load_worker_module(monkeypatch)
    import omrg_ocr_worker.protocol as worker_protocol

    def fake_parse(request):
        return worker_protocol.make_success(
            request.id,
            "# Parsed",
            ocr_backend=worker.WORKER_BACKEND,
            page_count=1,
        )

    monkeypatch.setattr(worker, "parse_document", fake_parse)
    request = omrg_protocol.make_request("req-loop-1", str(small_pdf))
    stdin = io.StringIO(omrg_protocol.encode_line(request) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    exit_code = worker.main()

    assert exit_code == 0
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    decoded = omrg_protocol.decode_response_line(lines[0], expected_id="req-loop-1")
    assert isinstance(decoded, omrg_protocol.ParseSuccess)
    assert decoded.markdown == "# Parsed"
    assert decoded.metadata["ocr_backend"] == worker.WORKER_BACKEND


def test_worker_loop_internal_error_is_one_bounded_envelope(
    monkeypatch: pytest.MonkeyPatch, small_pdf: Path
) -> None:
    """Any seam exception becomes one single-line error envelope."""
    worker = _load_worker_module(monkeypatch)

    def exploding_parse(request):
        raise RuntimeError("boom\nsecond line of a fake traceback")

    monkeypatch.setattr(worker, "parse_document", exploding_parse)
    request = omrg_protocol.make_request("req-loop-2", str(small_pdf))
    stdin = io.StringIO(omrg_protocol.encode_line(request) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    exit_code = worker.main()

    assert exit_code == 0
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    decoded = omrg_protocol.decode_response_line(lines[0], expected_id="req-loop-2")
    assert isinstance(decoded, omrg_protocol.ParseFailure)
    assert decoded.error.code == "internal_error"
    assert "\n" not in decoded.error.message
    assert "RuntimeError" in decoded.error.message


def test_worker_loop_invalid_path_uses_real_seam(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The real seam rejects a missing file with a structured error."""
    worker = _load_worker_module(monkeypatch)
    request = omrg_protocol.make_request("req-loop-3", str(tmp_path / "missing.pdf"))
    stdin = io.StringIO(omrg_protocol.encode_line(request) + "\n")
    stdout = io.StringIO()
    monkeypatch.setattr(sys, "stdin", stdin)
    monkeypatch.setattr(sys, "stdout", stdout)

    exit_code = worker.main()

    assert exit_code == 0
    lines = stdout.getvalue().splitlines()
    assert len(lines) == 1
    decoded = omrg_protocol.decode_response_line(lines[0], expected_id="req-loop-3")
    assert isinstance(decoded, omrg_protocol.ParseFailure)
    assert decoded.error.code == "invalid_pdf_path"


def test_worker_subprocess_stdout_is_pure_json_lines(small_pdf: Path) -> None:
    """The real ``python -m omrg_ocr_worker`` keeps stdout protocol-only.

    The main environment has no Paddle worker dependencies, so the
    terminal envelope is a ``paddle_unavailable`` error. This still
    proves the framing: exactly one JSON line on stdout, logs on stderr,
    exit status 0.
    """
    request = omrg_protocol.make_request("req-sub-1", str(small_pdf))
    completed = subprocess.run(
        [sys.executable, "-m", "omrg_ocr_worker"],
        cwd=WORKER_SRC,
        input=omrg_protocol.encode_line(request) + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    decoded = omrg_protocol.decode_response_line(stdout_lines[0], expected_id="req-sub-1")
    assert isinstance(decoded, omrg_protocol.ParseFailure)
    assert decoded.error.code == "paddle_unavailable"
    # Worker logs travel on stderr only.
    assert "starting" in completed.stderr


def test_worker_subprocess_rejects_wrong_version_request(small_pdf: Path) -> None:
    """A wrong-version request gets a correlated invalid_request envelope."""
    raw = '{"id":"req-sub-2","protocol_version":"0.9","type":"parse","pdf_path":"x"}'
    completed = subprocess.run(
        [sys.executable, "-m", "omrg_ocr_worker"],
        cwd=WORKER_SRC,
        input=raw + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0
    stdout_lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert len(stdout_lines) == 1
    decoded = omrg_protocol.decode_response_line(stdout_lines[0], expected_id="req-sub-2")
    assert isinstance(decoded, omrg_protocol.ParseFailure)
    assert decoded.error.code == "invalid_request"
    assert "unsupported_protocol_version" in decoded.error.message


def test_worker_subprocess_exits_on_uncorrelatable_line() -> None:
    """A non-JSON request line ends the process without any stdout output."""
    completed = subprocess.run(
        [sys.executable, "-m", "omrg_ocr_worker"],
        cwd=WORKER_SRC,
        input="definitely not json {{{\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "stopping" in completed.stderr
