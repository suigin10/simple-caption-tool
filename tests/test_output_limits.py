import json

from PIL import Image
import pytest

from captioner.runtime import AnalysisError, LocalRuntime, OUTPUT_TOKEN_LIMITS

ANALYSIS = {"description": "A person standing.", "character_description": "A person standing.",
            "style_description": "A person standing.", "content_tags": ["standing"],
            "appearance_tags": [], "style_tags": []}
VALID = json.dumps(ANALYSIS)


def setup_runtime(tmp_path, monkeypatch, replies):
    image = tmp_path / "test.png"
    Image.new("RGB", (40, 30), "white").save(image)
    runtime = LocalRuntime(tmp_path / "cache")
    calls = []
    progress = []
    runtime.progress = progress.append
    def request(route, data, **kwargs):
        calls.append(data)
        text, reason = replies[len(calls) - 1]
        return {"choices": [{"message": {"content": text}, "finish_reason": reason}],
                "usage": {"completion_tokens": 100}}
    monkeypatch.setattr(runtime, "request", request)
    return runtime, image, calls, progress


def test_truncated_response_retries_and_preserves_both_attempts(tmp_path, monkeypatch):
    runtime, image, calls, progress = setup_runtime(tmp_path, monkeypatch, [('{"description":', "length"), (VALID, "stop")])
    analysis, raw = runtime.analyze(image, 1024)
    assert analysis == ANALYSIS
    assert raw == VALID
    assert [c["max_tokens"] for c in calls] == list(OUTPUT_TOKEN_LIMITS)
    assert [a["valid"] for a in runtime.last_attempts] == [False, True]
    assert runtime.last_attempts[0]["raw"] == '{"description":'
    assert "60 English words" in calls[1]["messages"][1]["content"][0]["text"]
    assert len(progress) == 1


def test_valid_json_at_token_boundary_is_usable(tmp_path, monkeypatch):
    runtime, image, calls, _ = setup_runtime(tmp_path, monkeypatch, [(VALID, "length")])
    assert runtime.analyze(image, 1024)[0] == ANALYSIS
    assert len(calls) == 1
    assert runtime.last_attempts[0]["finish_reason"] == "length"


def test_repeated_truncation_stops_after_one_retry(tmp_path, monkeypatch):
    runtime, image, calls, _ = setup_runtime(tmp_path, monkeypatch, [('first partial', "length"), ('second partial', "length")])
    with pytest.raises(AnalysisError, match="自動再試行") as error:
        runtime.analyze(image, 1024)
    assert error.value.raw == 'second partial'
    assert len(calls) == 2
    assert [a["raw"] for a in runtime.last_attempts] == ['first partial', 'second partial']


def test_invalid_complete_json_retries_too(tmp_path, monkeypatch):
    runtime, image, calls, _ = setup_runtime(tmp_path, monkeypatch, [('{}', "stop"), (VALID, "stop")])
    assert runtime.analyze(image, 1024)[0] == ANALYSIS
    assert len(calls) == 2


def test_valid_response_does_not_retry(tmp_path, monkeypatch):
    runtime, image, calls, progress = setup_runtime(tmp_path, monkeypatch, [(VALID, "stop")])
    assert runtime.analyze(image, 1024)[1] == VALID
    assert len(calls) == 1
    assert not progress


def test_cancel_prevents_additional_inference(tmp_path, monkeypatch):
    runtime, image, calls, _ = setup_runtime(tmp_path, monkeypatch, [('partial', "length")])
    runtime.cancel.set()
    with pytest.raises(AnalysisError, match="中止"):
        runtime.analyze(image, 1024)
    assert len(calls) == 1
    assert runtime.last_attempts[0]["raw"] == 'partial'
