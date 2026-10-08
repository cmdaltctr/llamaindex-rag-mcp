"""Check model revision pins and hashes without network access."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def test_download_uses_both_frozen_revisions_and_records_hashes(tmp_path, monkeypatch):
    module = importlib.import_module("download_julia")
    import huggingface_hub

    calls = []

    def fetch(repo_id, filename, *, revision, local_dir):
        calls.append((repo_id, filename, revision))
        target = Path(local_dir) / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(filename.encode())
        return str(target)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fetch)
    model = {
        "model": "SupersonicLabs/Julia-1-ONNX",
        "revision": "onnx-pin",
        "reference_model_revision": "reference-pin",
    }
    hashes = module.download_files(model, tmp_path)
    assert set(hashes) == {"model.onnx", "model.onnx.data", "tokenizer.json"}
    assert all(len(value) == 64 for value in hashes.values())
    assert all(
        rev == ("onnx-pin" if repo.endswith("ONNX") else "reference-pin") for repo, _, rev in calls
    )
    assert any(filename == "julia/data.py" for _, filename, _ in calls)
    assert any(filename == "parity-cases.json" for _, filename, _ in calls)
