import json
import threading

from PIL import Image
import pytest

from captioner.core import Settings, parse_analysis, render
from captioner.hair import crop_head, parse_hair_detail, parse_heads
from captioner.runtime import LocalRuntime

BASE = {"description": "A person with black hair wears a white shirt.",
        "character_description": "A person with black hair wears a white shirt.",
        "style_description": "A person with black hair wears a white shirt.",
        "content_tags": ["white shirt", "bangs"], "appearance_tags": ["black hair"], "style_tags": []}


def test_head_crop_uses_original_pixels_and_padding():
    image = Image.new("RGB", (2000, 1000), "white")
    crop = crop_head(image, [250, 100, 500, 400])
    assert crop.size == (620, 372)
    assert crop_head(image, [0, 0, 2, 2]) is None


@pytest.mark.parametrize("box", [[-1, 0, 300, 300], [0, 0, 1001, 300], [500, 0, 100, 300],
                                  [0, 0, 0, 1], [True, 0, 300, 300], [0, 0, float("nan"), 300]])
def test_invalid_head_boxes_are_rejected(box):
    with pytest.raises(ValueError):
        parse_heads(json.dumps({"heads": [{"person": "left person", "box": box}]}))


def test_duplicate_head_boxes_do_not_repeat_inference():
    heads = parse_heads(json.dumps({"heads": [
        {"person": "left person", "box": [100, 100, 400, 500]},
        {"person": "same head", "box": [102, 102, 401, 501]}]}))
    assert len(heads) == 1


def test_absence_and_speculation_are_not_added_as_training_attributes():
    detail = parse_hair_detail(json.dumps({"description": "The person has blunt bangs. No accessories are visible.",
        "tags": ["blunt bangs", "cheek-length side locks", "no accessories", "possibly layered"]}),
        "the person", [100, 100, 400, 500])
    assert "No accessories" not in detail["description"]
    assert detail["tags"] == ["blunt bangs", "cheek-length side locks"]
    assert "cheek-length side locks" in detail["description"]


@pytest.mark.parametrize("mode", ["natural", "tags", "mixed"])
def test_supplemental_hair_observations_survive_json_and_rendering(mode):
    detail = parse_hair_detail(json.dumps({"description": "The person has eyebrow-length blunt bangs.",
        "tags": ["eyebrow-length blunt bangs", "cheek-length side locks"]}), "the person", [100, 100, 400, 500])
    data = parse_analysis(json.dumps({**BASE, "hair_details": [detail]}))
    caption = render(data, Settings(format=mode))
    for value in ("eyebrow-length blunt bangs", "cheek-length side locks", "black hair", "white shirt"):
        assert value in caption


def test_detailed_pass_crops_locally_and_preserves_base_analysis(tmp_path, monkeypatch):
    path = tmp_path / "image.png"
    Image.new("RGB", (2000, 1000), "white").save(path)
    runtime = LocalRuntime(tmp_path / "cache")
    requests = []
    def request(image, prompt, stage):
        requests.append((stage, image.size))
        if stage == "head_location":
            return json.dumps({"heads": [{"person": "left person", "box": [250, 100, 500, 400]}]})
        return json.dumps({"description": "The left person has eyebrow-length blunt bangs.", "tags": ["eyebrow-length blunt bangs"]})
    monkeypatch.setattr(runtime, "hair_request", request)
    data = runtime.enrich_hair(path, BASE)
    assert requests == [("head_location", (2000, 1000)), ("hair_closeup", (620, 372))]
    assert data["description"] == BASE["description"]
    assert data["hair_details"][0]["person"] == "left person"
    assert "hair_details" not in BASE
    assert not list(tmp_path.glob("*.jpg"))


def test_optional_detail_failure_keeps_valid_full_image_result(tmp_path, monkeypatch):
    path = tmp_path / "image.png"
    Image.new("RGB", (100, 100), "white").save(path)
    runtime = LocalRuntime(tmp_path / "cache")
    monkeypatch.setattr(runtime, "hair_request", lambda *args: (_ for _ in ()).throw(RuntimeError("local failure")))
    data = runtime.enrich_hair(path, BASE)
    assert data["description"] == BASE["description"]
    assert data["hair_details"] == []
    assert runtime.hair_warnings


def test_cancel_does_not_start_additional_hair_requests(tmp_path, monkeypatch):
    runtime = LocalRuntime(tmp_path / "cache")
    runtime.cancel.set()
    monkeypatch.setattr(runtime, "hair_request", lambda *args: pytest.fail("Unexpected request"))
    assert runtime.enrich_hair(tmp_path / "unused.png", BASE) == BASE


@pytest.mark.parametrize("enabled", [True, False])
def test_worker_respects_detailed_hair_toggle(tmp_path, enabled):
    from captioner.worker import AnalysisWorker
    from captioner.core import fingerprint
    path = tmp_path / "image.png"
    Image.new("RGB", (100, 100), "white").save(path)
    class Runtime:
        def start(self, *args): pass
        def analyze(self, *args): return dict(BASE), json.dumps(BASE)
        def enrich_hair(self, path, data):
            self.called = True
            return {**data, "hair_details": []}
        def stop(self): self.stopped = True
    runtime = Runtime()
    events = []
    worker = AnalysisWorker(tmp_path, [(path.name, fingerprint(path))], Settings(detailed_hair=enabled), runtime)
    worker.result.connect(lambda key, event: events.append(event))
    worker.run()
    assert getattr(runtime, "called", False) is enabled
    assert runtime.stopped
    assert events[-1]["event"] == "success"
    assert events[-1]["detailed_hair"] is enabled


def test_multiple_heads_keep_tags_associated_with_their_person():
    data = {**BASE, "hair_details": [
        {"person": "left person", "description": "The left person has blunt bangs.", "tags": ["blunt bangs"]},
        {"person": "right person", "description": "The right person has a high ponytail.", "tags": ["high ponytail"]}]}
    caption = render(data, Settings(format="tags"))
    assert "left person: blunt bangs" in caption
    assert "right person: high ponytail" in caption
