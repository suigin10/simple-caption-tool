import json

from PIL import Image
import pytest

from captioner.core import Project, Settings, render, resolve_trigger


@pytest.mark.parametrize("name,unit,length,separators,expected", [
    ("akari_school_001.png", "words", 1, "_-", "akari"),
    ("folder/akari_school_001.png", "words", 2, "_-", "akari_school"),
    ("folder/mio-casual-001.jpg", "words", 2, "_-", "mio-casual"),
    ("akari school 001.webp", "words", 2, "_-", "akari school"),
    ("my-character_pose_01.png", "words", 1, "_", "my-character"),
    ("akari_school_001.png", "characters", 5, "_-", "akari"),
    ("さくら_制服_001.png", "characters", 3, "_-", "さくら"),
    ("akari.png", "words", 10, "_-", "akari"),
    ("akari.png", "characters", 99, "_-", "akari"),
    ("akari[school]01.png", "words", 2, "[]", "akari[school"),
])
def test_prefix_length_extracts_from_basename(name, unit, length, separators, expected):
    settings = Settings(trigger_source="filename", trigger_unit=unit,
                        trigger_length=length, trigger_separators=separators)
    assert resolve_trigger(settings, name) == expected


def test_manual_trigger_ignores_filename_options():
    assert resolve_trigger(Settings(trigger="shared", trigger_length=20), "akari.png") == "shared"


def test_empty_word_prefix_is_rejected():
    with pytest.raises(ValueError, match="抽出"):
        resolve_trigger(Settings(trigger_source="filename"), "---.png")


def test_old_project_settings_use_manual_trigger_by_default(tmp_path):
    folder = tmp_path / ".captioner"
    folder.mkdir()
    (folder / "project.json").write_text(json.dumps({"schema_version": 1,
        "settings": {"trigger": "legacy"}, "images": []}), encoding="utf8")
    project = Project(tmp_path)
    assert project.settings.trigger_source == "manual"
    assert project.settings.trigger == "legacy"


def test_multicharacter_regenerate_export_and_reload(tmp_path):
    analysis = {"description": "A person stands.", "character_description": "A person stands.",
                "style_description": "A person stands.", "content_tags": ["standing"],
                "appearance_tags": [], "style_tags": []}
    names = ("akari_school_001.png", "mio_casual_002.png")
    for name in names:
        Image.new("RGB", (20, 20), "white").save(tmp_path / name)
    project = Project(tmp_path)
    for record in project.records.values():
        record.analysis = analysis
        record.status = "done"
    project.settings.trigger_source = "filename"
    project.settings.trigger_length = 1
    for mode in ("natural", "tags", "mixed"):
        project.settings.format = mode
        assert project.regenerate(list(names)) == 2
        assert project.records[names[0]].caption.startswith("akari, ")
        assert project.records[names[1]].caption.startswith("mio, ")
    project.edit(names[0], "manual caption")
    project.settings.trigger_length = 2
    assert project.regenerate(list(names)) == 1
    assert project.records[names[0]].caption == "manual caption"
    assert project.records[names[1]].caption.startswith("mio_casual, ")
    assert project.export() == (2, 0)
    assert (tmp_path / "mio_casual_002.txt").read_text(encoding="utf8").startswith("mio_casual, ")
    restored = Project(tmp_path)
    assert restored.settings.trigger_length == 2
    assert restored.settings.trigger_source == "filename"


def test_invalid_filename_does_not_partially_regenerate(tmp_path):
    for name in ("akari_001.png", "---.png"):
        Image.new("RGB", (20, 20), "white").save(tmp_path / name)
    project = Project(tmp_path)
    analysis = {"description": "Person.", "character_description": "Person.",
                "style_description": "Person.", "content_tags": [], "appearance_tags": [], "style_tags": []}
    for record in project.records.values():
        record.analysis, record.caption = analysis, "original"
    project.settings.trigger_source = "filename"
    with pytest.raises(ValueError):
        project.regenerate(["akari_001.png", "---.png"])
    assert all(r.caption == "original" for r in project.records.values())
