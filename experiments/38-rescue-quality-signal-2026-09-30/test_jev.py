"""Tests for hosted Jev arm C: request shape, retries, key safety and pairing."""

from __future__ import annotations

import io
import json
import sys
import urllib.error
from pathlib import Path

import pytest

EXP = Path(__file__).resolve().parent
sys.path.insert(0, str(EXP))

import jev_hosted as jev  # noqa: E402
import summarise_jev  # noqa: E402

QUESTION = "Is this text readable?"
KEY = "sk-secret-test-key"


def reply(value: float = 0.9, model: str = "jev-1.13.0") -> dict:
    return {
        "model": model,
        "answers": {"readable": {"type": "noul", "noul": value}},
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }


def test_request_sends_question_and_only_the_page_head():
    body = jev.build_body(QUESTION, "x" * 5000)
    assert len(body["state"]) == jev.HEAD_CHARACTERS == 2000
    assert body["model"] == "jev-latest"
    assert body["questions"]["readable"] == {"type": "noul", "instructions": QUESTION}


def test_post_retries_rate_limit_then_succeeds(monkeypatch):
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request.get_header("Authorization"))
        if len(calls) < 3:
            raise urllib.error.HTTPError(request.full_url, 429, "slow", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps(reply()).encode())

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    waits = []
    assert jev.post({}, KEY, sleep=waits.append)["model"] == "jev-1.13.0"
    assert len(calls) == 3
    assert waits == [1, 2]


def test_failure_message_never_contains_key_or_response_body(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.HTTPError(
            request.full_url, 401, "no", {}, io.BytesIO(f"bad {KEY} page text".encode())
        )

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(RuntimeError) as error:
        jev.post({}, KEY, sleep=lambda _: None)
    assert "401" in str(error.value)
    assert KEY not in str(error.value)
    assert "page text" not in str(error.value)


def test_probability_keeps_score_model_and_usage_but_not_text():
    client = jev.JevClient(QUESTION, key=KEY, send=lambda body, key: reply(0.25))
    result = client.probability("secret page text")
    assert result["score"] == 0.25
    assert result["model"] == "jev-1.13.0"
    assert {"input_tokens", "output_tokens", "wall_seconds"} <= result.keys()
    assert "secret page text" not in json.dumps(result)
    assert KEY not in json.dumps(result)


def test_out_of_bounds_score_is_rejected():
    client = jev.JevClient(QUESTION, key=KEY, send=lambda body, key: reply(1.2))
    with pytest.raises(ValueError, match="bounds"):
        client.probability("text")


def test_missing_key_is_refused(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        jev.JevClient(QUESTION)


def test_parallel_scoring_keeps_page_order():
    client = jev.JevClient(
        QUESTION, key=KEY, send=lambda body, key: reply(int(body["state"]) / 100)
    )
    scores = [r["score"] for r in jev.score_many(client, [str(n) for n in range(20)])]
    assert scores == [n / 100 for n in range(20)]


def test_alias_moving_to_a_new_model_stops_the_run():
    payload = {"rows": [{"model": "jev-1.13.0"}]}
    jev.check_model(payload, {"jev-1.13.0"})
    with pytest.raises(ValueError, match="changed model"):
        jev.check_model(payload, {"jev-1.14.0"})


def test_pairing_counts_junk_only_c_catches_as_second_signal():
    def rows(scores):
        return [
            {"doc_id": "d", "page": i, "tier": "liteparse", "class": "junk", "score": s}
            for i, s in enumerate(scores)
        ]

    a = rows([0.9, 0.9, 0.1, 0.9])
    c = rows([0.1, 0.1, 0.1, 0.9])
    result = summarise_jev.paired(
        a, c, {"equal_cost_threshold": 0.5}, {"equal_cost_threshold": 0.5}
    )
    assert (result["a_only"], result["b_only"]) == (0, 2)


def test_criteria_are_sent_only_when_given():
    assert "criteria" not in jev.build_body(QUESTION, "t")["questions"]["readable"]
    body = jev.build_body(QUESTION, "t", criteria={"true": "ok", "false": "bad"})
    assert body["questions"]["readable"]["criteria"] == {"true": "ok", "false": "bad"}


def test_wordings_map_descriptions_to_julia_options_and_jev_criteria():
    import score_wordings as sw

    w2 = {"question": "Q", "false": "garbled", "true": "usable"}
    assert sw.julia_request(w2)["options"] == ["garbled", "usable"]
    assert sw.jev_criteria(w2) == {"true": "usable", "false": "garbled"}
    assert sw.jev_criteria({"question": "Q", "false": "no", "true": "yes"}) is None


def test_openjev_requests_go_only_to_the_local_server(monkeypatch):
    import score_wordings as sw

    seen = []

    def fake_urlopen(request, timeout):
        seen.append(request.full_url)
        return io.BytesIO(json.dumps(reply(0.7, model="openjev")).encode())

    monkeypatch.setattr(jev.urllib.request, "urlopen", fake_urlopen)
    score = sw.scorer("openjev", {"question": "Q", "false": "no", "true": "yes"}, {})
    assert [r["score"] for r in score(["page one", "page two"])] == [0.7, 0.7]
    assert seen and all(url == "http://127.0.0.1:3000/v1/systemone" for url in seen)


def test_julia_choice_wording_sends_a_choice_request_with_ordered_options():
    import score_wordings as sw

    c1 = {"type": "choice", "question": "Q", "false": "garbled", "true": "readable"}
    request = sw.julia_request(c1)
    assert request["type"] == "choice"
    assert request["options"] == ["garbled", "readable"]
    assert sw.julia_request({"question": "Q", "false": "no", "true": "yes"})["type"] == "noul"
