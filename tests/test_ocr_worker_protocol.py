"""Wire-level tests for the duplicated OCR worker JSON Lines protocol.

The worker owns its protocol definitions and OMRG owns an identical
twin (OpenSpec change improve-rag-input-quality-5, task 2.2a). The two
modules never import each other, so these tests prove wire
compatibility the only way possible: byte-identical encoding and
mutual decoding.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from omrg.integrations.ocr_worker import protocol as omrg_protocol

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKER_SRC = REPO_ROOT / "ocr-worker" / "src"

_MODULE_CACHE: dict[str, ModuleType] | None = None


def _modules() -> dict[str, ModuleType]:
    """Return both protocol modules, importing the worker copy from source."""
    global _MODULE_CACHE
    if _MODULE_CACHE is None:
        worker_src = str(WORKER_SRC)
        sys.path.insert(0, worker_src)
        try:
            worker = importlib.import_module("omrg_ocr_worker.protocol")
        finally:
            sys.path.remove(worker_src)
        _MODULE_CACHE = {"omrg": omrg_protocol, "worker": worker}
    return _MODULE_CACHE


def _success_payload(request_id: str, **overrides: Any) -> dict[str, Any]:
    """Build a wire-shaped success payload, applying field overrides."""
    payload: dict[str, Any] = {
        "id": request_id,
        "protocol_version": "1.0",
        "type": "parse_result",
        "ok": True,
        "markdown": "# Heading\n\nBody text.",
        "metadata": {
            "ocr_backend": "stub-worker",
            "page_count": 2,
            "output_schema": {"id": "omrg.ocr.parse_output", "version": "1"},
        },
    }
    for key, value in overrides.items():
        if value is _DELETE:
            del payload[key]
        else:
            payload[key] = value
    return payload


class _Delete:
    """Sentinel for removing a field from a payload helper."""

    pass


_DELETE = _Delete()


def _failure_payload(request_id: str, **overrides: Any) -> dict[str, Any]:
    """Build a wire-shaped error payload, applying field overrides."""
    payload: dict[str, Any] = {
        "id": request_id,
        "protocol_version": "1.0",
        "type": "parse_error",
        "ok": False,
        "error": {"code": "stub_failure", "message": "stub failure"},
    }
    for key, value in overrides.items():
        if value is _DELETE:
            del payload[key]
        else:
            payload[key] = value
    return payload


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload)


# ── Wire compatibility across the two independent copies ──────────────────


def test_constants_agree_between_both_sides() -> None:
    """Twin modules must declare identical protocol identities."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    assert omrg.PROTOCOL_VERSION == worker.PROTOCOL_VERSION
    assert omrg.OUTPUT_SCHEMA_ID == worker.OUTPUT_SCHEMA_ID
    assert omrg.OUTPUT_SCHEMA_VERSION == worker.OUTPUT_SCHEMA_VERSION
    assert omrg.REQUEST_TYPE_PARSE == worker.REQUEST_TYPE_PARSE
    assert omrg.RESPONSE_TYPE_PARSE_RESULT == worker.RESPONSE_TYPE_PARSE_RESULT
    assert omrg.RESPONSE_TYPE_PARSE_ERROR == worker.RESPONSE_TYPE_PARSE_ERROR


def test_request_encoding_is_byte_identical() -> None:
    """Both sides must emit the same request line for the same envelope."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    omrg_line = omrg.encode_line(omrg.make_request("req-1", "/tmp/doc.pdf"))
    worker_line = worker.encode_line(worker.make_request("req-1", "/tmp/doc.pdf"))
    assert omrg_line == worker_line
    assert "\n" not in omrg_line
    assert json.loads(omrg_line)["type"] == "parse"


def test_success_encoding_is_byte_identical() -> None:
    """Both sides must emit the same success line for the same envelope."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    omrg_envelope = omrg.make_success("req-2", "# Doc", ocr_backend="paddleocr-vl", page_count=3)
    worker_envelope = worker.make_success(
        "req-2", "# Doc", ocr_backend="paddleocr-vl", page_count=3
    )
    assert omrg.encode_line(omrg_envelope) == worker.encode_line(worker_envelope)


def test_failure_encoding_is_byte_identical() -> None:
    """Both sides must emit the same error line for the same envelope."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    omrg_envelope = omrg.make_failure("req-3", "stub_failure", "it failed")
    worker_envelope = worker.make_failure("req-3", "stub_failure", "it failed")
    assert omrg.encode_line(omrg_envelope) == worker.encode_line(worker_envelope)


def test_worker_decodes_omrg_requests_and_responses() -> None:
    """The worker copy must accept lines produced by the OMRG copy."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    request = worker.decode_request_line(
        omrg.encode_line(omrg.make_request("req-4", "/docs/a.pdf"))
    )
    assert (request.id, request.pdf_path) == ("req-4", "/docs/a.pdf")

    success = omrg.make_success("req-5", "# M", ocr_backend="b", page_count=1)
    decoded = worker.decode_response_line(omrg.encode_line(success))
    assert isinstance(decoded, worker.ParseSuccess)
    assert decoded.markdown == "# M"

    failure = omrg.make_failure("req-6", "code_a", "boom")
    decoded_failure = worker.decode_response_line(omrg.encode_line(failure))
    assert isinstance(decoded_failure, worker.ParseFailure)
    assert decoded_failure.error.code == "code_a"


def test_omrg_decodes_worker_requests_and_responses() -> None:
    """The OMRG copy must accept lines produced by the worker copy."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    request = omrg.decode_request_line(
        worker.encode_line(worker.make_request("req-7", "/docs/b.pdf"))
    )
    assert request.pdf_path == "/docs/b.pdf"

    success = worker.make_success("req-8", "# W", ocr_backend="b", page_count=9)
    decoded = omrg.decode_response_line(worker.encode_line(success))
    assert isinstance(decoded, omrg.ParseSuccess)
    assert decoded.metadata["page_count"] == 9


# ── Per-module encode/decode behaviour (parametrised over both copies) ─────

REQUEST_CASES = [
    ("malformed_json", "not json at all {{{"),
    ("blank_line", "   "),
]

RESPONSE_CASES = [
    ("malformed_json", "not json at all {{{"),
    ("blank_line", ""),
]


@pytest.mark.parametrize("side", ["omrg", "worker"])
class TestProtocolValidation:
    """Strict validation rules, proven identical on both protocol copies."""

    def test_request_round_trip(self, side: str) -> None:
        mod = _modules()[side]
        request = mod.make_request("req-rt", "/docs/x.pdf")
        decoded = mod.decode_request_line(mod.encode_line(request))
        assert decoded.id == "req-rt"
        assert decoded.pdf_path == "/docs/x.pdf"
        assert decoded.protocol_version == mod.PROTOCOL_VERSION
        assert decoded.type == mod.REQUEST_TYPE_PARSE

    def test_success_round_trip_preserves_id_and_version(self, side: str) -> None:
        mod = _modules()[side]
        envelope = mod.make_success("req-ok", "# T", ocr_backend="paddleocr-vl", page_count=4)
        decoded = mod.decode_response_line(mod.encode_line(envelope))
        assert isinstance(decoded, mod.ParseSuccess)
        assert decoded.id == "req-ok"
        assert decoded.protocol_version == mod.PROTOCOL_VERSION
        assert decoded.metadata["ocr_backend"] == "paddleocr-vl"
        assert decoded.metadata["page_count"] == 4
        schema = decoded.metadata["output_schema"]
        assert schema["id"] == mod.OUTPUT_SCHEMA_ID
        assert schema["version"] == mod.OUTPUT_SCHEMA_VERSION

    def test_failure_round_trip(self, side: str) -> None:
        mod = _modules()[side]
        envelope = mod.make_failure("req-err", "timeout", "worker timed out")
        decoded = mod.decode_response_line(mod.encode_line(envelope))
        assert isinstance(decoded, mod.ParseFailure)
        assert decoded.id == "req-err"
        assert decoded.error.code == "timeout"

    def test_extra_metadata_keys_are_preserved(self, side: str) -> None:
        """Additive diagnostics inside metadata must survive the wire."""
        mod = _modules()[side]
        envelope = mod.make_success(
            "req-extra",
            "# T",
            ocr_backend="b",
            page_count=1,
            extra_metadata={"ocr_required": True},
        )
        decoded = mod.decode_response_line(mod.encode_line(envelope))
        assert isinstance(decoded, mod.ParseSuccess)
        assert decoded.metadata["ocr_required"] is True

    @pytest.mark.parametrize("label,line", REQUEST_CASES)
    def test_rejects_non_json_request_line(self, side: str, label: str, line: str) -> None:
        mod = _modules()[side]
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_request_line(line)
        assert excinfo.value.code == "invalid_json"

    @pytest.mark.parametrize("label,line", RESPONSE_CASES)
    def test_rejects_non_json_response_line(self, side: str, label: str, line: str) -> None:
        mod = _modules()[side]
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(line)
        assert excinfo.value.code == "invalid_json"

    def test_rejects_wrong_protocol_version(self, side: str) -> None:
        mod = _modules()[side]
        request = _dumps(
            {
                "id": "req-v",
                "protocol_version": "0.9",
                "type": "parse",
                "pdf_path": "/docs/x.pdf",
            }
        )
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_request_line(request)
        assert excinfo.value.code == "unsupported_protocol_version"

        response = _dumps(_success_payload("req-v", protocol_version="0.9"))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(response)
        assert excinfo.value.code == "unsupported_protocol_version"

    def test_rejects_mismatched_id(self, side: str) -> None:
        mod = _modules()[side]
        line = _dumps(_success_payload("req-actual"))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(line, expected_id="req-expected")
        assert excinfo.value.code == "mismatched_id"

    def test_mismatched_id_check_accepts_matching_id(self, side: str) -> None:
        mod = _modules()[side]
        line = _dumps(_success_payload("req-match"))
        decoded = mod.decode_response_line(line, expected_id="req-match")
        assert decoded.id == "req-match"

    def test_rejects_extra_envelope_fields(self, side: str) -> None:
        mod = _modules()[side]
        request = _dumps(
            {
                "id": "req-x",
                "protocol_version": "1.0",
                "type": "parse",
                "pdf_path": "/docs/x.pdf",
                "surprise": 1,
            }
        )
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_request_line(request)
        assert excinfo.value.code == "unexpected_field"

        response = _dumps(_success_payload("req-x", surprise=1))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(response)
        assert excinfo.value.code == "unexpected_field"

    def test_rejects_missing_envelope_fields(self, side: str) -> None:
        mod = _modules()[side]
        request = _dumps(
            {
                "id": "req-m",
                "protocol_version": "1.0",
                "type": "parse",
                # pdf_path missing
            }
        )
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_request_line(request)
        assert excinfo.value.code == "missing_field"

        response = _dumps(_success_payload("req-m", markdown=_DELETE))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(response)
        assert excinfo.value.code == "missing_field"

    def test_rejects_non_terminal_and_unknown_types(self, side: str) -> None:
        mod = _modules()[side]
        request_type_line = _dumps(
            {
                "id": "req-t",
                "protocol_version": "1.0",
                "type": "parse",
                "pdf_path": "/docs/x.pdf",
            }
        )
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(request_type_line)
        assert excinfo.value.code == "non_terminal_type"

        unknown_type = _dumps(_success_payload("req-t", type="progress"))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(unknown_type)
        assert excinfo.value.code == "unknown_type"

    def test_rejects_ok_flag_that_contradicts_type(self, side: str) -> None:
        mod = _modules()[side]
        line = _dumps(_success_payload("req-okflag", ok=False))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(line)
        assert excinfo.value.code == "invalid_field"

    def test_rejects_invalid_metadata_shapes(self, side: str) -> None:
        mod = _modules()[side]
        cases = [
            _success_payload("req-md", metadata="not-an-object"),
            _success_payload("req-md", metadata={"page_count": 1, "output_schema": None}),
            _success_payload(
                "req-md",
                metadata={
                    "ocr_backend": "b",
                    "page_count": 1,
                    "output_schema": {"id": "other.schema", "version": "1"},
                },
            ),
            _success_payload(
                "req-md",
                metadata={
                    "ocr_backend": "b",
                    "page_count": True,
                    "output_schema": {
                        "id": mod.OUTPUT_SCHEMA_ID,
                        "version": mod.OUTPUT_SCHEMA_VERSION,
                    },
                },
            ),
        ]
        expected = ["invalid_field", "missing_field", "output_schema_mismatch", "invalid_field"]
        for payload, code in zip(cases, expected, strict=True):
            with pytest.raises(mod.ProtocolError) as excinfo:
                mod.decode_response_line(_dumps(payload))
            assert excinfo.value.code == code

    def test_error_message_is_bounded_and_single_line(self, side: str) -> None:
        """Failure messages must be bounded and carry no raw newlines."""
        mod = _modules()[side]
        huge = "x" * (mod.MAX_ERROR_MESSAGE_LENGTH * 4) + "\ntraceback line\nmore"
        envelope = mod.make_failure("req-bounded", "internal_error", huge)
        line = mod.encode_line(envelope)
        assert "\n" not in line
        assert len(envelope.error.message) <= mod.MAX_ERROR_MESSAGE_LENGTH
        decoded = mod.decode_response_line(line)
        assert isinstance(decoded, mod.ParseFailure)
        assert "\n" not in decoded.error.message
        assert decoded.error.message.endswith("...")

    def test_error_envelope_body_is_validated(self, side: str) -> None:
        mod = _modules()[side]
        line = _dumps(_failure_payload("req-errbody", error={"code": "c"}))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(line)
        assert excinfo.value.code == "missing_field"

        line = _dumps(_failure_payload("req-errbody", error={"code": "", "message": "m"}))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(line)
        assert excinfo.value.code == "invalid_field"

    def test_request_id_and_path_must_be_non_empty_strings(self, side: str) -> None:
        mod = _modules()[side]
        for bad_id in ("", 7, None):
            with pytest.raises(mod.ProtocolError):
                mod.decode_request_line(
                    _dumps(
                        {
                            "id": bad_id,
                            "protocol_version": "1.0",
                            "type": "parse",
                            "pdf_path": "/docs/x.pdf",
                        }
                    )
                )
        with pytest.raises(mod.ProtocolError):
            mod.decode_request_line(
                _dumps(
                    {
                        "id": "req-p",
                        "protocol_version": "1.0",
                        "type": "parse",
                        "pdf_path": "",
                    }
                )
            )
