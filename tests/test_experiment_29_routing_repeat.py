"""Fast tooling tests for experiment 29 (repeat-pdf-routing-study).

No PDFs are read, no model is loaded, no network is used. These tests
exercise the repaired contracts the change requires before approval:

- task 1.1: checkpoint identity is bound to the approved collection and
  the policy spec; added, removed, replaced documents and a changed
  policy refuse unsafe resume.
- task 1.2: exception text never reaches public outputs; a synthetic
  private path cannot leak into a serialised artefact.
- task 3.3: the pinned historical policy is extracted from its revision
  (never the working tree), and a tampered plan fails preflight.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_EXPERIMENT_DIR = _REPO_ROOT / "experiments" / "29-pdf-routing-repeat-2026-09-13"
_CLASSIFY_PATH = _EXPERIMENT_DIR / "classify.py"
_PLAN_PATH = _EXPERIMENT_DIR / "plan.json"

#: The pre-fix revision: parent of 9bf4810, where `mixed` was still in
#: the unconditional set inside ocr_routing.py.
_PINNED_REVISION = "afe151e"


def _load_classify() -> Any:
    spec = importlib.util.spec_from_file_location("exp29_classify", _CLASSIFY_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["exp29_classify"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def classify() -> Any:
    return _load_classify()


def _documents(tmp_path: Path) -> list[dict]:
    """Synthetic approved collection: two PDFs with real digests."""
    docs = []
    for index, name in enumerate(("dev_001", "hold_001"), start=1):
        path = tmp_path / f"private-{name}.pdf"
        path.write_bytes(f"%PDF-fake-{name}".encode())
        import hashlib

        docs.append(
            {
                "doc_id": name,
                "path": str(path),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "split": "development" if index == 1 else "held_out",
            }
        )
    return docs


class TestCollectionDiscovery:
    def test_digest_verification_accepts_approved_bytes(self, classify, tmp_path):
        docs = _documents(tmp_path)
        verified = classify._verify_digests(docs)
        assert [doc_id for doc_id, _ in verified] == ["dev_001", "hold_001"]

    def test_replaced_document_refuses(self, classify, tmp_path):
        docs = _documents(tmp_path)
        Path(docs[1]["path"]).write_bytes(b"%PDF-replaced")
        with pytest.raises(SystemExit, match="digest mismatch"):
            classify._verify_digests(docs)

    def test_public_collection_carries_no_paths(self, classify, tmp_path, monkeypatch):
        docs = _documents(tmp_path)
        monkeypatch.setattr(classify, "PUBLIC_COLLECTION", tmp_path / "collection.public.json")
        classify._write_public_collection(docs)
        public = json.loads((tmp_path / "collection.public.json").read_text())
        serialised = json.dumps(public)
        for doc in docs:
            assert doc["path"] not in serialised
            assert Path(doc["path"]).name not in serialised
        assert {d["doc_id"] for d in public["documents"]} == {"dev_001", "hold_001"}

    def test_public_collection_refuses_drift(self, classify, tmp_path, monkeypatch):
        docs = _documents(tmp_path)
        target = tmp_path / "collection.public.json"
        monkeypatch.setattr(classify, "PUBLIC_COLLECTION", target)
        classify._write_public_collection(docs)
        drifted = [dict(docs[0], sha256="0" * 64), docs[1]]
        with pytest.raises(SystemExit, match="refusing to overwrite"):
            classify._write_public_collection(drifted)


class TestPrivacy:
    def test_exception_path_stays_out_of_public_row(self, classify, tmp_path, monkeypatch):
        docs = _documents(tmp_path)
        monkeypatch.setattr(classify, "PRIVATE_ERRORS", tmp_path / ".errors.private.json")
        private_path = docs[0]["path"]
        exc = ValueError(f"cannot parse {private_path}")
        row = classify._record_error("dev_001", exc, docs)
        assert row == {"doc_id": "dev_001", "error_class": "ValueError"}
        assert private_path not in json.dumps(row)
        private_log = json.loads((tmp_path / ".errors.private.json").read_text())
        assert private_path in private_log["dev_001"]["error"]

    def test_checkpoint_write_refuses_private_leak(self, classify, tmp_path):
        docs = _documents(tmp_path)
        private = classify._private_strings(docs)
        payload = {"rows": [{"doc_id": "dev_001", "note": docs[0]["path"]}]}
        with pytest.raises(SystemExit, match="privacy check failed"):
            classify._assert_no_private_leak(payload, private)

    def test_clean_checkpoint_passes(self, classify, tmp_path):
        docs = _documents(tmp_path)
        private = classify._private_strings(docs)
        payload = {"rows": [{"doc_id": "dev_001", "pdf_type": "mixed"}]}
        classify._assert_no_private_leak(payload, private)


class TestPinnedBaseline:
    def test_pinned_revision_yields_historical_unconditional_set(self, classify):
        pinned = classify._unconditional_types_at(
            _PINNED_REVISION, "src/omrg/integrations/pdf/ocr_routing.py"
        )
        assert pinned == frozenset({"scanned", "image_based", "mixed"})

    def test_live_candidate_dropped_mixed(self, classify):
        live = classify._live_unconditional_types()
        assert live == frozenset({"scanned", "image_based"})
        assert "mixed" not in live

    def test_plan_baseline_matches_pinned_revision(self, classify):
        plan = json.loads(_PLAN_PATH.read_text())
        baseline = plan["policies"]["baseline"]
        pinned = classify._unconditional_types_at(
            baseline["pinned_revision"], baseline["source_path"]
        )
        assert pinned == frozenset(baseline["unconditional_types"])

    def test_tampered_plan_fails_baseline_check(self, classify, tmp_path):
        """A plan claiming the wrong baseline set must fail verification."""
        plan = json.loads(_PLAN_PATH.read_text())
        plan["policies"]["baseline"]["unconditional_types"] = ["scanned"]
        pinned = classify._unconditional_types_at(
            plan["policies"]["baseline"]["pinned_revision"],
            plan["policies"]["baseline"]["source_path"],
        )
        assert pinned != frozenset(plan["policies"]["baseline"]["unconditional_types"])


class TestRoutingReplay:
    """Synthetic evidence rows replayed through the production gate."""

    # The experiment-28 false route: mixed, 991 pages, 10 flagged,
    # healthy text layer.
    BOOK_EVIDENCE = {
        "pdf_type": "mixed",
        "pdf_confidence": 0.76,
        "pages_needing_ocr": 10,
        "page_count": 991,
    }
    # doc_045-shaped: scanned, every page flagged.
    SCANNED_EVIDENCE = {
        "pdf_type": "scanned",
        "pdf_confidence": 1.0,
        "pages_needing_ocr": 23,
        "page_count": 23,
    }
    # doc_067-shaped: confidently text_based, zero extractable text.
    SLOMAN_EVIDENCE = {
        "pdf_type": "text_based",
        "pdf_confidence": 1.0,
        "pages_needing_ocr": 17,
        "page_count": 17,
    }

    def test_book_routes_under_baseline_not_candidate(self, classify):
        baseline = frozenset({"scanned", "image_based", "mixed"})
        candidate = frozenset({"scanned", "image_based"})
        gate = classify._Gate(0.5, 0.5)
        assert classify._gate_decision(self.BOOK_EVIDENCE, gate, baseline) is True
        assert classify._gate_decision(self.BOOK_EVIDENCE, gate, candidate) is False

    def test_true_positives_route_under_both(self, classify):
        gate = classify._Gate(0.5, 0.5)
        for evidence in (self.SCANNED_EVIDENCE, self.SLOMAN_EVIDENCE):
            for types in (
                frozenset({"scanned", "image_based", "mixed"}),
                frozenset({"scanned", "image_based"}),
            ):
                assert classify._gate_decision(evidence, gate, types) is True

    def test_enable_only_misses_threshold_only_detection(self, classify):
        """Enable-only (0.0 sentinels) keeps the book fast but loses Sloman."""
        gate = classify._Gate(0.0, 0.0)
        candidate = frozenset({"scanned", "image_based"})
        assert classify._gate_decision(self.BOOK_EVIDENCE, gate, candidate) is False
        assert classify._gate_decision(self.SLOMAN_EVIDENCE, gate, candidate) is False
        assert classify._gate_decision(self.SCANNED_EVIDENCE, gate, candidate) is True


class TestResumeSafety:
    def test_identity_binds_plan_labels_collection_and_code(self, classify, tmp_path, monkeypatch):
        monkeypatch.setattr(classify, "PLAN_PATH", _PLAN_PATH)
        docs = _documents(tmp_path)
        public = tmp_path / "collection.public.json"
        labels = tmp_path / "labels.json"
        labels.write_text('{"frozen": true, "labels": {}}')
        public.write_text(
            json.dumps(
                {
                    "documents": [
                        {"doc_id": d["doc_id"], "sha256": d["sha256"], "split": d["split"]}
                        for d in docs
                    ]
                }
            )
        )
        monkeypatch.setattr(classify, "PUBLIC_COLLECTION", public)
        monkeypatch.setattr(classify, "LABELS_PATH", labels)
        manifest = {"policies": {"candidate": {"unconditional_types": ["scanned"]}}}
        first = classify._run_identity(manifest)
        second = classify._run_identity(manifest)
        assert first == second
        changed = classify._run_identity(
            {"policies": {"candidate": {"unconditional_types": ["scanned", "mixed"]}}}
        )
        assert changed["runtime_manifest"] != first["runtime_manifest"]

    def test_resume_refused_on_identity_drift(self, classify):
        from experiments._lib.checkpoint_validity import evaluate_resume

        state = {"run_identity": {"plan": "a"}, "done": ["dev_001"], "rows": []}
        decision = evaluate_resume({"classifications": state}, {"plan": "b"})
        assert decision["action"] == "refuse"
        assert "plan" in decision["reasons"][0]

    def test_historical_checkpoint_without_identity_not_resumable(self, classify):
        from experiments._lib.checkpoint_validity import evaluate_resume

        state = {"done": ["dev_001"], "rows": []}
        decision = evaluate_resume({"classifications": state}, {"plan": "x"})
        assert decision["action"] == "refuse"

    def test_clean_checkpoint_resumes(self, classify):
        from experiments._lib.checkpoint_validity import evaluate_resume

        identity = {"plan": "a", "code": {"x": "h"}}
        state = {"run_identity": identity, "done": ["dev_001"], "rows": []}
        decision = evaluate_resume({"classifications": state}, identity)
        assert decision["action"] == "resume"


class TestRoutingCodeClean:
    def test_dirty_routing_source_detected(self, classify, monkeypatch):
        monkeypatch.setattr(
            classify, "_git", lambda *args: " M src/omrg/integrations/pdf/ocr_routing.py\n"
        )
        assert classify._routing_code_clean() is False

    def test_clean_routing_source_passes(self, classify, monkeypatch):
        monkeypatch.setattr(classify, "_git", lambda *args: "")
        assert classify._routing_code_clean() is True
