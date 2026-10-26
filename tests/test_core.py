import json
from pathlib import Path

from PIL import Image
import pytest

from captioner.core import Project, Settings, parse_analysis, render


@pytest.fixture
def analysis():
    return {"description": "A blue-haired person sits on a chair in a watercolor painting.",
            "character_description": "A person sits on a chair in a watercolor painting.",
            "style_description": "A blue-haired person sits on a chair.",
            "content_tags": ["person", "sitting", "chair"], "appearance_tags": ["blue hair"],
            "style_tags": ["watercolor"]}


def image(root: Path, name="image.png"):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (30, 40), "blue").save(path)
    return path


def test_roundtrip_resume_edit_protection_and_export(tmp_path, analysis):
    image(tmp_path, "日本語/sub/image.png")
    project = Project(tmp_path)
    key = next(iter(project.records))
    record = project.records[key]
    record.analysis, record.status = analysis, "running"
    project.edit(key, "日本語の編集済みキャプション")
    project.save()
    loaded = Project(tmp_path)
    assert loaded.records[key].status == "pending"
    assert loaded.regenerate([key]) == 0
    assert loaded.records[key].caption == "日本語の編集済みキャプション"
    assert loaded.export() == (1, 0)
    txt = (tmp_path / key).with_suffix(".txt")
    assert txt.read_bytes() == "日本語の編集済みキャプション\n".encode("utf-8")
    assert loaded.regenerate([key], True) == 1
    assert loaded.export() == (0, 1)
    assert loaded.export(True) == (1, 0)
    backups = list((tmp_path / ".captioner" / "txt-backups").rglob("*.bak"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf8").strip() == "日本語の編集済みキャプション"


def test_output_modes_do_not_mix_identity_and_style(analysis):
    assert "blue-haired" not in render(analysis, Settings())
    assert "blue-haired" in render(analysis, Settings(include_identity=True))
    assert "watercolor" not in render(analysis, Settings(target="style", format="mixed"))
    assert render(analysis, Settings(format="tags", trigger="token")).startswith("token, person, sitting")
    assert "blue hair" not in render(analysis, Settings(format="tags"))


def test_changed_image_invalidates_analysis_preserves_edits(tmp_path, analysis):
    path = image(tmp_path)
    project = Project(tmp_path)
    record = project.records["image.png"]
    record.analysis, record.status, record.caption = analysis, "done", "manual"
    project.save()
    Image.new("RGB", (50, 40), "red").save(path)
    loaded = Project(tmp_path)
    assert loaded.records["image.png"].analysis is None
    assert loaded.records["image.png"].status == "pending"
    assert loaded.records["image.png"].caption == "manual"


def test_same_stem_collision_preflight_writes_nothing(tmp_path):
    image(tmp_path, "a.png")
    image(tmp_path, "a.jpg")
    project = Project(tmp_path)
    for record in project.records.values():
        record.caption = "text"
    with pytest.raises(ValueError, match="重複"):
        project.export()
    assert not (tmp_path / "a.txt").exists()


def test_malicious_project_path_rejected(tmp_path):
    folder = tmp_path / ".captioner"
    folder.mkdir()
    (folder / "project.json").write_text(json.dumps({"schema_version": 1, "settings": {},
                                                    "images": [{"path": "../outside.png"}]}), encoding="utf8")
    with pytest.raises(ValueError, match="プロジェクト外"):
        Project(tmp_path)


def test_invalid_model_json_is_not_silently_accepted(analysis):
    assert parse_analysis("```json\n" + json.dumps(analysis) + "\n```") == analysis
    del analysis["style_description"]
    with pytest.raises(ValueError):
        parse_analysis(json.dumps(analysis))


def test_missing_image_is_not_exported(tmp_path):
    path = image(tmp_path)
    project = Project(tmp_path)
    project.records["image.png"].caption = "caption"
    project.save()
    path.unlink()
    loaded = Project(tmp_path)
    assert loaded.records["image.png"].status == "missing"
    assert loaded.export() == (0, 0)


def test_export_detects_modification_since_scan(tmp_path):
    path = image(tmp_path)
    project = Project(tmp_path)
    project.records["image.png"].caption = "caption"
    Image.new("RGB", (40, 40), "red").save(path)
    with pytest.raises(ValueError, match="変更"):
        project.export()


def test_existing_sidecar_is_imported_and_protected(tmp_path):
    image(tmp_path)
    (tmp_path / "image.txt").write_text("既存キャプション", encoding="utf-8-sig")
    project = Project(tmp_path)
    assert project.records["image.png"].caption == "既存キャプション"
    assert project.records["image.png"].edited


def test_restored_missing_image_becomes_pending_again(tmp_path):
    path = image(tmp_path)
    project = Project(tmp_path)
    project.save()
    data = path.read_bytes()
    path.unlink()
    missing = Project(tmp_path)
    missing.save()
    path.write_bytes(data)
    restored = Project(tmp_path)
    assert restored.records["image.png"].status == "pending"
