"""Julia 1 inference through ONNX Runtime and a numpy port of its encoder."""

from __future__ import annotations

import math
import time
from collections import Counter
from importlib.metadata import version
from pathlib import Path

import numpy as np
import onnxruntime as ort
from experiment_io import OUTPUT, approved_plan, atomic_json, read_json, sha256
from tokenizers import Tokenizer

QTYPES = {"choice": 0, "score": 1, "noul": 2}


def encode_request(
    tokenizer: Tokenizer, row: dict, max_length: int = 8192, head_length: int = 512
) -> dict[str, np.ndarray]:
    """Port julia.data.sequence and Collator with strict, lossless encoding."""
    import json

    if head_length + 4 >= max_length:
        raise ValueError("max_length must leave room beyond the question head")
    if not isinstance(row.get("state"), (str, dict, list)) or not isinstance(
        row.get("question"), str
    ):
        raise ValueError("state must be text/JSON and question must be text")
    options = row.get("options")
    qtype = row.get("type", "choice")
    if (
        not isinstance(options, list)
        or not 2 <= len(options) <= 20
        or any(not isinstance(option, str) or not option for option in options)
        or qtype not in QTYPES
        or (qtype == "noul" and len(options) != 2)
    ):
        raise ValueError("invalid option list or request type")
    mask_id, cls_id, sep_id, pad_id = [
        tokenizer.token_to_id(value) for value in ("<mask>", "<bos>", "<eos>", "<pad>")
    ]
    if any(value is None for value in (mask_id, cls_id, sep_id, pad_id)):
        raise ValueError("Tokenizer must define MASK, CLS, SEP and PAD IDs")
    state = (
        row["state"]
        if isinstance(row["state"], str)
        else json.dumps(row["state"], ensure_ascii=False)
    )
    if any("<mask>" in text for text in (state, row["question"], *options)):
        raise ValueError("Reserved model marker in request")
    head = tokenizer.encode(f"{qtype} question: {row['question']}", add_special_tokens=False).ids
    option_ids = [
        tokenizer.encode(" " + option, add_special_tokens=False).ids for option in options
    ]
    if any(len(ids) > 48 for ids in option_ids):
        raise ValueError("Option exceeds 48-token model contract")
    option_tokens = [[mask_id] + ids[:48] for ids in option_ids]
    budget = head_length - sum(map(len, option_tokens))
    if budget < 16:
        per_option = max(4, (head_length - 16) // len(option_tokens))
        option_tokens = [ids[:per_option] for ids in option_tokens]
        budget = head_length - sum(map(len, option_tokens))
    if len(head) > budget or any(
        len(a) != len(b) + 1 for a, b in zip(option_tokens, option_ids, strict=True)
    ):
        raise ValueError("Question/options exceed lossless head budget")
    ids = [cls_id] + head[: max(8, budget)] + [sep_id]
    positions = []
    for option in option_tokens:
        positions.append(len(ids))
        ids.extend(option)
    ids.append(sep_id)
    state_ids = tokenizer.encode(state, add_special_tokens=False).ids
    room = max_length - len(ids) - 1
    if room < 1 or len(state_ids) > room:
        raise ValueError("Game state exceeds lossless context budget")
    ids.extend(state_ids)
    ids.append(sep_id)
    length = min(max_length, ((len(ids) + 7) // 8) * 8)
    input_ids = np.full((1, length), pad_id, dtype=np.int64)
    attention = np.zeros((1, length), dtype=np.int64)
    input_ids[0, : len(ids)] = ids
    attention[0, : len(ids)] = 1
    return {
        "input_ids": input_ids,
        "attention_mask": attention,
        "marker_pos": np.array([positions], dtype=np.int64),
        "marker_mask": np.ones((1, len(positions)), dtype=np.bool_),
        "qtype": np.array([QTYPES[qtype]], dtype=np.int64),
    }


def yes_probability(logits: np.ndarray) -> float:
    """Return raw P(yes) for ordered [no, yes] logits without display rounding."""
    if logits.shape != (2,) or not np.all(np.isfinite(logits)):
        raise ValueError("expected two finite noul logits")
    probabilities = np.exp(logits.astype(np.float64) - np.max(logits))
    return float(probabilities[1] / probabilities.sum())


def parity_passes(matches: int, total: int, error: float) -> bool:
    """Apply the frozen P0 bounds without weakening either condition."""
    return bool(total == 100 and matches >= 99 and math.isfinite(error) and error <= 0.01)


class JuliaRuntime:
    """Local CPU-only Julia runtime with hash-bound parity before page scoring."""

    def __init__(self, plan: dict, *, require_parity: bool) -> None:
        """Load verified pinned files and the published inference policy."""
        self.definition = plan["candidates"]["B"]
        self.directory = OUTPUT / ".models"
        self.hashes = {
            name: sha256(self.directory / name) for name in self.definition["file_sha256"]
        }
        if self.hashes != self.definition["file_sha256"]:
            raise ValueError("Julia model file hashes differ from the pinned plan")
        self.policy = read_json(self.directory / "reference" / "inference-policy.json")
        if any(
            self.definition["request"][key] != self.policy[key]
            for key in ("max_length", "head_length", "strict_encoding")
        ):
            raise ValueError("Julia request differs from the published inference policy")
        self.code_hash = sha256(Path(__file__))
        self.packages = {name: version(name) for name in ("onnxruntime", "tokenizers", "numpy")}
        if require_parity:
            parity = read_json(OUTPUT / "parity.json")
            if (
                not parity["passed"]
                or parity["encoder_sha256"] != self.code_hash
                or (
                    parity["model_hashes"] != self.hashes
                    or parity["package_versions"] != self.packages
                )
            ):
                raise ValueError("P0 did not pass for this exact encoder, model and runtime")
        config = read_json(self.directory / "tokenizer_config.json")
        if [config[key] for key in ("mask_token", "cls_token", "sep_token", "pad_token")] != [
            "<mask>",
            "<bos>",
            "<eos>",
            "<pad>",
        ]:
            raise ValueError("pinned tokenizer special tokens differ from the encoder")
        self.tokenizer = Tokenizer.from_file(str(self.directory / "tokenizer.json"))
        self.tokenizer.no_padding()
        self.tokenizer.no_truncation()
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        self.session = ort.InferenceSession(
            str(self.directory / "model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self.session.disable_fallback()

    def logits(self, request: dict) -> np.ndarray:
        """Run one strict request through the pinned ONNX graph."""
        feed = encode_request(
            self.tokenizer, request, self.policy["max_length"], self.policy["head_length"]
        )
        result = self.session.run(None, feed)[0][0, : len(request["options"])]
        if not np.all(np.isfinite(result)):
            raise ValueError("Julia returned non-finite logits")
        return result

    def probability(self, text: str) -> float:
        """Score page text with the fixed question and false/true option order."""
        definition = self.definition["request"]
        request = {key: definition[key] for key in ("type", "options", "question")}
        request["state"] = text
        return yes_probability(self.logits(request))


def run_parity() -> None:
    """Evaluate all published requests and stop if P0 fails."""
    runtime = JuliaRuntime(approved_plan(), require_parity=False)
    cases = read_json(runtime.directory / "parity-cases.json")
    matches = 0
    max_error = 0.0
    rows = []
    start = time.perf_counter()
    for index, case in enumerate(cases):
        actual = runtime.logits(case["request"])
        reference = np.array(case["pytorch_logits"], dtype=np.float32)
        error = float(np.max(np.abs(actual - reference)))
        match = int(np.argmax(actual)) == int(np.argmax(reference))
        matches += int(match)
        max_error = max(max_error, error)
        rows.append({"case": index, "argmax_match": match, "max_abs_logit_error": error})
        print(f"[P0] {index + 1}/{len(cases)} argmax_match={match} error={error:.7f}", flush=True)
    payload = {
        "passed": parity_passes(matches, len(cases), max_error),
        "cases": len(cases),
        "argmax_matches": matches,
        "max_abs_logit_error": max_error,
        "type_mix": dict(Counter(c["request"].get("type", "choice") for c in cases)),
        "policy": {k: runtime.policy[k] for k in ("max_length", "head_length", "strict_encoding")},
        "publisher_parity_policy": {"max_length": 1024, "head_length": 256},
        "encoder_sha256": runtime.code_hash,
        "model_hashes": runtime.hashes,
        "package_versions": runtime.packages,
        "cases_sha256": sha256(runtime.directory / "parity-cases.json"),
        "wall_seconds": time.perf_counter() - start,
        "rows": rows,
    }
    atomic_json(OUTPUT / "parity.json", payload)
    if not payload["passed"]:
        raise RuntimeError("P0 failed; candidate B must not be scored; ask the operator")
    print(f"[P0] PASS: {matches}/{len(cases)}, maximum logit error {max_error:.7f}", flush=True)


if __name__ == "__main__":
    run_parity()
