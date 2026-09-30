"""Tests for the dots-mocr engine that need no model (tasks 3.1 to 3.4).

The layout converter, the patches, the hash check and the engine's
parse loop are pure Python. They run here, in the main OMRG
environment, on the committed Experiment 34 fixtures and on stubs. No
PyTorch, no weights, no network.

The real-engine checks (the KaTeX smoke on ``eq01`` p11 and the
``io06`` p28 smoke with network blocked) need the provisioned engine and
the operator's approval; they are not part of this suite.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from tests.fixtures.ocr_worker.isolation import isolated_worker_modules

REPO_ROOT = Path(__file__).resolve().parent.parent
DOTS_DIR = REPO_ROOT / "ocr-workers" / "engines" / "dots-mocr"
DOTS_SRC = DOTS_DIR / "src"
CORE_SRC = REPO_ROOT / "ocr-workers" / "core" / "src"
FIXTURES = REPO_ROOT / "experiments" / "34-worker-sample-review-2026-09-19" / "output" / "dots_mocr"


@pytest.fixture
def dots(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """Import the dots-mocr package modules from source."""
    monkeypatch.syspath_prepend(str(CORE_SRC))
    monkeypatch.syspath_prepend(str(DOTS_SRC))
    with isolated_worker_modules():
        yield importlib.import_module("omrg_ocr_dots_mocr")


def _layout(dots: Any) -> Any:
    return importlib.import_module("omrg_ocr_dots_mocr.layout")


def _raw(doc: str, page: int) -> str:
    return (FIXTURES / doc / f"p{page:03d}.raw.txt").read_text(encoding="utf-8")


# ── layout.py on the committed fixtures (task 3.3) ─────────────────────────


def test_eq01_p11_has_four_display_blocks_and_no_doubling(dots: Any) -> None:
    """``eq01`` p11: exactly 4 display blocks, each with one ``$$`` pair."""
    layout = _layout(dots)
    markdown, reason = layout.page_markdown(_raw("eq01", 11), hit_token_cap=False)
    assert reason is None
    blocks = re.findall(r"^\$\$\n(.*?)\n\$\$$", markdown, flags=re.S | re.M)
    assert len(blocks) == 4
    assert markdown.count("$$") == 8, "one opening and one closing $$ per block"
    assert "$$$$" not in markdown
    for block in blocks:
        assert not block.strip().startswith("$$")
        assert not block.strip().endswith("$$")


def test_bd03_p2_drops_page_header_and_footer(dots: Any) -> None:
    """``bd03`` p2: no "PLOS One" header, no DOI footer line."""
    layout = _layout(dots)
    markdown, reason = layout.page_markdown(_raw("bd03", 2), hit_token_cap=False)
    assert reason is None
    assert markdown.strip()
    assert "PLOS One" not in markdown
    assert "doi.org" not in markdown.lower()


def test_every_fixture_converts_without_furniture(dots: Any) -> None:
    """Every committed raw page parses and loses its header and footer text."""
    layout = _layout(dots)
    raws = sorted(FIXTURES.glob("*/p*.raw.txt"))
    assert len(raws) >= 40
    for raw_path in raws:
        raw = raw_path.read_text(encoding="utf-8")
        cells = layout.parse_layout(raw)
        assert cells is not None, raw_path
        markdown, reason = layout.page_markdown(raw, hit_token_cap=False)
        assert reason is None, raw_path
        for cell in cells:
            text = str(cell.get("text") or "").strip()
            if cell.get("category") in ("Page-header", "Page-footer") and len(text) > 12:
                kept = [c for c in cells if c.get("category") not in layout.DROPPED_CATEGORIES]
                if any(text in str(c.get("text") or "") for c in kept):
                    continue  # the same words also sit in body text
                assert text not in markdown, (raw_path, text)


@pytest.mark.parametrize(
    "formula",
    ["x^2", "$$x^2$$", "$$\nx^2\n$$", "$$ $$x^2$$ $$", "\\[x^2\\]"],
)
def test_formula_gets_exactly_one_pair(dots: Any, formula: str) -> None:
    """Spec: a formula already wrapped in ``$$`` keeps exactly one pair."""
    layout = _layout(dots)
    markdown = layout.cells_to_markdown([{"category": "Formula", "text": formula}])
    assert markdown == "$$\nx^2\n$$\n"


def test_headings_tables_and_pictures(dots: Any) -> None:
    """Title and section headers become headings; tables keep HTML; pictures drop."""
    layout = _layout(dots)
    markdown = layout.cells_to_markdown(
        [
            {"category": "Title", "text": "# The Title"},
            {"category": "Section-header", "text": "## 1 Intro"},
            {"category": "Table", "text": "<table><tr><td>1</td></tr></table>"},
            {"category": "Picture", "text": "should vanish"},
            {"category": "Text", "text": ""},
            {"category": "Page-footer", "text": "page 3"},
        ]
    )
    assert markdown == "# The Title\n\n## 1 Intro\n\n<table><tr><td>1</td></tr></table>\n"


def test_token_cap_page_is_empty(dots: Any) -> None:
    """Spec: a page that reached the token limit returns empty Markdown."""
    layout = _layout(dots)
    assert layout.page_markdown(_raw("eq01", 11), hit_token_cap=True) == ("", "token_cap")


@pytest.mark.parametrize("raw", ['[{"category": "Text", "text": "cut', "not json", "42"])
def test_unparsable_page_is_empty(dots: Any, raw: str) -> None:
    """Truncated or non-list JSON returns empty Markdown, never raw output."""
    layout = _layout(dots)
    assert layout.page_markdown(raw, hit_token_cap=False) == ("", "unparsable_layout")


def test_wrapped_layout_object_and_fence_are_accepted(dots: Any) -> None:
    """A fenced JSON object that wraps its cells is unwrapped."""
    layout = _layout(dots)
    raw = '```json\n{"layout": [{"category": "Text", "text": "Hello"}]}\n```'
    assert layout.page_markdown(raw, hit_token_cap=False) == ("Hello\n", None)


# ── patches.py and fetch (task 3.2) ────────────────────────────────────────

_VISION_SOURCE = (
    "import torch\nfrom flash_attn import flash_attn_varlen_func\n\nclass VisionTower:\n    pass\n"
)


def _model_folder(tmp_path: Path) -> Path:
    """A copy of the two files the patches touch, as upstream ships them."""
    folder = tmp_path / "DotsMOCR"
    folder.mkdir()
    (folder / "modeling_dots_vision.py").write_text(_VISION_SOURCE, encoding="utf-8")
    (folder / "modeling_dots_ocr.py").write_text("# model\n", encoding="utf-8")
    (folder / "config.json").write_text(
        json.dumps({"vision_config": {"attn_implementation": "flash_attention_2"}}),
        encoding="utf-8",
    )
    return folder


def _snapshot(folder: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(folder.iterdir())}


def test_patches_apply_once_and_are_idempotent(dots: Any, tmp_path: Path) -> None:
    """The second patch run on a copied modeling_dots_vision.py changes nothing."""
    patches = importlib.import_module("omrg_ocr_dots_mocr.patches")
    folder = _model_folder(tmp_path)
    assert patches.apply_patches(folder) == [
        "flash_attn import optional",
        "vision attn_implementation=sdpa",
    ]
    patched = (folder / "modeling_dots_vision.py").read_text(encoding="utf-8")
    assert "try:\n    from flash_attn import flash_attn_varlen_func\n" in patched
    assert "flash_attn_varlen_func = None" in patched
    after_first = _snapshot(folder)
    assert patches.apply_patches(folder) == []
    assert _snapshot(folder) == after_first


def test_fetch_twice_leaves_identical_files_and_hashes(
    dots: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Running the fetch steps twice leaves the same files and the same hashes."""
    fetch = importlib.import_module("omrg_ocr_dots_mocr.fetch")
    folder = _model_folder(tmp_path)
    monkeypatch.setattr(fetch, "model_dir", lambda: folder)
    first = fetch.fetch(download=False)
    files_after_first = _snapshot(folder)
    second = fetch.fetch(download=False)
    assert first["patches_changed"] and second["patches_changed"] == []
    assert _snapshot(folder) == files_after_first


def test_fetch_downloads_the_pinned_revision(
    dots: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The download names the pinned repository revision and the engine cache."""
    fetch = importlib.import_module("omrg_ocr_dots_mocr.fetch")
    folder = _model_folder(tmp_path)
    monkeypatch.setattr(fetch, "model_dir", lambda: folder)
    calls: list[dict[str, Any]] = []
    fake_hub = type(sys)("huggingface_hub")
    fake_hub.snapshot_download = lambda repo, **kwargs: calls.append({"repo": repo, **kwargs})
    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_hub)
    assert fetch.main() == 0
    assert calls == [
        {
            "repo": "rednote-hilab/dots.mocr",
            "revision": "e539fbb52280393adc081b289ec597430a0f9031",
            "local_dir": folder,
        }
    ]


def test_hash_check_refuses_a_changed_code_file(dots: Any, tmp_path: Path) -> None:
    """Any change to a model code file after provisioning is refused."""
    patches = importlib.import_module("omrg_ocr_dots_mocr.patches")
    folder = _model_folder(tmp_path)
    with pytest.raises(patches.CodeHashMismatchError, match="no code-hash record"):
        patches.verify_hashes(folder)
    patches.apply_patches(folder)
    patches.record_hashes(folder)
    patches.verify_hashes(folder)
    (folder / "modeling_dots_ocr.py").write_text("# tampered\n", encoding="utf-8")
    with pytest.raises(patches.CodeHashMismatchError, match="modeling_dots_ocr.py"):
        patches.verify_hashes(folder)
    (folder / "modeling_dots_ocr.py").write_text("# model\n", encoding="utf-8")
    (folder / "extra_module.py").write_text("print('new')\n", encoding="utf-8")
    with pytest.raises(patches.CodeHashMismatchError, match="extra_module.py"):
        patches.verify_hashes(folder)


def test_hash_record_from_another_patch_set_is_refused(dots: Any, tmp_path: Path) -> None:
    """A record written by another patch set forces re-provisioning."""
    patches = importlib.import_module("omrg_ocr_dots_mocr.patches")
    folder = _model_folder(tmp_path)
    patches.record_hashes(folder)
    record = json.loads((folder / patches.HASH_FILE).read_text(encoding="utf-8"))
    record["patch_set"] = "older"
    (folder / patches.HASH_FILE).write_text(json.dumps(record), encoding="utf-8")
    with pytest.raises(patches.CodeHashMismatchError, match="patch set"):
        patches.verify_hashes(folder)


def test_patches_on_real_model_copy_when_present(dots: Any, tmp_path: Path) -> None:
    """On a real model copy (if named), a second patch run changes nothing.

    Set ``OMRG_DOTS_MOCR_MODEL_DIR`` to a downloaded dots.mocr folder (for
    example the Experiment 34 copy) to run it; it skips otherwise, so the
    base-suite counts do not depend on the machine. Only the two small
    code files are copied, never the weights.
    """
    source = Path(os.environ.get("OMRG_DOTS_MOCR_MODEL_DIR", "/nonexistent"))
    if not (source / "modeling_dots_vision.py").is_file():
        pytest.skip("set OMRG_DOTS_MOCR_MODEL_DIR to a dots.mocr model folder")
    patches = importlib.import_module("omrg_ocr_dots_mocr.patches")
    folder = tmp_path / "DotsMOCR"
    folder.mkdir()
    for name in ("modeling_dots_vision.py", "config.json"):
        shutil.copy2(source / name, folder / name)
    patches.apply_patches(folder)
    before = _snapshot(folder)
    assert patches.apply_patches(folder) == []
    assert _snapshot(folder) == before
    source_text = (folder / "modeling_dots_vision.py").read_text(encoding="utf-8")
    assert not re.search(r"^from flash_attn import", source_text, flags=re.M)


# ── engine.py with stubbed model seams (task 3.4, code only) ───────────────


def test_engine_parse_converts_each_page_and_empties_bad_ones(
    dots: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``parse`` renders, generates and converts each page; bad pages give ""."""
    engine_mod = importlib.import_module("omrg_ocr_dots_mocr.engine")
    engine = engine_mod.DotsMocrEngine()
    outputs = {
        1: (_raw("eq01", 11), 1937),
        2: ("not json", 12),
        3: (_raw("bd03", 2), engine_mod.MAX_NEW_TOKENS),
    }
    rendered: list[int] = []
    monkeypatch.setattr(engine, "render_page", lambda pdf, page: rendered.append(page) or page)
    monkeypatch.setattr(engine, "generate", lambda image: outputs[image])
    pages = engine.parse(tmp_path / "x.pdf", [1, 2, 3])
    assert rendered == [1, 2, 3]
    assert pages[0].count("$$") == 8
    assert pages[1] == ""
    assert pages[2] == "", "a page at the token cap is not usable text"


def test_engine_identity_fields(dots: Any) -> None:
    """The contract fields name the pinned model and the patch set."""
    engine_mod = importlib.import_module("omrg_ocr_dots_mocr.engine")
    engine = engine_mod.ENGINE
    assert engine.name == "dots-mocr"
    assert engine.backend_id == "dots_mocr"
    assert engine.model == ("rednote-hilab/dots.mocr", "e539fbb52280393adc081b289ec597430a0f9031")
    assert "omrg-mps-1" in engine.pipeline[1]
    assert "torch" in engine.declared_packages
    assert engine_mod.RENDER_DPI == 200 and engine_mod.MIN_LONG_SIDE_PX == 1600
    assert engine_mod.MAX_NEW_TOKENS == 8192


def test_offline_env_is_forced(dots: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Offline variables and HF_HOME are assigned, overriding inherited values."""
    engine_mod = importlib.import_module("omrg_ocr_dots_mocr.engine")
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    monkeypatch.setenv("HF_HOME", "/elsewhere/hf")
    monkeypatch.setenv("OMRG_OCR_MODEL_CACHE", str(tmp_path))
    engine_mod.apply_offline_env()
    import os

    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
    assert os.environ["HF_HOME"] == str(tmp_path / "dots-mocr")


def test_engine_refuses_missing_or_changed_model(
    dots: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Loading fails with a structured error before any PyTorch import."""
    engine_mod = importlib.import_module("omrg_ocr_dots_mocr.engine")
    from omrg_ocr_worker_core.engine import WorkerParseError

    monkeypatch.setenv("OMRG_OCR_MODEL_CACHE", str(tmp_path))
    engine = engine_mod.DotsMocrEngine()
    with pytest.raises(WorkerParseError) as missing:
        engine.generate(object())
    assert missing.value.code == "model_missing"
    folder = tmp_path / "dots-mocr" / "DotsMOCR"
    folder.mkdir(parents=True)
    (folder / "modeling_dots_ocr.py").write_text("# code\n", encoding="utf-8")
    with pytest.raises(WorkerParseError) as changed:
        engine.generate(object())
    assert changed.value.code == "model_code_changed"


def test_engine_reports_missing_runtime(
    dots: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With a verified model but no PyTorch, the error is runtime_unavailable."""
    engine_mod = importlib.import_module("omrg_ocr_dots_mocr.engine")
    patches = importlib.import_module("omrg_ocr_dots_mocr.patches")
    from omrg_ocr_worker_core.engine import WorkerParseError

    monkeypatch.setenv("OMRG_OCR_MODEL_CACHE", str(tmp_path))
    folder = tmp_path / "dots-mocr" / "DotsMOCR"
    folder.mkdir(parents=True)
    (folder / "modeling_dots_ocr.py").write_text("# code\n", encoding="utf-8")
    patches.record_hashes(folder)
    monkeypatch.setitem(sys.modules, "torch", None)
    with pytest.raises(WorkerParseError) as excinfo:
        engine_mod.DotsMocrEngine().generate(object())
    assert excinfo.value.code == "runtime_unavailable"


def test_manifest_declares_gate_fetch_and_entry_point() -> None:
    """The dots-mocr manifest carries the licence gate, fetch script and entry point."""
    import tomllib

    manifest = tomllib.loads((DOTS_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    assert manifest["tool"]["omrg-ocr"] == {
        "licence-file": "LICENCE-NOTES.md",
        "requires-acceptance": True,
    }
    assert manifest["project"]["scripts"]["omrg-ocr-fetch"] == "omrg_ocr_dots_mocr.fetch:main"
    assert manifest["project"]["entry-points"]["omrg.ocr_engine"] == {
        "dots-mocr": "omrg_ocr_dots_mocr.engine:ENGINE"
    }
    assert "transformers==4.57.6" in manifest["project"]["dependencies"]
    notes = (DOTS_DIR / "LICENCE-NOTES.md").read_text(encoding="utf-8")
    for clause in ("3.3(c)", "5.2", "Clause 8", "Clause 9"):
        assert clause in notes
