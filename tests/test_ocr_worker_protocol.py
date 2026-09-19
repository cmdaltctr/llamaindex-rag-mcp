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
    assert omrg.SUPPORTED_PROTOCOL_VERSIONS == worker.SUPPORTED_PROTOCOL_VERSIONS
    assert omrg.PAGES_PROTOCOL_VERSION == worker.PAGES_PROTOCOL_VERSION
    assert omrg.OUTPUT_SCHEMA_ID == worker.OUTPUT_SCHEMA_ID
    assert omrg.OUTPUT_SCHEMA_VERSION == worker.OUTPUT_SCHEMA_VERSION
    assert omrg.REQUEST_TYPE_PARSE == worker.REQUEST_TYPE_PARSE
    assert omrg.RESPONSE_TYPE_PARSE_RESULT == worker.RESPONSE_TYPE_PARSE_RESULT
    assert omrg.RESPONSE_TYPE_PARSE_ERROR == worker.RESPONSE_TYPE_PARSE_ERROR


def test_twin_validation_modules_are_importable_and_agree() -> None:
    """The split validation helpers must stay twinned too.

    The decoder validation lives in a sibling module (the 500-line ceiling
    forced the split); both projects carry a copy, and the wire stays
    compatible only if both agree on the error codes and schema constants.
    """
    worker_src = str(WORKER_SRC)
    sys.path.insert(0, worker_src)
    try:
        worker_validation = importlib.import_module("omrg_ocr_worker.validation")
    finally:
        sys.path.remove(worker_src)
    from omrg.integrations.ocr_worker import validation as omrg_validation

    assert omrg_validation.OUTPUT_SCHEMA_ID == worker_validation.OUTPUT_SCHEMA_ID
    assert omrg_validation.OUTPUT_SCHEMA_VERSION == worker_validation.OUTPUT_SCHEMA_VERSION
    for name in (
        "ERR_INVALID_JSON",
        "ERR_UNSUPPORTED_PROTOCOL_VERSION",
        "ERR_MISSING_FIELD",
        "ERR_INVALID_FIELD",
        "ERR_UNEXPECTED_FIELD",
        "ERR_NON_TERMINAL_TYPE",
        "ERR_UNKNOWN_TYPE",
        "ERR_MISMATCHED_ID",
        "ERR_OUTPUT_SCHEMA_MISMATCH",
    ):
        assert getattr(omrg_validation, name) == getattr(worker_validation, name)
    # The protocol modules must re-export the public validation names so
    # every existing importer keeps working.
    assert omrg_protocol.ProtocolError is omrg_validation.ProtocolError
    assert omrg_protocol.OUTPUT_SCHEMA_ID is omrg_validation.OUTPUT_SCHEMA_ID


def test_request_encoding_is_byte_identical() -> None:
    """Both sides must emit the same request line for the same envelope."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    omrg_line = omrg.encode_line(omrg.make_request("req-1", "/tmp/doc.pdf"))
    worker_line = worker.encode_line(worker.make_request("req-1", "/tmp/doc.pdf"))
    assert omrg_line == worker_line
    assert "\n" not in omrg_line
    assert json.loads(omrg_line)["type"] == "parse"


def test_pages_request_encoding_is_byte_identical() -> None:
    """A page-listed request must encode identically on both sides."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    omrg_line = omrg.encode_line(omrg.make_request("req-p", "/tmp/doc.pdf", pages=[3, 7]))
    worker_line = worker.encode_line(worker.make_request("req-p", "/tmp/doc.pdf", pages=[3, 7]))
    assert omrg_line == worker_line
    payload = json.loads(omrg_line)
    assert payload["pages"] == [3, 7]
    assert payload["protocol_version"] == "1.1"


def test_plain_request_speaks_the_minimum_version() -> None:
    """A request without pages speaks 1.0, so an un-upgraded worker serves it.

    Protocol 1.1 introduced exactly one payload feature: the page list. A
    request that does not use it is expressible in 1.0, and speaking the
    minimum version keeps document-unit routing alive against a worker
    still on 1.0 during a rolling upgrade.
    """
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    for mod in (omrg, worker):
        request = mod.make_request("req-min", "/tmp/doc.pdf")
        assert request.protocol_version == "1.0"
        payload = json.loads(mod.encode_line(request))
        assert "pages" not in payload
        assert payload["protocol_version"] == "1.0"


def test_success_encoding_is_byte_identical() -> None:
    """Both sides must emit the same success line for the same envelope."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    omrg_envelope = omrg.make_success("req-2", "# Doc", ocr_backend="paddleocr-vl", page_count=3)
    worker_envelope = worker.make_success(
        "req-2", "# Doc", ocr_backend="paddleocr-vl", page_count=3
    )
    assert omrg.encode_line(omrg_envelope) == worker.encode_line(worker_envelope)


def test_pages_markdown_success_encoding_is_byte_identical() -> None:
    """A per-page success must encode identically on both sides."""
    omrg, worker = _modules()["omrg"], _modules()["worker"]
    omrg_envelope = omrg.make_success(
        "req-pm",
        "# P3\n\n# P7",
        ocr_backend="paddleocr-vl",
        page_count=2,
        pages_markdown=["# P3", "# P7"],
        protocol_version="1.1",
    )
    worker_envelope = worker.make_success(
        "req-pm",
        "# P3\n\n# P7",
        ocr_backend="paddleocr-vl",
        page_count=2,
        pages_markdown=["# P3", "# P7"],
        protocol_version="1.1",
    )
    assert omrg.encode_line(omrg_envelope) == worker.encode_line(worker_envelope)
    payload = json.loads(omrg.encode_line(omrg_envelope))
    assert payload["pages_markdown"] == ["# P3", "# P7"]
    assert payload["protocol_version"] == "1.1"


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
        # A plain request speaks the minimum version that expresses it.
        assert decoded.protocol_version == "1.0"
        assert decoded.pages is None
        assert decoded.type == mod.REQUEST_TYPE_PARSE

    def test_pages_request_round_trip(self, side: str) -> None:
        mod = _modules()[side]
        request = mod.make_request("req-rt-pages", "/docs/x.pdf", pages=[2, 5])
        decoded = mod.decode_request_line(mod.encode_line(request))
        assert decoded.id == "req-rt-pages"
        assert decoded.protocol_version == "1.1"
        assert decoded.pages == (2, 5)

    def test_decode_accepts_a_1_1_request_without_pages(self, side: str) -> None:
        """``pages`` is optional on 1.1: absence is the whole-document request."""
        mod = _modules()[side]
        line = _dumps(
            {
                "id": "req-11-plain",
                "protocol_version": "1.1",
                "type": "parse",
                "pdf_path": "/docs/x.pdf",
            }
        )
        decoded = mod.decode_request_line(line)
        assert decoded.protocol_version == "1.1"
        assert decoded.pages is None

    def test_rejects_pages_on_a_1_0_request(self, side: str) -> None:
        """Version 1.0 never defined ``pages``; carrying it there is a violation."""
        mod = _modules()[side]
        line = _dumps(
            {
                "id": "req-10-pages",
                "protocol_version": "1.0",
                "type": "parse",
                "pdf_path": "/docs/x.pdf",
                "pages": [2],
            }
        )
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_request_line(line)
        assert excinfo.value.code == "unexpected_field"

    @pytest.mark.parametrize(
        "label,pages",
        [
            ("empty_list", []),
            ("not_a_list", "3"),
            ("zero_page", [0]),
            ("negative_page", [-1]),
            ("bool_page", [True]),
            ("float_page", [1.5]),
            ("string_page", ["2"]),
            ("duplicate_pages", [1, 1]),
            ("unordered_pages", [2, 1]),
        ],
    )
    def test_rejects_invalid_pages_shapes(self, side: str, label: str, pages: Any) -> None:
        """The page list is non-empty, positive, strictly increasing integers."""
        mod = _modules()[side]
        line = _dumps(
            {
                "id": "req-bad-pages",
                "protocol_version": "1.1",
                "type": "parse",
                "pdf_path": "/docs/x.pdf",
                "pages": pages,
            }
        )
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_request_line(line)
        assert excinfo.value.code == "invalid_field"

    @pytest.mark.parametrize(
        "label,pages",
        [
            ("empty", []),
            ("zero", [0]),
            ("unordered", [2, 1]),
            ("not_ints", ["2"]),
            ("bool", [True]),
        ],
    )
    def test_make_request_validates_pages(self, side: str, label: str, pages: Any) -> None:
        """The builder refuses to construct an envelope the decoder would reject."""
        mod = _modules()[side]
        with pytest.raises(ValueError):
            mod.make_request("req-build-pages", "/docs/x.pdf", pages=pages)

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

    def test_pages_markdown_round_trip(self, side: str) -> None:
        """Per-page Markdown travels as a parallel list and survives the wire."""
        mod = _modules()[side]
        envelope = mod.make_success(
            "req-ok-pages",
            "# P2\n\n# P5",
            ocr_backend="paddleocr-vl",
            page_count=2,
            pages_markdown=["# P2", "# P5"],
        )
        decoded = mod.decode_response_line(mod.encode_line(envelope))
        assert isinstance(decoded, mod.ParseSuccess)
        assert decoded.pages_markdown == ("# P2", "# P5")
        assert decoded.protocol_version == "1.1"

    @pytest.mark.parametrize(
        "label,values",
        [
            ("plain_string", "# P2 # P5"),
            ("int_entries", ["# P2", 7]),
            ("none_entries", [None]),
            ("empty_list", []),
        ],
    )
    def test_make_success_validates_pages_markdown(
        self, side: str, label: str, values: Any
    ) -> None:
        """The builder refuses shapes the wire decoder would reject or mangle.

        A plain string is the trap: ``tuple()`` splits it into one page
        per character, and the decoder would accept those characters as
        pages. The builder and the decoder must agree before the wire.
        """
        mod = _modules()[side]
        with pytest.raises(ValueError):
            mod.make_success(
                "req-build-pm",
                "# T",
                ocr_backend="paddleocr-vl",
                page_count=2,
                pages_markdown=values,
            )

    def test_factories_stamp_the_requested_version(self, side: str) -> None:
        """A worker answers in the version the request spoke (rolling upgrade rule)."""
        mod = _modules()[side]
        success = mod.make_success(
            "req-v-echo", "# T", ocr_backend="b", page_count=1, protocol_version="1.0"
        )
        decoded = mod.decode_response_line(mod.encode_line(success))
        assert isinstance(decoded, mod.ParseSuccess)
        assert decoded.protocol_version == "1.0"

        failure = mod.make_failure("req-v-echo", "code", "msg", protocol_version="1.0")
        decoded_failure = mod.decode_response_line(mod.encode_line(failure))
        assert isinstance(decoded_failure, mod.ParseFailure)
        assert decoded_failure.protocol_version == "1.0"

    def test_rejects_pages_markdown_on_a_1_0_response(self, side: str) -> None:
        """Version 1.0 never defined ``pages_markdown`` either."""
        mod = _modules()[side]
        line = _dumps(_success_payload("req-10-pm", pages_markdown=["# P2"]))
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(line)
        assert excinfo.value.code == "unexpected_field"

    @pytest.mark.parametrize(
        "label,values",
        [
            ("not_a_list", "page"),
            ("empty_list", []),
            ("int_entries", [1]),
            ("none_entries", [None]),
            ("mixed_entries", ["ok", 2]),
        ],
    )
    def test_rejects_invalid_pages_markdown_shapes(
        self, side: str, label: str, values: Any
    ) -> None:
        """``pages_markdown`` is a non-empty list of strings; entries may be empty."""
        mod = _modules()[side]
        payload = _success_payload("req-bad-pm", protocol_version="1.1")
        payload["pages_markdown"] = values
        with pytest.raises(mod.ProtocolError) as excinfo:
            mod.decode_response_line(_dumps(payload))
        assert excinfo.value.code == "invalid_field"

    def test_make_success_refuses_pages_markdown_on_1_0(self, side: str) -> None:
        """The builder cannot construct an envelope the decoder would reject."""
        mod = _modules()[side]
        with pytest.raises(ValueError):
            mod.make_success(
                "req-build-pm",
                "# T",
                ocr_backend="b",
                page_count=1,
                pages_markdown=["# T"],
                protocol_version="1.0",
            )

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
