import json

from PIL import Image
import pytest

from captioner.core import Project, Settings, parse_analysis, render

APPEARANCE = {
    "description": "A green-eyed person with blue hair in twin braids and blunt bangs wears a red jacket over a white shirt.",
    "character_description": "A person wearing a jacket stands.",
    "style_description": "A green-eyed person with blue hair in twin braids and blunt bangs wears a red jacket over a white shirt.",
    "content_tags": ["twin braids", "blunt bangs", "red jacket", "white shirt"],
    "appearance_tags": ["blue hair", "green eyes"], "style_tags": ["watercolor"]}


@pytest.mark.parametrize("mode", ["natural", "tags", "mixed"])
@pytest.mark.parametrize("target", ["character", "style"])
def test_all_output_modes_preserve_appearance_even_with_legacy_suppression(mode, target):
    caption = render(parse_analysis(json.dumps(APPEARANCE)),
                     Settings(format=mode, target=target, include_identity=False))
    for detail in ("blue hair", "twin braids", "blunt bangs", "red jacket", "white shirt"):
        assert detail in caption
    assert ("green eyes" in caption) if mode == "tags" else ("green-eyed" in caption)
    if target == "style":
        assert "watercolor" not in caption


def test_old_project_recovers_appearance_and_keeps_edits(tmp_path):
    Image.new("RGB", (40, 40), "white").save(tmp_path / "akari_001.png")
    project = Project(tmp_path)
    project.settings = Settings(format="tags", trigger_source="filename", include_identity=False)
    record = project.records["akari_001.png"]
    record.analysis = parse_analysis(json.dumps(APPEARANCE))
    record.status = "done"
    project.save()
    restored = Project(tmp_path)
    assert restored.settings.include_identity is True
    assert restored.regenerate(["akari_001.png"]) == 1
    assert restored.export() == (1, 0)
    text = (tmp_path / "akari_001.txt").read_text(encoding="utf8")
    for detail in ("blue hair", "green eyes", "twin braids", "red jacket", "white shirt"):
        assert detail in text
    restored.edit("akari_001.png", "hand edited caption")
    assert restored.regenerate(["akari_001.png"]) == 0
    assert restored.records["akari_001.png"].caption == "hand edited caption"
